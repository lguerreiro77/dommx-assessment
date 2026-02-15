import streamlit as st

def init_session():
    defaults = {
        "user_id": None,
        "answers": {},
        "last_saved_snapshot": {},
        "just_saved": False,
        "intro_seen": False,
        "domain_intro_seen": False,
        "dom_idx": 0,
        "q_idx": 0,
    }

    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
            
    if "app_mode" not in st.session_state:
        st.session_state.app_mode = "login"
