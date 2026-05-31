import aiosqlite
from pathlib import Path

DB_PATH = Path("data/bot.db")


async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            members TEXT,
            privacy TEXT,
            posts_per_day TEXT,
            meta TEXT,
            raw_text TEXT,
            status TEXT DEFAULT 'discovered',
            joined INTEGER NOT NULL DEFAULT 0,
            join_requested_at TIMESTAMP,
            joined_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            location TEXT,
            occupation TEXT,
            raw_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_url TEXT NOT NULL,
            member_url TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_moderator INTEGER NOT NULL DEFAULT 0,
            is_verified INTEGER NOT NULL DEFAULT 0,
            can_follow INTEGER NOT NULL DEFAULT 0,
            can_add_friend INTEGER NOT NULL DEFAULT 0,
            raw_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_url, member_url),
            FOREIGN KEY(group_url) REFERENCES groups(url) ON DELETE CASCADE,
            FOREIGN KEY(member_url) REFERENCES members(url) ON DELETE CASCADE
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS member_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_url TEXT NOT NULL UNIQUE,
            member_name TEXT,
            message_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'drafted',
            drafted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sent_at TIMESTAMP,
            FOREIGN KEY(member_url) REFERENCES members(url) ON DELETE CASCADE
        )
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_groups_status ON groups(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_groups_joined ON groups(joined)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_group_members_group_url ON group_members(group_url)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_group_members_member_url ON group_members(member_url)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_member_messages_member_url ON member_messages(member_url)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_member_messages_status ON member_messages(status)")

        await db.commit()


def parse_group_meta(meta: str):
    parts = [part.strip() for part in meta.split("·")]
    privacy = ""
    members = ""
    posts_per_day = ""

    for part in parts:
        lowered = part.lower()

        if lowered in ["public", "private"]:
            privacy = part
        elif "member" in lowered:
            members = part
        elif "post" in lowered:
            posts_per_day = part

    return privacy, members, posts_per_day


def parse_member_lines(member: dict):
    lines = member.get("lines") or []
    name = member.get("name", "")

    ignored = {name, "Admin", "Moderator", "Follow", "Add Friend"}
    useful_lines = []

    for line in lines:
        line = line.strip()

        if not line:
            continue
        if line in ignored:
            continue
        if "Verified account" in line:
            continue
        if "view badge details" in line:
            continue

        useful_lines.append(line)

    location = useful_lines[0] if len(useful_lines) >= 1 else ""
    occupation = useful_lines[1] if len(useful_lines) >= 2 else ""

    return location, occupation


async def save_group(group: dict):
    privacy, members, posts_per_day = parse_group_meta(group.get("meta", ""))

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO groups (
            name, url, members, privacy, posts_per_day,
            meta, raw_text, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(url) DO UPDATE SET
            name = excluded.name,
            members = excluded.members,
            privacy = excluded.privacy,
            posts_per_day = excluded.posts_per_day,
            meta = excluded.meta,
            raw_text = excluded.raw_text,
            updated_at = CURRENT_TIMESTAMP
        """, (
            group.get("name", ""),
            group.get("url", ""),
            members,
            privacy,
            posts_per_day,
            group.get("meta", ""),
            group.get("raw_text", ""),
        ))

        await db.commit()


async def save_group_member(group: dict, member: dict):
    group_url = group.get("url", "")
    member_url = member.get("url", "")

    if not group_url or not member_url:
        return False

    location, occupation = parse_member_lines(member)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        await db.execute("""
        INSERT INTO members (
            name, url, location, occupation, raw_text, updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(url) DO UPDATE SET
            name = excluded.name,
            location = excluded.location,
            occupation = excluded.occupation,
            raw_text = excluded.raw_text,
            updated_at = CURRENT_TIMESTAMP
        """, (
            member.get("name", ""),
            member_url,
            location,
            occupation,
            member.get("raw_text", ""),
        ))

        await db.execute("""
        INSERT INTO group_members (
            group_url, member_url, is_admin, is_moderator,
            is_verified, can_follow, can_add_friend, raw_text, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(group_url, member_url) DO UPDATE SET
            is_admin = excluded.is_admin,
            is_moderator = excluded.is_moderator,
            is_verified = excluded.is_verified,
            can_follow = excluded.can_follow,
            can_add_friend = excluded.can_add_friend,
            raw_text = excluded.raw_text,
            updated_at = CURRENT_TIMESTAMP
        """, (
            group_url,
            member_url,
            1 if member.get("is_admin") else 0,
            1 if member.get("is_moderator") else 0,
            1 if member.get("is_verified") else 0,
            1 if member.get("can_follow") else 0,
            1 if member.get("can_add_friend") else 0,
            member.get("raw_text", ""),
        ))

        await db.commit()

    return True


async def has_member_been_messaged(member_url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
        SELECT id
        FROM member_messages
        WHERE member_url = ?
        LIMIT 1
        """, (member_url,))

        row = await cursor.fetchone()
        return row is not None


async def mark_member_message_drafted(member: dict, message_text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO member_messages (
            member_url,
            member_name,
            message_text,
            status
        )
        VALUES (?, ?, ?, 'drafted')
        ON CONFLICT(member_url) DO UPDATE SET
            member_name = excluded.member_name,
            message_text = excluded.message_text,
            status = 'drafted'
        """, (
            member.get("url", ""),
            member.get("name", ""),
            message_text,
        ))

        await db.commit()


async def mark_member_message_sent(member: dict, message_text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO member_messages (
            member_url,
            member_name,
            message_text,
            status,
            sent_at
        )
        VALUES (?, ?, ?, 'sent', CURRENT_TIMESTAMP)
        ON CONFLICT(member_url) DO UPDATE SET
            member_name = excluded.member_name,
            message_text = excluded.message_text,
            status = 'sent',
            sent_at = CURRENT_TIMESTAMP
        """, (
            member.get("url", ""),
            member.get("name", ""),
            message_text,
        ))

        await db.commit()


async def get_groups(status: str | None = None, joined: bool | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        query = "SELECT * FROM groups WHERE 1=1"
        params = []

        if status is not None:
            query += " AND status = ?"
            params.append(status)

        if joined is not None:
            query += " AND joined = ?"
            params.append(1 if joined else 0)

        query += " ORDER BY created_at DESC"

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        return [dict(row) for row in rows]


async def get_group_members(group_url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute("""
        SELECT
            members.*,
            group_members.is_admin,
            group_members.is_moderator,
            group_members.is_verified,
            group_members.can_follow,
            group_members.can_add_friend,
            group_members.raw_text AS group_raw_text
        FROM group_members
        JOIN members ON members.url = group_members.member_url
        WHERE group_members.group_url = ?
        ORDER BY group_members.created_at DESC
        """, (group_url,))

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_group_status(url: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        UPDATE groups
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE url = ?
        """, (status, url))

        await db.commit()


async def mark_group_joined(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        UPDATE groups
        SET
            joined = 1,
            status = 'joined',
            joined_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE url = ?
        """, (url,))

        await db.commit()


async def mark_group_unjoined(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        UPDATE groups
        SET joined = 0, updated_at = CURRENT_TIMESTAMP
        WHERE url = ?
        """, (url,))

        await db.commit()


async def get_group_by_url(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute("""
        SELECT *
        FROM groups
        WHERE url = ?
        LIMIT 1
        """, (url,))

        row = await cursor.fetchone()
        return dict(row) if row else None