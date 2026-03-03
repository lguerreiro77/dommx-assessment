import os
from pathlib import Path
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

json_path = BASE_DIR / os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = Credentials.from_service_account_file(
    str(json_path),
    scopes=SCOPES
)

gc = gspread.authorize(credentials)

sh = gc.open_by_key(os.getenv("SPREADSHEET_ID"))
ws = sh.worksheet("users")

print(ws.get_all_records())