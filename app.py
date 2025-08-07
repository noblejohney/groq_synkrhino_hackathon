import streamlit as st
from agent.chat_agent import SynkRhinoChatAgent

# Page configuration
st.set_page_config(page_title="SynkRhino AI Assistant", layout="wide")
st.title("🤖 SynkRhino + Groq AI - Data Quality Assistant")

# Initialize agent and history
if "agent" not in st.session_state:
    st.session_state.agent = SynkRhinoChatAgent()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Sidebar with help and debug toggle
with st.sidebar:
    st.markdown("## 💡 Examples")
    st.markdown("""
    - "Check nulls in customer table"
    - "Show failed validation results"
    - "Summarize row count mismatches"
    """)
    show_debug = st.checkbox("Show debug output", value=False)

# Input field
user_input = st.text_input("🗨️ Ask your data quality question:")

# Process user input
if user_input:
    with st.spinner("Groq AI is thinking..."):
        try:
            response = st.session_state.agent.process(user_input)
            st.session_state.chat_history.append(("🧑 You", user_input))
            st.session_state.chat_history.append(("🤖 SynkRhino", response))
        except Exception as e:
            response = f"⚠️ Error: {str(e)}"
            st.session_state.chat_history.append(("🤖 SynkRhino", response))

# Display chat history
st.markdown("### 📜 Conversation")
for speaker, msg in st.session_state.chat_history:
    st.markdown(f"**{speaker}:** {msg}")

# Debug output (optional)
if show_debug:
    st.markdown("### 🛠️ Debug Info")
    st.json({
        "session_state": dict(st.session_state)
    })
