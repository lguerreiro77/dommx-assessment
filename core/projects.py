import streamlit as st
from storage.project_storage import (
    get_projects,
    create_project,
    update_project,
    delete_project
)


@st.dialog("Manage Projects", width="medium")
def render_project_selection():
    user = st.session_state._temp_user
    user_id = user["email_hash"]

    all_projects = get_all_projects()
    user_projects = get_projects_for_user(user_id) or []
    active_projects = [p for p in all_projects if p.get("is_active", True)]
    project_map = {p["project_id"]: p["name"] for p in active_projects}

    left, center, right = st.columns([1, 3, 1])

    with center:
        st.markdown(
            f"""
            <h3 style='text-align:center; margin-bottom:10px;'>
                {APP_TITLE}
            </h3>
            """,
            unsafe_allow_html=True,
        )

        st.subheader("Select Project")

        if not active_projects:
            st.warning("No active projects available.")
            if st.button("Back to Login", use_container_width=True):
                st.session_state.app_mode = "login"
                st.session_state.pop("_temp_user", None)
                st.rerun()
            return

        selected_project = st.selectbox(
            "Project",
            options=list(project_map.keys()),
            format_func=lambda x: project_map.get(x, x),
            key="select_project_id",
        )

        selected_project_obj = next(
            (p for p in active_projects if p["project_id"] == selected_project),
            {}
        )

        allow_open = selected_project_obj.get("allow_open_access", False)
        has_access = selected_project in user_projects

        col_enter, col_request = st.columns(2)

        with col_enter:
            if st.button(
                "Enter",
                use_container_width=True,
                disabled=not (has_access or allow_open),
            ):
                st.session_state.user_id = user_id
                st.session_state.active_project = selected_project
                st.session_state.is_admin = (user.get("email") in ADMINS)
                st.session_state.app_mode = "app"
                st.session_state.pop("_temp_user", None)
                st.rerun()

        with col_request:
            if not has_access and not allow_open:
                if st.button("Request Access", use_container_width=True):
                    admin_email = get_env("SMTP_USER")
                    if admin_email:
                        send_email(
                            to=admin_email,
                            subject="Project Access Request",
                            body=f"""User: {user.get('email', '')}
Requested Project: {project_map.get(selected_project, selected_project)}
""",
                        )
                        st.session_state.app_mode = "login"
                        st.session_state.pop("_temp_user", None)
                        st.rerun()
            
