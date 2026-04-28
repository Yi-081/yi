# 🏆 競賽小幫手 LINE Bot

每天自動搜尋並推播適合「智慧保險系統」專題的比賽。

## 架構（完全免費）

```
GitHub Actions (每天 9:00 AM)
  └─→ Gemini AI 搜尋比賽
      └─→ LINE 推播到你的手機

Render (24/7 Webhook)
  └─→ 接收 LINE 訊息「比賽」
      └─→ 立即回覆最新賽事
```

## 設定步驟

### 1. GitHub Secrets（已完成）
到 Settings → Secrets → Actions 確認有以下 3 個：
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_USER_ID`
- `GEMINI_API_KEY`

### 2. 部署到 Render（Webhook 用）

1. 前往 https://render.com，用 GitHub 登入
2. New → Web Service → 選這個 repo
3. Build: `pip install -r requirements.txt`
4. Start: `gunicorn src.server:app --bind 0.0.0.0:$PORT --timeout 120`
5. 新增 Environment Variables：
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `LINE_CHANNEL_SECRET`
   - `GEMINI_API_KEY`
6. 部署完成後，複製網址填入 LINE Developers → Webhook URL：
   `https://你的名稱.onrender.com/webhook`

### 3. 測試

手動觸發：GitHub → Actions → Daily Competition Push → Run workflow

LINE 指令：
- 「比賽」→ 立即搜尋
- 「說明」→ 功能說明
- 「我的專題」→ 專題介紹
