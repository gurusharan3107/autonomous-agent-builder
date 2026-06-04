import sqlite3

conn = sqlite3.connect('.agent-builder/agent_builder.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'chat%'")
tables = [row[0] for row in cursor.fetchall()]
print(f'Chat tables: {tables}')

if 'chat_sessions' in tables:
    cursor.execute('SELECT COUNT(*) FROM chat_sessions')
    print(f'Chat sessions: {cursor.fetchone()[0]}')

if 'chat_messages' in tables:
    cursor.execute('SELECT COUNT(*) FROM chat_messages')
    print(f'Chat messages: {cursor.fetchone()[0]}')

conn.close()
