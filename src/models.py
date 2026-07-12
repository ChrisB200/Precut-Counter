import sqlite3
from dataclasses import dataclass
from enum import StrEnum


class ChannelType(StrEnum):
    TEXT = "text"
    FORUM = "forum"
    THREAD = "thread"


class ChannelRole(StrEnum):
    DROP = "drop"
    DEMON = "demon"
    LEADERBOARD = "leaderboard"


class LeaderboardType(StrEnum):
    GLOBAL = "global"
    DEMON = "demon"


@dataclass(slots=True)
class Channel:
    id: int
    type: ChannelType
    role: ChannelRole

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Channel":
        return cls(
            id=row["id"], type=ChannelType(row["type"]), role=ChannelRole(row["role"])
        )


@dataclass(slots=True)
class Demon:
    channel_id: int
    user_id: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Demon":
        return cls(channel_id=row["channel_id"], user_id=row["user_id"])


@dataclass(slots=True)
class Precut:
    id: int
    message_id: int
    user_id: int
    channel_id: int
    duration: float | None
    created_at: str


@dataclass(slots=True)
class PartialPrecut:
    id: int
    message_id: int
    user_id: int
    channel_id: int
    attachment_url: str
    created_at: str


@dataclass(slots=True)
class Leaderboard:
    id: int
    channel_id: int
    leaderboard: LeaderboardType
