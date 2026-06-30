import os
import sqlite3

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

prefix = ":"
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
