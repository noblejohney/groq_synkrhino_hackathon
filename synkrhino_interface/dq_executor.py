import psycopg2
import os
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

class SynkRhinoActions:
    def __init__(self):
        try:
            self.conn = psycopg2.connect(
                dbname=os.getenv("DB_NAME", "postgres"),
                user=os.getenv("DB_USER", ""),
                password=os.getenv("DB_PASS", ""),
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5432")
            )
            self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            self.conn = None
            self.cursor = None

    def run_null_check(self):
        if not self.cursor:
            return [{"error": "No DB connection"}]

        try:
            self.cursor.execute("""
                SELECT column_name, COUNT(*) AS null_count 
                FROM column_profile 
                WHERE null_count > 0 
                GROUP BY column_name
            """)
            return self.cursor.fetchall()
        except Exception as e:
            return [{"error": str(e)}]

    def run_row_count(self):
        if not self.cursor:
            return [{"error": "No DB connection"}]

        try:
            self.cursor.execute("""
                SELECT table_name, source_count, target_count 
                FROM row_count_validation
            """)
            return self.cursor.fetchall()
        except Exception as e:
            return [{"error": str(e)}]

    def get_validation_results(self):
        if not self.cursor:
            return [{"error": "No DB connection"}]

        try:
            self.cursor.execute("""
                SELECT * FROM validation_results 
                WHERE status = 'Failed' 
                ORDER BY validation_time DESC 
                LIMIT 5
            """)
            return self.cursor.fetchall()
        except Exception as e:
            return [{"error": str(e)}]

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
