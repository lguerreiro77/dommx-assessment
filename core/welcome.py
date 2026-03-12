import streamlit as st
import yaml
import os
import base64
import streamlit.components.v1 as components

from pathlib import Path
from core.config import BASE_DIR, resolve_path, get_project_root


@st.dialog("Document")
def show_doc(md):

    st.markdown(md)

    if st.button("Close", use_container_width=True):
        st.rerun()


def safe_load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except:
        return None


def render_welcome():    

    project_root = get_project_root()

    if not project_root:
        st.stop()    
        
    config = {}

    if project_root:
        project_config = Path(project_root) / "general" / "app_config.yaml"
        if project_config.exists():
            with open(project_config, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

    if not config:
        global_config = Path(BASE_DIR) / "data" / "general" / "app_config.yaml"
        if global_config.exists():
            with open(global_config, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

    intro_heading = config.get("intro", {}).get("heading", "")
    intro_message = config.get("intro", {}).get("message", "")
    show_intro = config.get("app", {}).get("show_intro", False)

    if not show_intro:
        st.session_state.intro_seen = True
        st.rerun()

    lang = st.session_state.get("locale") or config.get("app", {}).get("language_default", "us")
    
    st.markdown("""
        <style>

        /* largura maior do texto central */
        .welcome-intro {
            max-width: 760px;
            margin: auto;
        }

        /* painel lateral */
        div[data-testid="column"]:nth-child(2) {

            border-left: 1px solid rgba(0,0,0,0.15);
            padding-left: 22px;
        }

        /* espaço entre botões e borda */
        div[data-testid="column"]:nth-child(2) button,
        div[data-testid="column"]:nth-child(2) a {
            margin-left: 4px;
        }

        </style>
        """, unsafe_allow_html=True)

    docs_config = config.get("docs", [])
    valid_docs = []

    docs_path = Path(project_root) / "general" / "docs" 
    
    if isinstance(docs_config, list):
        docs_config = sorted(docs_config, key=lambda x: x.get("id", 0))

    if docs_path.exists():

        for d in docs_config:

            title = d.get("title")
            file_template = d.get("file")
            link = d.get("link")
            caption = d.get("caption")

            if file_template:

                file_lang = file_template.replace("{lang}", lang)
                file_en = file_template.replace("{lang}", "en")

                f_lang = docs_path / file_lang
                f_en = docs_path / file_en

                if f_lang.exists():
                    valid_docs.append({
                        "title": title,
                        "type": "file",
                        "path": f_lang,
                        "caption": caption
                    })

                elif f_en.exists():
                    valid_docs.append({
                        "title": title,
                        "type": "file",
                        "path": f_en,
                        "caption": caption
                    })

            elif link:

                valid_docs.append({
                    "title": title,
                    "type": "link",
                    "url": link,
                    "caption": caption
                })

    # estado do viewer de documentos
    if "doc_viewer" not in st.session_state:
        st.session_state.doc_viewer = None
    
    # layout definido ANTES de renderizar conteúdo
    if valid_docs:
        col_main, col_docs = st.columns([6.5,3.5])
    else:
        col_main = st.container()

    # conteúdo principal
    with col_main:

        st.markdown(
            st._html_tr(f"<h2 style='text-align:center'>{intro_heading}</h2>"),
            unsafe_allow_html=True
        )

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            st._html_tr(
                f"<div class='welcome-intro' style='text-align:justify;'>"
                f"{intro_message}"
                f"</div>"
            ),
            unsafe_allow_html=True
        )

        st.markdown("<br><br>", unsafe_allow_html=True)

        if st.button("Continue ➡", use_container_width=True):
            st.session_state.intro_seen = True
            st.rerun()

    # painel lateral
    if valid_docs:

        with col_docs:

            docs_box = st.container(border=True)

            with docs_box:

                st.markdown(
                    f"<div style='font-size:17px;font-weight:600;margin-bottom:12px'>"
                    f"{st._tr('📚 Reference Documents', force=True)}"
                    f"</div>",
                    unsafe_allow_html=True
                )

                for d in valid_docs:

                    if d["type"] == "file":

                        

                        file_path = d["path"]
                        ext = Path(file_path).suffix.lower()

                        # =========================
                        # PDF
                        # =========================
                        if ext == ".pdf":

                            with open(file_path, "rb") as f:
                                pdf_bytes = f.read()

                            if st.button(st._tr(f"📄 {d['title']}", force=True), use_container_width=True):

                                b64 = base64.b64encode(pdf_bytes).decode("utf-8")

                                components.html(
                                    f"""
                                    <script>
                                    (function() {{
                                        const b64 = "{b64}";
                                        const byteChars = atob(b64);
                                        const byteNumbers = new Array(byteChars.length);
                                        for (let i = 0; i < byteChars.length; i++) {{
                                            byteNumbers[i] = byteChars.charCodeAt(i);
                                        }}
                                        const byteArray = new Uint8Array(byteNumbers);
                                        const blob = new Blob([byteArray], {{ type: "application/pdf" }});
                                        const url = URL.createObjectURL(blob);
                                        window.open(url, "_blank");
                                        setTimeout(() => URL.revokeObjectURL(url), 60000);
                                    }})();
                                    </script>
                                    """,
                                    height=0,
                                )

                        # =========================
                        # MARKDOWN
                        # =========================
                        elif ext == ".md":

                            with open(file_path, "r", encoding="utf-8") as f:
                                md = f.read()

                            if st.button(st._tr(f"📄 {d['title']}", force=True), use_container_width=True):
                                show_doc(md)

                        # =========================
                        # DOCX
                        # =========================
                        elif ext == ".docx":

                            with open(file_path, "rb") as f:
                                st.download_button(
                                    label=st._tr(f"📄 {d['title']}", force=True),
                                    data=f,
                                    file_name=os.path.basename(file_path),
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    use_container_width=True
                                )

                        # =========================
                        # DEFAULT
                        # =========================
                        else:

                            with open(file_path, "rb") as f:
                                st.download_button(
                                    label=st._tr(f"📄 {d['title']}", force=True),
                                    data=f,
                                    file_name=os.path.basename(file_path),
                                    use_container_width=True
                                )

                    else:

                        st.link_button(
                            st._tr(f"🔗 {d['title']}", force=True),
                            d["url"],
                            use_container_width=True
                        )

                    if d.get("caption"):
                        st.caption(st._tr(d["caption"], force=True))
                        
    