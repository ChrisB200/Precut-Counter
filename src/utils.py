import asyncio
import logging
import subprocess
from collections import defaultdict
from datetime import datetime
from typing import NoReturn, cast

import discord
from discord import ForumChannel, TextChannel, Thread
from discord.client import Client
from tqdm import tqdm

from src.database import add_precut, get_channels_by_role
from src.models import Channel, ChannelRole, ChannelType, Demon, PartialPrecut, Precut

leaderboard_dirty = False

logger = logging.getLogger(__name__)


def group_demons_by_user(
    demons: list[Demon],
    channels: dict[int, Channel],
) -> dict[int, list[Channel]]:
    demons_by_user: defaultdict[int, list[Channel]] = defaultdict(list)

    for demon in demons:
        channel = channels[demon.channel_id]
        demons_by_user[demon.user_id].append(channel)

    return demons_by_user


def get_forum(client: Client, channels: list[Channel]) -> ForumChannel | None:
    for channel in channels:
        if channel.type is ChannelType.FORUM:
            forum = client.get_channel(channel.id)
            if isinstance(forum, ForumChannel):
                logger.debug("Found discord forum %d", forum.id)
                return forum

    logger.warning("Forum channel exists in database but could not be found in Discord")
    return None


def get_text_channel(client: Client, channels: list[Channel]) -> TextChannel | None:
    for channel in channels:
        if channel.type is ChannelType.TEXT:
            text_channel = client.get_channel(channel.id)
            if isinstance(text_channel, TextChannel):
                logger.debug("Found discord text channel%d", text_channel.id)
                return text_channel

    logger.warning("Text channel exists in database but could not be found in Discord")
    return None


def get_discord_demon(client: Client, id: int) -> discord.User | None:
    demon = client.get_user(id)
    if demon:
        logger.debug("Found discord demon %s (%d)", demon.name, demon.id)
        return demon

    logger.warning("Could not find demon with id %d in db", id)
    return None


async def get_forum_threads(forum: ForumChannel) -> list[Thread]:
    threads = list(forum.threads)

    # threads become inactive meaning that we can miss precuts by accident
    async for thread in forum.archived_threads():
        threads.append(thread)

    return threads


def get_precuts_from_message(
    message: discord.Message, user_id: int
) -> list[PartialPrecut]:
    attachments = list(message.attachments)

    # some precuts are forwarded messages
    if message.message_snapshots:
        snapshot = message.message_snapshots[0]
        attachments = list(snapshot.attachments)

    precuts: list[PartialPrecut] = []
    for attachment in attachments:
        # elegible precuts
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

        channel_id = message.channel.id
        precut = PartialPrecut(
            id=attachment.id,
            message_id=message.id,
            user_id=user_id,
            channel_id=channel_id,
            attachment_url=attachment.url,
            created_at=message.created_at.isoformat(),
        )

        precuts.append(precut)

    logger.debug("Found %d precuts attached to message %d", len(precuts), message.id)
    return precuts


async def process_partial_precut(partial_precut: PartialPrecut) -> Precut:
    duration = await calculate_duration(partial_precut.attachment_url)
    precut = Precut(
        id=partial_precut.id,
        message_id=partial_precut.message_id,
        user_id=partial_precut.user_id,
        channel_id=partial_precut.channel_id,
        duration=duration,
        created_at=partial_precut.created_at,
    )
    add_precut(precut)
    return precut


async def process_precut(
    partial_precut: PartialPrecut,
    progress: tqdm,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        await process_partial_precut(partial_precut)
        progress.update(1)


async def calculate_duration(attachment_url: str) -> float:
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


def get_drop_channel(client: Client) -> TextChannel | None:
    channels = get_channels_by_role(ChannelRole.DROP)
    if len(channels) > 0:
        channel = client.get_channel(channels[0].id)
        if isinstance(channel, TextChannel):
            return channel

    logger.warning("No DROP PRECUTS HERE channel defined in the database")
    return None


def is_message_in_channels(message: discord.Message):
    channels = get_channels_by_role(ChannelRole.DEMON)
    channels.extend(get_channels_by_role(ChannelRole.DROP))
    channels = [c.id for c in channels]

    if message.channel.id in channels:
        return True

    return False


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


def get_time(duration: float):
    hours = int(duration // 3600)
    minutes = int((duration % 3600) // 60)
    seconds = int(duration % 60)
    return hours, minutes, seconds
