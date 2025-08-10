# app.py
import json
import streamlit as st
from groq_interface.agent import SQLChatAgentREST

st.set_page_config(page_title="Groq + Postgres SQL Chat", page_icon="🤖", layout="centered", initial_sidebar_state="collapsed")

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    model = st.selectbox("Model", ["llama3-70b-8192", "llama3-8b-8192","llama-3.3-70b-versatile","openai/gpt-oss-120b","Claude 3.5 Sonnet","GPT‑4 Turbo"], 0)
    temperature = st.slider("Temperature", 0.0, 1.0, 0.0, 0.1)  # keep 0 for SQL accuracy
    schema = st.text_input("Schema", "synkrino")
    if st.button("🧹 Clear"):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": "Hi, I'm GROOK! Your Assistant in Data Engineering. What can I help you with?’)."
    }]

@st.cache_resource(show_spinner=False)
def get_agent(m, t, s):
    return SQLChatAgentREST(model=m, temperature=t, schema=s)

agent = get_agent(model, temperature, schema)

st.markdown("<h2 style='text-align:center;'>WELCOME TO SYNKRHINO</h2>", unsafe_allow_html=True)

for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar=("🤖" if m["role"]=="assistant" else "🧑")):
        st.markdown(m["content"])

question = st.chat_input("Please ask questions...")
if question:
    st.session_state.messages.append({"role":"user","content":question})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(question)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking…"):
            try:
                out = agent.answer(question)  # has sql, rows (capped), truncated flag
                st.markdown(out["answer"])

                with st.expander("ℹ️ SQL & Result"):
                    st.code(out["sql"], language="sql")
                    st.dataframe(out["rows"])  # shows up to UI_MAX_ROWS rows

                    if out["truncated"]:
                        st.warning(f"Showing first {len(out['rows'])} rows (truncated for UI).")
                        if st.button("⬇️ Download full results as CSV"):
                            try:
                                csv_path = agent.export_full_csv(out["sql"])
                                st.success(f"CSV ready: {csv_path}")
                                st.markdown(f"[Download CSV]({csv_path})")
                            except Exception as ex:
                                st.error(f"Export failed: {ex}")
            except Exception as e:
                err = f"⚠️ {e}"
                st.markdown(err)
                st.session_state.messages.append({"role":"assistant","content":err})
