import os
import requests
from datetime import datetime
from groq import Groq

LINE_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
SERPER_API_KEY = os.environ["SERPER_API_KEY"]

HEADERS = {
    "Authorization": f"Bearer {LINE_TOKEN}",
    "Content-Type": "application/json"
}

def search_google(query: str) -> str:
    resp = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "gl": "tw", "hl": "zh-tw", "num": 10}
    )
    data = resp.json()
    results = []
    for item in data.get("organic", []):
        results.append(f"標題：{item.get('title')}\n連結：{item.get('link')}\n摘要：{item.get('snippet')}")
    return "\n\n".join(results)

def search_competitions():
    today = datetime.now().strftime("%Y年%m月%d日")
    queries = [
        "2025 2026 台灣 金融科技競賽 報名",
        "2025 2026 台灣 AI創新競賽 大學生 報名中",
        "2025 2026 台灣 創新創業比賽 報名截止",
        "2025 2026 台灣 資訊應用競賽 大學生"
    ]
    all_results = []
    for q in queries:
        result = search_google(q)
        if result:
            all_results.append(result)
    combined = "\n\n---\n\n".join(all_results)

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": f"""今天是 {today}。以下是 Google 搜尋結果：
{combined}

請從以上搜尋結果中，找出【目前確認開放報名】的比賽，截止日期必須在 {today} 之後。
我的專題是「智慧保險系統」，主題：金融科技、AI應用、網站設計、線上諮詢媒合。

規則：
1. 只列確認開放報名的比賽，截止日期在今天之後
2. 找不到就說「目前查無開放報名的比賽」
3. 不可以用「通常在某月」這種說法
4. 沒有實際截止日期和連結的不列出

每個比賽格式：
🏆 比賽名稱
🏢 主辦：xxx
📅 截止：xxxx年xx月xx日
👥 人數：x~x人
📋 需準備：xxx
🔗 連結：https://...
💡 適合原因：一句話

繁體中文回答。"""
        }],
        max_tokens=2000
    )
    return response.choices[0].message.content

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
            "輸入「搜尋比賽」可隨時重新查詢"
        )
    except Exception as e:
        try:
            send_line_message(f"❌ 競賽搜尋發生錯誤：{str(e)}")
        except:
            pass
        raise

if __name__ == "__main__":
    main()
