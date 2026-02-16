# core/ui/dialogs.py
import streamlit as st

from core.ui.state_manager import close_dialog, open_dialog, set_flash, set_busy, is_busy
from core.ui.components import safe_button, empty_state


def render_dialog_if_any():
    """
    Centraliza dialogs.
    Nunca chama storage aqui. Apenas orquestra fluxo.
    """
    name = st.session_state.get("open_dialog")
    if not name:
        return

    if name == "user_project_manage":
        _dialog_user_project_manage()
    elif name == "project_edit":
        _dialog_project_edit()
    elif name == "confirm_delete":
        _dialog_confirm_delete()
    else:
        # fallback
        _dialog_unknown(name)


@st.dialog("Gerenciar vínculos usuário ↔ projeto")
def _dialog_user_project_manage():
    payload = st.session_state.get("dialog_payload", {})
    user_id = payload.get("user_id")
    project_id = payload.get("project_id")
    has_link = bool(payload.get("has_link", False))

    st.write("Aqui você controla vínculos sem nested dialogs.")
    st.caption("Este dialog não deve fazer leitura do Google Sheets.")
    st.divider()

    st.write(f"User: **{user_id or '-'}**")
    st.write(f"Project: **{project_id or '-'}**")

    if not user_id or not project_id:
        empty_state("Dados incompletos", "Faltou user_id ou project_id no payload.")
        if safe_button("Voltar", key="upm_back"):
            close_dialog(go_back=True)
        return

    # UX: botão remover vínculo desabilitado se não houver vínculo
    remove_disabled = not has_link

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if safe_button("Voltar", key="upm_back"):
            close_dialog(go_back=True)

    with col2:
        if safe_button("Remover vínculo", key="upm_remove", disabled=remove_disabled, help=None if has_link else "Usuário não tem vínculo com este projeto"):
            # aqui só abre confirmação, sem nested (usa stack)
            open_dialog("confirm_delete", payload={
                "kind": "user_project_link",
                "user_id": user_id,
                "project_id": project_id,
                "on_success_flash": "Vínculo removido.",
                "on_error_flash": "Falha ao remover vínculo."
            })

    with col3:
        if not has_link:
            st.info("Este usuário não tem vínculos com este projeto.")


@st.dialog("Editar projeto")
def _dialog_project_edit():
    payload = st.session_state.get("dialog_payload", {})
    project_id = payload.get("project_id")

    st.write("Dialog de edição. Não chama storage aqui.")
    st.caption("Passe dados prontos via payload (ex: nome atual, status etc).")
    st.divider()

    name = st.text_input("Nome", value=str(payload.get("name", "")))
    is_active = st.checkbox("Ativo", value=bool(payload.get("is_active", True)))

    col1, col2 = st.columns([1, 1])
    with col1:
        if safe_button("Cancelar", key="pe_cancel"):
            close_dialog(go_back=True)

    with col2:
        if safe_button("Salvar", key="pe_save", disabled=is_busy()):
            # Só sinaliza intenção.
            # A escrita real deve acontecer fora do dialog, em um handler de service, que depois fecha dialog e limpa cache.
            set_busy(True)
            try:
                # aqui você chamaria um callback passado por payload, se quiser
                cb = payload.get("on_save")
                if callable(cb):
                    cb({"project_id": project_id, "name": name, "is_active": is_active})
                set_flash("Alterações enviadas para salvar.", "success")
                close_dialog(go_back=True)
            except Exception:
                set_flash("Erro ao salvar.", "error")
            finally:
                set_busy(False)


@st.dialog("Confirmar ação")
def _dialog_confirm_delete():
    payload = st.session_state.get("dialog_payload", {})
    kind = payload.get("kind")

    st.warning("Confirme a ação. Este dialog não fecha o modal pai indevidamente.")
    st.write(f"Ação: **{kind}**")
    st.divider()

    col1, col2 = st.columns([1, 1])
    with col1:
        if safe_button("Voltar", key="cd_back"):
            close_dialog(go_back=True)

    with col2:
        if safe_button("Confirmar", key="cd_confirm", disabled=is_busy()):
            set_busy(True)
            try:
                cb = payload.get("on_confirm")
                if callable(cb):
                    cb(payload)
                set_flash(payload.get("on_success_flash", "Ação concluída."), "success")
                close_dialog(go_back=True)
            except Exception:
                set_flash(payload.get("on_error_flash", "Falha na ação."), "error")
                # não fecha tudo, só volta
                close_dialog(go_back=True)
            finally:
                set_busy(False)


@st.dialog("Dialog")
def _dialog_unknown(name: str):
    st.error(f"Dialog não reconhecido: {name}")
    if safe_button("Fechar", key="dlg_close"):
        close_dialog(go_back=True)
