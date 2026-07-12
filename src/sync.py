import asyncio
import logging

import discord
from discord import Client, ForumChannel, TextChannel, Thread
from tqdm import tqdm

from src.database import (
    add_channel,
    delete_channel,
    get_channel_by_id,
    get_channels,
    get_channels_by_type,
    get_demons,
    get_last_message_id,
)
from src.models import Channel, ChannelRole, ChannelType, PartialPrecut
from src.utils import (
    get_discord_demon,
    get_forum,
    get_forum_threads,
    get_precuts_from_message,
    get_text_channel,
    group_demons_by_user,
    process_precut,
)

logger = logging.getLogger(__name__)


async def sync_demons(client: Client, fresh=False):
    demons = get_demons()
    all_channels = {c.id: c for c in get_channels()}
    demon_channels = group_demons_by_user(demons, all_channels)

    for demon_id, channels in demon_channels.items():
        forum = get_forum(client, channels)
        text_channel = get_text_channel(client, channels)
        demon = get_discord_demon(client, demon_id)

        if not demon:
            logger.warning("Could not find demon %d", demon_id)
            continue

        if forum:
            logger.info(
                "Syncing forum %s for demon %s (%d)", forum.name, demon.name, demon.id
            )
            await sync_forum(forum, fresh)

        if text_channel:
            logger.info(
                "Syncing text channel %s for demon %s (%d)",
                text_channel.name,
                demon.name,
                demon.id,
            )
            await sync_precuts(text_channel, fresh)


async def sync_forum(forum: ForumChannel, fresh=False):
    await delete_missing_threads(forum)

    for thread in await get_forum_threads(forum):
        logger.debug(
            "forum=%d thread=%d name=%s type=%s",
            forum.id,
            thread.id,
            thread.name,
            type(thread).__name__,
        )

    threads = await get_forum_threads(forum)
    for thread in threads:
        channel = Channel(thread.id, ChannelType.THREAD, ChannelRole.DEMON)
        add_channel(channel)
        await sync_precuts(thread, fresh)


async def delete_missing_threads(forum: ForumChannel):
    forum_threads = {t.id for t in await get_forum_threads(forum)}
    db_threads = {t.id for t in get_channels_by_type(ChannelType.THREAD)}

    logger.debug("Checking for deleted threads in forum %s (%d)", forum.name, forum.id)

    deleted = 0
    for id in db_threads:
        if id not in forum_threads:
            has_deleted = delete_channel(id)
            logger.info("Removing deleted thread %s form db", id)
            deleted += 1 if has_deleted else 0

    logger.debug("Removed %d deleted thread(s)", deleted)


async def sync_precuts(channel: Thread | TextChannel, fresh=False):
    if fresh:
        logger.info("Syncing channel %s from the start", channel.name)
        history = channel.history(limit=None)
    else:
        last_message_id = get_last_message_id(channel.id)
        if not last_message_id:
            history = channel.history(limit=None)
            logger.info("Syncing channel %s from the start", channel.name)
        else:
            history = channel.history(
                limit=None, after=discord.Object(id=last_message_id), oldest_first=True
            )
            logger.info(
                "Syncing channel %s after message %d", channel.name, last_message_id
            )

    demon_user_ids = [demon.user_id for demon in get_demons()]
    channel_db = get_channel_by_id(channel.id)
    if not channel_db:
        logger.error("Could not complete sync precuts for channel %d", channel.id)
        return

    precuts: list[PartialPrecut] = []
    async for message in history:
        if channel_db.role == ChannelRole.DROP:
            if message.author.id not in demon_user_ids:
                precuts.extend(get_precuts_from_message(message, message.author.id))
        else:
            precuts.extend(get_precuts_from_message(message, message.author.id))

    total = len(precuts)
    if total == 0:
        logger.info(
            "No new precuts to sync for channel %s (%d)", channel.name, channel.id
        )
        return

    logger.info("Found %d precuts for channel %s (%d)", total, channel.name, channel.id)

    semaphore = asyncio.Semaphore(8)
    progress = tqdm(
        total=len(precuts),
        desc="Indexing",
        unit="video",
        dynamic_ncols=True,
    )
    tasks = [
        asyncio.create_task(process_precut(p, progress, semaphore)) for p in precuts
    ]
    await asyncio.gather(*tasks)
    progress.close()

    logger.info(
        "Synced %d precuts for channel %s (%d)", total, channel.name, channel.id
    )
