import logging

import discord
from discord import app_commands
from dotenv import load_dotenv

from config import ACCESS_TOKEN, DROP_PRECUT_CHANNEL, client, cursor
from database import (
    add_channel,
    add_leaderboard,
    add_precut,
    conn,
    delete_channel,
    delete_drop_precuts,
    delete_precut,
    get_channels,
    get_demon_leaderboard,
    get_global_leaderboard,
)
from embeds import leaderboard_embed
from utils import (
    get_duration,
    get_message,
    schedule_leaderboard_update,
    sync_precuts,
    update_leaderboards,
)

load_dotenv()

logger = logging.getLogger(__name__)


@client.event
async def on_message(message):
    if message.author.bot:
        return

    # Only index videos in the precut channel
    if message.channel.id == DROP_PRECUT_CHANNEL:
        donations = get_message(message)

        for donation in donations:
            donation["duration"] = await get_duration(donation["attachment_url"])
            add_precut(donation)

        conn.commit()

        await schedule_leaderboard_update()

    # Always process commands, regardless of channel
    await client.process_commands(message)


@client.event
async def on_message_delete(message):
    logger.debug("Attempting to delete message %s", message.id)
    delete_precut(message.id)
    await schedule_leaderboard_update()
    logger.info("Deleted attachments with message_id %s", message.id)


@client.event
async def on_ready():

    print(f"Logged in as {client.user}")

    demons = get_channels()
    for channel, owner_id in demons:
        print(f"Syncing {channel}")
        await sync_precuts(channel)
    await sync_precuts(DROP_PRECUT_CHANNEL)
    await schedule_leaderboard_update()
    synced = await client.tree.sync()


demon = app_commands.Group(
    name="demon",
    description="Demon commands",
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


@demon.command(name="register", description="Register a precut demon's channel")
async def register_demon(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.ForumChannel,
):
    if isinstance(channel, discord.TextChannel):
        first_message = await anext(
            channel.history(limit=1, oldest_first=True),
            None,
        )

        if first_message is None:
            return

        owner_id = first_message.author.id

    elif isinstance(channel, discord.ForumChannel):
        if not channel.threads:
            return

        first_thread = min(
            channel.threads,
            key=lambda t: t.created_at,
        )
        owner_id = first_thread.owner_id

    add_channel(channel.id, owner_id)
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM precuts
        WHERE author_id = ?
        AND channel_id = ?
        """,
        (owner_id, DROP_PRECUT_CHANNEL),
    )

    print(cursor.fetchone())
    delete_drop_precuts(owner_id)

    cursor.execute(
        """

        SELECT COUNT(*)

        FROM precuts

        WHERE author_id = ?

        AND channel_id = ?

        """,
        (owner_id, DROP_PRECUT_CHANNEL),
    )

    print("After:", cursor.fetchone())
    await interaction.response.send_message(
        f"Registered {channel.mention} (ID: {channel.id})"
    )
    await sync_precuts(channel.id)

    logger.info("Registered channel %s", channel.name)


@demon.command(name="unregister", description="Unregister a precut demon's channel")
async def unregister_demon(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.ForumChannel,
):
    delete_channel(channel.id)

    await interaction.response.send_message(
        f"Unregistered {channel.mention} (ID: {channel.id})"
    )

    logger.info("Unregistered channel %s", channel.name)


client.tree.add_command(demon)
client.run(ACCESS_TOKEN)
