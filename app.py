import time
import re
import streamlit as st
import streamlit.components.v1 as components
import json
import hashlib
import yaml
from pathlib import Path

# deep-translator pode não existir no ambiente: não pode derrubar o app
try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None

from core.state import init_session
from auth.auth_service import render_auth
from core.renderer import render_app
from core.config import APP_TITLE
from core.session_utils import logout

st.set_page_config(page_title=APP_TITLE, layout="centered")
init_session()


# -------------------------
# Idiomas possiveis e configurados
# -------------------------

def load_app_config():

    project_id = st.session_state.get("active_project")

    # 1️⃣ Tenta config do projeto
    if project_id:
        project_config = Path("data/projects") / str(project_id) / "General" / "app_config.yaml"
        if project_config.exists():
            with open(project_config, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}

    # 2️⃣ Tenta config global padrão correto
    global_paths = [
        Path("data/general/app_config.yaml"),
        Path("data/app_config.yaml"),
        Path("app_config.yaml"),
    ]

    for path in global_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}

    return {}
    

# -------------------------
# Variaveis de sistema
# -------------------------

TR_MARK = "__TR__"
    
def refresh_locale_config():

    app_config = load_app_config()
    app_section = app_config.get("app", {})

    default_locale = app_section.get("language_default", "us").lower()
    locales = [x.lower() for x in app_section.get("language_posible", ["us"])]

    if default_locale not in locales:
        locales.insert(0, default_locale)

    return default_locale, locales


DEFAULT_LOCALE, LOCALES = refresh_locale_config()


FLAGS = {k: "🌍" for k in LOCALES}
FLAGS.update({
    "us": "🇺🇸",
    "es": "🇪🇸",
    "pt": "🇵🇹",
    "fr": "🇫🇷",
    "it": "🇮🇹",
    "de": "🇩🇪",
})

LOCALE_TO_TRANSLATOR = {k: k for k in LOCALES}
LOCALE_TO_TRANSLATOR["us"] = "en"


def init_locale():

    # 🔹 Se já existe locale válido na sessão, nunca recalcula
    existing = st.session_state.get("locale")
    if existing and existing in LOCALES:
        return

    # 1️⃣ Query param tem prioridade
    qp_raw = _get_query_param("lang")
    if qp_raw and qp_raw.lower() in LOCALES:
        st.session_state.locale = qp_raw.lower()
        return

    # 2️⃣ Browser (apenas se não houver projeto ainda)
    if not st.session_state.get("active_project"):

        try:
            accept_lang = st.context.headers.get("accept-language", "")
        except Exception:
            accept_lang = ""

        if accept_lang:
            short = accept_lang[:2].lower()
            if short in LOCALES:
                st.session_state.locale = short
                return

    # 3️⃣ Fallback
    st.session_state.locale = DEFAULT_LOCALE
    
# -------------------------
# Query param helpers
# -------------------------
def _get_query_param(name: str) -> str:
    try:
        return st.query_params.get(name, "") or ""
    except Exception:
        qp = st.experimental_get_query_params() or {}
        v = qp.get(name, [""])
        return (v[0] if isinstance(v, list) and v else "") or ""


def _set_query_param(name: str, value: str) -> None:
    try:
        st.query_params[name] = value
    except Exception:
        st.experimental_set_query_params(**{name: value})


# -------------------------
# Translation
# -------------------------
@st.cache_data(show_spinner=False)
def _translator_instance(target_base: str):
    if GoogleTranslator is None:
        return None
    return GoogleTranslator(source="auto", target=target_base)


def _tr_cached(text: str, target_base: str) -> str:

    if not text:
        return ""

    if GoogleTranslator is None:
        return text

    cache_key = f"{target_base}::{text}"

    if "_persistent_tr_cache" not in st.session_state:
        st.session_state["_persistent_tr_cache"] = {}

    cache = st.session_state["_persistent_tr_cache"]

    if cache_key in cache:
        return cache[cache_key]

    try:
        translator = _translator_instance(target_base)
        if not translator:
            return text

        result = translator.translate(text)
        cache[cache_key] = result
        return result

    except Exception:
        return text


