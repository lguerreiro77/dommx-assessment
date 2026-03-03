import os
import yaml
import streamlit as st
from googletrans import Translator

translator = Translator()

def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_supported_languages():
    config = load_yaml("config/app_config.yaml")
    possible = config.get("language_posible", [])
    default = config.get("language_default")

    fs = load_yaml("config/filesystem_setup.yaml")
    main_domain = fs.get("main_domain")

    existing = []
    for lang in possible:
        path = os.path.join("data", "domains", main_domain, lang)
        if os.path.exists(path):
            existing.append(lang)

    if not existing and default:
        default_path = os.path.join("data", "domains", main_domain, default)
        if os.path.exists(default_path):
            return [default]

    return existing if existing else [default]

def resolve_language(browser_lang):
    config = load_yaml("config/app_config.yaml")
    possible = config.get("language_posible", [])
    default = config.get("language_default")

    fs = load_yaml("config/filesystem_setup.yaml")
    main_domain = fs.get("main_domain")

    def lang_exists(lang):
        path = os.path.join("data", "domains", main_domain, lang)
        return os.path.exists(path)

    if browser_lang in possible and lang_exists(browser_lang):
        return browser_lang

    if lang_exists(default):
        return default

    raise Exception("No valid language structure found.")

def translate_text(text):
    lang = st.session_state.get("current_language")
    if not lang:
        return text
    try:
        return translator.translate(text, dest=lang).text
    except:
        return text