import sqlite3
import json as _json
from datetime import datetime

DATABASE_NAME = "lucia.db"


def get_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    connection = get_connection()
    cursor = connection.cursor()

    # 1. Conversations Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT 'New Chat',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Messages Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)

    # 3. Conversation Summary Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_summary (
            conversation_id INTEGER PRIMARY KEY,
            summary TEXT NOT NULL,
            last_message_id INTEGER DEFAULT 0,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)

    # 4. Long-term Memories Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            memory TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            importance REAL DEFAULT 0.5,
            embedding TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)

    connection.commit()
    connection.close()


# =========================
# CONVERSATION OPERATIONS
# =========================

def create_conversation(title="New Chat"):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("INSERT INTO conversations (title) VALUES (?)", (title,))
    conv_id = cursor.lastrowid
    connection.commit()
    connection.close()
    return conv_id


def get_all_conversations():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, title, updated_at 
        FROM conversations 
        ORDER BY updated_at DESC
    """)
    rows = cursor.fetchall()
    connection.close()
    return rows


def update_conversation_title(conversation_id, title):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        UPDATE conversations SET title = ? WHERE id = ?
    """, (title, conversation_id))
    connection.commit()
    connection.close()


def touch_conversation(conversation_id):
    """Update timestamp for ordering in sidebar"""
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?
    """, (conversation_id,))
    connection.commit()
    connection.close()


def delete_conversation(conversation_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    cursor.execute("DELETE FROM conversation_summary WHERE conversation_id = ?", (conversation_id,))
    cursor.execute("DELETE FROM memories WHERE conversation_id = ?", (conversation_id,))
    cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    connection.commit()
    connection.close()


# =========================
# MESSAGE OPERATIONS
# =========================

def save_message(conversation_id, role, content):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO messages (conversation_id, role, content)
        VALUES (?, ?, ?)
    """, (conversation_id, role, content))
    msg_id = cursor.lastrowid
    cursor.execute("""
        UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?
    """, (conversation_id,))
    connection.commit()
    connection.close()
    return msg_id


def get_messages(conversation_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, role, content FROM messages
        WHERE conversation_id = ?
        ORDER BY id ASC
    """, (conversation_id,))
    rows = cursor.fetchall()
    connection.close()
    return rows


def get_recent_messages(conversation_id, limit=20):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT role, content FROM messages
        WHERE conversation_id = ?
        ORDER BY id DESC LIMIT ?
    """, (conversation_id, limit))
    rows = cursor.fetchall()
    connection.close()
    return rows[::-1]


def delete_last_assistant_message(conversation_id):
    """For regenerate feature"""
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id FROM messages 
        WHERE conversation_id = ? AND role = 'assistant'
        ORDER BY id DESC LIMIT 1
    """, (conversation_id,))
    row = cursor.fetchone()
    if row:
        cursor.execute("DELETE FROM messages WHERE id = ?", (row[0],))
        connection.commit()
    connection.close()


# =========================
# SUMMARY OPERATIONS
# =========================

def get_summary(conversation_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT summary, last_message_id FROM conversation_summary
        WHERE conversation_id = ?
    """, (conversation_id,))
    row = cursor.fetchone()
    connection.close()
    if row:
        return row[0], row[1]
    return "", 0


def save_summary(conversation_id, summary, last_message_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO conversation_summary 
        (conversation_id, summary, last_message_id)
        VALUES (?, ?, ?)
    """, (conversation_id, summary, last_message_id))
    connection.commit()
    connection.close()


def get_messages_after(conversation_id, message_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, role, content FROM messages
        WHERE conversation_id = ? AND id > ?
        ORDER BY id ASC
    """, (conversation_id, message_id))
    rows = cursor.fetchall()
    connection.close()
    return rows


# =========================
# LONG-TERM MEMORY OPERATIONS
# =========================

def save_memory(conversation_id, memory, category="general", importance=0.5, embedding=None):
    connection = get_connection()
    cursor = connection.cursor()
    embedding_str = _json.dumps(embedding) if embedding else None
    cursor.execute("""
        INSERT INTO memories (conversation_id, memory, category, importance, embedding)
        VALUES (?, ?, ?, ?, ?)
    """, (conversation_id, memory, category, importance, embedding_str))
    mem_id = cursor.lastrowid
    connection.commit()
    connection.close()
    return mem_id


def get_all_memories(conversation_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, memory, category, importance, embedding 
        FROM memories
        WHERE conversation_id = ?
        ORDER BY importance DESC, created_at DESC
    """, (conversation_id,))
    rows = cursor.fetchall()
    connection.close()

    memories = []
    for row in rows:
        memories.append({
            "id": row[0],
            "memory": row[1],
            "category": row[2],
            "importance": row[3],
            "embedding": _json.loads(row[4]) if row[4] else None
        })
    return memories


def update_memory(memory_id, new_memory, embedding=None):
    connection = get_connection()
    cursor = connection.cursor()
    embedding_str = _json.dumps(embedding) if embedding else None
    if embedding_str:
        cursor.execute("""
            UPDATE memories 
            SET memory = ?, embedding = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_memory, embedding_str, memory_id))
    else:
        cursor.execute("""
            UPDATE memories 
            SET memory = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_memory, memory_id))
    connection.commit()
    connection.close()


def delete_memory(memory_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    connection.commit()
    connection.close()


def get_top_memories(conversation_id, limit=5):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT memory, category FROM memories
        WHERE conversation_id = ?
        ORDER BY importance DESC
        LIMIT ?
    """, (conversation_id, limit))
    rows = cursor.fetchall()
    connection.close()
    return rows

def get_global_memories():
    """
    Fetches all memories across ALL conversations.
    Ensures LUCIA has a global user profile memory regardless of active chat.
    """
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, memory, category, importance, embedding 
        FROM memories
        ORDER BY importance DESC, created_at DESC
    """)
    rows = cursor.fetchall()
    connection.close()

    memories = []
    for row in rows:
        memories.append({
            "id": row[0],
            "memory": row[1],
            "category": row[2],
            "importance": row[3],
            "embedding": _json.loads(row[4]) if row[4] else None
        })
    return memories

# Initialize database schema on load
init_db()