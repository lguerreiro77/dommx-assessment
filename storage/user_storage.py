import os
import json
import hashlib
from auth.crypto_service import encrypt, decrypt
from core.config import BASE_DIR

USERS_DIR = os.path.join(BASE_DIR, "data/users")
os.makedirs(USERS_DIR, exist_ok=True)

def user_path(user_id):
    return os.path.join(USERS_DIR, f"{user_id}.dat")

def hash_text(text):
    return hashlib.sha256(text.encode()).hexdigest()

def save_user(user_id, payload):
    blob = encrypt(json.dumps(payload))
    with open(user_path(user_id), "wb") as f:
        f.write(blob)

def load_user(user_id):
    path = user_path(user_id)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return json.loads(decrypt(f.read()))
