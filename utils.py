import asyncio
import logging
import subprocess
from datetime import datetime
from typing import cast

import discord
from tqdm import tqdm

from config import DROP_PRECUT_CHANNEL, client, conn
from database import (
    add_precut,
    get_demon_leaderboard,
    get_demon_owner_id,
    get_demon_owner_ids,
    get_global_leaderboard,
    get_latest_message_id,
    get_leaderboard_messages,
    is_first_time_run,
)
from embeds import leaderboard_embed

leaderboard_dirty = False

logger = logging.getLogger(__name__)


def mark_leaderboards_dirty():
    global leaderboard_dirty
    leaderboard_dirty = True


async def leaderboard_updater():
    global leaderboard_dirty

    while True:
        if leaderboard_dirty:
            leaderboard_dirty = False
            await update_leaderboards()

        await asyncio.sleep(5)


async def get_duration(attachment_url):
    result = await asyncio.to_thread(
        subprocess.run,
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            attachment_url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    return float(result.stdout.strip())


def get_message(message, owner_id: int):
    attachments = list(message.attachments)

    if message.message_snapshots:
        snapshot = message.message_snapshots[0]
        attachments = list(snapshot.attachments)

    donations = []
    for attachment in attachments:
        if not attachment.content_type:
            continue

        if not attachment.content_type.startswith("video/"):
            continue

        is_video = (
            attachment.content_type is not None
            and attachment.content_type.startswith("video/")
        ) or attachment.filename.lower().endswith((".mp4", ".mov", ".webm", ".mkv"))

        if not is_video:
            continue

        if isinstance(message.channel, discord.Thread):
            channel_id = message.channel.parent_id
        else:
            channel_id = message.channel.id

        temp = {
            "author_id": owner_id,
            "attachment_id": attachment.id,
            "attachment_url": attachment.url,
            "message_id": message.id,
            "duration": None,
            "created_at": message.created_at.isoformat(),
            "channel_id": channel_id,
        }

        donations.append(temp)

    return donations


async def sync_forum(forum: discord.ForumChannel):
    for thread in forum.threads:
        await sync_text_channel(thread.id)


async def sync_text_channel(channel_id: int, first=False):
    channel = client.get_channel(channel_id)
    if channel is None:
        return

    if first:
        latest_message_id = None
    else:
        latest_message_id = get_latest_message_id(channel_id)

    donations = []

    if latest_message_id is None:
        print("First sync...")

        history = channel.history(limit=None)
    else:
        print(f"Syncing after message {latest_message_id}")

        history = channel.history(
            limit=None,
            after=discord.Object(id=latest_message_id),
            oldest_first=True,
        )

    registered_demons = get_demon_owner_ids()
    channel_owner_id = get_demon_owner_id(channel.id)

    async for message in history:
        if channel.id == DROP_PRECUT_CHANNEL:
            # Ignore uploads from registered demons in the drop channel.
            if message.author.id in registered_demons:
                continue

            owner_id = message.author.id

        elif channel_owner_id is not None:
            # Everything in a registered demon's channel belongs to them.
            owner_id = channel_owner_id

        else:
            continue

        donations.extend(get_message(message, owner_id))

    total = len(donations)

    if total == 0:
        print("No new precuts to index.")
        return

    print(f"Found {total} new precuts.")
    print("Calculating durations...")

    progress = tqdm(
        total=total,
        desc="Indexing",
        unit="video",
        dynamic_ncols=True,
    )

    semaphore = asyncio.Semaphore(8)

    async def process_donation(donation):
        async with semaphore:
            donation["duration"] = await get_duration(donation["attachment_url"])

            add_precut(donation)

            progress.update(1)

    tasks = [asyncio.create_task(process_donation(donation)) for donation in donations]

    await asyncio.gather(*tasks)

    progress.close()

    conn.commit()

    print("Finished indexing.")


async def sync_precuts(channel_id: int, first=False):
    channel = client.get_channel(channel_id)

    if isinstance(channel, discord.TextChannel):
        await sync_text_channel(channel.id, first)

    elif isinstance(channel, discord.ForumChannel):
        await sync_forum(channel)

    mark_leaderboards_dirty()


async def first_time_run():
    channel = client.get_channel(DROP_PRECUT_CHANNEL)
    if channel is None:
        raise ValueError("DROP_PRECUT_CHANNEL not found")

    is_first_time = is_first_time_run()
    if not is_first_time:
        return

    print("Scanning channel history...")

    donations = []

    async for message in channel.history(limit=None):
        donations.extend(get_message(message))

    total = len(donations)

    print(f"Found {total} videos.")
    print("Calculating durations...")

    semaphore = asyncio.Semaphore(8)

    progress = tqdm(
        total=total,
        desc="Indexing",
        unit="video",
        dynamic_ncols=True,
    )

    async def process_donation(donation):
        async with semaphore:
            donation["duration"] = await get_duration(donation["attachment_url"])

            add_precut(donation)

            progress.update(1)

    tasks = [asyncio.create_task(process_donation(donation)) for donation in donations]

    await asyncio.gather(*tasks)

    progress.close()

    conn.commit()

    print("Finished indexing.")


async def update_leaderboards():
    for message_id, channel_id, board_type in get_leaderboard_messages():
        channel = client.get_channel(channel_id)

        if channel is None:
            continue

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            continue

        if board_type == "global":
            rows = get_global_leaderboard()
        else:
            rows = get_demon_leaderboard()

        embed = await leaderboard_embed(client, rows)

        await message.edit(embed=embed[0])


async def first_channel_message(channel: discord.TextChannel) -> discord.Message | None:
    first_message = None

    async for message in channel.history(limit=1, oldest_first=True):
        first_message = message
        break

    return first_message


def get_forum_owner(channel: discord.ForumChannel) -> int | None:
    if not channel.threads:
        logger.warning("There are no threads in forum %s", channel.name)
        return None

    # assume that the earliest thread is created by the forum owner
    first_thread = min(
        channel.threads,
        key=lambda t: cast(datetime, t.created_at),
    )
    owner_id = first_thread.owner_id
    logger.debug("Found owner id: %s in forum channel %s", owner_id, channel.name)

    return owner_id
