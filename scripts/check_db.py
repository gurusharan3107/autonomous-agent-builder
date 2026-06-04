import sqlite3

conn = sqlite3.connect('.agent-builder/agent_builder.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM features')
print(f'Features: {cursor.fetchone()[0]}')

cursor.execute('SELECT COUNT(*) FROM tasks')
print(f'Tasks: {cursor.fetchone()[0]}')

cursor.execute('SELECT title, status FROM features LIMIT 5')
print('\nFirst 5 features:')
for row in cursor.fetchall():
    print(f'  - {row[0]} [{row[1]}]')

conn.close()
