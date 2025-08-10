# test_pg.py
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

try:
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", "5432"),
        connect_timeout=10,
        options="-c statement_timeout=8000"
    )
    print("✅ Connected to database")

    with conn.cursor() as cur:
        # Check basic connection info
        cur.execute("SELECT current_database(), current_user, inet_server_addr(), inet_server_port();")
        print("DB Info:", cur.fetchone())

        # List all user tables
        cur.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name;
        """)
        tables = cur.fetchall()

        print(f"\n📋 Found {len(tables)} tables:")
        for schema, table in tables:
            print(f"  {schema}.{table}")

    conn.close()

except Exception as e:
    print("❌ Connection error:", e)
