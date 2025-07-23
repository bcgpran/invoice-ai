# sessions/session_manager.py

import streamlit as st
import uuid

# --- (init, list_sessions, create_session, delete_session, rename_session, get_current_session are unchanged) ---
def init():
    """Initializes the session state. Creates a default session if none exist."""
    if "sessions" not in st.session_state:
        st.session_state.sessions = {}
    
    if "current_session" not in st.session_state:
        st.session_state.current_session = ""

    # If there are no sessions at all, create one to start
    if not st.session_state.sessions:
        create_session(name="Chat 1")

def list_sessions() -> list[tuple[str, str]]:
    """Returns a list of all existing sessions as (id, name) tuples."""
    # Return in reverse order so newest sessions are at the top
    return sorted(
        [(sid, data["name"]) for sid, data in st.session_state.sessions.items()],
        key=lambda item: st.session_state.sessions[item[0]].get("created_at", 0),
        reverse=True
    )

def create_session(name: str = None) -> str:
    """Creates a new chat session with a unique ID and sets it as current."""
    session_id = str(uuid.uuid4())[:8]
    if not name:
        name = f"Chat {len(st.session_state.sessions) + 1}"
    
    st.session_state.sessions[session_id] = {
        "name": name,
        "messages": [{"role": "assistant", "content": "Hello! How can I help you with your invoices today?"}],
        "created_at": uuid.uuid4().int # For sorting
    }
    
    st.session_state.current_session = session_id
    return session_id

def delete_session(session_id: str):
    """Deletes a session and switches to another one."""
    if session_id in st.session_state.sessions:
        del st.session_state.sessions[session_id]
        
        # Switch to another session if one exists, otherwise create a new one
        remaining_sessions = list_sessions()
        if remaining_sessions:
            st.session_state.current_session = remaining_sessions[0][0]
        else:
            create_session(name="Chat 1")

def rename_session(session_id: str, new_name: str):
    """Renames a specific session."""
    if session_id in st.session_state.sessions and new_name:
        st.session_state.sessions[session_id]["name"] = new_name

def get_current_session() -> str:
    """Safely retrieves the current session ID."""
    return st.session_state.get("current_session", "")

# [MODIFIED] - The add_message function now accepts an optional 'downloads' dictionary.
def add_message(session_id: str, role: str, content: str, downloads: dict = None):
    """Adds a message to a session's chat history, including any downloadables."""
    if session_id in st.session_state.sessions:
        message = {"role": role, "content": content}
        if downloads:
            message["downloads"] = downloads
        
        st.session_state.sessions[session_id]["messages"].append(message)