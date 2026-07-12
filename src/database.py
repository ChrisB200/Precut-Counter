import logging
import sqlite3

from src.models import Channel, ChannelRole, ChannelType, Demon, Precut

logger = logging.getLogger(__name__)

conn = sqlite3.connect("database/precut_counter.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
conn.execute("PRAGMA foreign_keys = ON")
conn.executescript(open("database/precut_counter.sql").read())


def get_channels() -> list[Channel]:
    cursor.execute("SELECT * FROM channels")
    rows = cursor.fetchall()
    channels = [Channel.from_row(row) for row in rows]

    logger.debug("loaded %d channels from db", len(channels))
    return channels


def get_channel_by_id(id: int) -> Channel | None:
    cursor.execute(
        "SELECT * FROM channels WHERE id = ?",
        (id,),
    )
    row = cursor.fetchone()
    if row:
        channel = Channel.from_row(row)
        logger.debug("Loaded channel %d", channel.id)
        return channel

    logger.warning("Could not find channel %d in database", id)
    return None


def get_channels_by_type(ctype: ChannelType) -> list[Channel]:
    cursor.execute(
        "SELECT * FROM channels WHERE type = ?",
        (ctype.value,),
    )
    rows = cursor.fetchall()
    channels = [Channel.from_row(row) for row in rows]

    logger.debug("Loaded %d %s channels from db", len(channels), ctype.value)
    return channels


def get_channels_by_role(role: ChannelRole) -> list[Channel]:
    cursor.execute(
        "SELECT * FROM channels WHERE role = ?",
        (role.value,),
    )
    rows = cursor.fetchall()
    channels = [Channel.from_row(row) for row in rows]

    logger.debug("Loaded %d %s channels from db", len(channels), role.value)
    return channels


def delete_channel(id: int) -> bool:
    cursor.execute("DELETE FROM channels WHERE id = ?", (id,))
    conn.commit()

    if not cursor.rowcount:
        logger.debug("Channel %d did not exist", id)
        return False

    logger.debug("Deleted channel %d", id)
    return True


def get_demons() -> list[Demon]:
    cursor.execute("SELECT * FROM demons")
    rows = cursor.fetchall()
    demons = [Demon.from_row(row) for row in rows]

    logger.debug("loaded %d demons from db", len(demons))
    return demons


def add_channel(channel: Channel) -> bool:
    cursor.execute(
        """
        INSERT OR IGNORE INTO channels (
            id,
            role,
            type
        )
        VALUES (?, ?, ?)
    """,
        (channel.id, channel.role.value, channel.type.value),
    )
    conn.commit()

    if not cursor.rowcount:
        logger.debug("Channel %d already exists", channel.id)
        return False

    logger.debug("Added channel id: %d", channel.id)
    return True


def get_last_message_id(channel_id: int) -> int | None:
    cursor.execute(
        """
        SELECT MAX(message_id) AS message_id
        FROM precuts
        WHERE channel_id = ?
    """,
        (channel_id,),
    )

    row = cursor.fetchone()
    if row is None:
        logger.warning("Could not find message id in channel %d", channel_id)
        return None

    message_id = row["message_id"]
    return message_id


def add_precut(precut: Precut) -> bool:
    cursor.execute(
        """
        INSERT OR IGNORE INTO precuts (
            id,
            message_id,
            user_id,
            channel_id,
            duration,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            precut.id,
            precut.message_id,
            precut.user_id,
            precut.channel_id,
            precut.duration,
            precut.created_at,
        ),
    )
    conn.commit()

    if not cursor.rowcount:
        logger.debug("Precut %d already exists", precut.id)
        return False

    logger.debug("Added precut %d", precut.id)
    return True


def delete_precuts_by_message_id(message_id: int) -> bool:
    cursor.execute("DELETE FROM precuts WHERE message_id = ?", (message_id,))
    conn.commit()

    if not cursor.rowcount:
        logger.debug("Precut with message_id %d did not exist", message_id)
        return False

    logger.debug("Deleted precut with message_id %d", message_id)
    return True


def add_demon(demon: Demon):
    cursor.execute(
        """
        INSERT OR IGNORE INTO demons (
            channel_id,
            user_id
        )
        VALUES (?, ?)
    """,
        (demon.channel_id, demon.user_id),
    )
    conn.commit()

    if not cursor.rowcount:
        logger.debug("Demon %d already exists", demon.user_id)
        return False

    logger.debug("Added demon id: %d", demon.user_id)
    return True


def delete_precuts_by_user_id(user_id: int) -> bool:
    cursor.execute("DELETE FROM precuts WHERE user_id = ?", (user_id,))
    conn.commit()

    if not cursor.rowcount:
        logger.debug("Precut with user_id %d did not exist", user_id)
        return False

    logger.debug("Deleted precut with user_id %d", user_id)
    return True


def get_global_leaderboard():
    cursor.execute("""
        SELECT
            author_id,
            COUNT(*) AS precut_count,
            SUM(duration) AS total_duration
        FROM precuts
        GROUP BY author_id
        ORDER BY total_duration DESC
        LIMIT 10;
        """)

    rows = cursor.fetchall()

    return rows


def get_demon_leaderboard():
    cursor.execute("""
    SELECT
        a.author_id,
        COUNT(*) AS precuts,
        SUM(a.duration) AS total_duration
    FROM precuts a
    JOIN channels c
        ON a.author_id = c.owner_id
    GROUP BY a.author_id
    ORDER BY total_duration DESC
    LIMIT 10;
    """)
    rows = cursor.fetchall()
    return rows


def get_stats(user_id: int):
    cursor.execute(
        """
        SELECT *
        FROM (
            SELECT
                user_id,
                COUNT(*) AS count,
                SUM(duration) AS duration,
                RANK() OVER (
                    ORDER BY SUM(duration) DESC,
                             COUNT(*) DESC
                ) AS rank
            FROM precuts
            GROUP BY user_id
        )
        WHERE user_id = ?;
        """,
        (user_id,),
    )

    row = cursor.fetchone()
    return row


def get_last_donation(user_id: int):
    cursor.execute(
        """
        SELECT message_id, channel_id
        FROM precuts
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 1;
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    return row
