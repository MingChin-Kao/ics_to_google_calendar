from ics import Calendar
import requests
import json
import config
import logging

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

def fetch_ics_from_url(url: str) -> Calendar:
    logging.info(f"從 URL 獲取 ICS 檔案: {url}")
    response = requests.get(url)
    response.raise_for_status()
    return Calendar(response.text)

def calendar_to_json(calendar):
    logging.info("將 Calendar 轉換為 JSON 格式")
    events = []
    for event in calendar.events:
        try:
            rrule = None
            for item in event.extra:
                if item.name.lower() == "rrule":
                    rrule = item.value
                    break

            events.append({
                "uid": event.uid,
                "name": event.name,
                "begin": str(event.begin),
                "end": str(event.end),
                "created": str(event.created),
                "last_modified": str(event.last_modified),
                "location": event.location,
                "description": event.description,
                "recurrence_rules": rrule,
                "status": event.status,
            })
        except Exception as e:
            logging.error(f"解析事件失敗: {e}")
    return events

def save_json_to_file(events: list, output_path: str):
    logging.info(f"將事件 JSON 儲存到檔案: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    try:
        calendar = fetch_ics_from_url(config.ICS_URL)
        events_json = calendar_to_json(calendar)
        save_json_to_file(events_json, config.OUTPUT_JSON_FILE)
        logging.info("ICS 轉換為 JSON 並儲存完成")
    except Exception as e:
        logging.error(f"執行過程中發生錯誤: {e}")
