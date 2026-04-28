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
    today = datetime.now().strftime("%Y年%m月%d日")
    prompt = (
        f"今天是{today}。請列出台灣適合大學生參加、與以下主題相關的比賽：「{PROJECT_INFO}」。"
        f"涵蓋金融科技、AI應用、網站設計、創新創業類。"
        f"每個比賽列出：名稱、主辦單位、大約報名時間（依歷年慣例）、組員人數、需準備資料、官網連結。"
        f"列出5個，繁體中文，格式清晰。"
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash-lite:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def push(user_id: str, text: str):
    """Push message to user (no time limit, unlike reply token)"""
    max_len = 4900
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split = text.rfind('\n', 0, max_len) or max_len
        chunks.append(text[:split])
        text = text[split:].lstrip('\n')

    for chunk in chunks[:5]:
        requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers=HEADERS,
            json={"to": user_id, "messages": [{"type": "text", "text": chunk}]}
        )


def handle_async(reply_token: str, user_id: str, msg: str):
    try:
        low = msg.strip().lower()
        if any(k in low for k in ['比賽', '競賽', '搜尋', '找', '報名']):
            # 立刻用 reply 回應（在30秒內），然後用 push 傳結果（無時間限制）
            reply(reply_token, "🔍 搜尋比賽中，結果稍後送達...")
            result = search_now()
            push(user_id, f"🏆 最新比賽（{datetime.now().strftime('%m/%d')}）\n━━━━━━\n{result}")
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
        try:
            push(user_id, f"❌ 發生錯誤：{str(e)[:100]}")
        except:
            pass


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
            user_id = ev.get("source", {}).get("userId", "")
            t = threading.Thread(
                target=handle_async,
                args=(ev.get("replyToken", ""), user_id, ev["message"]["text"]),
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
