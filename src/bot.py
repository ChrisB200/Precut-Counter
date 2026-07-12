import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.database import (
    add_channel,
    add_demon,
    delete_precuts_by_message_id,
    delete_precuts_by_user_id,
    get_channels_by_role,
    get_last_donation,
    get_stats,
)
from src.leaderboard import mark_leaderboards_dirty
from src.models import Channel, ChannelRole, ChannelType, Demon
from src.sync import sync_demons, sync_forum, sync_precuts
from src.utils import (
    first_channel_message,
    get_drop_channel,
    get_forum_owner,
    get_precuts_from_message,
    is_message_in_channels,
    process_partial_precut,
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

prefix = ":"
intents = discord.Intents.default()
intents.message_content = True

client = commands.Bot(command_prefix=prefix, intents=intents)

demon = app_commands.Group(
    name="demon",
    description="Demon commands",
)

precut = app_commands.Group(
    name="precut",
    description="Precut commands",
)


@client.event
async def on_ready():
    logger.info("Logged in as %s", client.user)
    # client.loop.create_task(leaderboard_updater())

    await sync_demons(client)

    drop_precuts_here = get_drop_channel(client)
    if drop_precuts_here:
        await sync_precuts(drop_precuts_here)

    mark_leaderboards_dirty()
    await client.tree.sync()


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if is_message_in_channels(message):
        precuts = get_precuts_from_message(message, message.author.id)
        for precut in precuts:
            await process_partial_precut(precut)
            mark_leaderboards_dirty()

    # Always process commands, regardless of channel
    await client.process_commands(message)


@client.event
async def on_message_delete(message: discord.Message):
    if is_message_in_channels(message):
        delete_precuts_by_message_id(message.id)
        mark_leaderboards_dirty()
        logger.info("Deleted precuts with message_id %s", message.id)


@client.event
async def on_thread_create(thread: discord.Thread):
    parent = thread.parent

    if not isinstance(parent, discord.ForumChannel):
        return

    user_id = get_forum_owner(parent)
    if user_id is None:
        return

    c = Channel(
        id=thread.id,
        type=ChannelType.THREAD,
        role=ChannelRole.DEMON,
    )
    d = Demon(c.id, user_id)

    add_channel(c)
    add_demon(d)

    logger.info(
        "Registered new thread %s (%d) for demon %d",
        thread.name,
        thread.id,
        user_id,
    )


@precut.command(
    name="donations", description="Choose what channel precuts are donated in"
)
async def register_donations(
    interaction: discord.Interaction, channel: discord.TextChannel
):
    drop_precuts = get_channels_by_role(ChannelRole.DROP)
    if drop_precuts:
        logger.warning("Can't register multiple drop precut channels")
        await interaction.response.send_message(
            "Can't register multiple drop precut channels", ephemeral=True
        )
        return

    drop_precuts = Channel(channel.id, ChannelType.TEXT, ChannelRole.DROP)
    add_channel(drop_precuts)

    logger.info("Registered channel %s (%d) for drop precuts", channel.name, channel.id)
    await interaction.response.send_message(
        f"Registered channel {channel.name} ({channel.id}) for drop precuts",
        ephemeral=True,
    )
    await sync_precuts(channel)


@demon.command(name="register", description="Register a precut demon's channel")
async def register_demon(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.ForumChannel,
):
    if isinstance(channel, discord.TextChannel):
        logger.info("Attempting to register channel (text) demon %s", channel.name)
        first_message = await first_channel_message(channel)
        if not first_message:
            logger.warning(
                "Cannot register text channel %s: no messages found",
                channel.name,
            )
            await interaction.response.send_message(
                "This channel has no messages to determine the owner.",
                ephemeral=True,
            )
            return

        user_id = first_message.author.id
        c = Channel(channel.id, ChannelType.TEXT, ChannelRole.DEMON)
        d = Demon(c.id, user_id)
        add_channel(c)
        add_demon(d)

        await interaction.response.send_message(
            f"Registered {channel.mention} (ID: {channel.name})", ephemeral=True
        )
        logger.info("Registered channel %s for owner %s", channel.id, user_id)

        # allows us to recount precuts from their channel and not DROP PRECUTS
        delete_precuts_by_user_id(user_id)
        await sync_precuts(channel)

    elif isinstance(channel, discord.ForumChannel):
        logger.info("Attempting to register channel (forum) demon %s", channel.name)
        user_id = get_forum_owner(channel)

        if not user_id:
            logger.warning(
                "Cannot register forum channel %s: no threads found",
                channel.name,
            )
            await interaction.response.send_message(
                "This channel has no threads to determine the owner.",
                ephemeral=True,
            )
            return

        c = Channel(channel.id, ChannelType.FORUM, ChannelRole.DEMON)
        d = Demon(c.id, user_id)
        add_channel(c)
        add_demon(d)
        # register all channels within the forum
        for thread in channel.threads:
            t = Channel(thread.id, ChannelType.THREAD, ChannelRole.DEMON)
            add_channel(t)

        await interaction.response.send_message(
            f"Registered {channel.mention} (ID: {channel.name})", ephemeral=True
        )

        logger.info("Registered channel %s for owner %s", channel.id, user_id)

        # allows us to recount precuts from their channel and not DROP PRECUTS
        delete_precuts_by_user_id(user_id)
        await sync_forum(channel)


@precut.command(name="stats", description="Check precut stats")
async def stats(
    interaction: discord.Interaction,
    user: discord.Member | None = None,
):
    if not user:
        user = user or interaction.user

    stats = get_stats(user.id)
    last_donation = get_last_donation(user.id)

    message = None
    if last_donation:
        channel = client.get_channel(last_donation[1])
        message = await channel.fetch_message(last_donation[0])

    embed = await stats_embed(stats, message, user)

    await interaction.response.send_message(embed=embed)


client.tree.add_command(demon)
client.tree.add_command(precut)
