"""
競賽小幫手 - Webhook 伺服器
部署在 Render，24/7 接收 LINE 訊息
"""
import os
import hashlib
import hmac
import base64
import json
import threading
import logging
from flask import Flask, request, abort
import requests
from datetime import datetime
import google.generativeai as genai

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

HEADERS = {
    "Authorization": f"Bearer {LINE_TOKEN}",
    "Content-Type": "application/json"
}

PROJECT_INFO = "智慧保險系統：AI配對保險員諮詢、保單AI分析、FinTech+網站設計+AI應用"


def verify_signature(body: bytes, signature: str) -> bool:
    h = hmac.new(LINE_SECRET.encode('utf-8'), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(h).decode(), signature)


def reply(reply_token: str, text: str):
    max_len = 4900
    msgs = []
    while text and len(msgs) < 5:
        if len(text) <= max_len:
            msgs.append({"type": "text", "text": text})
            break
        split = text.rfind('\n', 0, max_len) or max_len
        msgs.append({"type": "text", "text": text[:split]})
        text = text[split:].lstrip('\n')

    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers=HEADERS,
        json={"replyToken": reply_token, "messages": msgs}
    )


def search_now():
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(model_name="gemini-2.0-flash", tools="google_search")
    today = datetime.now().strftime("%Y年%m月%d日")
    resp = model.generate_content(
        f"今天是{today}。搜尋台灣目前開放報名、適合「{PROJECT_INFO}」參加的比賽，"
        f"列出3個最相關的，每個包含：名稱、截止日期、主題、組員人數、需要資料、報名連結。繁體中文，簡潔格式。"
    )
    return resp.text


def handle_async(reply_token: str, msg: str):
    try:
        low = msg.strip().lower()
        if any(k in low for k in ['比賽', '競賽', '搜尋', '找', '報名']):
            reply(reply_token, "🔍 搜尋中，約需30秒，請稍候...")
            result = search_now()
            reply(reply_token, f"🏆 最新比賽（{datetime.now().strftime('%m/%d')}）\n━━━━━━\n{result}")
        elif any(k in low for k in ['說明', 'help', '幫助', '功能']):
            reply(reply_token,
                "🤖 競賽小幫手\n"
                "━━━━━━━━━\n"
                "📌 每天早上 9:00 自動推播比賽\n\n"
                "💬 指令：\n"
                "  「比賽」→ 立即搜尋\n"
                "  「說明」→ 使用說明\n"
                "  「我的專題」→ 查看專題資訊"
            )
        elif any(k in low for k in ['專題', '作品']):
            reply(reply_token,
                "📋 智慧保險系統\n"
                "━━━━━━━━━\n"
                "• AI 配對線上真人保險員\n"
                "• 保單 AI 自動分析\n"
                "• 諮詢報告彙整給保險員\n\n"
                "🔑 主題：FinTech / AI / 網站設計\n\n"
                "傳「比賽」搜尋適合賽事！"
            )
        else:
            reply(reply_token, "Hi！傳「比賽」搜尋最新賽事 🏆\n傳「說明」查看功能")
    except Exception as e:
        logger.error(f"handle error: {e}")
        reply(reply_token, f"❌ 發生錯誤：{str(e)[:100]}")


@app.route("/webhook", methods=["POST"])
def webhook():
    sig = request.headers.get("X-Line-Signature", "")
    body = request.get_data()

    if LINE_SECRET and not verify_signature(body, sig):
        abort(400)

    try:
        events = json.loads(body).get("events", [])
    except Exception:
        abort(400)

    for ev in events:
        if ev.get("type") == "message" and ev.get("message", {}).get("type") == "text":
            t = threading.Thread(
                target=handle_async,
                args=(ev.get("replyToken", ""), ev["message"]["text"]),
                daemon=True
            )
            t.start()

    return "OK", 200


@app.route("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}, 200


@app.route("/")
def index():
    return "🏆 競賽小幫手 LINE Bot is running!", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
