#!/usr/bin/env python3
"""Daily LinkedIn influencer digest -> Telegram channel.
Fetches recent posts via an Apify LinkedIn scraper, keeps only posts
published TODAY (in TIMEZONE), and sends each to the Telegram channel.
Standard library only.  Usage: python3 digest.py [--dry-run]
"""
import json, os, sys, html, urllib.request, urllib.parse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))

KEYS = ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "APIFY_TOKEN", "TIMEZONE",
        "APIFY_ACTOR", "MAX_POSTS_PER_PROFILE")

def load_env():
    """Settings come from environment variables; a local .env file (optional)
    fills in anything not set. Works locally, in CI, or any scheduler."""
    env = {}
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    env.update({k: os.environ[k] for k in KEYS if os.environ.get(k)})
    missing = [k for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "APIFY_TOKEN") if not env.get(k)]
    if missing:
        sys.exit(f"Missing required settings: {', '.join(missing)} (set env vars or create .env)")
    return env

def http_json(url, payload=None, timeout=300):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def fetch_posts(env, profiles):
    actor = env.get("APIFY_ACTOR", "harvestapi~linkedin-profile-posts")
    url = (f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
           f"?token={urllib.parse.quote(env['APIFY_TOKEN'])}")
    payload = {
        "targetUrls": [p["linkedin"] for p in profiles],
        "maxPosts": int(env.get("MAX_POSTS_PER_PROFILE", 5)),
    }
    return http_json(url, payload)

def parse_date(item):
    """Return an aware datetime for the post, trying the common field shapes."""
    cands = []
    pa = item.get("postedAt")
    if isinstance(pa, dict):
        cands += [pa.get("timestamp"), pa.get("date")]
    else:
        cands.append(pa)
    cands += [item.get(k) for k in ("postedAtTimestamp", "postedAtISO", "publishedAt", "createdAt", "date", "time")]
    for c in cands:
        if c in (None, ""):
            continue
        try:
            if isinstance(c, (int, float)) or (isinstance(c, str) and c.isdigit()):
                ts = float(c)
                return datetime.fromtimestamp(ts / 1000 if ts > 1e11 else ts, tz=timezone.utc)
            d = datetime.fromisoformat(str(c).replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except (ValueError, OSError):
            continue
    return None

def norm(u):
    return (u or "").lower().split("?")[0].rstrip("/").replace("https://", "").replace("http://", "").replace("www.", "")

def author_of(item, profiles):
    a = item.get("author")
    name = (a.get("name") if isinstance(a, dict) else a) or item.get("authorName")
    if name:
        return name
    src = norm(item.get("query", {}).get("targetUrl") if isinstance(item.get("query"), dict) else item.get("profileUrl"))
    for p in profiles:
        if src and norm(p["linkedin"]) == src:
            return p["name"]
    return "Unknown author"

def slug(u):
    n = norm(u)
    return n.split("/in/")[1].split("/")[0] if "/in/" in n else ""

def own_post_author(item, profiles):
    """Return the influencer's name if this item was WRITTEN by a tracked influencer
    (skips reposts / 'X liked this' items that show up in their activity feed)."""
    a = item.get("author") or {}
    aid = (a.get("publicIdentifier") or slug(a.get("linkedinUrl"))) if isinstance(a, dict) else ""
    if item.get("repostedBy"):
        return None
    for p in profiles:
        if aid and aid.lower() == slug(p["linkedin"]):
            return p["name"]
    return None

def post_url(item):
    return item.get("linkedinUrl") or item.get("url") or item.get("postUrl") or item.get("shareUrl") or ""

def post_text(item):
    return (item.get("content") or item.get("text") or item.get("commentary") or "").strip()

def excerpt(text, n=600):
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"

def send(env, text, dry):
    if dry:
        print("---\n" + text)
        return
    url = f"https://api.telegram.org/bot{env['TELEGRAM_TOKEN']}/sendMessage"
    r = http_json(url, {"chat_id": env["TELEGRAM_CHAT_ID"], "text": text,
                        "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=30)
    if not r.get("ok"):
        raise RuntimeError(f"Telegram error: {r}")

def main():
    dry = "--dry-run" in sys.argv
    env = load_env()
    tz = ZoneInfo(env.get("TIMEZONE", "Asia/Yerevan"))
    today = datetime.now(tz).date()
    with open(os.path.join(HERE, "influencers.json")) as f:
        profiles = json.load(f)

    items = fetch_posts(env, profiles)
    seen, todays, skipped = set(), [], 0
    not_own = 0
    for it in items:
        name = own_post_author(it, profiles)
        if not name:                                      # repost / someone else's post
            not_own += 1
            continue
        d = parse_date(it)
        u = post_url(it)
        if not d or d.astimezone(tz).date() != today:   # date filter: today only
            skipped += 1
            continue
        if u in seen:
            continue
        seen.add(u)
        todays.append((d, name, it))
    todays.sort(key=lambda x: x[0])

    print(f"{today}: fetched {len(items)} items, {not_own} reposts/others skipped, "
          f"{skipped} older skipped, {len(todays)} from today")
    if not todays:
        send(env, f"📭 No new posts today ({today:%d %b %Y}).", dry)
        return
    send(env, f"📰 <b>AI-in-QA daily digest · {today:%d %b %Y}</b>\n{len(todays)} new post(s) today", dry)
    for d, name, it in todays:
        msg = (f"👤 <b>{html.escape(name)}</b> · {d.astimezone(tz):%d %b %Y, %H:%M}\n\n"
               f"{html.escape(excerpt(post_text(it)) or '(no text)')}\n\n"
               f"🔗 <a href=\"{html.escape(post_url(it))}\">Open on LinkedIn</a>")
        send(env, msg, dry)
    print(f"Sent {len(todays)} post(s).")

if __name__ == "__main__":
    main()