def html_tr(html: str) -> str:
    """
    Traduz só o TEXTO dentro do HTML, preservando tags.
    Ex: "<h3>Login</h3>" => "<h3>Entrar</h3>" (dependendo do idioma)
    """
    if not html or not isinstance(html, str):
        return html

    # se for idioma default, nem mexe
    if st.session_state.get("locale", DEFAULT_LOCALE) == DEFAULT_LOCALE:
        return html

    # troca texto entre > ... <
    def repl(m):
        chunk = m.group(1)
        # não traduz whitespace puro
        if not chunk or chunk.strip() == "":
            return chunk
        return tr(chunk)

    return re.sub(r">([^<>]+)<", lambda m: ">" + repl(m) + "<", html)


# expõe helpers para outros módulos (auth_service.py etc)
# st._tr = tr
st._html_tr = html_tr


def tr(text: str, *, force=False) -> str:

    if not text or not isinstance(text, str):
        return text

    raw = text.strip()

    # 🔹 Nunca traduz códigos tipo Q1, Q12
    if re.fullmatch(r"[Qq]\d+", raw):
        return text

    # 🔹 Nunca traduz siglas técnicas tipo DG, DA, DSO
    if re.fullmatch(r"[A-Z]{2,6}", raw):
        return text

    # 🔹 Nunca traduz códigos mistos tipo D1_Q2, Q1.1
    if re.fullmatch(r"[A-Z0-9_.\-]+", raw):
        return text

    # 🔹 Se bloqueado (assessment YAML), não traduz
    if not force and st.session_state.get("_block_auto_tr"):
        return text

    if text.startswith(TR_MARK):
        return text.replace(TR_MARK, "", 1)

    loc = st.session_state.get("locale", DEFAULT_LOCALE)

    if loc == DEFAULT_LOCALE:
        return text

    target_base = LOCALE_TO_TRANSLATOR.get(loc)

    if not target_base:
        return text

    return _tr_cached(text, target_base)
        
st._tr = tr

def _stable_hash(obj) -> str:
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _walk_translate_values(obj, translate_fn):
    # traduz só VALORES (não mexe em keys)
    if isinstance(obj, str):
        out = translate_fn(obj)
        return (TR_MARK + out) if out else out
    if isinstance(obj, list):
        return [_walk_translate_values(x, translate_fn) for x in obj]
    if isinstance(obj, dict):
        return {k: _walk_translate_values(v, translate_fn) for k, v in obj.items()}
    return obj


# -------------------------
# Locale selector (flag only)
# -------------------------
def render_locale_flag_combo():

    current = st.session_state.get("locale", DEFAULT_LOCALE)

    if current not in LOCALES:
        st.session_state.locale = DEFAULT_LOCALE
        current = DEFAULT_LOCALE

    current_index = LOCALES.index(current)

    selected = st.selectbox(
        "Language",
        options=LOCALES,
        index=current_index,
        format_func=lambda k: FLAGS.get(k, "🏳️"),
        label_visibility="collapsed",
        key="global_locale_selector"
    )

    if selected != current:
        st.session_state.locale = selected
        _set_query_param("lang", selected)

        # limpa cache de tradução para evitar “não traduzido” cacheado
        try:
            _tr_cached.clear()
        except Exception:
            pass

        st.rerun()


# -------------------------
# Auto patch Streamlit (translate without refactor)
# -------------------------
def _translate_value(v):
    return tr(v) if isinstance(v, str) else v


def _wrap_streamlit_func(func, *, translate_kwargs=None, skip_if_kwargs=None, translate_all_str_args=False):
    if getattr(func, "_dommx_wrapped", False):
        return func

    translate_kwargs = set(translate_kwargs or [])
    skip_if_kwargs = dict(skip_if_kwargs or {})

    def wrapper(*args, **kwargs):

        for k, expected in skip_if_kwargs.items():
            if kwargs.get(k) == expected:
                return func(*args, **kwargs)

        # 🔒 Nunca traduz durante assessment YAML
        if st.session_state.get("_block_auto_tr"):
            return func(*args, **kwargs)

        if translate_all_str_args and args:
            args = tuple(_translate_value(a) for a in args)

        elif args and isinstance(args[0], str):
            label_text = args[0]

            if re.fullmatch(r"[Qq]\d+", label_text.strip()):
                pass
            elif re.fullmatch(r"[A-Z]{2,6}", label_text.strip()):
                pass
            else:
                label_text = tr(label_text)

            args = (label_text,) + args[1:]

        for k in translate_kwargs:
            if k in kwargs and isinstance(kwargs[k], str):
                kwargs[k] = tr(kwargs[k])

        return func(*args, **kwargs)

    wrapper._dommx_wrapped = True
    return wrapper


