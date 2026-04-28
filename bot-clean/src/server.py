import os
import hashlib
import hmac
import base64
import json
import threading
from flask import Flask, request, abort
import requests
from datetime import datetime
import google.generativeai as genai

app = Flask(__name__)

LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

HEADERS = {
    "Authorization": f"Bearer {LINE_TOKEN}",
    "Content-Type": "application/json"
}

def verify_signature(body: bytes, signature: str) -> bool:
    hash_val = hmac.new(LINE_SECRET.encode('utf-8'), body, hashlib.sha256).digest()
    expected = base64.b64encode(hash_val).decode('utf-8')
    return hmac.compare_digest(expected, signature)

def reply_message(reply_token: str, text: str):
    """立刻回覆（有時效限制）"""
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    requests.post("https://api.line.me/v2/bot/message/reply", headers=HEADERS, json=payload)

def push_message(user_id: str, text: str):
    """主動推送（無時效限制，搜尋完再送）"""
    max_len = 4900
    messages = []
    while len(text) > max_len:
        split_point = text.rfind('\n', 0, max_len)
        if split_point == -1:
            split_point = max_len
        messages.append(text[:split_point])
        text = text[split_point:].lstrip('\n')
    messages.append(text)

    for msg in messages:
        payload = {"to": user_id, "messages": [{"type": "text", "text": msg}]}
        requests.post("https://api.line.me/v2/bot/message/push", headers=HEADERS, json=payload)

def search_competitions_quick():
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(model_name="gemini-2.0-flash", tools="google_search")
    today = datetime.now().strftime("%Y年%m月%d日")
    prompt = f"""今天是 {today}，請用 Google 搜尋台灣【現在確認開放報名】的學生競賽。
搜尋：2025金融科技競賽報名、2025 AI創新競賽大學生台灣、創新創業比賽報名中。
規則：只列截止日期在 {today} 之後的比賽；每個要有實際日期和報名連結；不能說通常在某月；找不到就說目前查無開放比賽。
格式每筆：
🏆 名稱
🏢 主辦：xxx
📅 截止：xxxx年xx月xx日
👥 人數：x~x人
🔗 連結：https://...
💡 適合原因：一句話
繁體中文。"""
    response = model.generate_content(prompt)
    return response.text

def handle_search_async(user_id: str):
    """背景執行搜尋，完成後 push 結果"""
    try:
        result = search_competitions_quick()
        today_str = datetime.now().strftime("%m/%d")
        push_message(user_id, f"🏆 比賽情報（{today_str}）\n━━━━━━━━━━━━━━━\n{result}")
        push_message(user_id, "━━━━━━━━━━━━━━━\n💡 以上為確認開放報名的比賽\n輸入「比賽」可重新查詢")
    except Exception as e:
        push_message(user_id, f"❌ 搜尋時發生錯誤，請稍後再試")

def handle_message_async(reply_token: str, user_id: str, user_message: str):
    try:
        msg_lower = user_message.strip().lower()

        if any(kw in msg_lower for kw in ['比賽', '競賽', '搜尋', '找', '報名', 'competition']):
            # 立刻回覆收到，讓使用者知道在處理
            reply_message(reply_token, "🔍 收到！正在搜尋最新比賽...\n結果約1分鐘內會送過來，請稍候 ⏳")
            # 背景搜尋完再 push
            thread = threading.Thread(target=handle_search_async, args=(user_id,))
            thread.daemon = True
            thread.start()

        elif any(kw in msg_lower for kw in ['說明', '幫助', 'help', '怎麼用', '功能']):
            reply_message(reply_token,
                "🤖 競賽小幫手使用說明\n━━━━━━━━━\n"
                "📌 每天早上 9 點自動推播比賽資訊\n\n"
                "🔍 手動查詢：\n"
                "  輸入「比賽」→ 搜尋最新賽事\n"
                "  輸入「我的專題」→ 查看專題資訊\n\n"
                "🎯 專為「智慧保險系統」客製化\n"
                "   涵蓋：金融科技/AI/網站設計類比賽"
            )

        elif any(kw in msg_lower for kw in ['專題', '作品', '介紹']):
            reply_message(reply_token,
                "📋 智慧保險系統\n━━━━━━━━━\n"
                "🎯 核心功能：\n"
                "• 配對線上真人保險員諮詢\n"
                "• AI 分析個人保單\n"
                "• AI 彙總報告給保險員\n\n"
                "🔑 技術主題：金融科技、AI應用、網站設計\n\n"
                "輸入「比賽」搜尋適合的賽事！"
            )

        else:
            reply_message(reply_token,
                "Hi！我是競賽小幫手 🏆\n"
                "輸入「比賽」→ 搜尋最新賽事\n"
                "輸入「說明」→ 查看使用方式"
            )

    except Exception as e:
        print(f"Error: {e}")

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data()
    if LINE_SECRET and not verify_signature(body, signature):
        abort(400)
    try:
        events = json.loads(body)["events"]
    except Exception:
        abort(400)
    for event in events:
        if event.get("type") != "message":
            continue
        if event.get("message", {}).get("type") != "text":
            continue
        reply_token = event.get("replyToken", "")
        user_id = event.get("source", {}).get("userId", "")
        user_message = event["message"]["text"]
        thread = threading.Thread(target=handle_message_async, args=(reply_token, user_id, user_message))
        thread.daemon = True
        thread.start()
    return "OK", 200

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}, 200

@app.route("/", methods=["GET"])
def index():
    return "LINE Bot Competition Finder is running! 🏆", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
