import streamlit as st
from pathlib import Path
import logging

from utils.azure_uploader import upload_files_to_blob
from sessions.session_manager import (
    list_sessions, 
    get_current_session, 
    create_session, 
    delete_session, 
    rename_session
)

logger = logging.getLogger(__name__)

def _apply_sidebar_style(
    bg_color: str = "#092B26", 
    text_color: str = "#D8DEE9",
    input_text_color: str = "#0C0C0C"
):
    """
    Applies custom CSS for a fixed sidebar, including a larger logo.
    """
    st.markdown(
        f"""
        <style>
        /* --- Core Sidebar Layout for Fixed Position --- */
        section[data-testid="stSidebar"] {{
            height: 100vh !important;
            background-color: {bg_color} !important;
            display: flex;
            flex-direction: column;
        }}

        [data-testid="stSidebarHeader"] {{
            background-color: {bg_color} !important;
        }}

        /* --- CHANGE: Make the logo bigger --- */
        [data-testid="stSidebarHeader"] img {{
            max-height: 80px !important; /* Adjust this value as needed */
            height: auto !important;
            width: auto !important;
            margin: 1rem 0; /* Adds some vertical space around the logo */
        }}

        /* --- NEW: Style for the logo in the COLLAPSED sidebar --- */
        /* This keeps the logo large and centered when the sidebar is collapsed. */
        section[data-testid="stSidebar"][aria-collapsed="true"] [data-testid="stSidebarHeader"] {{
            /* Allow the oversized logo to be visible */
            overflow: visible;
        }}

        section[data-testid="stSidebar"][aria-collapsed="true"] [data-testid="stSidebarHeader"] img {{
            /* Define a fixed, large size for the collapsed logo */
            width: 60px !important;
            height: 60px !important;
            margin: 1rem 0; /* Maintain vertical spacing */
            object-fit: contain; /* Ensure image scales well */
            
            /* 
            Center the oversized logo.
            The collapsed sidebar is 2.5rem (~40px) wide.
            Our logo is 60px wide.
            To center it, we shift it left by half the difference: (60px - 40px) / 2 = 10px.
            */
            transform: translateX(-10px);
        }}


        [data-testid="stSidebarContent"] {{
            flex-grow: 1; 
            overflow-y: auto; 
            overflow-x: hidden;
        }}

        /* --- NEW: Enhance Expander Visibility --- */
        /* Target the expander container to make the border more visible */
        section[data-testid="stSidebar"] [data-testid="stExpander"] {{
            border: 1px solid #8892B0 !important; /* A more visible border color */
            border-radius: 0.5rem; /* Add rounded corners for a modern look */
        }}

        /* Target the expander's arrow (chevron icon) to make it more visible */
        section[data-testid="stSidebar"] [data-testid="stExpander"] summary svg {{
            fill: {text_color} !important;
        }}
        /* --- End of New Styles --- */


        /* --- General Text & Widget Styling --- */
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] .st-emotion-cache-1g8w3tj, 
        section[data-testid="stSidebar"] label[data-baseweb="checkbox"] {{
            color: {text_color} !important;
        }}

        /* Selectbox */
        section[data-testid="stSidebar"] div[data-baseweb="select"] > div:first-child {{
            background-color: white !important;
            border: 1px solid #E0E0E0 !important;
        }}
        section[data-testid="stSidebar"] div[data-baseweb="select"] span {{ color: {input_text_color} !important; }}
        section[data-testid="stSidebar"] div[data-baseweb="select"] svg {{ fill: {input_text_color} !important; }}
        
        /* Text Input */
        section[data-testid="stSidebar"] div[data-baseweb="input"] > input {{
            background-color: white !important;
            color: {input_text_color} !important;
            border: 1px solid #E0E0E0 !important;
        }}
        
        /* Buttons */
        section[data-testid="stSidebar"] button {{
            background-color: white !important;
            border: 1px solid #E0E0E0 !important;
        }}
        section[data-testid="stSidebar"] button p {{
            color: {input_text_color} !important;
        }}
        section[data-testid="stSidebar"] button svg {{
            fill: {input_text_color} !important;
        }}
        
        /* File Uploader */
        section[data-testid="stSidebar"] div[data-testid="stFileUploaderDropzone"] {{
            background-color: white !important;
            border: 1px dashed #E0E0E0 !important;
        }}
        section[data-testid="stSidebar"] div[data-testid="stFileUploaderDropzone"] * {{ color: #999999 !important; }}
        section[data-testid="stSidebar"] div[data-testid="stFileUploaderDropzone"] button {{
             background-color: #F0F2F6 !important;
             color: {input_text_color} !important;
             border: 1px solid #E0E0E0 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

def get_session_generated_files(session_id: str) -> list[dict]:
    """
    Scans the message history of a given session and collects all generated files.
    """
    if not session_id or session_id not in st.session_state.sessions:
        return []

    all_files = []
    seen_filenames = set()
    for msg in reversed(st.session_state.sessions[session_id].get("messages", [])):
        if "downloads" in msg and msg["downloads"]:
            for link_text, file_info in msg["downloads"].items():
                if file_info["file_name"] not in seen_filenames:
                    all_files.append(file_info)
                    seen_filenames.add(file_info["file_name"])
    return all_files

def render_session_manager():
    """Renders the UI for chat session management."""
    all_sessions = list_sessions()
    session_dict = dict(all_sessions)
    session_ids = [s[0] for s in all_sessions]
    current_session_id = get_current_session()
    
    if current_session_id not in session_ids:
        current_session_id = session_ids[0] if session_ids else None
    
    selected_session = st.selectbox(
        "Select a Chat",
        options=session_ids,
        format_func=lambda sid: session_dict.get(sid, "Unknown Chat"),
        index=session_ids.index(current_session_id) if current_session_id in session_ids else 0,
        key="session_selector"
    )
    
    if selected_session and selected_session != current_session_id:
        st.session_state.current_session = selected_session
        st.rerun()

    col1, col2 = st.columns(2)
    if col1.button("➕ New Chat", use_container_width=True):
        create_session()
        st.rerun()

    if col2.button("🗑️ Delete Chat", use_container_width=True, type="secondary"):
        if current_session_id:
            delete_session(current_session_id)
            st.rerun()
            
    with st.expander("Rename Current Chat"):
        new_name = st.text_input(
            "New name", 
            placeholder=session_dict.get(current_session_id, ""), 
            label_visibility="collapsed"
        )
        if st.button("Rename", key="rename_button", use_container_width=True):
            if new_name and current_session_id:
                rename_session(current_session_id, new_name)
                st.rerun()

def render():
    """Renders the entire sidebar with a fixed position and internal scrolling."""
    _apply_sidebar_style()

    script_dir = Path(__file__).parent.parent
    
    # --- IMPORTANT: Make sure this path points to your new "BCG X" logo file. ---
    logo_path = script_dir / "assets" / "logo.png"

    if logo_path.exists():
        st.logo(str(logo_path))

    with st.sidebar:
        # --- Expander 1: Chat Sessions ---
        with st.expander("Chat Sessions", expanded=True):
            render_session_manager()

        # --- Expander 2: Generated Files ---
        with st.expander("Generated Files", expanded=True):
            current_session_id = get_current_session()
            generated_files = get_session_generated_files(current_session_id)

            if not generated_files:
                st.caption("No files have been generated in this session yet.")
            else:
                for i, file_info in enumerate(generated_files):
                    st.download_button(
                        label=f"📄 {file_info['file_name']}",
                        data=file_info['data'],
                        file_name=file_info['file_name'],
                        mime="text/csv",
                        use_container_width=True,
                        key=f"sidebar_dl_{current_session_id}_{i}"
                    )

        # --- Expander 3: Data Upload Center ---
        with st.expander("Data Upload Center", expanded=False):
            if st.session_state.get("upload_status"):
                status = st.session_state.upload_status
                if status["type"] == "success": st.success(status["message"])
                else: st.error(status["message"])
                st.session_state.upload_status = None

            if "invoice_key" not in st.session_state: st.session_state.invoice_key = 0
            if "po_key" not in st.session_state: st.session_state.po_key = 0
            if "contract_key" not in st.session_state: st.session_state.contract_key = 0
            
            st.subheader("📄 Invoices")
            invoices_uploader = st.file_uploader(
                "Upload to `invoices/incoming/`", type=["pdf", "xml", "jpg", "png", "jpeg"],
                accept_multiple_files=True, key=f"invoices_uploader_{st.session_state.invoice_key}",
                label_visibility="collapsed"
            )
            if invoices_uploader:
                with st.spinner(f"Uploading {len(invoices_uploader)} file(s)..."):
                    uploaded, error = upload_files_to_blob(invoices_uploader, "invoices", "incoming")
                if error: st.session_state.upload_status = {"type": "error", "message": error}
                else: st.session_state.upload_status = {"type": "success", "message": f"Uploaded {len(uploaded)} invoice(s)."}
                st.session_state.invoice_key += 1
                st.rerun()

            st.markdown("---")

            st.subheader("📈 Purchase Orders")
            po_uploader = st.file_uploader(
                "Upload to `invoices/master/`", type=["csv", "xlsx"],
                accept_multiple_files=True, key=f"po_uploader_{st.session_state.po_key}",
                label_visibility="collapsed"
            )
            if po_uploader:
                with st.spinner(f"Uploading {len(po_uploader)} file(s)..."):
                    uploaded, error = upload_files_to_blob(po_uploader, "invoices", "master")
                if error: st.session_state.upload_status = {"type": "error", "message": error}
                else: st.session_state.upload_status = {"type": "success", "message": f"Uploaded {len(uploaded)} PO file(s)."}
                st.session_state.po_key += 1
                st.rerun()

            st.markdown("---")

            st.subheader("✍️ Contracts")
            contracts_uploader = st.file_uploader(
                "Upload to `invoices/contracts/`", type=["pdf", "docx"],
                accept_multiple_files=True, key=f"contracts_uploader_{st.session_state.contract_key}",
                label_visibility="collapsed"
            )
            if contracts_uploader:
                with st.spinner(f"Uploading {len(contracts_uploader)} file(s)..."):
                    uploaded, error = upload_files_to_blob(contracts_uploader, "invoices", "contracts")
                if error: st.session_state.upload_status = {"type": "error", "message": error}
                else: st.session_state.upload_status = {"type": "success", "message": f"Uploaded {len(uploaded)} contract(s)."}
                st.session_state.contract_key += 1
                st.rerun()