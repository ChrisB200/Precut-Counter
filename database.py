from config import DROP_PRECUT_CHANNEL, conn, cursor


def add_precut(precut):
    cursor.execute(
        """
        INSERT OR IGNORE INTO precuts (
            attachment_id,
            message_id,
            author_id,
            channel_id,
            duration,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            precut["attachment_id"],
            precut["message_id"],
            precut["author_id"],
            precut["channel_id"],
            precut["duration"],
            precut["created_at"],
        ),
    )


def delete_precut(message_id):
    cursor.execute(
        "DELETE FROM precuts WHERE message_id = ?",
        (message_id,),
    )
    conn.commit()


def is_first_time_run():
    cursor.execute("SELECT COUNT(*) FROM precuts")
    count = cursor.fetchone()[0]
    return count == 0


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


def add_channel(channel_id, owner_id):
    cursor.execute(
        """
        INSERT OR IGNORE into channels (
            channel_id,
            owner_id
        )
        VALUES (?, ?)
    """,
        (channel_id, owner_id),
    )

    conn.commit()


def delete_channel(channel_id):
    cursor.execute(
        "DELETE FROM channels WHERE channel_id = ?",
        (channel_id,),
    )
    conn.commit()


def get_latest_message_id(channel_id):
    cursor.execute(
        """
        SELECT MAX(message_id)
        FROM precuts
        WHERE channel_id = ?
    """,
        (channel_id,),
    )

    row = cursor.fetchone()
    return row[0]


def get_channels():
    cursor.execute("SELECT * FROM channels")
    rows = cursor.fetchall()
    return rows


def add_leaderboard(message_id, channel_id, board_type):
    cursor.execute(
        """
        INSERT OR REPLACE INTO leaderboards (
            message_id,
            channel_id,
            type
        )
        VALUES (?, ?, ?)
        """,
        (message_id, channel_id, board_type),
    )

    conn.commit()


def get_leaderboard_messages():
    cursor.execute("""
        SELECT
            message_id,
            channel_id,
            type
        FROM leaderboards
    """)

    return cursor.fetchall()


def delete_drop_precuts(author_id):
    cursor.execute(
        """
        DELETE FROM precuts
        WHERE author_id = ?
        AND channel_id = ?
        """,
        (author_id, DROP_PRECUT_CHANNEL),
    )

    conn.commit()


def get_demon_owner_ids():
    cursor.execute("""
        SELECT owner_id
        FROM channels
    """)

    return {row[0] for row in cursor.fetchall()}