def _wrap_tabs(func):
    if getattr(func, "_dommx_wrapped", False):
        return func

    def wrapper(tabs, *args, **kwargs):
        if isinstance(tabs, list):
            tabs = [tr(x) if isinstance(x, str) else x for x in tabs]
        return func(tabs, *args, **kwargs)

    wrapper._dommx_wrapped = True
    return wrapper


def patch_streamlit_i18n() -> None:
    for name in ["success", "error", "warning", "info", "caption", "text", "title", "header", "subheader"]:
        if hasattr(st, name):
            setattr(st, name, _wrap_streamlit_func(getattr(st, name), translate_all_str_args=False))

    if hasattr(st, "write"):
        st.write = _wrap_streamlit_func(st.write, translate_all_str_args=True)

    # 🔹 PATCH BUTTON (traduz primeiro argumento)
    if hasattr(st, "button"):
        original_button = st.button

        def button_wrapper(label, *args, **kwargs):
            if isinstance(label, str):
                label = tr(label)
            return original_button(label, *args, **kwargs)

        st.button = button_wrapper

    # 🔹 PATCH DOWNLOAD BUTTON
    if hasattr(st, "download_button"):
        original_download = st.download_button

        def download_wrapper(label, *args, **kwargs):
            if isinstance(label, str):
                label = tr(label)
            return original_download(label, *args, **kwargs)

        st.download_button = download_wrapper

    # markdown: NÃO traduz unsafe html globalmente (para não quebrar layout)
    # 🔹 PATCH MARKDOWN
    if hasattr(st, "markdown"):

        original_markdown = st.markdown

        def markdown_wrapper(body, *args, **kwargs):

            # 🔒 assessment YAML: nunca traduz nada
            if st.session_state.get("_block_auto_tr"):
                return original_markdown(body, *args, **kwargs)

            unsafe = kwargs.get("unsafe_allow_html") is True

            if isinstance(body, str):

                # 1) HTML com unsafe_allow_html=True
                if unsafe:
                    # NÃO traduz CSS/STYLE
                    if "<style" in body.lower():
                        return original_markdown(body, *args, **kwargs)

                    # traduz HTML mantendo tags
                    html_tr_fn = getattr(st, "_html_tr", None)
                    if callable(html_tr_fn):
                        body = html_tr_fn(body)
                    return original_markdown(body, *args, **kwargs)

                # 2) Markdown normal
                body = tr(body)

            return original_markdown(body, *args, **kwargs)

        st.markdown = markdown_wrapper

    kw = ["label", "help", "placeholder"]
    for name in [                
        "selectbox",
        "radio",
        "multiselect",
        "checkbox",
        "toggle",
        "text_input",
        "text_area",
        "number_input",
        "date_input",
        "time_input",
        "file_uploader",
        "form_submit_button",
        "expander",
    ]:
        if hasattr(st, name):
            setattr(st, name, _wrap_streamlit_func(getattr(st, name), translate_kwargs=kw, translate_all_str_args=False))

    if hasattr(st, "tabs"):
        st.tabs = _wrap_tabs(st.tabs)

    if hasattr(st, "tabs"):
        st.tabs = _wrap_tabs(st.tabs)

    # 🔹 PATCH SPINNER
    if hasattr(st, "spinner"):
        original_spinner = st.spinner

        def spinner_wrapper(text="", *args, **kwargs):
            if isinstance(text, str):
                text = tr(text)
            return original_spinner(text, *args, **kwargs)

        st.spinner = spinner_wrapper

init_locale()
patch_streamlit_i18n()


# -------------------------------------------------
# PROJECT CONFIG ERROR SCREEN (logout in 4s)
# -------------------------------------------------
if st.session_state.get("project_config_error"):
    msg = st.session_state.get("project_config_error_msg") or "Project configuration directory does not exist."
    st.error(msg)

    logout_at = st.session_state.get("logout_at")
    if logout_at:
        remaining = int(float(logout_at) - time.time())
        if remaining > 0:
            st.info(f"You will be logged out automatically in {remaining} seconds...")
            time.sleep(1)
            st.rerun()
        else:
            logout()
    else:
        logout()

    st.stop()


# -------------------------
# Routing
# -------------------------
if st.session_state.app_mode in ["login", "register", "select_project"]:
    col_main, col_lang = st.columns([0.88, 0.12])
    with col_lang:
        render_locale_flag_combo()
    render_auth()
else:
    col_main, col_lang = st.columns([0.88, 0.12])
    with col_main:
        st.title(APP_TITLE)
    with col_lang:
        render_locale_flag_combo()
    render_app()