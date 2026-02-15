import streamlit as st
from storage.project_storage import get_projects, create_project


def render_projects_modal():

    if "_flash" in st.session_state:
        level = st.session_state._flash.get("level", "info")
        msg = st.session_state._flash.get("msg", "")
        if level == "success":
            st.success(msg)
        elif level == "error":
            st.error(msg)
        else:
            st.info(msg)
        del st.session_state._flash

    projects = get_projects()

    # ---------------- CREATE ----------------
    st.markdown("### Create New Project")

    new_name = st.text_input("Project Name", key="new_project_name")
    open_flag = st.checkbox(
        "Allow open access (users can login without association)",
        key="new_project_open"
    )

    if st.button("Create", key="create_project_btn"):
        if new_name:
            existing = [p["name"].strip().lower() for p in projects]

            if new_name.strip().lower() in existing:
                st.session_state._flash = {
                    "msg": "Project name already exists.",
                    "level": "error"
                }
            else:
                create_project(
                    new_name.strip(),
                    st.session_state.user_id,
                    open_flag
                )
                st.session_state._flash = {
                    "msg": "Project created successfully.",
                    "level": "success"
                }

            st.session_state.open_dialog = "projects"
            st.rerun()

    st.divider()

    if st.button("👥 Associate Users", use_container_width=True, key="btn_associate_users"):
        st.session_state.open_dialog = "associate"
        st.rerun()

    # ---------------- LIST ----------------
    st.markdown("### Existing Projects")

    if not projects:
        st.info("No projects available.")
        return

    for p in projects:
        st.markdown(f"• {p.get('name')}")
