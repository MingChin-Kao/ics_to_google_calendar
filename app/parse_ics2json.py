from ics import Calendar
import requests
import json
import config
import logging
from datetime import datetime

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
    
    # 第一步：按 UID 分組事件
    events_by_uid = {}
    for event in calendar.events:
        if event.uid not in events_by_uid:
            events_by_uid[event.uid] = []
        events_by_uid[event.uid].append(event)
    
    # 第二步：處理每組事件，添加例外日期
    processed_events = []
    for uid, events_list in events_by_uid.items():
        # 如果這個 UID 只有一個事件，直接添加
        if len(events_list) == 1:
            processed_events.append(events_list[0])
            continue
        
        # 分離週期事件和單次事件
        recurring_events = []
        single_events = []
        for event in events_list:
            has_rrule = False
            for item in event.extra:
                if item.name.lower() == "rrule":
                    has_rrule = True
                    break
            
            if has_rrule:
                recurring_events.append(event)
            else:
                single_events.append(event)
        
        # 如果沒有週期事件，全部添加
        if not recurring_events:
            processed_events.extend(events_list)
            continue
        
        # 對於每個週期事件，添加例外日期
        for recurring_event in recurring_events:
            # 檢查並初始化 EXDATE 屬性
            has_exdate = False
            exdate_list = []
            
            for item in recurring_event.extra:
                if item.name.lower() == "exdate":
                    has_exdate = True
                    exdate_list = item.value.split(",")
                    break
            
            # 為每個單次事件的日期添加到 EXDATE
            for single_event in single_events:
                # 檢查單次事件是否在週期事件範圍內
                # 1. 檢查開始時間 - 單次事件應在週期事件開始之後
                # 2. 如果週期事件有結束時間，確保單次事件在結束前
                is_in_range = recurring_event.begin <= single_event.begin
                
                # 檢查是否有 UNTIL 值 (週期結束時間)
                has_until = False
                until_time = None
                
                for item in recurring_event.extra:
                    if item.name.lower() == "rrule":
                        rrule_parts = item.value.split(";")
                        for part in rrule_parts:
                            if part.startswith("UNTIL="):
                                has_until = True
                                until_str = part.split("=")[1]
                                # 嘗試多種方式解析 UNTIL 時間
                                try:
                                    # 首先移除可能的時區信息
                                    base_time_str = until_str
                                    if "+" in base_time_str:
                                        base_time_str = base_time_str.split("+")[0]
                                    elif "Z" in base_time_str:
                                        base_time_str = base_time_str.replace("Z", "")
                                    
                                    # 使用正確的格式解析
                                    if "T" in base_time_str:
                                        until_time = datetime.strptime(base_time_str, "%Y%m%dT%H%M%S")
                                    else:
                                        until_time = datetime.strptime(base_time_str, "%Y%m%d")
                                    
                                    logging.debug(f"成功解析 UNTIL 時間: {until_str} -> {until_time}")
                                except Exception as e:
                                    logging.warning(f"無法解析 UNTIL 時間: {until_str}, 錯誤: {e}")
                
                if is_in_range:
                    # 格式化時間為 YYYYMMDDTHHMMSSZ
                    exdate = single_event.begin.strftime("%Y%m%dT%H%M%SZ")
                    if exdate not in exdate_list:
                        exdate_list.append(exdate)
            
            # 如果有例外日期，更新或添加 EXDATE 屬性
            if exdate_list:
                exdate_value = ",".join(exdate_list)
                if has_exdate:
                    # 更新現有 EXDATE
                    for item in recurring_event.extra:
                        if item.name.lower() == "exdate":
                            item.value = exdate_value
                            break
                else:
                    # 替代方案，不使用 ContentLine
                    # 直接記錄要添加的例外日期，在 JSON 轉換時處理
                    # 不修改原始事件的 extra
                    if not hasattr(recurring_event, 'exdate_to_add'):
                        recurring_event.exdate_to_add = exdate_value
                    else:
                        recurring_event.exdate_to_add = exdate_value
            
            processed_events.append(recurring_event)
        
        # 修改篩選單次事件的部分
        filtered_single_events = []
        for single_event in single_events:
            # 添加一個標記表示這是週期事件的例外
            single_event.is_recurrence_exception = True
            single_event.recurrence_id = single_event.begin.strftime("%Y%m%dT%H%M%SZ")
            
            # 無論是否為例外，都添加單次事件，讓它們可以出現在新時間點
            filtered_single_events.append(single_event)

        # 添加所有單次事件，包括例外事件
        processed_events.extend(filtered_single_events)
    
    # 第三步：轉換處理後的事件為 JSON
    result_events = []
    for event in processed_events:
        try:
            rrule = None
            exdate = None
            
            for item in event.extra:
                if item.name.lower() == "rrule":
                    rrule = item.value
                elif item.name.lower() == "exdate":
                    exdate = item.value
            
            # 檢查是否有記錄的例外日期
            if hasattr(event, 'exdate_to_add'):
                exdate = event.exdate_to_add
            
            event_json = {
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
            }
            
            # 添加例外日期到 JSON
            if exdate:
                event_json["exdate"] = exdate
            
            result_events.append(event_json)
            
        except Exception as e:
            logging.error(f"解析事件失敗: {e}")
    
    return result_events

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
