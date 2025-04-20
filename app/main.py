#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import hashlib
import json
import pickle
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from ics import Calendar
from ics.event import Event
import config as config  # 引用設定檔

# 初始化 logging
logging.basicConfig(
    filename=config.LOG_FILE,
    level=getattr(logging, config.LOG_LEVEL.upper(), "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# 新增 StreamHandler 將 log 輸出到終端機
# console_handler = logging.StreamHandler()
# console_handler.setLevel(getattr(logging, config.LOG_LEVEL.upper(), "INFO"))
# console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
# console_handler.setFormatter(console_formatter)
# logging.getLogger().addHandler(console_handler)

# ---------- HASH / SYNC RECORD ----------
def compute_event_hash(event):
    logging.debug("計算事件的 hash 值")
    
    # 獲取 rrule 的安全方式
    rrule_value = None
    if hasattr(event, 'extra'):
        if isinstance(event.extra, dict):
            rrule_value = event.extra.get('rrule')
        elif hasattr(event.extra, 'rrule'):
            rrule_value = event.extra.rrule
    
    content = json.dumps({
        'summary': event.name,
        # 移除 description 欄位
        'location': event.location,
        'start': str(event.begin),
        'end': str(event.end),
        'rrule': rrule_value
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(content.encode("utf-8")).hexdigest()

def get_sync_record_path(calendar_id):
    record_path = os.path.join(config.DATA_PATH, f"last_synced_{calendar_id.replace('@', '_').replace('.', '_')}.json")
    return record_path

def load_last_sync(calendar_id):
    path = get_sync_record_path(calendar_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_last_sync(sync_data, calendar_id):
    path = get_sync_record_path(calendar_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sync_data, f, ensure_ascii=False, indent=2)

# ---------- AUTH ----------
def get_credentials():
    creds = None
    if os.path.exists(config.TOKEN_FILE):
        with open(config.TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = _get_new_credentials()
        else:
            creds = _get_new_credentials()

        with open(config.TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)

    return creds

def _get_new_credentials():
    if os.path.exists(config.CREDENTIALS_FILE):
        flow = InstalledAppFlow.from_client_secrets_file(config.CREDENTIALS_FILE, config.SCOPES)
        return flow.run_local_server(port=0)
    else:
        raise FileNotFoundError(f"需要 {config.CREDENTIALS_FILE} 文件來獲取新憑證")

# ---------- PARSING ----------
def get_events_from_json(json_file):
    with open(json_file, 'r', encoding='utf-8') as f:
        events_data = json.load(f)
    valid_events = []
    
    for event_data in events_data:
        try:
            # 檢查是否為字典並包含必要欄位
            if not isinstance(event_data, dict):
                logging.warning(f"跳過非字典格式事件: {event_data}")
                continue
                
            # 檢查必要欄位是否存在
            if 'begin' not in event_data or 'end' not in event_data or 'name' not in event_data:
                logging.warning(f"跳過缺少必要欄位的事件: {event_data}")
                continue
                
            event = Event()
            event.name = event_data.get('name', '未命名事件')
            event.uid = event_data.get('uid', '')
            event.begin = datetime.fromisoformat(event_data.get('begin', '').replace('Z', '+00:00'))
            event.end = datetime.fromisoformat(event_data.get('end', '').replace('Z', '+00:00'))
            event.description = event_data.get('description')
            event.location = event_data.get('location')
            
            # 處理週期性規則
            if 'recurrence_rules' in event_data and event_data['recurrence_rules']:
                rrule_str = event_data['recurrence_rules']
                if isinstance(rrule_str, str) and rrule_str.strip():
                    if not hasattr(event, 'extra') or not isinstance(event.extra, dict):
                        event.extra = {}
                    if not rrule_str.startswith('RRULE:'):
                        rrule_str = f"RRULE:{rrule_str}"
                    event.extra['rrule'] = [rrule_str]
            
            # 處理例外日期
            if 'exdate' in event_data and event_data['exdate']:
                exdate_str = event_data['exdate']
                if not hasattr(event, 'extra'):
                    event.extra = {}
                event.extra['exdate'] = exdate_str
                
            valid_events.append(event)
        except Exception as e:
            logging.warning(f"解析事件失敗: {e}, 事件資料: {event_data}")
    
    # 創建新的 Calendar 物件並添加所有有效事件
    new_calendar = Calendar()
    for event in valid_events:
        new_calendar.events.add(event)
    
    return new_calendar

# ---------- GOOGLE EVENT FORMAT ----------
def convert_ics_to_google_event(ics_event):
    google_event = {
        'summary': ics_event.name,
    }
    if ics_event.description:
        google_event['description'] = ics_event.description
    if ics_event.location:
        google_event['location'] = ics_event.location

    tz = ZoneInfo(config.TIMEZONE)
    start_dt = ics_event.begin.replace(tzinfo=tz).astimezone(tz)
    end_dt = ics_event.end.replace(tzinfo=tz).astimezone(tz)

    if start_dt.time() == datetime.min.time() and end_dt.time() == datetime.min.time():
        google_event['start'] = {'date': start_dt.date().isoformat()}
        google_event['end'] = {'date': end_dt.date().isoformat()}
    else:
        google_event['start'] = {'dateTime': start_dt.isoformat(), 'timeZone': config.TIMEZONE}
        google_event['end'] = {'dateTime': end_dt.isoformat(), 'timeZone': config.TIMEZONE}

    if hasattr(ics_event, 'extra') and isinstance(ics_event.extra, dict):
        rrule_val = ics_event.extra.get('rrule')
        if isinstance(rrule_val, list) and rrule_val:
            rrule_str = rrule_val[0].strip()
            if not rrule_str.startswith("RRULE:"):
                rrule_str = f"RRULE:{rrule_str}"
            google_event['recurrence'] = [rrule_str]

    # 處理例外日期 - 修改這部分
    if hasattr(ics_event, 'extra'):
        # 添加調試日誌
        logging.debug(f"處理事件例外日期: {ics_event.name}, extra 類型: {type(ics_event.extra)}")
        
        # 當 extra 是字典時
        if isinstance(ics_event.extra, dict) and 'exdate' in ics_event.extra:
            if "recurrence" not in google_event:
                google_event["recurrence"] = []
            
            exdates = ics_event.extra['exdate'].split(",")
            for exdate in exdates:
                # 清理格式但保留原始時間
                exdate_cleaned = exdate.replace("Z", "").replace("+00:00", "")
                if "T" not in exdate_cleaned:
                    exdate_cleaned = f"{exdate_cleaned}T000000"
                
                # 使用正確的時區格式
                google_event["recurrence"].append(f"EXDATE;TZID={config.TIMEZONE}:{exdate_cleaned}")
                logging.debug(f"添加例外日期: {exdate} -> EXDATE;TZID={config.TIMEZONE}:{exdate_cleaned}")
        
        # 當 extra 是 Container 物件時
        elif hasattr(ics_event.extra, 'exdate'):
            if "recurrence" not in google_event:
                google_event["recurrence"] = []
            
            exdate_str = str(ics_event.extra.exdate)
            exdates = exdate_str.split(",")
            for exdate in exdates:
                exdate_cleaned = exdate.replace("Z", "").replace("+00:00", "")
                if "T" not in exdate_cleaned:
                    exdate_cleaned = f"{exdate_cleaned}T000000"
                
                google_event["recurrence"].append(f"EXDATE;TZID={config.TIMEZONE}:{exdate_cleaned}")
                logging.debug(f"添加例外日期 (Container): {exdate} -> EXDATE;TZID={config.TIMEZONE}:{exdate_cleaned}")

    # 處理週期事件的例外 (時間被修改的實例)
    if hasattr(ics_event, 'is_recurrence_exception') and ics_event.is_recurrence_exception:
        # 如果這是週期事件的例外，添加 recurringEventId 屬性
        parent_id = hashlib.md5((calendar_id + '|' + 
                               (ics_event.uid or ics_event.name) + '|' + 
                               'recurring'
                               ).encode()).hexdigest()
        
        google_event['recurringEventId'] = parent_id
        google_event['originalStartTime'] = {
            'dateTime': ics_event.begin.replace(tzinfo=tz).isoformat(),
            'timeZone': config.TIMEZONE
        }
        
        logging.debug(f"處理週期事件例外: {ics_event.name}, 原始開始時間: {ics_event.recurrence_id}")

    # 調試輸出
    if 'recurrence' in google_event:
        logging.debug(f"事件 {ics_event.name} 的完整 recurrence 參數: {google_event['recurrence']}")

    return google_event

# ---------- SYNC ----------
def sync_to_google(json_file, calendar_id=config.DEFAULT_CALENDAR_ID):
    logging.info(f"開始同步 {json_file} 至 Google Calendar (Calendar ID: {calendar_id})")
    creds = get_credentials()
    service = build('calendar', 'v3', credentials=creds)

    try:
        calendar = get_events_from_json(json_file)
        google_events = service.events().list(
            calendarId=calendar_id,
            timeMin=(datetime.utcnow() - timedelta(days=365)).isoformat() + 'Z',
            timeMax=(datetime.utcnow() + timedelta(days=365)).isoformat() + 'Z',
            singleEvents=True,
            maxResults=2500,
            orderBy='startTime'
        ).execute().get('items', [])
 
        google_events_dict = {event.get('id'): event for event in google_events}
        last_sync = load_last_sync(calendar_id)
        new_sync = {}
        added, updated, skipped, deleted = 0, 0, 0, 0

        # 分開處理週期事件和例外事件
        recurring_events = []
        exception_events = []
        
        for event in calendar.events:
            # 確保 event 是 Event 物件
            if not isinstance(event, Event):
                logging.warning(f"跳過非 Event 物件: {event}")
                continue

            # 安全獲取 rrule
            has_rrule = False
            rrule_value = None
            if hasattr(event, 'extra'):
                if isinstance(event.extra, dict) and 'rrule' in event.extra:
                    has_rrule = True
                    rrule_value = event.extra.get('rrule')
                elif hasattr(event.extra, 'rrule'):
                    has_rrule = True
                    rrule_value = event.extra.rrule
            
            # 對週期事件和單次事件區分處理
            event_date = event.begin.date().isoformat()  # 獲取日期部分
            if has_rrule:
                # 週期事件 - 使用 UID 生成一致的 ID
                event_id = hashlib.md5((calendar_id + '|' + 
                                      (event.uid or event.name) + '|' + 
                                      'recurring'
                                      ).encode()).hexdigest()
                recurring_events.append(event)
            elif hasattr(event, 'is_recurrence_exception'):
                exception_events.append(event)
            else:
                # 單次事件 - 使用 UID + 日期生成 ID
                # 相同 UID 在不同日期會有不同 ID
                event_id = hashlib.md5((calendar_id + '|' + 
                                      (event.uid or event.name) + '|' + 
                                      event_date + '|' +
                                      str(event.begin.time())
                                      ).encode()).hexdigest()
                
                google_event = convert_ics_to_google_event(event)
                google_event['id'] = event_id
                event_hash = compute_event_hash(event)
                new_sync[event_id] = event_hash

                if last_sync.get(event_id) == event_hash:
                    skipped += 1
                    logging.info(f"🟡 跳過未變更事件: {google_event['summary']}")
                    continue

                # 如果事件 ID 已存在，先刪除再插入
                if event_id in google_events_dict:
                    try:
                        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
                        logging.info(f"❌ 刪除重複事件: {google_event['summary']}")
                    except Exception as e:
                        logging.warning(f"⚠️ 刪除重複事件失敗: {e}")

                try:
                    service.events().insert(calendarId=calendar_id, body=google_event).execute()
                    added += 1
                    logging.info(f"🆕 新增事件: {google_event['summary']}")
                except Exception as e:
                    logging.error(f"⚠️ 插入事件失敗: {e}")

        # 先處理週期事件
        for event in recurring_events:
            # 週期事件 - 使用 UID 生成一致的 ID
            event_id = hashlib.md5((calendar_id + '|' + 
                                  (event.uid or event.name) + '|' + 
                                  'recurring'
                                  ).encode()).hexdigest()
            
            google_event = convert_ics_to_google_event(event)
            google_event['id'] = event_id
            event_hash = compute_event_hash(event)
            new_sync[event_id] = event_hash

            if last_sync.get(event_id) == event_hash:
                skipped += 1
                logging.info(f"🟡 跳過未變更事件: {google_event['summary']}")
                continue

            # 如果事件 ID 已存在，先刪除再插入
            if event_id in google_events_dict:
                try:
                    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
                    logging.info(f"❌ 刪除重複事件: {google_event['summary']}")
                except Exception as e:
                    logging.warning(f"⚠️ 刪除重複事件失敗: {e}")

            try:
                service.events().insert(calendarId=calendar_id, body=google_event).execute()
                added += 1
                logging.info(f"🆕 新增事件: {google_event['summary']}")
            except Exception as e:
                logging.error(f"⚠️ 插入事件失敗: {e}")

        # 再處理例外事件
        for event in exception_events:
            # 例外事件 - 使用 UID + 日期生成 ID
            event_id = hashlib.md5((calendar_id + '|' + 
                                  (event.uid or event.name) + '|' + 
                                  event.begin.date().isoformat()
                                  ).encode()).hexdigest()
            
            google_event = convert_ics_to_google_event(event)
            google_event['id'] = event_id
            event_hash = compute_event_hash(event)
            new_sync[event_id] = event_hash

            if last_sync.get(event_id) == event_hash:
                skipped += 1
                logging.info(f"🟡 跳過未變更事件: {google_event['summary']}")
                continue

            # 如果事件 ID 已存在，先刪除再插入
            if event_id in google_events_dict:
                try:
                    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
                    logging.info(f"❌ 刪除重複事件: {google_event['summary']}")
                except Exception as e:
                    logging.warning(f"⚠️ 刪除重複事件失敗: {e}")

            try:
                service.events().insert(calendarId=calendar_id, body=google_event).execute()
                added += 1
                logging.info(f"🆕 新增事件: {google_event['summary']}")
            except Exception as e:
                logging.error(f"⚠️ 插入事件失敗: {e}")

        # 儲存同步紀錄
        save_last_sync(new_sync, calendar_id)
        logging.info(f"✅ 同步完成：新增 {added}，更新 {updated}，跳過 {skipped}，刪除 {deleted}")
    except Exception as e:
        logging.error(f"同步過程中發生錯誤: {e}")

# ---------- MAIN ----------
if __name__ == "__main__":
    logging.info(f"開始同步 {config.DEFAULT_JSON_FILE} 至 Google Calendar...")
    sync_to_google(config.DEFAULT_JSON_FILE)
