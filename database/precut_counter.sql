CREATE TABLE IF NOT EXISTS channels(
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL CHECK (
        type IN ('text', 'forum', 'thread')
  ),
  role TEXT NOT NULL CHECK (
        role IN ('drop', 'demon', 'leaderboard')
  )
);

CREATE TABLE IF NOT EXISTS demons(
  channel_id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,

  FOREIGN KEY (channel_id) REFERENCES channels(id)
    ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS precuts (
  id INTEGER PRIMARY KEY,
  message_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  channel_id INTEGER NOT NULL,
  duration REAL NOT NULL,
  created_at TEXT NOT NULL,

  FOREIGN KEY (channel_id) REFERENCES channels(id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS leaderboards (
  id INTEGER PRIMARY KEY,
  channel_id INTEGER NOT NULL,
  type TEXT NOT NULL CHECK (
        type IN ('global', 'demon')
  ),

  FOREIGN KEY (channel_id) REFERENCES channels(id)
    ON DELETE CASCADE
);
