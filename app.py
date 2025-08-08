import streamlit as st
from groq_interface.groq_client import GroqClient

# --------------------------------------------------------------
# 1️⃣ Page config
# --------------------------------------------------------------
st.set_page_config(page_title="Grook", page_icon="💬", layout="centered")

# --------------------------------------------------------------
# 2️⃣ Sidebar
# --------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Chat Settings")
    model = st.selectbox(
        "Model",
        ["llama3-70b-8192", "llama3-8b-8192"],
        index=0,
    )
    temperature = st.slider("Temperature", 0.0, 1.5, 0.7, 0.1)
    sys_prompt = st.text_area("System Prompt", "You are a helpful assistant.", height=100)

    if st.button("🧹 Clear chat"):
        st.session_state.messages = [
            {"role": "assistant", "content": "Hi! I'm Grook. How can I help today?"}
        ]
        st.rerun()

    st.markdown("---")
    st.caption("How may I assist you?")

# --------------------------------------------------------------
# 3️⃣ Session state – message history
# --------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hi! I'm Grook. How can I help today?"}
    ]

# --------------------------------------------------------------
# 4️⃣ Groq client – single‑instance
# --------------------------------------------------------------
groq = GroqClient(model=model)   # <-- passes chosen model

# --------------------------------------------------------------
# 5️⃣ Helper – ask Groq
# --------------------------------------------------------------
def llm_reply(messages, temperature):
    """
    Pass the conversation to Groq and return the reply.

    Parameters
    ----------
    messages : list[dict]
        The full conversation (system + history).
    temperature : float
        Sampling temperature (currently unused in Groq, but kept for API symmetry).

    Returns
    -------
    str
        The assistant's reply text.
    """
    # We ignore `temperature` because Groq’s API does not expose it yet.
    # If you use an LLM that does support it, add `"temperature": temperature` to the payload.
    return groq.chat(messages)

# --------------------------------------------------------------
# 6️⃣ Render chat bubbles
# --------------------------------------------------------------
st.markdown("<h2 style='text-align:center;'>WELCOME TO SYNKRHINO</h2>", unsafe_allow_html=True)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "🧑"):
        st.markdown(msg["content"])

# --------------------------------------------------------------
# 7️⃣ Chat input
# --------------------------------------------------------------
user_input = st.chat_input("Type your message…")

if user_input:
    # 1️⃣ Store user message
    st.session_state.messages.append({"role": "user", "content": user_input})

    # 2️⃣ Show user message immediately
    with st.chat_message("user", avatar="🧑"):
        st.markdown(user_input)

    # 3️⃣ Build conversation for Groq
    convo = []
    if sys_prompt.strip():
        convo.append({"role": "system", "content": sys_prompt.strip()})
    convo.extend(st.session_state.messages)

    # 4️⃣ Ask Groq – spinner
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking…"):
            try:
                answer = llm_reply(convo, temperature)
            except Exception as exc:
                answer = f"⚠️ Error contacting Groq: {exc}"

        st.markdown(answer)

    # 5️⃣ Persist assistant reply
    st.session_state.messages.append({"role": "assistant", "content": answer})