import os
import hashlib
import hmac
import base64
import json
import threading
from flask import Flask, request, abort
import requests
from datetime import datetime
from groq import Groq

app = Flask(__name__)

LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")

HEADERS = {
    "Authorization": f"Bearer {LINE_TOKEN}",
    "Content-Type": "application/json"
}

conversation_history = {}

def verify_signature(body: bytes, signature: str) -> bool:
    hash_val = hmac.new(LINE_SECRET.encode('utf-8'), body, hashlib.sha256).digest()
    expected = base64.b64encode(hash_val).decode('utf-8')
    return hmac.compare_digest(expected, signature)

def reply_message(reply_token: str, text: str):
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    requests.post("https://api.line.me/v2/bot/message/reply", headers=HEADERS, json=payload)

def push_message(user_id: str, text: str):
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

def search_competitions_quick():
    today = datetime.now().strftime("%Y年%m月%d日")
    queries = [
        "2025 2026 台灣 金融科技競賽 報名",
        "2025 2026 台灣 AI創新競賽 大學生 報名中",
        "2025 2026 台灣 創新創業比賽 報名截止"
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

請找出【目前確認開放報名】的比賽（截止日期在 {today} 之後）。
我的專題：智慧保險系統，主題：金融科技、AI應用、網站設計。
規則：只列有實際截止日期和連結的比賽；找不到就說目前查無；不可說通常在某月。
格式：🏆名稱 🏢主辦 📅截止 👥人數 🔗連結 💡適合原因。繁體中文。"""
        }],
        max_tokens=2000
    )
    return response.choices[0].message.content

def chat_with_groq(user_id: str, user_message: str) -> str:
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": user_message})

    if len(conversation_history[user_id]) > 10:
        conversation_history[user_id] = conversation_history[user_id][-10:]

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": """你是「競賽小幫手」，專門協助使用者參加比賽。
使用者的專題是「智慧保險系統」：網站平台配對保險員諮詢、AI分析保單、金融科技應用。
你可以幫忙：比賽準備建議、簡報架構、團隊分工、評審問題預測等。
用繁體中文回答，口氣友善親切。
如果使用者問比賽資訊，提醒他輸入「比賽」來搜尋最新賽事。"""
            }
        ] + conversation_history[user_id],
        max_tokens=1000
    )

    reply = response.choices[0].message.content
    conversation_history[user_id].append({"role": "assistant", "content": reply})
    return reply

def handle_search_async(user_id: str):
    try:
        result = search_competitions_quick()
        today_str = datetime.now().strftime("%m/%d")
        push_message(user_id, f"🏆 比賽情報（{today_str}）\n━━━━━━━━━━━━━━━\n{result}")
        push_message(user_id, "━━━━━━━━━━━━━━━\n💡 以上為確認開放報名的比賽\n輸入「比賽」可重新查詢")
    except Exception as e:
        print(f"Search error: {e}")
        push_message(user_id, f"❌ 搜尋時發生錯誤，請稍後再試\n{str(e)[:100]}")

def handle_message_async(reply_token: str, user_id: str, user_message: str):
    try:
        msg_lower = user_message.strip().lower()

        if any(kw in msg_lower for kw in ['比賽', '競賽', '搜尋比賽', '找比賽', '報名']):
            reply_message(reply_token, "🔍 收到！正在搜尋最新比賽...\n結果約1分鐘內會送過來，請稍候 ⏳")
            thread = threading.Thread(target=handle_search_async, args=(user_id,))
            thread.daemon = True
            thread.start()

        elif any(kw in msg_lower for kw in ['說明', 'help', '怎麼用', '功能']):
            reply_message(reply_token,
                "🤖 競賽小幫手使用說明\n━━━━━━━━━\n"
                "📌 每天早上 9 點自動推播比賽\n\n"
                "🔍 指令：\n"
                "  「比賽」→ 搜尋最新賽事\n"
                "  「說明」→ 查看此說明\n\n"
                "💬 也可以直接聊天！\n"
                "  問我比賽準備、簡報建議、分工方式等等"
            )

        else:
            reply = chat_with_groq(user_id, user_message)
            reply_message(reply_token, reply)

    except Exception as e:
        print(f"Error: {e}")
        reply_message(reply_token, "❌ 發生錯誤，請稍後再試")

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

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}, 200

@app.route("/", methods=["GET"])
def index():
    return "LINE Bot Competition Finder is running! 🏆", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
