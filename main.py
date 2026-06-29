import asyncio
import logging
import os
import sqlite3
import subprocess

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

logger = logging.getLogger(__name__)

prefix = "."
intents = discord.Intents.default()
intents.message_content = True

client = commands.Bot(command_prefix=prefix, intents=intents)

conn = sqlite3.connect("precut_counter.db")
cursor = conn.cursor()
conn.executescript(open("precut_counter.sql").read())


ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
if ACCESS_TOKEN is None:
    raise ValueError("ACCESS_TOKEN env var not provided")

drop_precut_channel = os.getenv("DROP_PRECUT_CHANNEL")
if drop_precut_channel is None:
    raise ValueError("DROP_PRECUT_CHANNEL env var not provided")

DROP_PRECUT_CHANNEL = int(drop_precut_channel)


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


def add_attachment(attachment):
    cursor.execute(
        """
        INSERT OR IGNORE INTO attachments (
            attachment_id,
            message_id,
            author_id,
            duration
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            attachment["attachment_id"],
            attachment["message_id"],
            attachment["author_id"],
            attachment["duration"],
        ),
    )


def get_message(message):
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

        temp = {
            "author_id": message.author.id,
            "attachment_id": attachment.id,
            "attachment_url": attachment.url,
            "message_id": message.id,
            "duration": None,
        }

        donations.append(temp)

    return donations


def is_first_time_run():
    cursor.execute("SELECT COUNT(*) FROM attachments")
    count = cursor.fetchone()[0]
    return count == 0


async def first_time_run():
    channel = client.get_channel(DROP_PRECUT_CHANNEL)
    if channel is None:
        raise ValueError("DROP_PRECUT_CHANNEL not found")

    if not is_first_time_run():
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

            add_attachment(donation)

            progress.update(1)

    tasks = [asyncio.create_task(process_donation(donation)) for donation in donations]

    await asyncio.gather(*tasks)

    progress.close()

    conn.commit()

    print("Finished indexing.")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    # Only index videos in the precut channel
    if message.channel.id == DROP_PRECUT_CHANNEL:
        donations = get_message(message)

        for donation in donations:
            donation["duration"] = await get_duration(donation["attachment_url"])
            add_attachment(donation)

        conn.commit()

    # Always process commands, regardless of channel
    await client.process_commands(message)


@client.event
async def on_message_delete(message):
    print("message delete")
    cursor.execute(
        "DELETE FROM attachments WHERE message_id = ?",
        (message.id,),
    )
    conn.commit()


@client.event
async def on_ready():

    await client.tree.sync()
    print(f"Logged in as {client.user}")

    await first_time_run()


@client.command()
async def leaderboard(ctx):
    cursor.execute("SELECT COUNT(*) FROM attachments")
    print(cursor.fetchone())
    cursor.execute(
        """
        SELECT
            author_id,
            COUNT(*) AS precut_count,
            SUM(duration) AS total_duration
        FROM attachments
        GROUP BY author_id
        ORDER BY total_duration DESC
        LIMIT 10;
        """
    )

    rows = cursor.fetchall()

    embed = discord.Embed(
        title="🏆 Precut Leaderboard",
        colour=discord.Colour.gold(),
    )

    if not rows:
        embed.description = "No precuts have been indexed yet."
        await ctx.response.send_message(embed=embed)
        return

    for i, (author_id, count, duration) in enumerate(rows, start=1):
        user = client.get_user(author_id)

        if user is None:
            try:
                user = await client.fetch_user(author_id)
            except discord.NotFound:
                username = f"Unknown User ({author_id})"
            else:
                username = user.display_name
        else:
            username = user.display_name

        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        seconds = int(duration % 60)

        embed.add_field(
            name=f"{i}. {username}",
            value=(f"📹 **{count}** precuts\n" f"⏱️ **{hours}h {minutes}m {seconds}s**"),
            inline=False,
        )

    await ctx.send(embed=embed)


client.run(ACCESS_TOKEN)
