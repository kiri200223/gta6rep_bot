#!/usr/bin/env python3
"""
GTA 6 PC Build / Repack Checker for GitHub Actions
Hybrid architecture: FitGirl RSS + Reddit + YouTube (Scrapetube + RSS) + Gemini AI Verification
"""

import os
import sys
import argparse
import datetime
import xml.etree.ElementTree as ET
import requests

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------
CUTOFF_DATE = datetime.date(2026, 12, 4)

REDDIT_SUBREDDITS = ["CrackWatch", "PiratedGames", "pcgaming"]
REDDIT_QUERY = "GTA 6 OR GTA VI OR Cyberleek"
REDDIT_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GTA6Checker/1.0"}

FITGIRL_RSS_URL = "https://fitgirl-repacks.site/feed/"

# YouTube channel RSS feeds (example format: https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID)
# To monitor freetoseven, replace with their channel ID: e.g. "https://www.youtube.com/feeds/videos.xml?channel_id=UC..."
YOUTUBE_CHANNEL_RSS = [
    # "https://www.youtube.com/feeds/videos.xml?channel_id=UC_example_freetoseven_channel_id",
]

# Keywords and Filters
FITGIRL_KEYWORDS = ["gta 6", "gta vi", "grand theft auto vi"]

REDDIT_REQ_1 = ["gta 6", "gta vi", "grand theft auto vi", "cyberleek"]
REDDIT_REQ_2 = ["repack", "release", "playable", "working", "build", "port", "fitgirl", "dodi", "crack"]
REDDIT_STOPWORDS = ["fake", "scam", "virus", "malware", "stealer", "meme", "humor", "question"]

YOUTUBE_REQ = ["gta 6", "gta vi", "cyberleek"]
YOUTUBE_STOPWORDS = ["fake", "scam", "meme", "trailer", "concept"]

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ---------------------------------------------------------------------------
# Telegram Notification
# ---------------------------------------------------------------------------
def send_telegram(text: str) -> bool:
    """Send message to Telegram with link previews disabled. Logs errors to stdout."""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[Telegram] TG_BOT_TOKEN or TG_CHAT_ID is not configured in environment variables.")
        return False
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print("[Telegram] Notification sent successfully.")
            return True
        else:
            print(f"[Telegram] Error response ({resp.status_code}): {resp.text}")
    except Exception as exc:
        print(f"[Telegram] Network error sending message: {exc}")
    return False


