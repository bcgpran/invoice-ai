# chat_window.py

import streamlit as st
import logging
import os
import requests
import json
import re
from dotenv import load_dotenv
from sessions.session_manager import add_message

# --- Configuration & Initialization ---
load_dotenv()
logger = logging.getLogger(__name__)

API_ENDPOINT = st.secrets.get("API_ENDPOINT", os.environ.get("API_ENDPOINT"))
API_CODE = st.secrets.get("API_CODE", os.environ.get("API_CODE"))

# --- Helper Functions ---

def get_chat_response(user_query: str, conversation_history: list) -> dict:
    """Sends a request to the backend orchestrator and returns the full JSON response."""
    if not API_ENDPOINT:
        return {"error": "API_ENDPOINT not configured."}
    
    payload = {"query": user_query, "history": conversation_history}
    params = {"code": API_CODE} if API_CODE else {}
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(API_ENDPOINT, json=payload, params=params, headers=headers, timeout=120)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return {"error": f"Failed to connect to the agent: {e}"}

def process_and_fetch_downloads(response_text: str) -> tuple[str, dict]:
    """Parses agent's response for markdown links and fetches file data."""
    if not isinstance(response_text, str):
        return str(response_text), {}

    pattern = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')
    main_text = pattern.sub('', response_text).strip()
    
    fetched_downloads = {}
    matches = pattern.finditer(response_text)
    for match in matches:
        link_text = match.group(1)
        url = match.group(2)
        try:
            file_response = requests.get(url, timeout=60)
            file_response.raise_for_status()
            fetched_downloads[link_text] = {
                "data": file_response.content,
                "file_name": link_text,
            }
        except requests.exceptions.RequestException as e:
            st.error(f"Failed to download file '{link_text}': {e}")
            main_text += f"\n\n_(Error: Could not download file '{link_text}')_"
    return main_text, fetched_downloads

def execute_full_email_flow(session_id: str):
    """Sets the state to trigger the final email sending process."""
    st.session_state.sessions[session_id]["consent_flow_state"] = "sending_email"
    st.rerun()

# --- Main Render Function ---

def render(session_id: str):
    """Renders the main chat interface and handles the consent flow state machine."""
    
    st.markdown("""
        <style>
            div[style*="flex-direction: row-reverse"] > div[data-testid="stChatMessageContent"] {
                background-color: transparent !important;
            }
        </style>
        """, unsafe_allow_html=True)
    
    assistant_avatar = "assets/icon2.png"
    user_avatar = "assets/icon.png"
    sess = st.session_state.sessions.get(session_id, {})
    
    # 1. Display all existing chat messages
    for msg in sess.get("messages", []):
        avatar = assistant_avatar if msg["role"] == "assistant" else user_avatar
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(f'<span style="font-size: 18px;">{msg["content"]}</span>', unsafe_allow_html=True)
            if "downloads" in msg:
                for link_text, file_info in msg["downloads"].items():
                    st.download_button(
                        label=f"Download: {file_info['file_name']}",
                        data=file_info["data"],
                        file_name=file_info["file_name"],
                        mime="text/csv",
                        key=f"dl_{session_id}_{msg.get('id', file_info['file_name'])}"
                    )

    # --- Consent Flow State Machine ---
    consent_state = sess.get("consent_flow_state")

    if consent_state == "awaiting_confirmation":
        draft = sess.get("consent_draft", {})
        st.markdown("---")
        st.info("The agent has prepared this email draft. Please review:")

        # --- FIX: Convert `to_emails` object to string before rendering ---
        # The draft['to_emails'] is an object, not a simple string.
        # Directly rendering it causes the '[object Object]' error.
        # By converting it to a string with str(), we display its actual content.
        to_emails_display = str(draft.get("to_emails", "[Not Specified]"))
        
        st.markdown(f'**To:**')
        st.code(to_emails_display)

        subject_display = draft.get("subject", "[No Subject]")
        body_display = draft.get("body", "")

        st.markdown(f'**Subject:**')
        st.markdown(subject_display)

        st.text_area("Body:", value=body_display, height=150, disabled=True, key="draft_body")
        st.markdown("---")

        col1, col2 = st.columns(2)
        if col1.button("Looks Good, Proceed", use_container_width=True):
            add_message(session_id, "user", "Yes, that looks good. Please proceed.")
            execute_full_email_flow(session_id)

        if col2.button("Cancel", use_container_width=True, type="secondary"):
            st.session_state.sessions[session_id]["consent_flow_state"] = None
            add_message(session_id, "assistant", "Okay, I've cancelled the email request. How else can I help?")
            st.rerun()
    
    elif consent_state == "sending_email":
        with st.chat_message("assistant", avatar=assistant_avatar):
            with st.spinner("Generating file and sending email... This may open a browser tab for you to sign in. Please check your browser."):
                history_from_state = sess.get("history_for_consent", [])
                draft = sess.get("consent_draft", {})
                original_query = sess.get("original_query_for_consent", "the user's request")

                history_to_send = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in history_from_state
                    if msg.get("role") in ["user", "assistant"]
                ]

                # Convert draft['to_emails'] to a clean string for the prompt
                to_emails_prompt_str = str(draft.get('to_emails', ''))

                final_prompt = (
                    f"The user wants to send an email based on their original request: '{original_query}'. "
                    f"They have approved the following draft:\n"
                    f"To: {to_emails_prompt_str}\n"
                    f"Subject: {draft.get('subject')}\n"
                    f"Body: {draft.get('body')}\n"
                    f"Your task is to now execute this. First, use `export_sql_query_to_csv_tool` to create the necessary file. "
                    f"Then, use `send_email_with_attachments_tool` with the file URL and the exact draft details above."
                )
                
                response_data = get_chat_response(final_prompt, history_to_send)
                
                st.session_state.sessions[session_id]["consent_flow_state"] = None
                answer = response_data.get("answer", f"An error occurred: {response_data.get('error', 'Unknown issue')}")
                main_text, fetched_downloads = process_and_fetch_downloads(answer)
                add_message(session_id, "assistant", content=main_text, downloads=fetched_downloads)
                st.rerun()

    # 2. Handle new user input
    if prompt := st.chat_input("Ask about your invoices..."):
        add_message(session_id, "user", prompt)
        st.rerun()

    # 3. Generate a new response if the last message was from the user
    messages = sess.get("messages", [])
    if messages and messages[-1]["role"] == "user" and not consent_state:
        prompt = messages[-1]["content"]
        with st.chat_message("assistant", avatar=assistant_avatar):
            with st.spinner("Thinking..."):
                history_to_send = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in messages[:-1]
                    if msg.get("role") in ["user", "assistant"]
                ]
                
                response_data = get_chat_response(prompt, history_to_send)
                
                if response_data.get("error"):
                    add_message(session_id, "assistant", f"Error: {response_data['error']}")
                elif response_data.get("action_required") == "user_consent_email":
                    st.session_state.sessions[session_id]["consent_flow_state"] = "awaiting_confirmation"
                    st.session_state.sessions[session_id]["consent_draft"] = response_data["draft_details"]
                    st.session_state.sessions[session_id]["history_for_consent"] = response_data["history"]
                    st.session_state.sessions[session_id]["original_query_for_consent"] = response_data["original_query"]
                    add_message(session_id, "assistant", "I can help with that. I've prepared an email draft for your review.")
                else:
                    answer = response_data.get("answer", "Sorry, I encountered an issue.")
                    main_text, fetched_downloads = process_and_fetch_downloads(answer)
                    add_message(session_id, "assistant", content=main_text, downloads=fetched_downloads)
                
                st.rerun()