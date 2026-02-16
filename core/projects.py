import streamlit as st
from storage.project_storage import (
    get_projects,
    create_project,
    update_project,
    delete_project,
)


@st.dialog("Manage Projects", width="medium")
def render_projects_modal():
    # -------------------------
    # FLASH
    # -------------------------
    flash = st.session_state.pop("_flash", None)
    if flash:
        level = flash.get("level", "info")
        msg = flash.get("msg", "")
        if level == "success":
            st.success(msg)
        elif level == "error":
            st.error(msg)
        elif level == "warning":
            st.warning(msg)
        else:
            st.info(msg)

    projects = get_projects() or []

    # colapsar expanders após operação
    collapse_all = bool(st.session_state.pop("_collapse_projects", False))

    # ---------------- CREATE ----------------
    st.markdown("### Create New Project")

    new_name = st.text_input("Project Name", key="new_project_name")
    open_flag = st.checkbox(
        "Allow open access (users can login without association)",
        key="new_project_open",
    )

    if st.button("Create", key="create_project_btn"):
        name = (new_name or "").strip()

        if not name:
            st.session_state["_flash"] = {"msg": "Project name is required.", "level": "error"}
            st.session_state.open_dialog = "projects"
            st.rerun()

        existing = {(p.get("name", "").strip().lower()) for p in projects}
        if name.lower() in existing:
            st.session_state["_flash"] = {"msg": "Project name already exists.", "level": "error"}
            st.session_state.open_dialog = "projects"
            st.rerun()

        create_project(name, st.session_state.user_id, open_flag)
        st.session_state["_flash"] = {"msg": "Project created successfully.", "level": "success"}
        st.session_state["_collapse_projects"] = True
        st.session_state.open_dialog = "projects"
        st.rerun()

    st.divider()

    if st.button("👥 Associate Users", use_container_width=True, key="btn_associate_users"):
        st.session_state.dialog_return_to = "projects"
        st.session_state.open_dialog = "associate"
        st.rerun()

    # ---------------- LIST ----------------
    st.markdown("### Existing Projects")

    if not projects:
        st.info("No projects available.")
        return

    for p in projects:
        project_id = p.get("project_id")
        project_name = p.get("name", "")

        expanded_state = False if collapse_all else False

        with st.expander(project_name, expanded=expanded_state):
            edited_name = st.text_input(
                "Edit Name",
                value=project_name,
                key=f"edit_name_{project_id}",
            )

            raw_active = p.get("is_active", True)
            active_value = raw_active if isinstance(raw_active, bool) else str(raw_active).strip().lower() == "true"

            is_active = st.checkbox(
                "Active",
                value=active_value,
                key=f"active_{project_id}",
            )

            raw_open = p.get("allow_open_access", False)
            open_value = raw_open if isinstance(raw_open, bool) else str(raw_open).strip().lower() == "true"

            allow_open = st.checkbox(
                "Allow open access",
                value=open_value,
                key=f"open_{project_id}",
            )

            col1, col2 = st.columns(2)

            with col1:
                if st.button("Update", key=f"update_{project_id}"):
                    update_project(project_id, (edited_name or "").strip(), is_active, allow_open)
                    st.session_state["_flash"] = {"msg": "Project updated successfully.", "level": "success"}
                    st.session_state["_collapse_projects"] = True
                    st.session_state.open_dialog = "projects"
                    st.rerun()

            with col2:
                if st.button("Delete", key=f"delete_{project_id}"):
                    delete_project(project_id)
                    st.session_state["_flash"] = {"msg": "Project deleted successfully.", "level": "success"}
                    st.session_state["_collapse_projects"] = True
                    st.session_state.open_dialog = "projects"
                    st.rerun()