# ---------------------------------------------------------------------------
# FitGirl RSS Parser
# ---------------------------------------------------------------------------
def check_fitgirl_rss():
    """Checks FitGirl RSS feed for GTA 6. If matched, immediately sends Telegram alert."""
    print("[FitGirl] Checking RSS feed...")
    try:
        resp = requests.get(
            FITGIRL_RSS_URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[FitGirl] RSS returned HTTP {resp.status_code}")
            return

        root = ET.fromstring(resp.content)
        # Parse RSS 2.0 items
        for item in root.findall(".//item"):
            title_elem = item.find("title")
            link_elem = item.find("link")
            title = title_elem.text if title_elem is not None and title_elem.text else ""
            link = link_elem.text if link_elem is not None and link_elem.text else ""
            title_lower = title.lower()

            if any(kw in title_lower for kw in FITGIRL_KEYWORDS):
                print(f"[FitGirl] MATCH FOUND! Title: {title}")
                msg = (
                    "🔥 [FitGirl Repacks] GTA 6 / VI DETECTED! 🔥\n\n"
                    f"Название: {title}\n"
                    f"Ссылка: {link}\n"
                )
                send_telegram(msg)
                return
        print("[FitGirl] No matches found in latest RSS entries.")
    except Exception as exc:
        print(f"[FitGirl] Error checking RSS: {exc}")


# ---------------------------------------------------------------------------
# Reddit Parser
# ---------------------------------------------------------------------------
def check_reddit() -> list:
    """Checks Reddit subreddits via search.json. Returns a list of candidate items."""
    candidates = []
    print("[Reddit] Checking subreddits...")

    for sub in REDDIT_SUBREDDITS:
        url = f"https://www.reddit.com/r/{sub}/search.json"
        params = {
            "q": REDDIT_QUERY,
            "restrict_sr": 1,
            "sort": "top",
            "t": "day",
            "limit": 15,
        }
        try:
            resp = requests.get(url, params=params, headers=REDDIT_HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"[Reddit] r/{sub} search returned HTTP {resp.status_code}")
                continue

            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            for post in posts:
                post_data = post.get("data", {})
                score = post_data.get("score", 0)
                title = post_data.get("title", "")
                selftext = post_data.get("selftext", "") or ""
                permalink = f"https://reddit.com{post_data.get('permalink', '')}"
                title_lower = title.lower()

                # Filter condition: score >= 50
                if score < 50:
                    continue

                # Filter condition: at least one from REQ_1 AND one from REQ_2
                has_req1 = any(kw in title_lower for kw in REDDIT_REQ_1)
                has_req2 = any(kw in title_lower for kw in REDDIT_REQ_2)
                if not (has_req1 and has_req2):
                    continue

                # Stopwords filter
                if any(sw in title_lower for sw in REDDIT_STOPWORDS):
                    continue

                print(f"[Reddit] Candidate found in r/{sub}: [{score} pts] {title}")
                candidates.append({
                    "source": f"Reddit r/{sub}",
                    "title": title,
                    "text": selftext[:400].strip(),
                    "link": permalink,
                })
        except Exception as exc:
            print(f"[Reddit] Error fetching r/{sub}: {exc}")

    return candidates


# ---------------------------------------------------------------------------
# YouTube Parser
# ---------------------------------------------------------------------------
def check_youtube() -> list:
    """Checks YouTube using scrapetube and RSS feeds. Returns candidate videos."""
    candidates = []
    print("[YouTube] Checking YouTube...")

    # 1. scrapetube search
    try:
        import scrapetube

        videos = scrapetube.get_search(
            query="GTA 6 PC port working OR repack Cyberleek",
            limit=10,
            sort_by="upload_date",
        )
        for vid in videos:
            title = ""
            if "title" in vid and "runs" in vid["title"] and vid["title"]["runs"]:
                title = vid["title"]["runs"][0].get("text", "")
            elif "title" in vid and "simpleText" in vid["title"]:
                title = vid["title"]["simpleText"]

            video_id = vid.get("videoId", "")
            link = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
            title_lower = title.lower()

            if not title:
                continue

            has_req = any(kw in title_lower for kw in YOUTUBE_REQ)
            has_stop = any(sw in title_lower for sw in YOUTUBE_STOPWORDS)

            if has_req and not has_stop:
                print(f"[YouTube] Candidate found via search: {title}")
                candidates.append({
                    "source": "YouTube Search",
                    "title": title,
                    "text": f"Video ID: {video_id}",
                    "link": link,
                })
    except Exception as exc:
        print(f"[YouTube] Error running scrapetube search: {exc}")

    # 2. Channel RSS Feeds
    for rss_url in YOUTUBE_CHANNEL_RSS:
        try:
            resp = requests.get(rss_url, timeout=15)
            if resp.status_code != 200:
                print(f"[YouTube RSS] Feed returned HTTP {resp.status_code}: {rss_url}")
                continue

            root = ET.fromstring(resp.content)
            # Atom feed namespace
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns)
            for entry in entries:
                title_elem = entry.find("atom:title", ns)
                link_elem = entry.find("atom:link", ns)
                title = title_elem.text if title_elem is not None and title_elem.text else ""
                link = link_elem.attrib.get("href", "") if link_elem is not None else ""
                title_lower = title.lower()

                has_req = any(kw in title_lower for kw in YOUTUBE_REQ)
                has_stop = any(sw in title_lower for sw in YOUTUBE_STOPWORDS)

                if has_req and not has_stop:
                    print(f"[YouTube RSS] Candidate found: {title}")
                    candidates.append({
                        "source": "YouTube Channel RSS",
                        "title": title,
                        "text": "",
                        "link": link,
                    })
        except Exception as exc:
            print(f"[YouTube RSS] Error checking {rss_url}: {exc}")

    return candidates


