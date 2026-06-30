CREATE TABLE IF NOT EXISTS precuts(
  attachment_id INTEGER PRIMARY KEY,
  message_id INTEGER NOT NULL,
  author_id INTEGER NOT NULL,
  channel_id INTEGER NOT NULL,
  duration REAL NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channels(
  channel_id INTEGER PRIMARY KEY,
  owner_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS leaderboards (
  message_id INTEGER PRIMARY KEY,
  channel_id INTEGER NOT NULL,
  type TEXT NOT NULL
)
