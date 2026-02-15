import streamlit as st
from storage.project_storage import (
    get_projects,
    create_project,
    update_project,
    delete_project,
)

@st.dialog("Manage Projects", width="Medium")
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

            st.success(st.session_state._flash["msg"])
            del st.session_state._flash
            
            projects = get_projects()


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
        with st.expander(f"{p.get('name')}"):

            new_project_name = st.text_input(
                "Edit Name",
                value=p.get("name"),
                key=f"edit_name_{p.get('project_id')}"
            )

            is_active = st.checkbox(
                "Active",
                value=p.get("is_active", True),
                key=f"active_{p.get('project_id')}"
            )

            allow_open = st.checkbox(
                "Allow open access",
                value=p.get("allow_open_access", False),
                key=f"open_{p.get('project_id')}"
            )

            col1, col2 = st.columns(2)

            with col1:
                if st.button("Update", key=f"update_{p.get('project_id')}"):
                    update_project(
                        p.get("project_id"),
                        new_project_name.strip(),
                        is_active,
                        allow_open
                    )
                    st.session_state._flash = {
                        "msg": "Project updated successfully.",
                        "level": "success"
                    }
                    st.success("Project updated successfully.")
                    projects = get_projects()


            with col2:
                if st.button("Delete", key=f"delete_{p.get('project_id')}"):
                    delete_project(p.get("project_id"))
                    st.session_state._flash = {
                        "msg": "Project deleted.",
                        "level": "success"
                    }                    
                    st.success("Project deleted.")
                    projects = get_projects()
