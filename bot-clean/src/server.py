import os
import hashlib
import hmac
import base64
import json
import threading
import re
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

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1EnI7ZuvLCF2F4oqW-EeDRW94Uv-uMCsvciN-bh9tOKE/edit?usp=sharing"

conversation_history = {}
pending_competitions = {}
push_time = {"hour": 9, "minute": 0}  # 預設早上 9:00
waiting_for_time = set()  # 記錄哪些 user 正在設定時間

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

def parse_time_input(text: str):
    text = text.strip().replace(" ", "")

    # 判斷上午/下午/晚上
    is_pm = any(kw in text for kw in ['下午', '晚上', '傍晚', '夜'])
    is_am = any(kw in text for kw in ['早上', '上午', '早', '凌晨'])

    # 移除中文時段詞再解析
    clean = re.sub(r'(早上|上午|下午|晚上|傍晚|凌晨|早|夜)', '', text)

    h, m = None, None

    # 7點半
    match = re.search(r'(\d{1,2})點半', clean)
    if match:
        h, m = int(match.group(1)), 30

    # 7點30分 / 7點30
    if h is None:
        match = re.search(r'(\d{1,2})點(\d{1,2})分?', clean)
        if match:
            h, m = int(match.group(1)), int(match.group(2))

    # 7點 / 7時
    if h is None:
        match = re.search(r'(\d{1,2})[點時]', clean)
        if match:
            h, m = int(match.group(1)), 0

    # 7:30 / 7：30
    if h is None:
        match = re.search(r'(\d{1,2})[：:](\d{2})', clean)
        if match:
            h, m = int(match.group(1)), int(match.group(2))

    # 7.30
    if h is None:
        match = re.search(r'(\d{1,2})\.(\d{2})', clean)
        if match:
            h, m = int(match.group(1)), int(match.group(2))

    # 730 / 0730
    if h is None:
        match = re.fullmatch(r'(\d{3,4})', clean)
        if match:
            t = match.group(1).zfill(4)
            h, m = int(t[:2]), int(t[2:])

    # 純數字 7 或 17
    if h is None:
        match = re.fullmatch(r'(\d{1,2})', clean)
        if match:
            h, m = int(match.group(1)), 0

    if h is None:
        return None

    # 套用上午/下午邏輯
    if is_pm and h != 12 and h < 12:
        h += 12  # 晚上7點 → 19點
    if is_am and h == 12:
        h = 0    # 早上12點 → 0點

    return h, m

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

請將每筆比賽用 [COMPETITION] 標記分隔，格式如下：
[COMPETITION]
🏆 比賽名稱
🏢 主辦：xxx
📅 截止：xxxx年xx月xx日
👥 人數：x~x人
🔗 連結：https://...
💡 適合原因：一句話
[/COMPETITION]

繁體中文。"""
        }],
        max_tokens=3000
    )
    return response.choices[0].message.content

def parse_competitions(raw: str):
    items = re.findall(r'\[COMPETITION\](.*?)\[/COMPETITION\]', raw, re.DOTALL)
    return [item.strip() for item in items]

def chat_with_groq(user_id: str, user_message: str) -> str:
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": user_message})

    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": """你是「競賽小幫手」，是使用者的好朋友兼比賽顧問，個性活潑、親切、有點幽默。
使用者的專題是「智慧保險系統」：網站平台配對保險員諮詢、AI分析保單、金融科技應用。

你的說話風格：
- 像朋友聊天，不要太正式
- 可以用輕鬆的語氣詞，例如「欸」「哈哈」「不用擔心」「其實蠻簡單的」
- 回答不要太長，重點講清楚就好
- 可以主動關心使用者的進度

你擅長幫忙：
- 比賽準備建議、簡報架構
- 團隊分工、時程規劃
- 預測評審可能問的問題
- 幫使用者分析專題優劣勢

