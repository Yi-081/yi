import os
import requests
from datetime import datetime
import google.generativeai as genai

LINE_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

HEADERS = {
    "Authorization": f"Bearer {LINE_TOKEN}",
    "Content-Type": "application/json"
}

def search_competitions():
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        tools="google_search"
    )
    today = datetime.now().strftime("%Y年%m月%d日")
    prompt = f"""今天是 {today}，請用 Google 搜尋找出台灣【現在實際開放報名】的學生競賽。

請搜尋這些關鍵字：
- "2025 金融科技競賽 報名"
- "2025 AI創新競賽 大學生 台灣"
- "2025 創新創業比賽 報名中"
- "2026 資訊應用競賽 報名"

我的專題是「智慧保險系統」，主題涵蓋：金融科技、AI應用、網站設計、線上諮詢媒合。

【重要規則】
1. 只列出【目前確認開放報名】的比賽，截止日期必須在 {today} 之後
2. 如果找不到確認開放的比賽，直接說「目前查無開放報名的比賽，建議明天再查」
3. 絕對不可以用「通常在某月」這種不確定的說法
4. 沒有實際截止日期和報名連結的比賽一律不列出

每個比賽用以下格式：
🏆 比賽名稱
🏢 主辦：xxx
📅 報名截止：xxxx年xx月xx日
👥 組員人數：x~x人
📋 需準備：xxx
🔗 報名連結：https://...
💡 適合原因：一句話

請用繁體中文回答。"""
    response = model.generate_content(prompt)
    return response.text

def send_line_message(text):
    max_len = 4900
    messages = []
    while len(text) > max_len:
        split_point = text.rfind('\n', 0, max_len)
        if split_point == -1:
            split_point = max_len
        messages.append(text[:split_point])
        text = text[split_point:].lstrip('\n')
    messages.append(text)
    for i, msg in enumerate(messages):
        payload = {
            "to": LINE_USER_ID,
            "messages": [{"type": "text", "text": msg}]
        }
        resp = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers=HEADERS,
            json=payload
        )
        resp.raise_for_status()
        print(f"Message {i+1}/{len(messages)} sent: {resp.status_code}")

def main():
    print(f"[{datetime.now()}] Starting competition search...")
    try:
        today_str = datetime.now().strftime("%Y/%m/%d")
        send_line_message(
            f"🏆 每日競賽情報\n📅 {today_str}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"正在搜尋今日開放報名的比賽...\n"
            f"（智慧保險系統專題適用）"
        )
        competitions = search_competitions()
        send_line_message(competitions)
        send_line_message(
            "━━━━━━━━━━━━━━━\n"
            "💡 以上為今日確認開放報名的比賽\n"
            "📌 下次推播：明天早上 9 點\n"
            "輸入「比賽」可隨時重新查詢"
        )
    except Exception as e:
        try:
            send_line_message(f"❌ 競賽搜尋發生錯誤：{str(e)}")
        except:
            pass
        raise

if __name__ == "__main__":
    main()
