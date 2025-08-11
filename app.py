import os
import json
import uuid
import streamlit as st
from groq_interface.agent import SQLChatAgentREST  # import your class

st.set_page_config(
    page_title="GROOK-SynkRhino Assistant",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
)

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --------------------------- Sidebar ---------------------------
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    model = st.selectbox(
        "Model",
        [
            "llama3-70b-8192",
            "llama3-8b-8192",
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
            "Claude 3.5 Sonnet",
            "GPT-4 Turbo",
        ],
        index=0,
    )
    temperature = st.slider("Temperature", 0.0, 1.0, 0.0, 0.1)  # keep low for SQL accuracy
    schema = st.text_input("Schema", "synkrino")

    st.markdown("---")
    st.markdown("#### 🤖 Agent behavior")

    # Default SQL system prompt (supports {default_limit} formatting)
    default_system = (
        "You write ONLY PostgreSQL SELECT queries for read-only analytics. "
        "Return ONLY the SQL, with no code fences or commentary. Single statement; no semicolons; "
        "no INSERT/UPDATE/DELETE/TRUNCATE/DROP/ALTER/CREATE/GRANT/REVOKE. Add LIMIT {default_limit} if not specified."
    )
    system_prompt = st.text_area("System prompt (SQL mode)", value=default_system, height=140)

    answer_mode = st.selectbox(
        "Answer mode",
        ["sql_and_brief_answer", "sql_only"],
        index=0,
        help="sql_only returns the SQL as the chat answer; otherwise a short summary is generated from results.",
    )

    mode = st.selectbox(
        "Assistant mode",
        ["auto", "sql_only", "chat_only"],
        index=0,
        help="auto routes between SQL or general chat based on the question.",
    )

    col1, col2 = st.columns(2)
    with col1:
        strict_readonly = st.checkbox("Strict read-only (block DDL/DML)", True)
        force_single_statement = st.checkbox("Force single SELECT", True)
        strip_semicolon = st.checkbox("Strip trailing semicolon", True)
    with col2:
        auto_limit = st.checkbox("Auto-append LIMIT", True)
        default_limit = st.number_input("Default LIMIT", 1, 10000, 100, step=50)
        ui_max_rows = st.number_input(
            "UI max rows",
            10,
            10000,
            500,
            step=50,
            help="Max rows to show in the preview table. Full CSV export is separate.",
        )

    disallowed = st.text_input(
        "Disallowed keywords (comma-separated)",
        "INSERT,UPDATE,DELETE,TRUNCATE,DROP,ALTER,CREATE,GRANT,REVOKE",
        help="Blocked anywhere in the query when Strict read-only is on.",
    )
    enable_search = st.toggle(
        "Enable web search for real-world facts (SerpAPI)",
        value=False,
        help="Requires SERPAPI_KEY in environment.",
    )

    if st.button("🧹 Clear chat"):
        st.session_state.messages = []
        st.rerun()

# --------------------------- Agent factory ---------------------------
behavior = {
    "system_prompt": system_prompt.replace("{default_limit}", str(default_limit)),
    "answer_mode": answer_mode,
    "strict_readonly": bool(strict_readonly),
    "force_single_statement": bool(force_single_statement),
    "strip_trailing_semicolon": bool(strip_semicolon),
    "auto_limit": bool(auto_limit),
    "default_limit": int(default_limit),
    "disallow_keywords": [kw.strip().upper() for kw in disallowed.split(",") if kw.strip()],
    "ui_max_rows": int(ui_max_rows),
    "mode": mode,
    "enable_search": bool(enable_search),
    "search_provider": "serpapi",
}
behavior_key = json.dumps(behavior, sort_keys=True)

@st.cache_resource(show_spinner=False)
def get_agent(m, t, s, behavior_json):
    cfg = json.loads(behavior_json)
    return SQLChatAgentREST(
        model=m,
        temperature=t,
        schema=s,
        system_prompt=cfg["system_prompt"],
        answer_mode=cfg["answer_mode"],
        strict_readonly=cfg["strict_readonly"],
        force_single_statement=cfg["force_single_statement"],
        strip_trailing_semicolon=cfg["strip_trailing_semicolon"],
        auto_limit=cfg["auto_limit"],
        default_limit=cfg["default_limit"],
        disallow_keywords=cfg["disallow_keywords"],
        ui_max_rows=cfg["ui_max_rows"],
        mode=cfg["mode"],
        enable_search=cfg["enable_search"],
        search_provider=cfg["search_provider"],
    )

