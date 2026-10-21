CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('STUDENT','STAFF','ADMIN')),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), session_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS request_types (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS requests (
 id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE,
 student_id INTEGER NOT NULL REFERENCES users(id), type_id INTEGER NOT NULL REFERENCES request_types(id),
 title TEXT NOT NULL, content TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('NEW','IN_PROGRESS','WAITING_STUDENT','COMPLETED','CANCELLED','REJECTED')),
 assignee_id INTEGER REFERENCES users(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history (
 id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES requests(id), action TEXT NOT NULL,
 from_status TEXT, to_status TEXT NOT NULL, actor_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES requests(id),
 sender_id INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attachments (
 id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES requests(id), message_id INTEGER REFERENCES messages(id),
 filename TEXT NOT NULL, mime_type TEXT NOT NULL, content BLOB NOT NULL, size INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
 id INTEGER PRIMARY KEY, recipient_id INTEGER NOT NULL REFERENCES users(id),
 request_id INTEGER NOT NULL REFERENCES requests(id), event_type TEXT NOT NULL,
 is_read INTEGER NOT NULL DEFAULT 0 CHECK(is_read IN (0,1)), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency (
 user_id INTEGER NOT NULL REFERENCES users(id), method TEXT NOT NULL, path TEXT NOT NULL,
 key TEXT NOT NULL, digest TEXT NOT NULL, body TEXT NOT NULL, status INTEGER NOT NULL,
 PRIMARY KEY(user_id,method,path,key)
);
CREATE INDEX IF NOT EXISTS requests_student ON requests(student_id,status);
CREATE INDEX IF NOT EXISTS requests_assignee ON requests(assignee_id,status);
CREATE INDEX IF NOT EXISTS notifications_recipient ON notifications(recipient_id,id);
CREATE INDEX IF NOT EXISTS history_request ON history(request_id,id);
CREATE INDEX IF NOT EXISTS messages_request ON messages(request_id,id);
