CREATE TABLE IF NOT EXISTS attachments(
  attachment_id INTEGER PRIMARY KEY,
  message_id INTEGER NOT NULL,
  author_id INTEGER NOT NULL,
  duration REAL NOT NULL
);
