import sqlite3

conn = sqlite3.connect('agent_builder.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM tasks')
print(f'Tasks: {cursor.fetchone()[0]}')

cursor.execute('SELECT title, status FROM tasks LIMIT 10')
print('\nTasks:')
for row in cursor.fetchall():
    print(f'  - {row[0]} [{row[1]}]')

cursor.execute('SELECT COUNT(*) FROM features')
print(f'\nFeatures: {cursor.fetchone()[0]}')

cursor.execute('SELECT name FROM projects')
print('\nProjects:')
for row in cursor.fetchall():
    print(f'  - {row[0]}')

conn.close()
