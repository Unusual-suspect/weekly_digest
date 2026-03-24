#!/usr/bin/env python3
"""
Regulatory Intelligence Agent — 100% Free RSS Edition
No AI, no paid APIs. Reads RSS feeds directly from EBA, European Commission,
EUR-Lex, Finextra and others. Filters for relevance, sends HTML email via SendGrid.
Cost: $0.00/week forever.
"""

import os
import re
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from dataclasses import dataclass, field
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── RSS FEEDS ─────────────────────────────────────────────────────────────────

FEEDS = [
    {
        "name": "EBA",
        "url": "https://www.eba.europa.eu/rss.xml",
        "area": "EBA / Prudential",
        "icon": "🏛️",
    },
    {
        "name": "European Commission — Financial Stability",
        "url": "https://ec.europa.eu/newsroom/fisma/rss-feeds",
        "area": "EU Commission",
        "icon": "🇪🇺",
    },
    {
        "name": "EUR-Lex — Latest legislation",
        "url": "https://eur-lex.europa.eu/rss/rss_RECENT.xml",
        "area": "EU Legislation",
        "icon": "📜",
    },
    {
        "name": "Finextra",
        "url": "https://www.finextra.com/rss/headlines.aspx",
        "area": "Fintech News",
        "icon": "📰",
    },
    {
        "name": "ECB Press Releases",
        "url": "https://www.ecb.europa.eu/rss/press.html",
        "area": "ECB",
        "icon": "🏦",
    },
    {
        "name": "Payments & Cards Network",
        "url": "https://www.paymentscardsandmobile.com/feed/",
        "area": "Payments Industry",
        "icon": "💳",
    },
]

# ── KEYWORDS FOR RELEVANCE FILTERING ─────────────────────────────────────────

# Items matching ANY keyword in their title or description are included
KEYWORDS = [
    # PSD3 / Open Banking
    "psd3", "psd2", "payment services directive", "open banking", "psr",
    "payment services regulation", "pisp", "aisp", "account access",
    # AI Act
    "ai act", "artificial intelligence act", "high-risk ai", "ai regulation",
    "agentic", "autonomous payment", "ai agent", "llm payment",
    # SCA / 3DS
    "sca", "strong customer authentication", "3ds", "3ds2",
    "merchant-initiated", "mit exemption", "step-up authentication",
    # Payments general
    "instant payment", "sepa", "open finance", "payment fraud",
    "payment regulation", "digital euro", "cbdc", "e-money",
    # Fintech regulation
    "fintech", "eba", "esma", "eiopa", "dora", "mica", "crypto", "stablecoin",
    "digital finance", "regtech", "sandbox", "innovation hub",
    # Agentic commerce
    "delegated authority", "payment delegation", "ai commerce",
    "autonomous transaction", "agent payment",
]

# Urgency keywords — items containing these get flagged
URGENT_KEYWORDS = [
    "deadline", "enforcement", "mandatory", "enters into force",
    "final", "adopted", "penalty", "fine", "sanction", "breach",
    "consultation closes", "response due",
]

ACT_SOON_KEYWORDS = [
    "consultation", "draft", "proposed", "guideline", "recommendation",
    "transposition", "implementation", "coming into effect", "q1", "q2",
    "2026", "review",
]


# ── DATA MODEL ────────────────────────────────────────────────────────────────

@dataclass
class Article:
    title: str
    url: str
    summary: str
    published: Optional[datetime]
    source: str
    area: str
    icon: str
    urgency: str = "Watch"

    def age_days(self) -> int:
        if not self.published:
            return 0
        now = datetime.now(timezone.utc)
        pub = self.published
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        return (now - pub).days


# ── RSS PARSER ────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RegulatoryIntelBot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml",
}

