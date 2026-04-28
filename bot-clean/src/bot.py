"""
競賽小幫手 - 每日推播腳本
由 GitHub Actions 每天早上 9:00 自動執行
不需要伺服器，完全免費
"""
import os
import requests
from datetime import datetime

LINE_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

HEADERS = {
    "Authorization": f"Bearer {LINE_TOKEN}",
    "Content-Type": "application/json"
}

PROJECT_DESCRIPTION = """
我的專題作品是「智慧保險系統」，主要功能：
1. 網站平台，能配對線上真人保險員進行諮詢
2. 使用者可上傳自身保單資料，由 AI 保險員進行分析
3. AI 將諮詢記錄與保單分析彙總給真人保險員
4. 讓使用者透過網站就能輕鬆處理保險事務

技術核心與主題：
- 金融科技（FinTech）
- 網站設計（Web Design）
- AI 人工智慧應用（AI Application）
- 資料分析與視覺化
- 線上諮詢媒合系統
"""

def search_competitions():
    """Use Gemini REST API to find relevant competitions"""
    today = datetime.now().strftime("%Y年%m月%d日")

    prompt = f"""今天是 {today}。

請幫我列出台灣適合大學生參加、與以下專題相關的比賽：

{PROJECT_DESCRIPTION}

請整理出 3-5 個最相關的比賽，每個比賽請提供：
- 比賽名稱
- 主辦單位
- 報名截止日期（依歷年慣例估計）
- 比賽主題/類別
- 組員人數限制
- 需要準備的資料
- 參賽資格條件
- 官方網站連結
- 為何適合我的智慧保險系統專題（1-2句）

請用繁體中文回答，格式清晰易讀。"""

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def send_line_message(text):
    """Send push message to LINE user, splitting if over 5000 chars"""
    max_len = 4900
    chunks = []
    while len(text) > max_len:
        split = text.rfind('\n', 0, max_len)
        if split == -1:
            split = max_len
        chunks.append(text[:split])
        text = text[split:].lstrip('\n')
    chunks.append(text)

    for i, chunk in enumerate(chunks):
        payload = {
            "to": LINE_USER_ID,
            "messages": [{"type": "text", "text": chunk}]
        }
        resp = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers=HEADERS,
            json=payload
        )
        resp.raise_for_status()
        print(f"Message {i+1}/{len(chunks)} sent: HTTP {resp.status_code}")


def main():
    print(f"[{datetime.now()}] Starting competition search...")

    today_str = datetime.now().strftime("%Y/%m/%d")
    send_line_message(
        f"🏆 競賽情報日報\n"
        f"📅 {today_str}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"正在搜尋最新比賽資訊...\n"
        f"（智慧保險系統專題適用）"
    )

    result = search_competitions()
    print("Search done, sending result...")
    send_line_message(result)

    send_line_message(
        "━━━━━━━━━━━━━━━\n"
        "💡 報名前請至官方網站確認最新資訊\n"
        "📌 明天同一時間再次推播\n"
        "傳「比賽」可隨時手動查詢"
    )
    print("All done!")


if __name__ == "__main__":
    main()
