import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Carrega .env no ambiente local
load_dotenv()

try:
    import streamlit as st
except Exception:
    st = None


def _get_fernet_key() -> bytes:
    """
    Priority:
      1) Streamlit Cloud Secrets
      2) .env (local)
    """
    key = None

    # Streamlit Cloud
    if st is not None:
        try:
            key = st.secrets.get("FERNET_KEY", None)
        except Exception:
            key = None

    # Local .env
    if not key:
        key = os.getenv("FERNET_KEY")

    if not key:
        raise RuntimeError("FERNET_KEY not found in Streamlit Secrets or environment variables.")

    if isinstance(key, bytes):
        return key

    return key.encode("utf-8")


_cipher = Fernet(_get_fernet_key())


def encrypt_text(data: str) -> str:
    if data is None:
        data = ""
    return _cipher.encrypt(str(data).encode()).decode()


def decrypt_text(token: str) -> str:
    if not token:
        return ""
    return _cipher.decrypt(token.encode()).decode()
