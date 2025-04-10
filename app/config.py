# app/config.py
import json
import os

# 取得 data 資料夾內的 config.json 路徑
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_PATH = os.path.join(BASE_DIR, 'data')
CONFIG_PATH = os.path.join(DATA_PATH, 'config.json')

# 讀取設定
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    _config = json.load(f)

# 設定變數
SCOPES = _config.get("SCOPES", ['https://www.googleapis.com/auth/calendar'])
CREDENTIALS_FILE = os.path.join(DATA_PATH, _config.get("CREDENTIALS_FILE", "credentials.json"))
TOKEN_FILE = os.path.join(DATA_PATH, _config.get("TOKEN_FILE", "token.pickle"))
TIMEZONE = _config.get("TIMEZONE", "Asia/Taipei")
DEFAULT_CALENDAR_ID = _config.get("DEFAULT_CALENDAR_ID", "")
ICS_URL = _config.get("ICS_URL", "")
OUTPUT_JSON_FILE = os.path.join(DATA_PATH, _config.get("OUTPUT_JSON_FILE", "events.json"))
LOG_FILE = os.path.join(DATA_PATH, _config.get("LOG_FILE", "application.log"))
LOG_LEVEL = _config.get("LOG_LEVEL", "INFO")