agent = get_agent(model, temperature, schema, behavior_key)

# --------------------------- Chat UI ---------------------------
st.markdown("<h2 style='text-align:center;'>WELCOME TO SYNKRHINO</h2>", unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": "Hi, I'm GROOK! Your hybrid assistant for data engineering and quick help. Ask me anything.",
    }]

# Render history
for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar=("🤖" if m["role"] == "assistant" else "🧑")):
        st.markdown(m["content"])

# ---- Chat input with PAPERCLIP upload (with safe fallback) ----
submission = None
try:
    # Newer Streamlit builds may support file attachments on chat_input
    submission = st.chat_input(
        "Type a message or attach files…",
        accept_file="multiple",                      # "multiple" | True (single)
        file_type=["csv", "xlsx", "json", "pdf"]     # optional filter
    )
except TypeError:
    # Fallback for older Streamlit: separate uploader + chat box
    colq, colu = st.columns([3, 2])
    with colq:
        question_fallback = st.chat_input("Type your question (SQL or general)…")
    with colu:
        uploads_fallback = st.file_uploader("📎 Attach files", type=["csv", "xlsx", "json", "pdf"],
                                            accept_multiple_files=True)
    if question_fallback or uploads_fallback:
        submission = {"text": question_fallback or "", "files": uploads_fallback or []}

if submission:
    # Normalize input
    if isinstance(submission, str):
        text, files = submission, []
    else:
        text = submission.get("text", "")
        files = submission.get("files", [])

    # Show the user message
    if text:
        st.session_state.messages.append({"role": "user", "content": text})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(text)

    # Handle attachments: display + save to disk
    saved_paths = []
    for f in files:
        with st.chat_message("user", avatar="🧑"):
            st.write(f"📎 {f.name} ({f.type}, {f.size} bytes)")
        # Save uniquely
        raw = f.getvalue()
        unique_name = f"{uuid.uuid4().hex}_{os.path.basename(f.name)}"
        save_path = os.path.join(UPLOAD_DIR, unique_name)
        with open(save_path, "wb") as out:
            out.write(raw)
        saved_paths.append(save_path)

    # === Call your agent only with text; you can later route saved_paths to your APIs ===
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking…"):
            try:
                # If nothing typed but files uploaded, pass a default message
                prompt = text or (f"Uploaded {len(saved_paths)} file(s): " + ", ".join(os.path.basename(p) for p in saved_paths))
                out = agent.answer(prompt)  # -> {sql, rows, truncated, wrapped_sql, answer}
                st.markdown(out.get("answer") or "")

                # SQL details (only if this was a SQL route)
                if out.get("sql"):
                    with st.expander("ℹ️ SQL & Result"):
                        st.code(out["sql"], language="sql")
                        rows = out.get("rows", [])
                        st.dataframe(rows, use_container_width=True)

                        if out.get("truncated"):
                            st.warning(f"Showing first {behavior['ui_max_rows']} rows (preview capped).")

                        # Download full results
                        if st.button("⬇️ Export full results as CSV"):
                            try:
                                csv_path = agent.export_full_csv(out["sql"])
                                with open(csv_path, "rb") as fh:
                                    st.download_button(
                                        "Download CSV",
                                        fh,
                                        file_name=os.path.basename(csv_path),
                                        mime="text/csv",
                                    )
                            except Exception as ex:
                                st.error(f"Export failed: {ex}")

                # Save assistant message to history
                st.session_state.messages.append({"role": "assistant", "content": out.get("answer") or ""})

            except Exception as e:
                err = f"⚠️ {e}"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})

    # Optional: show where files were saved (helpful in demo)
    if saved_paths:
        with st.expander("📂 Saved attachments"):
            for p in saved_paths:
                st.write(p)
