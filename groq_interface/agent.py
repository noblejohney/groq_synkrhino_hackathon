import os, re, json, csv, uuid
from typing import Dict, Any, List
from functools import lru_cache
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from langchain_community.utilities import SQLDatabase
from groq_interface.groq_rest import GroqREST

load_dotenv()

# ---- caps ----
UI_MAX_ROWS = 1000          # rows shown in the app
DOWNLOAD_MAX_ROWS = 2_000_000  # safety upper bound for download (adjust to your infra)

def build_db_uri() -> str:
    return (
        "postgresql+psycopg2://{u}:{p}@{h}:{pt}/{d}?sslmode={ssl}{opts}"
    ).format(
        u=os.getenv("DB_USER", ""),
        p=os.getenv("DB_PASS", ""),
        h=os.getenv("DB_HOST", "localhost"),
        pt=os.getenv("DB_PORT", "5432"),
        d=os.getenv("DB_NAME", ""),
        ssl=os.getenv("PG_SSLMODE", "prefer"),
        opts=f"&options={os.getenv('PG_OPTIONS')}" if os.getenv("PG_OPTIONS") else "",
    )

def validate_sql(sql: str) -> str:
    s = (sql or "").strip()
    if not s.lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed.")
    if ";" in s:
        raise ValueError("Semicolons / multiple statements are not allowed.")
    banned = [" insert ", " update ", " delete ", " drop ", " alter ",
              " create ", " truncate ", " grant ", " revoke "]
    low = f" {s.lower()} "
    if any(b in low for b in banned):
        raise ValueError("Dangerous keyword detected; blocked.")
    return s  # NOTE: no LIMIT injected here (exactness preserved)

class SQLChatAgentREST:
    def __init__(self, model="openai/gpt-oss-120b", temperature=0.0, schema="synkrino"):
        print(model,temperature,schema,'GROQ------------>>>')
        self.groq = GroqREST(model=model, temperature=temperature)
        self.schema = schema
        # Keep LangChain SQLDatabase for schema introspection
        self.db = SQLDatabase.from_uri(build_db_uri(), schema=schema)
        # Use SQLAlchemy for safe, chunked execution
        self.engine = create_engine(build_db_uri(), pool_pre_ping=True)

    @lru_cache(maxsize=1)
    def get_schema(self) -> str:
        raw = self.db.get_table_info()
        return raw[:6000]  # keep schema short for LLM

    # --- LLM prompts (same as before or your version) ---
    SQL_SYSTEM = (
    "You write ONLY PostgreSQL SELECT queries for read-only analytics. "
    "Return ONLY the SQL, with no code fences or commentary. Single statement; no semicolons; "
    "no INSERT/UPDATE/DELETE/TRUNCATE/DROP/ALTER/CREATE/GRANT/REVOKE. Add LIMIT 100 if not specified.")

    # SQL_SYSTEM = ("You are an assistant data‑engineer that only writes PostgreSQL SELECT queries "
    #     "for read‑only analytics.  When asked a question, produce a single SELECT "
    #     "statement (no semicolons, no DDL/DML, no schema changes).  Include a short "
    #     "explanation.  Return a JSON object:\n"
    #     "{\n  \"sql\": \"<your SQL>\",\n  \"explanation\": \"<explanation>\"\n}\n"
    #     "Do not add any code fences, comments, or extraneous text.")

    SQL_USER_TMPL = "Database schema:\n{schema}\n\nUser question:\n{question}\n\nReturn ONLY the SQL query."

    SUM_SYSTEM = "Summarize the SQL result concisely for a business user. If empty, say so briefly."
    SUM_USER_TMPL = "Question: {question}\nSQL: {sql}\nRows (sample): {rows}"

    def generate_sql(self, question: str) -> str:
        schema = self.get_schema()
        messages = [
            {"role": "system", "content": self.SQL_SYSTEM},
            {"role": "user", "content": self.SQL_USER_TMPL.format(schema=schema, question=question)},
        ]
        sql = self.groq.chat(messages, max_tokens=384).strip()
        sql = sql.replace("```sql", "").replace("```", "").strip()
        return validate_sql(sql)

    # ---- server-side capped execution for the UI ----
    def run_sql_capped(self, sql: str, max_rows: int = UI_MAX_ROWS) -> Dict[str, Any]:
        """
        Executes a capped version of the query for UI safety:
          SELECT * FROM ( <original SQL> ) t LIMIT max_rows + 1
        Returns:
          { 'rows': List[dict], 'truncated': bool, 'wrapped_sql': str }
        """
        wrapped = f"SELECT * FROM ({sql}) AS t LIMIT {max_rows + 1}"
        rows: List[dict] = []
        truncated = False
        with self.engine.connect() as conn:
            res = conn.execute(text(wrapped))
            cols = list(res.keys())
            for i, r in enumerate(res):
                if i >= max_rows:
                    truncated = True
                    break
                rows.append({c: r[idx] for idx, c in enumerate(cols)})
        return {"rows": rows, "truncated": truncated, "wrapped_sql": wrapped}

    # ---- on-demand: export full results to CSV (re-exec without LIMIT) ----
    def export_full_csv(self, sql: str, out_dir: str = "exports") -> str:
        """
        Streams full results to a CSV. Use with caution: can be large.
        Returns CSV file path.
        """
        os.makedirs(out_dir, exist_ok=True)
        csv_path = os.path.join(out_dir, f"query_{uuid.uuid4().hex}.csv")
        with self.engine.connect() as conn, open(csv_path, "w", newline="", encoding="utf-8") as f:
            res = conn.execution_options(stream_results=True).execute(text(sql))
            writer = None
            count = 0
            while True:
                chunk = res.fetchmany(1000)
                if not chunk:
                    break
                if writer is None:
                    cols = list(res.keys())
                    writer = csv.DictWriter(f, fieldnames=cols)
                    writer.writeheader()
                for r in chunk:
                    writer.writerow({c: r[idx] for idx, c in enumerate(cols)})
                    count += 1
                    if count > DOWNLOAD_MAX_ROWS:  # hard safety stop
                        break
                if count > DOWNLOAD_MAX_ROWS:
                    break
        return csv_path

    def summarize(self, question: str, sql: str, rows_sample) -> str:
        sample = json.dumps(rows_sample, default=str)[:4000]
        messages = [
            {"role": "system", "content": self.SUM_SYSTEM},
            {"role": "user", "content": self.SUM_USER_TMPL.format(question=question, sql=sql, rows=sample)},
        ]
        return self.groq.chat(messages, max_tokens=384)

    def answer(self, question: str) -> Dict[str, Any]:
        sql = self.generate_sql(question)            # exact (no LIMIT)
        ui = self.run_sql_capped(sql)                # capped for UI
        answer = self.summarize(question, sql, ui["rows"])
        return {
            "sql": sql,
            "rows": ui["rows"],
            "truncated": ui["truncated"],
            "wrapped_sql": ui["wrapped_sql"],
            "answer": answer
        }
