import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

class SynkRhinoActions:
    """
    Executes DB/DQ actions and dispatches based on Groq intent.

    Expected Groq structured response (preferred):
      {
        "action": "null_check" | "row_count" | "failed_results" | "count_tables" | "custom_query",
        "args": { "table": "customer", "schema": "public", "limit": 5, ... }
      }

    Fallback (unstructured string): we’ll keyword-route safely.
    """

    def __init__(self):
        try:
            self.conn = psycopg2.connect(
                dbname=os.getenv("DB_NAME", "postgres"),
                user=os.getenv("DB_USER", ""),
                password=os.getenv("DB_PASS", ""),
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5432"),
            )
            self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            self.conn = None
            self.cursor = None

        # simple allowlist for schemas/tables if you want to restrict
        self.allowed_schemas = set(os.getenv("ALLOWED_SCHEMAS", "public").split(","))
        # Example: ALLOWED_TABLES="column_profile,row_count_validation,validation_results"
        self.allowed_tables = set(os.getenv("ALLOWED_TABLES", "").split(",")) if os.getenv("ALLOWED_TABLES") else None

    # ---------- Public: LLM dispatcher ----------

    def run_action(self, groq_result):
        """
        Accepts a dict (preferred) or string from Groq and dispatches to the right handler.
        """
        if not self.cursor:
            return [{"error": "No DB connection"}]

        # Normalize input to dict with {"action": ..., "args": {...}}
        action, args = self._normalize_groq_result(groq_result)

        # Route
        if action == "null_check":
            return self.run_null_check(args)
        if action == "row_count":
            return self.run_row_count(args)
        if action == "failed_results" or action == "summary" or action == "failures":
            return self.get_validation_results(args)
        if action == "count_tables":
            return self.count_tables(args)
        if action == "greeting":
            return [{"message": "👋 Hello! I'm your SynkRhino DQ Assistant. How can I help?"}]
        if action == "custom_query":
            return self.run_custom_query(args)

        # Unknown -> echo safely
        return [{"info": "Unrecognized action", "received": {"action": action, "args": args}}]

    # ---------- Normalization ----------

    def _normalize_groq_result(self, groq_result):
        """
        Try to coerce Groq output into (action, args) tuple.
        """
        # If dict-like already
        if isinstance(groq_result, dict):
            return groq_result.get("action", "").lower(), groq_result.get("args", {}) or {}

        # If JSON string
        if isinstance(groq_result, str):
            s = groq_result.strip()
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    return obj.get("action", "").lower(), obj.get("args", {}) or {}
            except json.JSONDecodeError:
                pass

            # Fallback keyword routing
            low = s.lower()
            if "greeting" in low or "hello" in low or "hi" in low:
                return "greeting", {}
            if "null" in low:
                return "null_check", {}
            if "row count" in low:
                return "row_count", {}
            if "failed" in low or "summary" in low or "failure" in low:
                return "failed_results", {}
            if "how many tables" in low or "count tables" in low:
                return "count_tables", {}

        return "", {}

    # ---------- Handlers ----------

    def run_null_check(self, args=None):
        try:
            # Optional filter by table/column if provided + allowed
            table = (args or {}).get("table")
            if table and self.allowed_tables and table not in self.allowed_tables:
                return [{"error": f"Table '{table}' not allowed."}]

            if table:
                self.cursor.execute(
                    """
                    SELECT column_name, null_count
                    FROM column_profile
                    WHERE null_count > 0 AND table_name = %s
                    ORDER BY null_count DESC
                    """,
                    (table,),
                )
            else:
                self.cursor.execute(
                    """
                    SELECT table_name, column_name, null_count
                    FROM column_profile
                    WHERE null_count > 0
                    ORDER BY null_count DESC
                    """
                )
            return self.cursor.fetchall()
        except Exception as e:
            return [{"error": str(e)}]

    def run_row_count(self, args=None):
        try:
            table = (args or {}).get("table")
            if table and self.allowed_tables and table not in self.allowed_tables:
                return [{"error": f"Table '{table}' not allowed."}]

            if table:
                self.cursor.execute(
                    """
                    SELECT table_name, source_count, target_count
                    FROM row_count_validation
                    WHERE table_name = %s
                    """,
                    (table,),
                )
            else:
                self.cursor.execute(
                    """
                    SELECT table_name, source_count, target_count
                    FROM row_count_validation
                    ORDER BY table_name
                    """
                )
            return self.cursor.fetchall()
        except Exception as e:
            return [{"error": str(e)}]

    def get_validation_results(self, args=None):
        try:
            limit = int((args or {}).get("limit", 5))
            self.cursor.execute(
                """
                SELECT *
                FROM validation_results
                WHERE status = 'Failed'
                ORDER BY validation_time DESC
                LIMIT %s
                """,
                (limit,),
            )
            return self.cursor.fetchall()
        except Exception as e:
            return [{"error": str(e)}]

    def count_tables(self, args=None):
        try:
            schema = (args or {}).get("schema", "public")
            if schema not in self.allowed_schemas:
                return [{"error": f"Schema '{schema}' not allowed."}]
            self.cursor.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = %s
                """,
                (schema,),
            )
            row = self.cursor.fetchone()
            return [{"schema": schema, "table_count": list(row.values())[0] if row else 0}]
        except Exception as e:
            return [{"error": str(e)}]

    def run_custom_query(self, args=None):
        """
        Extremely cautious custom query executor:
        - Only allows SELECT
        - Optional whitelist for table name
        - Parameter injection via %s and tuple
        """
        try:
            query = (args or {}).get("sql", "")
            params = (args or {}).get("params", [])
            if not query.strip().lower().startswith("select"):
                return [{"error": "Only SELECT statements are allowed."}]

            # crude but helpful safety: block semicolons & dangerous keywords
            banned = [";", "insert ", "update ", "delete ", "drop ", "alter ", "create ", "grant ", "revoke "]
            low = query.lower()
            if any(b in low for b in banned):
                return [{"error": "Query contains disallowed tokens."}]

            # optional: enforce allowed table usage
            if self.allowed_tables:
                if not any(t in low for t in self.allowed_tables):
                    return [{"error": "Query must reference an allowed table."}]

            self.cursor.execute(query, tuple(params))
            return self.cursor.fetchall()
        except Exception as e:
            return [{"error": str(e)}]

    # ---------- Utilities ----------

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
