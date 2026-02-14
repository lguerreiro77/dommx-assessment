import os
from cryptography.fernet import Fernet
from core.config import BASE_DIR

KEY_PATH = os.path.join(BASE_DIR, "data/general/secret.key")

if not os.path.exists(KEY_PATH):
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    with open(KEY_PATH, "wb") as f:
        f.write(Fernet.generate_key())

with open(KEY_PATH, "rb") as f:
    SECRET_KEY = f.read()

cipher = Fernet(SECRET_KEY)

def encrypt(data: str) -> bytes:
    return cipher.encrypt(data.encode())

def decrypt(blob: bytes) -> str:
    return cipher.decrypt(blob).decode()
