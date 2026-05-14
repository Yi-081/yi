"""
比賽爬蟲：自動抓取金融科技、保險、智慧保單相關比賽資訊
資料來源：競技網、各官方公告、FINDIT 等
"""

import json
import re
import hashlib
import logging
from datetime import datetime, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

KEYWORDS = [
    "金融科技", "fintech", "FinTech", "保險", "insurance",
    "智慧保單", "InsurTech", "insurtech", "金融", "理財",
    "區塊鏈", "blockchain", "數位金融", "支付", "借貸",
]

OUTPUT_FILE = Path(__file__).parent / "competitions.json"


# ── 工具函式 ─────────────────────────────────────────────────────────────────

def make_id(title: str, url: str) -> str:
    raw = f"{title}{url}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def is_relevant(text: str) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in KEYWORDS)


def parse_date(raw: str) -> str:
    """嘗試將各種日期格式轉成 YYYY-MM-DD，失敗回傳空字串。"""
    raw = raw.strip()
    patterns = [
        r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
        r"(\d{4})年(\d{1,2})月(\d{1,2})日?",
        r"(\d{4})\.(\d{1,2})\.(\d{1,2})",
    ]
    for p in patterns:
        m = re.search(p, raw)
        if m:
            y, mo, d = m.groups()
            try:
                return date(int(y), int(mo), int(d)).isoformat()
            except ValueError:
                pass
    return ""


def get_status(deadline: str) -> str:
    if not deadline:
        return "unknown"
    try:
        dl = date.fromisoformat(deadline)
        today = date.today()
        if dl < today:
            return "closed"
        if (dl - today).days <= 30:
            return "closing_soon"
        return "open"
    except ValueError:
        return "unknown"


def fetch(url: str, timeout: int = 15) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        return BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        log.warning(f"無法抓取 {url}：{e}")
        return None


# ── 各來源爬蟲 ───────────────────────────────────────────────────────────────

def scrape_jingji() -> list[dict]:
    """競技網 jingji.com.tw — 台灣最大比賽資訊聚合站"""
    results = []
    base = "https://www.jingji.com.tw"
    # 搜尋金融科技相關關鍵字
    for keyword in ["金融科技", "保險", "FinTech"]:
        url = f"{base}/search?q={keyword}"
        soup = fetch(url)
        if not soup:
            continue
        for card in soup.select("article.competition-card, .contest-item, .card"):
            title_el = card.select_one("h2, h3, .title, .name")
            link_el = card.select_one("a[href]")
            deadline_el = card.select_one(".deadline, .date, time")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            url_detail = link_el["href"] if link_el else ""
            if url_detail and not url_detail.startswith("http"):
                url_detail = base + url_detail
            deadline = parse_date(deadline_el.get_text() if deadline_el else "")
            results.append({
                "id": make_id(title, url_detail),
                "title": title,
                "organizer": "競技網來源",
                "category": ["fintech"],
                "deadline": deadline,
                "registration_start": "",
                "prize": "",
                "description": "",
                "url": url_detail,
                "source": "競技網",
                "status": get_status(deadline),
            })
    return results


def scrape_fsc() -> list[dict]:
    """金管會 fsc.gov.tw — 官方金融科技相關比賽公告"""
    results = []
    url = "https://www.fsc.gov.tw/ch/home.jsp?id=96&parentpath=0,2"
    soup = fetch(url)
    if not soup:
        return results
    base = "https://www.fsc.gov.tw"
    for row in soup.select("table tr, .list-item, li"):
        link_el = row.select_one("a[href]")
        if not link_el:
            continue
        title = link_el.get_text(strip=True)
        if not is_relevant(title):
            continue
        href = link_el["href"]
        if not href.startswith("http"):
            href = base + href
        date_el = row.select_one("td:last-child, .date, time")
        deadline = parse_date(date_el.get_text() if date_el else "")
        results.append({
            "id": make_id(title, href),
            "title": title,
            "organizer": "金融監督管理委員會",
            "category": ["fintech", "insurance"],
            "deadline": deadline,
            "registration_start": "",
            "prize": "",
            "description": "",
            "url": href,
            "source": "金管會",
            "status": get_status(deadline),
        })
    log.info(f"金管會：找到 {len(results)} 筆")
    return results


def scrape_tii() -> list[dict]:
    """保發中心 tii.org.tw — 保險相關競賽"""
    results = []
    url = "https://www.tii.org.tw/tii/information/information1/"
    soup = fetch(url)
    if not soup:
        return results
    base = "https://www.tii.org.tw"
    for link_el in soup.select("a[href]"):
        title = link_el.get_text(strip=True)
        if len(title) < 5 or not is_relevant(title):
            continue
        href = link_el["href"]
        if not href.startswith("http"):
            href = base + href
        results.append({
            "id": make_id(title, href),
            "title": title,
            "organizer": "財團法人保險事業發展中心",
            "category": ["insurance"],
            "deadline": "",
            "registration_start": "",
            "prize": "",
            "description": "",
            "url": href,
            "source": "保發中心",
            "status": "unknown",
        })
    log.info(f"保發中心：找到 {len(results)} 筆")
    return results


