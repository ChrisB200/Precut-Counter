import logging

import discord
from discord import app_commands
from dotenv import load_dotenv

from config import ACCESS_TOKEN, DROP_PRECUT_CHANNEL, client
from database import (
    add_channel,
    add_leaderboard,
    add_precut,
    conn,
    delete_channel,
    delete_drop_precuts,
    delete_leaderboard,
    delete_owner_channels,
    delete_precut,
    get_channels,
    get_demon_leaderboard,
    get_global_leaderboard,
    get_leaderboard_message,
    get_stats,
)
from embeds import leaderboard_embed, stats_embed
from utils import (
    first_channel_message,
    get_duration,
    get_forum_owner,
    get_message,
    leaderboard_updater,
    mark_leaderboards_dirty,
    sync_precuts,
)

load_dotenv()

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


@client.event
async def on_message(message):
    if message.author.bot:
        return

    # Only index videos in the precut channel
    if message.channel.id == DROP_PRECUT_CHANNEL:
        print("donation")
        donations = get_message(message, message.author.id)

        for donation in donations:
            donation["duration"] = await get_duration(donation["attachment_url"])
            add_precut(donation)

        conn.commit()

        mark_leaderboards_dirty()

    # Always process commands, regardless of channel
    await client.process_commands(message)


@client.event
async def on_message_delete(message):
    delete_precut(message.id)
    mark_leaderboards_dirty()
    logger.info("Deleted attachments with message_id %s", message.id)


@client.event
async def on_ready():
    logger.info("Logged in as %s", client.user)
    client.loop.create_task(leaderboard_updater())

    demons = get_channels()
    for channel_id, owner_id in demons:
        logger.info("Syncing precuts for channel %s owned by %s", channel_id, owner_id)
        await sync_precuts(channel_id)

    await sync_precuts(DROP_PRECUT_CHANNEL)
    mark_leaderboards_dirty()
    await client.tree.sync()


demon = app_commands.Group(
    name="demon",
    description="Demon commands",
)

precut = app_commands.Group(
    name="precut",
    description="Precut commands",
)


@app_commands.choices(
    type=[
        app_commands.Choice(name="Global", value="global"),
        app_commands.Choice(name="Demons", value="demons"),
    ]
)
@client.tree.command(
    name="leaderboard",
    description="Create a live leaderboard.",
)
async def leaderboard(
    interaction: discord.Interaction,
    type: app_commands.Choice[str],
):
    if type.value == "global":
        rows = get_global_leaderboard()
    else:
        rows = get_demon_leaderboard()

    embed = (await leaderboard_embed(client, rows))[0]

    await interaction.response.send_message(embed=embed)

    message = await interaction.original_response()

    add_leaderboard(
        message.id,
        message.channel.id,
        type.value,
    )


@client.tree.command(
    name="remove-leaderboard",
    description="Remove a leaderboard by its message ID",
)
async def remove_leaderboard(
    interaction: discord.Interaction,
    message_id: str,
):
    row = get_leaderboard_message(int(message_id))
    if row is None:
        await interaction.response.send_message(
            "That message isn't a registered leaderboard.",
            ephemeral=True,
        )
        return

    _, channel_id, _ = row

    channel = client.get_channel(channel_id)
    if channel is None:
        channel = await client.fetch_channel(channel_id)

    try:
        message = await channel.fetch_message(int(message_id))
        await message.delete()
    except discord.NotFound:
        pass

    delete_leaderboard(int(message_id))

    await interaction.response.send_message(
        "Leaderboard removed.",
        ephemeral=True,
    )


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

        owner_id = first_message.author.id
        add_channel(channel.id, owner_id)

    elif isinstance(channel, discord.ForumChannel):
        logger.info("Attempting to register channel (forum) demon %s", channel.name)
        owner_id = get_forum_owner(channel)

        if not owner_id:
            logger.warning(
                "Cannot register forum channel %s: no threads found",
                channel.name,
            )
            await interaction.response.send_message(
                "This channel has no threads to determine the owner.",
                ephemeral=True,
            )
            return

        # register all channels within the forum
        for thread in channel.threads:
            add_channel(thread.id, owner_id)

    # allows us to recount precuts from their channel and not DROP PRECUTS
    delete_drop_precuts(owner_id)

    await interaction.response.send_message(
        f"Registered {channel.mention} (ID: {channel.name})", ephemeral=True
    )
    logger.info("Registered channel %s for owner %s", channel.id, owner_id)

    await sync_precuts(channel.id)


@demon.command(name="unregister", description="Unregister a precut demon's channel")
async def unregister_demon(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.ForumChannel,
):
    if isinstance(channel, discord.TextChannel):
        delete_channel(channel.id)
        await interaction.response.send_message(
            f"Unregistered {channel.mention} (ID: {channel.id})", ephemeral=True
        )
    elif isinstance(channel, discord.ForumChannel):
        owner_id = get_forum_owner(channel)
        if not owner_id:
            await interaction.response.send_message(
                f"Could not find owner for forum channel {channel.mention}",
                ephemeral=True,
            )
            return

        delete_owner_channels(owner_id)
        await interaction.response.send_message(
            f"Unregistered {channel.mention} (ID: {channel.id})", ephemeral=True
        )

    # ensures that if a demon is unregistered
    # then their precuts are recounted from DROP PRECUTS
    await sync_precuts(DROP_PRECUT_CHANNEL, True)

    logger.info("Unregistered channel %s", channel.name)


@precut.command(name="stats", description="Check precut stats")
async def stats(
    interaction: discord.Interaction,
    user: discord.Member | None = None,
):
    if not user:
        user = user or interaction.user

    stats = get_stats(user.id)
    embed = await stats_embed(interaction.client, stats, user)

    await interaction.response.send_message(embed=embed)


client.tree.add_command(demon)
client.tree.add_command(precut)
client.run(ACCESS_TOKEN)