# ---------------------------------------------------------------------------
# Gemini AI Verification
# ---------------------------------------------------------------------------
def verify_with_gemini(candidates: list) -> str:
    """Verifies candidates with gemini-2.5-flash via Google Generative Language REST API."""
    if not GEMINI_API_KEY:
        print("[Gemini] GEMINI_API_KEY is not set. Skipping AI verification.")
        return "NO"

    print(f"[Gemini] Verifying {len(candidates)} candidate(s) using gemini-2.5-flash...")

    candidates_summary = ""
    for idx, c in enumerate(candidates, 1):
        candidates_summary += (
            f"--- Candidate #{idx} ---\n"
            f"Source: {c['source']}\n"
            f"Title: {c['title']}\n"
            f"Text: {c.get('text', '')}\n"
            f"Link: {c['link']}\n\n"
        )

    system_instruction = (
        "Ты — строгий фактчекер релизов видеоигр. Твоя задача — проверить данные и определить, "
        "вышла ли РЕАЛЬНО РАБОЧАЯ ПК-сборка, порт или репак GTA 6 (Grand Theft Auto VI), "
        "включая фанатский рабочий порт/рекомпиляцию слитой сборки Xbox от Cyberleek.\n\n"
        "КРИТИЧЕСКИЕ ПРАВИЛА:\n"
        "1. Если материалы подтверждают, что УЖЕ вышла реально рабочая ПК-сборка/порт/репак GTA 6 "
        "(не кликбейт, не фейк, не обсуждение слухов, не вирус/скам, не 'скоро выйдет', не концепт/трейлер), "
        "начни ответ со слова 'YES' и ниже дай короткую сводку:\n"
        "   - Точное название сборки/репака\n"
        "   - Источник / имя репакера\n"
        "   - SHA-256 хеш (если указан в тексте, иначе 'Не указан')\n"
        "   - Ссылка на оригинал\n"
        "2. Во ВСЕХ остальных случаях ответь строго одним словом: NO."
    )

    prompt = (
        f"Проанализируй следующие найденные публикации:\n\n"
        f"{candidates_summary}\n\n"
        f"Подтверждают ли эти публикации факт выхода реально рабочей сборки GTA 6 на ПК?"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{system_instruction}\n\n{prompt}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1000,
        }
    }

    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"[Gemini] API error ({resp.status_code}): {resp.text}")
            return "NO"

        data = resp.json()
        candidates_resp = data.get("candidates", [])
        if not candidates_resp:
            print("[Gemini] Empty response from model.")
            return "NO"

        text_content = ""
        parts = candidates_resp[0].get("content", {}).get("parts", [])
        for part in parts:
            text_content += part.get("text", "")

        return text_content.strip()
    except Exception as exc:
        print(f"[Gemini] Network or processing error: {exc}")
        return "NO"


# ---------------------------------------------------------------------------
# Main Execution Flow
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="GTA 6 PC Build / Repack Monitor")
    parser.add_argument("--test", action="store_true", help="Send test message to Telegram and exit")
    parser.add_argument("--yt", action="store_true", help="Force YouTube checking regardless of day of month")
    args = parser.parse_args()

    # 1. Test flag
    if args.test:
        print("[Mode] Running Telegram test...")
        success = send_telegram("🤖 GTA 6 Monitor: Тестовое сообщение. Бот и канал связи работают штатно!")
        sys.exit(0 if success else 1)

    # 2. Date Autostop check
    today = datetime.date.today()
    print(f"[Status] Current date: {today}, Cutoff date: {CUTOFF_DATE}")
    if today >= CUTOFF_DATE:
        print(f"[Autostop] Target date {CUTOFF_DATE} reached. Script terminating normally (exit 0).")
        sys.exit(0)

    # 3. FitGirl RSS (Daily, highest priority)
    check_fitgirl_rss()

    # 4. Reddit check (Daily)
    reddit_candidates = check_reddit()

    # 5. YouTube check (Even days or if --yt flag is set)
    yt_candidates = []
    is_even_day = (today.day % 2 == 0)
    if args.yt or is_even_day:
        reason = "--yt flag passed" if args.yt else f"even day of month ({today.day})"
        print(f"[YouTube] Running YouTube check ({reason})...")
        yt_candidates = check_youtube()
    else:
        print(f"[YouTube] Skipping YouTube check today (day {today.day} is odd). Use --yt to force.")

    # 6. Aggregate candidates
    all_candidates = reddit_candidates + yt_candidates
    if not all_candidates:
        print("[Status] No potential candidates found on Reddit or YouTube. Exiting cleanly.")
        sys.exit(0)

    print(f"[Status] Found {len(all_candidates)} potential candidate(s). Proceeding to Gemini verification...")

    # 7. Gemini AI verification
    ai_result = verify_with_gemini(all_candidates)
    print(f"[Gemini Output]\n{ai_result}\n")

    # 8. Notify Telegram if confirmed
    if ai_result.startswith("YES"):
        print("[ALERT] Gemini verified playable GTA 6 PC build! Sending Telegram notification...")
        send_telegram(f"🚨 GTA 6 PC BUILD CONFIRMED! 🚨\n\n{ai_result}")
    else:
        print("[Status] Gemini concluded NO (or not confirmed). No Telegram notification sent.")


if __name__ == "__main__":
    main()
