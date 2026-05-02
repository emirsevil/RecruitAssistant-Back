"""
Fix the alembic_version table when it points to a deleted migration.
Sets the version to the actual current head: 2f88837e306c
"""
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:123456@localhost:5432/recruit")

# Parse connection params from URL
# postgresql://user:password@host:port/dbname
url = DATABASE_URL.replace("postgresql://", "")
user_pass, rest = url.split("@")
user, password = user_pass.split(":")
host_port, dbname = rest.split("/")
if ":" in host_port:
    host, port = host_port.split(":")
else:
    host, port = host_port, "5432"

CORRECT_REVISION = "db4f96fe3be4"

conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)
conn.autocommit = True
cur = conn.cursor()

cur.execute("SELECT version_num FROM alembic_version;")
rows = cur.fetchall()
print(f"Current alembic_version rows: {rows}")

cur.execute("DELETE FROM alembic_version;")
cur.execute("INSERT INTO alembic_version (version_num) VALUES (%s);", (CORRECT_REVISION,))

cur.execute("SELECT version_num FROM alembic_version;")
rows = cur.fetchall()
print(f"Updated alembic_version rows: {rows}")

cur.close()
conn.close()
print("✅ Done! alembic_version stamped to:", CORRECT_REVISION)
