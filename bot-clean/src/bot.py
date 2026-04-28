"""
競賽小幫手 - 每日推播腳本
由 GitHub Actions 每天早上 9:00 自動執行
"""
import os
import requests
from datetime import datetime

LINE_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

HEADERS = {
    "Authorization": f"Bearer {LINE_TOKEN}",
    "Content-Type": "application/json"
}

PROJECT_DESCRIPTION = """
智慧保險系統：
1. 網站配對線上真人保險員諮詢
2. 使用者上傳保單由 AI 分析
3. AI 彙總資訊給真人保險員
技術：金融科技、AI應用、網站設計
"""

def search_competitions():
    today = datetime.now().strftime("%Y年%m月%d日")
    prompt = f"""今天是 {today}。

請幫我列出台灣適合大學生參加、與以下專題相關的比賽：
{PROJECT_DESCRIPTION}

請整理出 3-5 個最相關的比賽，每個比賽提供：
- 比賽名稱
- 主辦單位
- 報名截止日期（依歷年慣例估計）
- 比賽主題/類別
- 組員人數限制
- 需要準備的資料
- 官方網站連結
- 為何適合我的智慧保險系統專題（1-2句）

請用繁體中文回答，格式清晰易讀。"""

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 3000
        },
        timeout=60
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def send_line_message(text):
    max_len = 4900
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split = text.rfind('\n', 0, max_len) or max_len
        chunks.append(text[:split])
        text = text[split:].lstrip('\n')
    for i, chunk in enumerate(chunks):
        payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": chunk}]}
        resp = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers=HEADERS, json=payload
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
