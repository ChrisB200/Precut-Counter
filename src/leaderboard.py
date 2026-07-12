import asyncio
import logging

import discord

from .embeds import leaderboard_embed

logger = logging.getLogger(__name__)


def mark_leaderboards_dirty():
    global leaderboard_dirty
    leaderboard_dirty = True
