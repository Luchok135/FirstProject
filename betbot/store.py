import sqlite3
import time
from pathlib import Path

PERIOD = 30 * 86400

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS subscriptions(user_id INTEGER PRIMARY KEY, until INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS payments(charge TEXT PRIMARY KEY, user_id INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sources(chat_id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sent(chat_id INTEGER, message_id INTEGER, PRIMARY KEY(chat_id,message_id));
        ''')

    def grant(self, user_id, charge, now=None):
        now = int(time.time()) if now is None else now
        with self.db:
            if not self.db.execute('INSERT OR IGNORE INTO payments VALUES (?,?)', (charge,user_id)).rowcount:
                return False
            self.db.execute('INSERT INTO subscriptions VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET until=MAX(until,?)+?', (user_id,now+PERIOD,now,PERIOD))
        return True

    def active(self, user_id):
        row = self.db.execute('SELECT until FROM subscriptions WHERE user_id=?',(user_id,)).fetchone()
        return bool(row and row[0] > time.time())

    def topic(self, chat_id):
        row = self.db.execute('SELECT topic_id FROM sources WHERE chat_id=?',(chat_id,)).fetchone()
        return row[0] if row else None

    def seen(self, chat_id, message_id):
        return self.db.execute('SELECT 1 FROM sent WHERE chat_id=? AND message_id=?',(chat_id,message_id)).fetchone() is not None

    def mark(self, chat_id, message_id):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO sent VALUES (?,?)',(chat_id,message_id))
