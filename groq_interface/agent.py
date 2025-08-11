import os, re, json, csv, uuid, hashlib, time, requests
from datetime import datetime, timezone
from typing import Dict, Any, List
from functools import lru_cache
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from langchain_community.utilities import SQLDatabase
from groq_interface.groq_rest import GroqREST

load_dotenv()

DOWNLOAD_MAX_ROWS = 2_000_000
SCHEMA_CACHE_DIR = os.getenv("SCHEMA_CACHE_DIR", "state/schema_cache")
SCHEMA_TTL_SEC  = int(os.getenv("SCHEMA_TTL_SEC", "3600"))
os.makedirs(SCHEMA_CACHE_DIR, exist_ok=True)

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

class SQLChatAgentREST:
    # ---- Prompts ----
    DEFAULT_SQL_SYSTEM = (
        "You write ONLY PostgreSQL SELECT queries for read-only analytics. "
        "Return ONLY the SQL, with no code fences or commentary. Single statement; no semicolons; "
        "no INSERT/UPDATE/DELETE/TRUNCATE/DROP/ALTER/CREATE/GRANT/REVOKE. Add LIMIT {default_limit} if not specified."
    )
    SQL_USER_TMPL = "Database schema:\n{schema}\n\nUser question:\n{question}\n\nReturn ONLY the SQL query."

    GENERAL_SYSTEM = (
        "You are a concise, friendly assistant. Be practical, accurate, and brief. "
        "If the user asks about the connected database, ask a clarifying question or provide a safe next step. "
        "If the user asks for current info, mention the date you know ({today})."
    )

    SUM_SYSTEM = "Summarize the SQL result concisely for a business user. If empty, say so briefly."
    SUM_USER_TMPL = "Question: {question}\nSQL: {sql}\nRows (sample): {rows}"

    def __init__(
        self,
        model: str = "openai/gpt-oss-120b",
        temperature: float = 0.0,
        schema: str = "synkrino",
        # Behavior knobs
        system_prompt: str | None = None,
        answer_mode: str = "sql_and_brief_answer",   # or "sql_only"
        strict_readonly: bool = True,
        force_single_statement: bool = True,
        strip_trailing_semicolon: bool = True,
        auto_limit: bool = True,
        default_limit: int = 100,
        disallow_keywords: list[str] | None = None,
        ui_max_rows: int = 500,
        # NEW: hybrid controls
        mode: str = "auto",  # "auto" | "sql_only" | "chat_only"
        enable_search: bool = False,   # requires SERPAPI_KEY
        search_provider: str = "serpapi",
    ):
        self.groq = GroqREST(model=model, temperature=temperature)
        self.schema = schema
        self.answer_mode = answer_mode
        self.strict_readonly = strict_readonly
        self.force_single_statement = force_single_statement
        self.strip_trailing_semicolon = strip_trailing_semicolon
        self.auto_limit = auto_limit
        self.default_limit = int(default_limit)
        self.ui_max_rows = int(ui_max_rows)
        self.mode = mode
        self.enable_search = enable_search
        self.search_provider = search_provider

        # Disallow list
        self.disallow_keywords = {kw.upper() for kw in (disallow_keywords or [
            "INSERT","UPDATE","DELETE","TRUNCATE","DROP","ALTER","CREATE","GRANT","REVOKE"
        ])}
        self._disallow_re = re.compile(r"\b(" + "|".join(sorted(map(re.escape, self.disallow_keywords))) + r")\b", re.I)

        # System prompts
        tmpl = system_prompt or self.DEFAULT_SQL_SYSTEM
        self.sql_system_prompt = tmpl.format(default_limit=self.default_limit)
        self.general_system_prompt = self.GENERAL_SYSTEM.format(
            today=datetime.now(timezone.utc).date().isoformat()
        )

        # DB handles
        self.db = SQLDatabase.from_uri(build_db_uri(), schema=schema)
        self.engine = create_engine(build_db_uri(), pool_pre_ping=True)

    # ---------- Schema cache (disk) ----------
    @lru_cache(maxsize=1)
    def get_schema(self) -> str:
        key_src = f"{self.schema}::{build_db_uri()}"
        key = hashlib.sha256(key_src.encode()).hexdigest()
        path = os.path.join(SCHEMA_CACHE_DIR, f"{key}.txt")

        if os.path.exists(path) and (time.time() - os.path.getmtime(path) < SCHEMA_TTL_SEC):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()[:6000]

        raw = self.db.get_table_info()
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)
        return raw[:6000]

    # ---------- Intent routing ----------
    def classify_intent(self, question: str) -> str:
        q = question.strip().lower()

        # Fast heuristics
        if q.startswith("/sql ") or re.search(r"\b(select|from|join|where|group by|order by)\b", q):
            return "sql"
        if q.startswith("/search "):
            return "search"
        # Simple SQL-ish cues
        if "table" in q or "column" in q or "rows" in q:
            # let auto decide as SQL (can still fail validation and fall back)
            return "sql"

        # Optionally ask the LLM (very small prompt) — keeps it robust
        msgs = [
            {"role":"system","content":"Classify the user's intent as one token: SQL or CHAT or SEARCH."},
            {"role":"user","content":question}
        ]
        try:
            out = self.groq.chat(msgs, max_tokens=4).strip().upper()
            if "SQL" in out: return "sql"
            if "SEARCH" in out: return "search"
        except Exception:
            pass
        return "chat"

    # ---------- Web search (optional) ----------
    def web_search(self, query: str, num: int = 5) -> List[dict] | None:
        if not self.enable_search or self.search_provider != "serpapi":
            return None
        api_key = os.getenv("SERPAPI_KEY")
        if not api_key:
            return None
        try:
            r = requests.get(
                "https://serpapi.com/search.json",
                params={"engine":"google","q":query,"num":num,"api_key":api_key},
                timeout=12
            )
            r.raise_for_status()
            data = r.json()
            results = data.get("organic_results", [])[:num]
            return [{"title":x.get("title"), "snippet":x.get("snippet"), "link":x.get("link")} for x in results]
        except Exception:
            return None

    # ---------- LLM → SQL ----------
    def generate_sql(self, question: str) -> str:
        schema = self.get_schema()
        messages = [
            {"role": "system", "content": self.sql_system_prompt},
            {"role": "user", "content": self.SQL_USER_TMPL.format(schema=schema, question=question)},
        ]
        sql = self.groq.chat(messages, max_tokens=384).strip()
        sql = sql.replace("```sql", "").replace("```", "").strip()
        return self._validate_and_rewrite_sql(sql)

    def _validate_and_rewrite_sql(self, sql: str) -> str:
        s = (sql or "").strip()
        if self.strip_trailing_semicolon and s.endswith(";"):
            s = s[:-1].rstrip()
        if not re.match(r"^\s*(select|with)\b", s, re.I):
            raise ValueError("Only SELECT queries (or WITH … SELECT) are allowed.")
        if self.force_single_statement and ";" in s:
            raise ValueError("Semicolons / multiple statements are not allowed.")
        if self.strict_readonly and self._disallow_re.search(s):
            raise ValueError("Dangerous keyword detected; blocked.")
        if self.auto_limit and not self._has_limit(s):
            s = f"{s} LIMIT {self.default_limit}"
        return s

    def _has_limit(self, sql: str) -> bool:
        low = sql.lower()
        return bool(re.search(r"\blimit\s+\d+\b", low) or
                    re.search(r"\bfetch\s+first\s+\d+\s+rows?\s+only\b", low))

    # ---------- Execution ----------
    def run_sql_capped(self, sql: str, max_rows: int | None = None) -> Dict[str, Any]:
        cap = int(max_rows) if max_rows is not None else self.ui_max_rows
        wrapped = f"SELECT * FROM ({sql}) AS t LIMIT {cap + 1}"
        rows, truncated = [], False
        with self.engine.connect() as conn:
            res = conn.execute(text(wrapped))
            cols = list(res.keys())
            for i, r in enumerate(res):
                if i >= cap:
                    truncated = True
                    break
                rows.append({c: r[idx] for idx, c in enumerate(cols)})
        return {"rows": rows, "truncated": truncated, "wrapped_sql": wrapped}

    # ---------- CSV export ----------
    def export_full_csv(self, sql: str, out_dir: str = "exports") -> str:
        os.makedirs(out_dir, exist_ok=True)
        csv_path = os.path.join(out_dir, f"query_{uuid.uuid4().hex}.csv")
        with self.engine.connect() as conn, open(csv_path, "w", newline="", encoding="utf-8") as f:
            res = conn.execution_options(stream_results=True).execute(text(sql))
            writer, count = None, 0
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
                    if count > DOWNLOAD_MAX_ROWS:
                        break
                if count > DOWNLOAD_MAX_ROWS:
                    break
        return csv_path

    # ---------- General chat ----------
    def chat_general(self, question: str) -> str:
        msgs = [
            {"role":"system","content": self.general_system_prompt},
            {"role":"user","content": question}
        ]
        return self.groq.chat(msgs, max_tokens=512)

    def chat_with_search(self, question: str) -> str:
        context = self.web_search(question, num=5)
        if not context:
            return self.chat_general(question)
        bullets = "\n".join([f"- {x['title']}: {x.get('snippet','')}" for x in context if x.get("title")])
        msgs = [
            {"role":"system","content": self.general_system_prompt},
            {"role":"user","content": f"Question: {question}\nUse this context if helpful:\n{bullets}"}
        ]
        return self.groq.chat(msgs, max_tokens=512)

    # ---------- Summarization ----------
    def summarize(self, question: str, sql: str, rows_sample) -> str:
        sample = json.dumps(rows_sample, default=str)[:4000]
        messages = [
            {"role": "system", "content": self.SUM_SYSTEM},
            {"role": "user", "content": self.SUM_USER_TMPL.format(question=question, sql=sql, rows=sample)},
        ]
        return self.groq.chat(messages, max_tokens=384)

    # ---------- Public API ----------
    def answer(self, question: str) -> Dict[str, Any]:
        route = "sql" if self.mode == "sql_only" else "chat" if self.mode == "chat_only" else self.classify_intent(question)

        if route == "sql":
            sql = self.generate_sql(question)
            ui = self.run_sql_capped(sql)
            answer = sql if self.answer_mode == "sql_only" else self.summarize(question, sql, ui["rows"])
            return {
                "sql": sql,
                "rows": ui["rows"],
                "truncated": ui["truncated"],
                "wrapped_sql": ui["wrapped_sql"],
                "answer": answer
            }

        # chat / search branch
        content = self.chat_with_search(question) if route == "search" else self.chat_general(question)
        return {
            "sql": None,
            "rows": [],
            "truncated": False,
            "wrapped_sql": None,
            "answer": content
        }