def scrape_findit() -> list[dict]:
    """FINDIT 創業比賽資訊"""
    results = []
    url = "https://findit.org.tw/zh-TW/activities"
    soup = fetch(url)
    if not soup:
        return results
    base = "https://findit.org.tw"
    for card in soup.select(".activity-card, .event-card, article"):
        title_el = card.select_one("h2, h3, .title")
        link_el = card.select_one("a[href]")
        date_el = card.select_one(".date, time, .deadline")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not is_relevant(title):
            continue
        href = link_el["href"] if link_el else ""
        if href and not href.startswith("http"):
            href = base + href
        deadline = parse_date(date_el.get_text() if date_el else "")
        results.append({
            "id": make_id(title, href),
            "title": title,
            "organizer": "FINDIT",
            "category": ["fintech", "startup"],
            "deadline": deadline,
            "registration_start": "",
            "prize": "",
            "description": "",
            "url": href,
            "source": "FINDIT",
            "status": get_status(deadline),
        })
    log.info(f"FINDIT：找到 {len(results)} 筆")
    return results


def scrape_tfta() -> list[dict]:
    """台灣金融科技協會 tfta.org.tw"""
    results = []
    url = "https://www.tfta.org.tw/news"
    soup = fetch(url)
    if not soup:
        return results
    base = "https://www.tfta.org.tw"
    for item in soup.select("article, .news-item, li"):
        link_el = item.select_one("a[href]")
        if not link_el:
            continue
        title = link_el.get_text(strip=True)
        if len(title) < 5:
            continue
        href = link_el["href"]
        if not href.startswith("http"):
            href = base + href
        date_el = item.select_one(".date, time")
        deadline = parse_date(date_el.get_text() if date_el else "")
        results.append({
            "id": make_id(title, href),
            "title": title,
            "organizer": "台灣金融科技協會",
            "category": ["fintech"],
            "deadline": deadline,
            "registration_start": "",
            "prize": "",
            "description": "",
            "url": href,
            "source": "台灣金融科技協會",
            "status": get_status(deadline),
        })
    log.info(f"台灣金融科技協會：找到 {len(results)} 筆")
    return results


def scrape_ihergo() -> list[dict]:
    """iHergo — 台灣競賽資訊整合平台（黑客松、創新競賽）"""
    results = []
    url = "https://www.ihergo.com/categories/fintech"
    soup = fetch(url)
    if not soup:
        return results
    base = "https://www.ihergo.com"
    for card in soup.select(".contest-card, .item, article"):
        title_el = card.select_one("h2, h3, .name, .title")
        link_el = card.select_one("a[href]")
        deadline_el = card.select_one(".deadline, .date, time")
        prize_el = card.select_one(".prize, .reward, .award")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = link_el["href"] if link_el else ""
        if href and not href.startswith("http"):
            href = base + href
        deadline = parse_date(deadline_el.get_text() if deadline_el else "")
        prize = prize_el.get_text(strip=True) if prize_el else ""
        results.append({
            "id": make_id(title, href),
            "title": title,
            "organizer": "",
            "category": ["fintech"],
            "deadline": deadline,
            "registration_start": "",
            "prize": prize,
            "description": "",
            "url": href,
            "source": "iHergo",
            "status": get_status(deadline),
        })
    log.info(f"iHergo：找到 {len(results)} 筆")
    return results


# ── 去重合併 ─────────────────────────────────────────────────────────────────

def deduplicate(competitions: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for c in competitions:
        if c["id"] not in seen:
            seen.add(c["id"])
            out.append(c)
    return out


# ── 讀取舊資料（手動新增的不覆蓋）────────────────────────────────────────────

def load_existing() -> list[dict]:
    if OUTPUT_FILE.exists():
        data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        return data.get("competitions", [])
    return []


OVERWRITE_FIELDS = {"deadline", "url", "organizer", "description", "prize", "category", "registration_start"}

def merge(existing: list[dict], scraped: list[dict]) -> list[dict]:
    scraped_map = {c["id"]: c for c in scraped}
    merged = []
    for c in existing:
        fresh = scraped_map.get(c["id"])
        if fresh and not c.get("manual"):
            for field in OVERWRITE_FIELDS:
                if fresh.get(field):
                    c[field] = fresh[field]
        c["status"] = get_status(c.get("deadline", ""))
        merged.append(c)
    existing_ids = {c["id"] for c in existing}
    merged.extend(c for c in scraped if c["id"] not in existing_ids)
    return merged


# ── 主程式 ───────────────────────────────────────────────────────────────────

def main():
    log.info("開始爬取比賽資料...")
    scrapers = [
        scrape_fsc,
        scrape_tii,
        scrape_findit,
        scrape_tfta,
        scrape_ihergo,
        scrape_jingji,
    ]
    scraped: list[dict] = []
    for fn in scrapers:
        try:
            items = fn()
            scraped.extend(items)
        except Exception as e:
            log.error(f"{fn.__name__} 失敗：{e}")

    scraped = deduplicate(scraped)
    existing = load_existing()
    competitions = merge(existing, scraped)
    # 排序：截止日期近的在前，無截止日期的在後
    def sort_key(c):
        d = c.get("deadline", "")
        return d if d else "9999-99-99"
    competitions.sort(key=sort_key)

    old_last_updated = ""
    if OUTPUT_FILE.exists():
        old_data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        old_last_updated = old_data.get("last_updated", "")
        old_competitions = old_data.get("competitions", [])
    else:
        old_competitions = []

    content_changed = json.dumps(competitions, ensure_ascii=False, sort_keys=True) != \
                      json.dumps(old_competitions, ensure_ascii=False, sort_keys=True)

    output = {
        "last_updated": datetime.now().isoformat(timespec="seconds") if content_changed else old_last_updated,
        "count": len(competitions),
        "competitions": competitions,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if content_changed:
        log.info(f"完成！共 {len(competitions)} 筆，資料有變更，已寫入 {OUTPUT_FILE}")
    else:
        log.info(f"完成！共 {len(competitions)} 筆，資料無變更，last_updated 保持不動")


if __name__ == "__main__":
    main()
