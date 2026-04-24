import sqlite3

conn = sqlite3.connect('.agent-builder/agent_builder.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM tasks')
print(f'Tasks: {cursor.fetchone()[0]}')

cursor.execute('SELECT title, status, feature_id FROM tasks LIMIT 10')
print('\nTasks:')
for row in cursor.fetchall():
    print(f'  - {row[0]} [{row[1]}] (feature: {row[2]})')

cursor.execute('SELECT id, title FROM features LIMIT 10')
print('\nFeatures:')
for row in cursor.fetchall():
    print(f'  - {row[1]} (ID: {row[0]})')

conn.close()
