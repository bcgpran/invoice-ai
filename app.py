# app.py

import streamlit as st
import logging
import base64
from pathlib import Path

from sessions.session_manager import init, get_current_session, create_session
from components.sidebar import render as render_sidebar
from components.chat_window import render as render_chat

from htbuilder import HtmlElement, div, p, img, styles, a
from htbuilder.units import percent, px

# --- Basic Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# NOTE: The helper functions below are identical to your first app.
# You can copy them directly. They are included here for completeness.

@st.cache_data
def get_base64(file_path: Path) -> str:
    """Reads a binary file and returns its Base64 encoded string."""
    with open(file_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

def apply_ui_enhancements(image_file: Path):
    """Applies custom CSS for the modern UI."""
    if not image_file.exists():
        st.warning(f"Background image not found. Expected at: {image_file}")
        return
    image_ext = image_file.suffix.strip('.')
    encoded_image = get_base64(image_file)
    page_style_css = f'''
    <style>
    .stApp {{
        background-image: url("data:image/{image_ext};base64,{encoded_image}");
        background-size: cover; background-attachment: fixed;
    }}
    [data-testid="stBlockContainer"] {{
        background-color: rgba(255, 255, 255, 0.9); border-radius: 15px;
        padding: 2rem 3rem; margin-top: 3rem; backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.2);
        padding-bottom: 5rem;
    }}
    /* This style applies to st.header now */
    h1 {{ color: #0d2a4b; text-align: center; padding-bottom: 1rem; }}
    [data-testid="stHeader"] {{ background: none !important; }}
    .stMarkdown, p, li {{ color: #1a3a5d; }}
    [data-testid="stSidebarHeader"] {{ position: sticky; top: 0; z-index: 100; background-color: transparent; }}
    </style>
    '''
    st.markdown(page_style_css, unsafe_allow_html=True)

def image(src_as_string, **style): return img(src=src_as_string, style=styles(**style))
def link(link, text, **style): return a(_href=link, _target="_blank", style=styles(**style))(text)
def layout(*args):
    style = """<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} .stApp { bottom: 40px; }</style>"""
    style_div = styles(position="fixed", left=0, bottom=0, margin=px(0, 0, 0, 0), width=percent(100), text_align="center", height="auto", opacity=1, background_color="rgba(255, 255, 255, 0.85)", backdrop_filter="blur(10px)", color="#0d2a4b", font_style="italic", padding="5px 10px")
    body = p(style=styles(margin="0")); foot = div(style=style_div)(body)
    st.markdown(style, unsafe_allow_html=True)
    for arg in args:
        if isinstance(arg, str): body(arg)
        elif isinstance(arg, HtmlElement): body(arg)
    st.markdown(str(foot), unsafe_allow_html=True)

def render_disclaimer_footer():
    """Renders the disclaimer footer."""
    myargs = ["Disclaimer: This AI assistant is an MVP. Please verify critical information."]
    layout(*myargs)

# --- Main Application ----
def main():
    st.set_page_config(page_title="Invoice AI Chat", layout="wide", initial_sidebar_state="expanded")

    script_dir = Path(__file__).parent
    background_image_path = script_dir / "assets" / "background.jpg"
    apply_ui_enhancements(background_image_path)

    init()
    session_id = get_current_session()
    if not session_id:
        session_id = create_session()

    # CHANGE: Replaced st.title with st.header and removed emojis for a smaller, cleaner look.
    st.header("Invoice AI Chat Assistant")

    # Render main components
    render_sidebar()
    render_chat(session_id)
    render_disclaimer_footer()

if __name__ == "__main__":
    main()