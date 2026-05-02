import sys
import os

sys.path.append(os.path.abspath("."))

import streamlit as st
import base64
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.main import invoke as agent_invoke   # ✅ FIXED IMPORT

# ---- Async runner ----
_executor = ThreadPoolExecutor(max_workers=1)

def run_async(coro):
    future = _executor.submit(lambda: asyncio.run(coro))
    return future.result()

# ---- Session state ----
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "chat" not in st.session_state:
    st.session_state.chat = []

st.set_page_config(page_title="NovAtel AI", layout="wide")
st.title("NovAtel AI Assistant")

# ---- File upload ----
uploaded_file = st.file_uploader(
    "Upload log file",
    type=["log", "txt", "asc", "csv", "json", "gps", "gpf","ASCII","ABBREV_ASCII"]
)

if uploaded_file:
    file_bytes = uploaded_file.read()
    file_b64 = base64.b64encode(file_bytes).decode()

    response = run_async(agent_invoke({
        "type": "upload",
        "filename": uploaded_file.name,
        "file": file_b64,
        "session_id": st.session_state.session_id
    }))

    st.success("File uploaded!")
    st.write(response.get("reply", ""))   # ✅ INSIDE block

# ---- Chat UI ----
user_input = st.chat_input("Ask something...")

if user_input:
    st.session_state.chat.append(("user", user_input))

    response = run_async(agent_invoke({
        "type": "chat",
        "prompt": user_input,   # ✅ FIXED (was "message")
        "session_id": st.session_state.session_id
    }))

    reply = response.get("reply", "")
    st.session_state.chat.append(("agent", reply))

# ---- Display chat ----
for role, msg in st.session_state.chat:
    with st.chat_message(role):
        st.write(msg)