如果使用者問比賽資訊，提醒他輸入「比賽」來搜尋最新賽事。
用繁體中文回答。"""
            }
        ] + conversation_history[user_id],
        max_tokens=1000
    )

    reply = response.choices[0].message.content
    conversation_history[user_id].append({"role": "assistant", "content": reply})
    return reply

def handle_search_async(user_id: str):
    try:
        raw = search_competitions_quick()
        competitions = parse_competitions(raw)
        today_str = datetime.now().strftime("%m/%d")

        if not competitions:
            push_message(user_id,
                f"找到了！以下是目前開放報名的比賽（{today_str}）👇\n━━━━━━━━━━━━━━━"
            )
            push_message(user_id, raw)
            push_message(user_id, "有問題隨時問我 😊")
            return

        first_three = competitions[:3]
        remaining = competitions[3:]

        push_message(user_id,
            f"找到了！以下是目前開放報名的比賽（{today_str}）👇\n━━━━━━━━━━━━━━━"
        )
        for comp in first_three:
            push_message(user_id, comp)

        if remaining:
            pending_competitions[user_id] = remaining
            push_message(user_id,
                f"還有 {len(remaining)} 個比賽我還沒告訴你 👀\n"
                "要繼續看嗎？回覆「還有哪些」或「繼續」我再列給你！"
            )
        else:
            push_message(user_id,
                "以上就是目前全部開放的比賽囉 ✅\n有問題隨時問我～"
            )

    except Exception as e:
        print(f"Search error: {e}")
        push_message(user_id, f"哎呀，搜尋出了點問題 😅 稍後再試試？\n（{str(e)[:80]}）")

def handle_message_async(reply_token: str, user_id: str, user_message: str):
    try:
        msg_lower = user_message.strip().lower()
        msg = user_message.strip()

        # === 正在等待使用者輸入推播時間 ===
        if user_id in waiting_for_time:
            result = parse_time_input(msg)
            if result:
                h, m = result
                if 0 <= h <= 23 and 0 <= m <= 59:
                    push_time["hour"] = h
                    push_time["minute"] = m
                    waiting_for_time.discard(user_id)
                    time_str = f"{h:02d}:{m:02d}"
                    reply_message(reply_token,
                        f"好！推播時間已改成每天 {time_str} ⏰\n"
                        f"明天起就會在這個時間通知你囉～"
                    )
                else:
                    reply_message(reply_token, "欸，時間好像不太對 😅 再輸入一次？（例如：8點、7:30、8點半）")
            else:
                reply_message(reply_token, "我看不太懂欸 🤔 可以試試「8點」「7:30」「7點半」這種格式！")
            return

        # === 查看剩下的比賽 ===
        if any(kw in msg_lower for kw in ['還有', '繼續', '下一個', '其他', '更多']):
            if user_id in pending_competitions and pending_competitions[user_id]:
                remaining = pending_competitions[user_id]
                show = remaining[:3]
                rest = remaining[3:]
                pending_competitions[user_id] = rest
                reply_message(reply_token, "好！繼續來看～ 👇")
                for comp in show:
                    push_message(user_id, comp)
                if rest:
                    push_message(user_id, f"還剩 {len(rest)} 個，要繼續看嗎？回覆「繼續」就好！")
                else:
                    push_message(user_id, "好了，全部看完囉 ✅ 有問題隨時問我！")
            else:
                reply = chat_with_groq(user_id, user_message)
                reply_message(reply_token, reply)

        # === 搜尋比賽 ===
        elif any(kw in msg_lower for kw in ['搜尋比賽', '找比賽', '最新比賽']):
            reply_message(reply_token, "收到！我去幫你找一下 🔍\n大概一分鐘內送過來，先等我一下～")
            thread = threading.Thread(target=handle_search_async, args=(user_id,))
            thread.daemon = True
            thread.start()

        # === 推播設定 ===
        elif any(kw in msg_lower for kw in ['推播設定', '推播時間', '每日推播', '改推播', '設定推播']):
            h = push_time["hour"]
            m = push_time["minute"]
            time_str = f"{h:02d}:{m:02d}"
            waiting_for_time.add(user_id)
            reply_message(reply_token,
                f"目前推播時間是每天 {time_str} ⏰\n\n"
                "想改成幾點呢？直接告訴我就好！\n"
                "（例如：8點、7:30、7點半、9點15分）"
            )

        # === 說明 ===
        elif any(kw in msg_lower for kw in ['說明', 'help', '怎麼用', '功能']):
            h = push_time["hour"]
            m = push_time["minute"]
            time_str = f"{h:02d}:{m:02d}"
            reply_message(reply_token,
                "嗨！我是競賽小幫手 🏆\n━━━━━━━━━\n"
                f"📌 每天 {time_str} 自動推播最新比賽\n\n"
                "你可以這樣用：\n"
                "  🔍 按「搜尋比賽」→ 馬上幫你找\n"
                "  📋 按「已報名比賽」→ 開啟報名進度表\n"
                "  ⏰ 按「推播設定」→ 更改推播時間\n"
                "  💬 直接聊天 → 問我準備建議、簡報怎麼做\n\n"
                "專為「智慧保險系統」客製化 👀"
            )

        # === 一般聊天 ===
        else:
            reply = chat_with_groq(user_id, user_message)
            reply_message(reply_token, reply)

    except Exception as e:
        print(f"Error: {e}")
        reply_message(reply_token, "啊，好像出了點問題 😅 稍後再試試？")

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
        thread = threading.Thread(
            target=handle_message_async,
            args=(reply_token, user_id, user_message)
        )
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
