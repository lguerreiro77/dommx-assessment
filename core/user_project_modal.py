import streamlit as st
from storage.user_storage import get_all_users
from storage.project_storage import get_all_projects
from storage.user_project_storage import (
    associate_users_projects,
    remove_user_project_association,
    get_all_user_projects,
)

# -------------------------
# stack helpers
# -------------------------
def _stack():
    s = st.session_state.get("dialog_stack")
    if not isinstance(s, list) or not s:
        s = []
    return s

def _go(dialog_name: str):
    st.session_state.open_dialog = dialog_name
    st.rerun()

def _back(fallback: str = "projects"):
    s = _stack()
    if len(s) >= 2:
        s.pop()
        st.session_state.dialog_stack = s
        _go(s[-1])
    else:
        st.session_state.dialog_stack = [fallback]
        _go(fallback)

def _push(dialog_name: str):
    s = _stack()
    if not s:
        s = ["projects"]
    if not s or s[-1] != dialog_name:
        s.append(dialog_name)
    st.session_state.dialog_stack = s

def _flash_render():
    flash = st.session_state.pop("_flash", None)
    if not flash:
        return
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


# =====================================================
# ASSOCIATE USERS
# =====================================================
@st.dialog("User Project Associations", width="medium")
def render_user_project_modal():
    _push("associate")
    _flash_render()

    # 1) LOAD FIRST (para não deixar botão clicável antes do load)
    users = get_all_users() or []
    projects = get_all_projects() or []
    associations = get_all_user_projects() or []

    # 2) HEADER AFTER LOAD (agora o botão não aparece antes)
    col_back, col_remove = st.columns([1, 1])

    with col_back:
        if st.button("← Back", use_container_width=True, key="assoc_back"):
            _back("projects")

    has_any_links = len(associations) > 0

    with col_remove:
        if st.button(
            "🔗 Remove association",
            use_container_width=True,
            disabled=not has_any_links,
            key="assoc_remove_link",
        ):
            _push("remove_association")
            _go("remove_association")

    if not users:
        st.warning("No users found.")
        return

    # active only
    active_projects = []
    for p in projects:
        raw = p.get("is_active", True)
        active = raw if isinstance(raw, bool) else str(raw).strip().lower() == "true"
        if active:
            active_projects.append(p)

    if not active_projects:
        st.warning("No active projects found.")
        return

    user_options = {u["email_hash"]: f"{u['full_name']} ({u['email']})" for u in users}
    project_options = {p["project_id"]: p["name"] for p in active_projects}

    st.markdown("### Associate users to projects")

    selected_users = st.multiselect(
        "Users",
        options=list(user_options.keys()),
        format_func=lambda x: user_options[x],
        key="assoc_users",
    )

    selected_projects = st.multiselect(
        "Projects",
        options=list(project_options.keys()),
        format_func=lambda x: project_options[x],
        key="assoc_projects",
    )

    st.divider()

    if st.button("Associate", use_container_width=True, key="assoc_btn"):
        if not selected_users:
            st.warning("Select at least one user.")
            return
        if not selected_projects:
            st.warning("Select at least one project.")
            return

        associate_users_projects(selected_users, selected_projects, st.session_state.user_id)

        st.session_state["_flash"] = {"msg": "Users successfully associated.", "level": "success"}
        _go("associate")


# =====================================================
# REMOVE ASSOCIATION
# =====================================================
@st.dialog("Remove association", width="medium")
def render_remove_association_modal():
    _push("remove_association")
    _flash_render()

    # LOAD FIRST
    users = get_all_users() or []
    projects = get_all_projects() or []
    associations = get_all_user_projects() or []

    # HEADER AFTER LOAD
    if st.button("← Back", use_container_width=True, key="rm_back"):
        _back("associate")

    if not associations:
        st.info("No associations exist to remove.")
        st.button("Remove", use_container_width=True, disabled=True, key="rm_disabled_none")
        return

    if not users:
        st.warning("No users found.")
        return

    project_map = {p["project_id"]: p.get("name", p["project_id"]) for p in projects}
    user_options = {u["email_hash"]: f"{u['full_name']} ({u['email']})" for u in users}

    st.markdown("### Remove an association")

    selected_user = st.selectbox(
        "User",
        options=list(user_options.keys()),
        format_func=lambda x: user_options[x],
        key="rm_user",
    )

    linked = [
        r.get("project_id")
        for r in associations
        if r.get("user_id") == selected_user
    ]

    if not linked:
        st.info("No associations for this user.")
        st.button("Remove", use_container_width=True, disabled=True, key="rm_disabled_user")
        return

    selected_project = st.selectbox(
        "Project",
        options=linked,
        format_func=lambda x: project_map.get(x, x),
        key="rm_project",
    )

    st.divider()

    if st.button("Remove", use_container_width=True, key="rm_btn"):
        remove_user_project_association(selected_user, selected_project)

        # rerun e re-leitura vão recalcular associations e desabilitar botão se zerou
        st.session_state["_flash"] = {"msg": "Association removed successfully.", "level": "success"}
        _go("remove_association")
