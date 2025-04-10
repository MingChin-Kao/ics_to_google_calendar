from parse_ics2json import fetch_ics_from_url, calendar_to_json, save_json_to_file
from main import sync_to_google
import config
import logging

if __name__ == "__main__":
    # 初始化 logging
    logging.basicConfig(
        filename=config.LOG_FILE,
        level=getattr(logging, config.LOG_LEVEL.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # 新增 StreamHandler 將 log 輸出到終端機
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.LOG_LEVEL.upper(), "INFO"))
    console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    logging.getLogger().addHandler(console_handler)
    
    try:
        # Step 1: Fetch ICS and convert to JSON
        calendar = fetch_ics_from_url(config.ICS_URL)
        events_json = calendar_to_json(calendar)
        save_json_to_file(events_json, config.OUTPUT_JSON_FILE)
        logging.info("ICS 轉換為 JSON 並儲存完成")

        # Step 2: Sync JSON to Google Calendar
        sync_to_google(config.OUTPUT_JSON_FILE)
    except Exception as e:
        logging.error(f"執行過程中發生錯誤: {e}")