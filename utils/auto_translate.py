import re
import streamlit as st
from googletrans import Translator

translator = Translator()

_original_write = st.write
_original_markdown = st.markdown
_original_text = st.text
_original_button = st.button
_original_subheader = st.subheader
_original_header = st.header
_original_title = st.title
_original_caption = st.caption
_original_spinner = st.spinner


def _translate(value):
    lang = st.session_state.get("current_language")
    if not lang:
        return value

    if isinstance(value, str):

        # Não traduz HTML / CSS
        if "<" in value and ">" in value:
            return value

        # Não traduz blocos tipo {variable}
        if re.search(r"{.*?}", value):
            return value

        try:
            return translator.translate(value, dest=lang).text
        except:
            return value

    return value


def enable_auto_translation():

    def write(*args, **kwargs):
        args = [_translate(a) for a in args]
        return _original_write(*args, **kwargs)

    def markdown(body, *args, **kwargs):
        if kwargs.get("unsafe_allow_html", False):
            return _original_markdown(body, *args, **kwargs)

        if isinstance(body, str):
            body = _translate(body)

        return _original_markdown(body, *args, **kwargs)

    def text(*args, **kwargs):
        args = [_translate(a) for a in args]
        return _original_text(*args, **kwargs)

    def button(label, *args, **kwargs):
        label = _translate(label)
        return _original_button(label, *args, **kwargs)

    def subheader(label, *args, **kwargs):
        label = _translate(label)
        return _original_subheader(label, *args, **kwargs)

    def header(label, *args, **kwargs):
        label = _translate(label)
        return _original_header(label, *args, **kwargs)

    def title(label, *args, **kwargs):
        label = _translate(label)
        return _original_title(label, *args, **kwargs)

    def caption(label, *args, **kwargs):
        label = _translate(label)
        return _original_caption(label, *args, **kwargs)

    def spinner(text="", *args, **kwargs):
        if isinstance(text, str):
            text = _translate(text)
        return _original_spinner(text, *args, **kwargs)

    st.write = write
    st.markdown = markdown
    st.text = text
    st.button = button
    st.subheader = subheader
    st.header = header
    st.title = title
    st.caption = caption
    st.spinner = spinner