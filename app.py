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
from core.i18n_markers import YAMLText

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


def _get_cache_path(locale: str) -> Path:
    return Path(f"data/domains/{locale}/ui_cache.json")


def _load_cache(locale: str) -> dict:
    path = _get_cache_path(locale)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(locale: str, cache: dict):
    path = _get_cache_path(locale)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def _ui_translate_openai(text: str, target_lang: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a translation engine for UI text. "
                        "Translate the user text strictly into the requested language. "
                        "Return only the translated text. "
                        "Do not explain anything. "
                        "Do not keep the original language."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Translate to {target_lang}:\n\n{text}",
                },
            ]
        )

        result = response.choices[0].message.content.strip()
        return result if result else text

    except Exception:
        return text
        
def _tr_cached(text: str, target_base: str) -> str:

    if not text:
        return ""

    loc = st.session_state.get("locale", DEFAULT_LOCALE)
    cache_path = Path(f"data/domains/{loc}/ui_cache.json")
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if cache_path.exists():
            cache = json.loads(cache_path.read_text(encoding="utf-8")) or {}
        else:
            cache = {}
    except Exception:
        cache = {}

    cache_key = text  # cache por idioma já está no path

    if cache_key in cache:
        return cache[cache_key]

    translated = _ui_translate_openai(text, target_base)

    cache[cache_key] = translated
    try:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return translated


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

    if text is None:
        return text

    if not isinstance(text, str):
        return text

    if isinstance(text, YAMLText):
        return str(text)

    raw = text.strip()

    # 🔒 NÃO traduz nada quando estiver renderizando YAML
    if st.session_state.get("_yaml_rendering") and not force:
        return text
        
    raw = text.strip()

    # 🔹 nunca traduz códigos tipo Q1
    if re.fullmatch(r"[Qq]\d+", raw):
        return text

    # 🔹 nunca traduz siglas/códigos curtos
    if re.fullmatch(r"[A-Z]{2,6}", raw):
        return text

    # 🔹 nunca traduz identificadores mistos (IDs, Quarter, etc)
    if re.fullmatch(r"[A-Z0-9_.\-]+", raw):
        return text

    # 🔒 se bloqueado e não forçado, não traduz
    if (not force) and st.session_state.get("_block_auto_tr"):
        return text

    loc = st.session_state.get("locale", DEFAULT_LOCALE)

    # idioma default não traduz
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
        
        st.rerun()


# -------------------------
# Auto patch Streamlit (translate without refactor)
# -------------------------
def _translate_value(v):
    if isinstance(v, YAMLText):
        return v
    return tr(v) if isinstance(v, str) else v


def _wrap_tabs(func):
    if getattr(func, "_dommx_wrapped", False):
        return func

    def wrapper(tabs, *args, **kwargs):
        if isinstance(tabs, list):
            tabs = [tr(x) if isinstance(x, str) else x for x in tabs]
        return func(tabs, *args, **kwargs)

    wrapper._dommx_wrapped = True
    return wrapper


def patch_streamlit_i18n():

    def _wrap_streamlit_func(func, *, translate_kwargs=(), skip_if_kwargs=None, translate_all_str_args=False):

        if getattr(func, "_dommx_wrapped", False):
            return func

        skip_if_kwargs = skip_if_kwargs or {}

        def _translate_value(v):
            if isinstance(v, str) and getattr(v, "_dommx_yaml", False):
                return v
            return tr(v) if isinstance(v, str) else v

        def wrapper(*args, **kwargs):
            
            # 🚫 NÃO interceptar markdown com HTML
            if func.__name__ == "markdown" and kwargs.get("unsafe_allow_html"):
                return func(*args, **kwargs)

            # Se algum kwarg pede "skip", não traduz
            for k, expected in skip_if_kwargs.items():
                if kwargs.get(k) == expected:
                    return func(*args, **kwargs)

            # Traduz todos args string (raramente usado)
            if translate_all_str_args and args:
                args = tuple(_translate_value(a) for a in args)

            # Traduz primeiro argumento (label) se for string e não for YAML
            elif args and isinstance(args[0], str):
                label_text = args[0]

                if not getattr(label_text, "_dommx_yaml", False):

                    # não traduz códigos curtos
                    s = label_text.strip()
                    if re.fullmatch(r"[Qq]\d+", s):
                        pass
                    elif re.fullmatch(r"[A-Z]{2,6}", s):
                        pass
                    else:
                        label_text = tr(label_text)

                args = (label_text,) + args[1:]

            # Traduz kwargs relevantes (placeholder/help/caption etc)
            for k in translate_kwargs:
                if k in kwargs and isinstance(kwargs[k], str):
                    if getattr(kwargs[k], "_dommx_yaml", False):
                        continue
                    kwargs[k] = tr(kwargs[k])

            return func(*args, **kwargs)

        wrapper._dommx_wrapped = True
        return wrapper


    # ---- WRAPS PRINCIPAIS (UI hardcoded) ----
    # Observação: YAML aparece como YAMLText e será ignorado pelo wrapper.

    WRAP_SPECS = {
        # mensagens
        "success": {"translate_kwargs": ()},
        "error": {"translate_kwargs": ()},
        "warning": {"translate_kwargs": ()},
        "info": {"translate_kwargs": ()},

        # textos
        "title": {"translate_kwargs": ()},
        "header": {"translate_kwargs": ()},
        "subheader": {"translate_kwargs": ()},
        "caption": {"translate_kwargs": ()},
        "text": {"translate_kwargs": ()},
        "write": {"translate_kwargs": ()},
        "markdown": {"translate_kwargs": ()},

        # botões
        "button": {"translate_kwargs": ("help",)},
        "download_button": {"translate_kwargs": ("help",)},

        # inputs (o que estava falhando pra você)
        "text_input": {"translate_kwargs": ("help", "placeholder")},
        "text_area": {"translate_kwargs": ("help", "placeholder")},
        "number_input": {"translate_kwargs": ("help", "placeholder")},
        "date_input": {"translate_kwargs": ("help",)},
        "time_input": {"translate_kwargs": ("help",)},
        "selectbox": {"translate_kwargs": ("help",)},
        "radio": {"translate_kwargs": ("help",)},
        "multiselect": {"translate_kwargs": ("help",)},
        "checkbox": {"translate_kwargs": ("help",)},
        "toggle": {"translate_kwargs": ("help",)},

        # uploader (o que estava falhando pra você)
        "file_uploader": {"translate_kwargs": ("help",)},
        # form submit
        "form_submit_button": {"translate_kwargs": ("help",)},
    }

    for name, spec in WRAP_SPECS.items():
        if hasattr(st, name):
            original = getattr(st, name)
            wrapped = _wrap_streamlit_func(
                original,
                translate_kwargs=spec.get("translate_kwargs", ()),
                skip_if_kwargs=spec.get("skip_if_kwargs", None),
                translate_all_str_args=spec.get("translate_all_str_args", False),
            )
            setattr(st, name, wrapped)

    # spinner
    if hasattr(st, "spinner"):
        original_spinner = st.spinner

        def spinner_wrapper(text="", *args, **kwargs):
            if isinstance(text, str) and not getattr(text, "_dommx_yaml", False):
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