def fetch_feed(feed: dict) -> list[Article]:
    articles = []
    try:
        resp = requests.get(feed["url"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        # Handle both RSS and Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for item in items[:30]:
            def tag(name):
                t = item.find(name)
                if t is None:
                    t = item.find(f"atom:{name}", ns)
                return (t.text or "").strip() if t is not None else ""

            title   = tag("title")
            url     = tag("link") or tag("id")
            summary = tag("description") or tag("summary") or tag("content")
            pub_str = tag("pubDate") or tag("published") or tag("updated")

            # Clean HTML from summary
            summary = re.sub(r"<[^>]+>", " ", summary)
            summary = re.sub(r"\s+", " ", summary).strip()[:300]

            # Parse date
            published = None
            if pub_str:
                try:
                    published = parsedate_to_datetime(pub_str)
                except Exception:
                    try:
                        published = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    except Exception:
                        pass

            if title and url:
                articles.append(Article(
                    title=title,
                    url=url,
                    summary=summary,
                    published=published,
                    source=feed["name"],
                    area=feed["area"],
                    icon=feed["icon"],
                ))

        log.info(f"{feed['name']}: {len(articles)} items fetched")
    except Exception as e:
        log.warning(f"Failed to fetch {feed['name']}: {e}")
    return articles


# ── FILTERING ─────────────────────────────────────────────────────────────────

def is_relevant(article: Article) -> bool:
    text = (article.title + " " + article.summary).lower()
    return any(kw in text for kw in KEYWORDS)


def assign_urgency(article: Article) -> str:
    text = (article.title + " " + article.summary).lower()
    if any(kw in text for kw in URGENT_KEYWORDS):
        return "Urgent"
    if any(kw in text for kw in ACT_SOON_KEYWORDS):
        return "Act Soon"
    return "Watch"


def filter_and_score(articles: list[Article], days: int = 7) -> list[Article]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    filtered = []
    for a in articles:
        if not is_relevant(a):
            continue
        if a.published:
            pub = a.published
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            if pub < cutoff:
                continue
        a.urgency = assign_urgency(a)
        filtered.append(a)

    # Sort: Urgent first, then by date
    urgency_order = {"Urgent": 0, "Act Soon": 1, "Watch": 2}
    filtered.sort(key=lambda a: (
        urgency_order.get(a.urgency, 2),
        -(a.published.timestamp() if a.published else 0)
    ))
    return filtered


# ── EMAIL BUILDER ─────────────────────────────────────────────────────────────

URGENCY_STYLE = {
    "Urgent":   {"color": "#dc2626", "bg": "#fef2f2", "border": "#fca5a5"},
    "Act Soon": {"color": "#d97706", "bg": "#fffbeb", "border": "#fcd34d"},
    "Watch":    {"color": "#2563eb", "bg": "#eff6ff", "border": "#93c5fd"},
}


def _article_card(a: Article) -> str:
    cfg     = URGENCY_STYLE.get(a.urgency, URGENCY_STYLE["Watch"])
    age     = f"{a.age_days()}d ago" if a.published else ""
    summary = a.summary if a.summary else "No preview available."

    return f"""
<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;
            margin-bottom:12px;overflow:hidden;">
  <div style="padding:12px 16px 10px;border-bottom:0.5px solid #f3f4f6;">
    <div style="display:flex;justify-content:space-between;align-items:center;
                gap:6px;margin-bottom:7px;flex-wrap:wrap;">
      <span style="background:#f1f5f9;color:#475569;font-size:10px;font-weight:600;
                   padding:2px 8px;border-radius:20px;text-transform:uppercase;
                   letter-spacing:.4px;">{a.icon}&nbsp;{a.area}</span>
      <div style="display:flex;align-items:center;gap:6px;">
        {f'<span style="font-size:10px;color:#9ca3af;">{age}</span>' if age else ''}
        <span style="background:{cfg['bg']};color:{cfg['color']};
                     border:1px solid {cfg['border']};font-size:10px;font-weight:700;
                     padding:2px 8px;border-radius:20px;text-transform:uppercase;">
          &#9679; {a.urgency}
        </span>
      </div>
    </div>
    <a href="{a.url}" style="font-size:14px;font-weight:700;color:#111827;
                              text-decoration:none;line-height:1.35;display:block;">
      {a.title}
    </a>
    <p style="margin:3px 0 0;font-size:10px;color:#9ca3af;">
      {a.source}
    </p>
  </div>
  <div style="padding:10px 16px;">
    <p style="margin:0 0 10px;font-size:12px;color:#6b7280;line-height:1.55;">
      {summary}
    </p>
    <a href="{a.url}"
       style="font-size:11px;font-weight:600;color:#1d4ed8;text-decoration:none;">
      Read full article &rarr;
    </a>
  </div>
</div>"""


def build_email(articles: list[Article]) -> tuple[str, str]:
    today    = datetime.now(timezone.utc).strftime("%d %B %Y")
    week_num = datetime.now(timezone.utc).isocalendar()[1]
    count    = len(articles)

    urgent   = [a for a in articles if a.urgency == "Urgent"]
    act_soon = [a for a in articles if a.urgency == "Act Soon"]
    watch    = [a for a in articles if a.urgency == "Watch"]

    subject = f"Your weekly regulatory news is here — {count} updates, Week {week_num}"

    # Summary badges
    badges = []
    if urgent:
        badges.append(f'<span style="color:#f87171;font-weight:700;">&#9679; {len(urgent)} Urgent</span>')
    if act_soon:
        badges.append(f'<span style="color:#fbbf24;font-weight:700;">&#9679; {len(act_soon)} Act Soon</span>')
    if watch:
        badges.append(f'<span style="color:#60a5fa;font-weight:700;">&#9679; {len(watch)} Watch</span>')
    badge_html = " &nbsp;&middot;&nbsp; ".join(badges)

    # Source pills
    source_counts: dict[str, int] = {}
    for a in articles:
        source_counts[a.area] = source_counts.get(a.area, 0) + 1
    source_pills = "".join(
        f'<span style="background:#f1f5f9;color:#475569;font-size:10px;font-weight:600;'
        f'padding:3px 8px;border-radius:20px;margin:2px;display:inline-block;">'
        f'{k} ({v})</span>'
        for k, v in source_counts.items()
    )

    cards_html = "".join(_article_card(a) for a in articles)

    no_results = ""
    if not articles:
        no_results = """
<div style="background:#f9fafb;border:1px dashed #e5e7eb;border-radius:10px;
            padding:24px;text-align:center;color:#9ca3af;font-size:14px;">
  No relevant regulatory developments found this week.
</div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;
             font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
<div style="max-width:620px;margin:0 auto;padding:24px 16px;">

  <!-- Header -->
  <div style="background:#0f172a;border-radius:12px;
              padding:26px 28px 22px;margin-bottom:18px;color:#fff;">
    <div style="font-size:10px;color:#64748b;font-weight:700;letter-spacing:1.2px;
                text-transform:uppercase;margin-bottom:6px;">
      Regulatory Intelligence &middot; Week {week_num} &middot; {today}
    </div>
    <h1 style="margin:0 0 6px;font-size:20px;font-weight:800;line-height:1.25;">
      EU Payments &amp; Agentic Commerce<br>Regulatory Monitor
    </h1>
    <p style="margin:0 0 14px;color:#94a3b8;font-size:12px;">
      {count} developments this week &middot; Sources: EBA, ECB, EUR-Lex, Finextra &amp; more
    </p>
    <div style="padding-top:12px;border-top:1px solid rgba(255,255,255,.12);
                display:flex;gap:14px;flex-wrap:wrap;">
      {badge_html}
    </div>
  </div>

  <!-- Source breakdown -->
  <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;
              padding:12px 16px;margin-bottom:18px;">
    <p style="margin:0 0 7px;font-size:10px;font-weight:700;color:#6b7280;
              text-transform:uppercase;letter-spacing:.5px;">Sources this week</p>
    <div>{source_pills}</div>
  </div>

  <!-- Articles -->
  {cards_html}
  {no_results}

  <!-- Footer -->
  <div style="text-align:center;color:#9ca3af;font-size:10px;
              line-height:1.7;padding:16px 0 8px;">
    Regulatory Intelligence Agent &middot; 100% Free &middot; RSS Edition<br>
    Direct feeds from EBA &middot; ECB &middot; EUR-Lex &middot; Finextra &middot; European Commission<br>
    Delivered every Monday 07:00 CET &middot; No AI, no paid APIs
  </div>

</div>
</body>
</html>"""

    return subject, html


# ── SENDGRID ──────────────────────────────────────────────────────────────────

def send_email(subject: str, html: str) -> bool:
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        json={
            "personalizations": [{"to": [{"email": os.environ["EMAIL_TO"]}]}],
            "from": {"email": os.environ["EMAIL_FROM"], "name": "Reg Intel Agent"},
            "subject": subject,
            "content": [{"type": "text/html", "value": html}],
        },
        headers={
            "Authorization": f"Bearer {os.environ['SENDGRID_API_KEY']}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    if resp.status_code in (200, 202):
        log.info(f"Email sent (HTTP {resp.status_code})")
        return True
    log.error(f"SendGrid {resp.status_code}: {resp.text}")
    return False


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    dry_run  = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    lookback = int(os.environ.get("LOOKBACK_DAYS", "7"))

    log.info(f"Fetching {len(FEEDS)} RSS feeds (past {lookback} days)")

    all_articles = []
    for feed in FEEDS:
        articles = fetch_feed(feed)
        all_articles.extend(articles)

    log.info(f"Total fetched: {len(all_articles)} items")

    relevant = filter_and_score(all_articles, days=lookback)
    log.info(f"Relevant after filtering: {len(relevant)} items")

    subject, html = build_email(relevant)

    if dry_run:
        with open("preview.html", "w") as f:
            f.write(html)
        log.info("DRY RUN — saved to preview.html")
        print(f"\nSubject: {subject}")
        print(f"Articles: {len(relevant)}")
        for a in relevant:
            print(f"  [{a.urgency:8}] {a.area:20} {a.title[:60]}")
    else:
        if not relevant:
            log.info("No relevant articles — skipping email")
            return
        send_email(subject, html)

    log.info("Done.")


if __name__ == "__main__":
    main()
