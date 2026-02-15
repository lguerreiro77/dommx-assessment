import streamlit as st
from storage.project_storage import (
    get_projects,
    create_project,
    update_project,
    delete_project
)


@st.dialog("Manage Projects", width="medium")
def render_projects_modal():

    projects = get_projects()

    # ---------------- CREATE ----------------
    st.markdown("### Create New Project")

    new_name = st.text_input("Project Name", key="new_project_name")

    if st.button("Create", key="create_project_btn"):
        if new_name:
            create_project(new_name, st.session_state.user_id)
            st.success("Project created successfully.")
            st.rerun()

    st.divider()

    if st.button("👥 Associate Users", use_container_width=True, key="btn_associate_users"):
        st.session_state.open_dialog = "associate"
        st.rerun()


    # ---------------- LIST ----------------
    st.markdown("### Existing Projects")

    for p in projects:

        with st.expander(p["name"]):

            name_edit = st.text_input(
                "Name",
                value=p["name"],
                key=f"name_{p['project_id']}"
            )

            active_edit = st.checkbox(
                "Active",
                value=p["is_active"],
                key=f"active_{p['project_id']}"
            )

            col1, col2 = st.columns(2)

            with col1:
                if st.button("Update", key=f"update_{p['project_id']}"):
                    update_project(
                        p["project_id"],
                        name_edit,
                        active_edit
                    )
                    st.success("Project updated.")
                    st.rerun()

            with col2:
                if st.button("Delete", key=f"delete_{p['project_id']}"):
                    delete_project(p["project_id"])
                    st.warning("Project deleted.")
                    st.rerun()
                    
    if st.button("Close", use_container_width=True):
        st.rerun()
            
