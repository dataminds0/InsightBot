# -- coding: utf-8 --
import re
import os
import json
import time
import csv
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlunparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

# ----------------------------------------------------
# SETTINGS
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}
TIMEOUT = 5
MAX_LINKS_PER_SITE = 100
REQUEST_DELAY_SEC = 0.5

# ----------------------------------------------------
# SITES
SITES = [
    # English
    {"name": "cnn", "list_url": "https://edition.cnn.com/world", "base": "https://edition.cnn.com",
    "link_selector": "a.container_link.containerlink--type-article, a.container_lead-plus-headlines_link, a[href*='/202']",
    "rss": "https://rss.cnn.com/rss/edition_world.rss"},
    {"name": "bbc", "list_url": "https://www.bbc.com/news", "base": "https://www.bbc.com",
    "link_selector": "a.gs-c-promo-heading[href*='/news/']",
    "rss": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "nytimes", "list_url": "https://www.nytimes.com/section/world", "base": "https://www.nytimes.com",
    "link_selector": "a[href*='/20'][href$='.html']",
    "rss": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
    {"name": "guardian", "list_url": "https://www.theguardian.com/world", "base": "https://www.theguardian.com",
    "link_selector": "a[href*='/world/']",
    "rss": "https://www.theguardian.com/world/rss"},
    {"name": "reuters", "list_url": "https://www.reuters.com/world", "base": "https://www.reuters.com",
    "link_selector": "a[href*='/world/']",
    "rss": "https://feeds.reuters.com/reuters/worldNews"},
    {"name": "washingtonpost", "list_url": "https://www.washingtonpost.com/world", "base": "https://www.washingtonpost.com",
    "link_selector": "a[href*='/world/']",
    "rss": "https://feeds.washingtonpost.com/rss/world"},
    {"name": "forbes", "list_url": "https://www.forbes.com", "base": "https://www.forbes.com",
    "link_selector": "a[href*='/']",
    "rss": ""},
    {"name": "techcrunch", "list_url": "https://techcrunch.com", "base": "https://techcrunch.com",
    "link_selector": "a.post-block__title__link",
    "rss": "https://techcrunch.com/feed/"},
    {"name": "thenextweb", "list_url": "https://thenextweb.com", "base": "https://thenextweb.com",
    "link_selector": "a[href*='/news/']",
    "rss": ""},
    {"name": "medium", "list_url": "https://medium.com/topic/world", "base": "https://medium.com",
    "link_selector": "a[href*='medium.com']",
    "rss": "https://medium.com/feed/tag/world"},
    {"name": "devto", "list_url": "https://dev.to", "base": "https://dev.to",
    "link_selector": "a.crayons-story__hidden-navigation-link",
    "rss": "https://dev.to/feed"},
    {"name": "mashable", "list_url": "https://mashable.com", "base": "https://mashable.com",
    "link_selector": "a[href*='/article/']",
    "rss": "https://mashable.com/feeds/rss"},
    {"name": "wsj", "list_url": "https://www.wsj.com/news/world", "base": "https://www.wsj.com",
    "link_selector": "a[href*='/articles/']",
    "rss": ""},
    {"name": "wired", "list_url": "https://www.wired.com", "base": "https://www.wired.com",
    "link_selector": "a[href*='/story/']",
    "rss": "https://www.wired.com/feed/rss"},
    {"name": "npr", "list_url": "https://www.npr.org/sections/world/", "base": "https://www.npr.org",
    "link_selector": "a[href*='/202']",
    "rss": "https://feeds.npr.org/1004/rss.xml"},
    {"name": "vox", "list_url": "https://www.vox.com/world", "base": "https://www.vox.com",
    "link_selector": "a[href*='/20']",
    "rss": "https://www.vox.com/rss/world/index.xml"},
    {"name": "bloomberg", "list_url": "https://www.bloomberg.com/world", "base": "https://www.bloomberg.com",
    "link_selector": "a[href*='/news/articles/']",
    "rss": ""},
    {"name": "seekingalpha", "list_url": "https://seekingalpha.com/market-news", "base": "https://seekingalpha.com",
    "link_selector": "a[href*='/news/']",
    "rss": "https://seekingalpha.com/market_currents.xml"},
    {"name": "engadget", "list_url": "https://www.engadget.com", "base": "https://www.engadget.com",
    "link_selector": "a[href*='/202']",
    "rss": "https://www.engadget.com/rss.xml"},
    {"name": "verge", "list_url": "https://www.theverge.com", "base": "https://www.theverge.com",
    "link_selector": "a[href*='/20']",
    "rss": "https://www.theverge.com/rss/index.xml"},
    {"name": "ft", "list_url": "https://www.ft.com/world", "base": "https://www.ft.com",
    "link_selector": "a[href*='/content/']",
    "rss": ""},
    {"name": "arstechnica", "list_url": "https://arstechnica.com", "base": "https://arstechnica.com",
    "link_selector": "a[href*='/20']",
    "rss": "https://arstechnica.com/feed/"},
    {"name": "cnet", "list_url": "https://www.cnet.com/news/", "base": "https://www.cnet.com",
    "link_selector": "a[href*='/news/']",
    "rss": "https://www.cnet.com/rss/news/"},
    {"name": "slashdot", "list_url": "https://slashdot.org", "base": "https://slashdot.org",
    "link_selector": "a.story",
    "rss": "http://rss.slashdot.org/Slashdot/slashdotMain"},
    {"name": "huffpost", "list_url": "https://www.huffpost.com/news/world-news", "base": "https://www.huffpost.com",
    "link_selector": "a[href*='/entry/']",
    "rss": "https://www.huffpost.com/section/world-news/feed"},

    # Arabic
    {"name": "aljazeera_ar", "list_url": "https://www.aljazeera.net", "base": "https://www.aljazeera.net",
    "link_selector": "a[href*='/news/']",
    "rss": "https://www.aljazeera.net/aljazeera-arabic-feed"},
    {"name": "skynewsarabia", "list_url": "https://www.skynewsarabia.com", "base": "https://www.skynewsarabia.com",
    "link_selector": "a[href*='/news/']",
    "rss": "https://www.skynewsarabia.com/web/rss/rss"},
    {"name": "alarabiya", "list_url": "https://www.alarabiya.net", "base": "https://www.alarabiya.net",
    "link_selector": "a[href*='/news/']",
    "rss": "https://www.alarabiya.net/.mrss/ar.xml"},
    {"name": "akhbaar24", "list_url": "https://www.akhbaar24.com", "base": "https://www.akhbaar24.com",
    "link_selector": "a[href*='/article/']",
    "rss": ""},
    {"name": "middleeastonline", "list_url": "https://middle-east-online.com", "base": "https://middle-east-online.com",
    "link_selector": "a[href*='/']",
    "rss": ""},
    {"name": "thenational", "list_url": "https://www.thenationalnews.com", "base": "https://www.thenationalnews.com",
    "link_selector": "a[href*='/']",
    "rss": "https://www.thenationalnews.com/arc/outboundfeeds/rss/"},
    {"name": "arabiccnn", "list_url": "https://arabic.cnn.com", "base": "https://arabic.cnn.com",
    "link_selector": "a[href*='/']",
    "rss": "https://arabic.cnn.com/rss"},
    {"name": "bbcarabic", "list_url": "https://www.bbc.com/arabic", "base": "https://www.bbc.com/arabic",
    "link_selector": "a[href*='/']",
    "rss": "https://feeds.bbci.co.uk/arabic/rss.xml"},
    {"name": "masaar", "list_url": "https://www.masaar.com", "base": "https://www.masaar.com",
    "link_selector": "a[href*='/']",
    "rss": ""},
    {"name": "9elp", "list_url": "https://9elp.com", "base": "https://9elp.com",
    "link_selector": "a[href*='/']",
    "rss": ""},

    # Russian
    {"name": "rt", "list_url": "https://www.rt.com", "base": "https://www.rt.com",
    "link_selector": "a[href*='/']",
    "rss": "https://www.rt.com/rss/news/"},
    {"name": "tass", "list_url": "https://tass.com", "base": "https://tass.com",
    "link_selector": "a[href*='/']",
    "rss": "https://tass.com/rss/v2.xml"},
    {"name": "rbc", "list_url": "https://www.rbc.ru", "base": "https://www.rbc.ru",
    "link_selector": "a[href*='/']",
    "rss": "https://rssexport.rbc.ru/rbcnews/news/20/full.rss"},
    {"name": "meduza", "list_url": "https://meduza.io/en", "base": "https://meduza.io/en",
    "link_selector": "a[href*='/']",
    "rss": "https://meduza.io/en/rss/all"},
    {"name": "echo", "list_url": "https://echo.msk.ru", "base": "https://echo.msk.ru",
    "link_selector": "a[href*='/']",
    "rss": ""},
]

# ----------------------------------------------------
# NETWORK HELPERS
def make_session():
    s = requests.Session()
    retries = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update(HEADERS)
    return s

def domain_headers(url: str):
    ua_mobile = ("Mozilla/5.0 (Linux; Android 12; SM-G991B) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                 "Chrome/128.0.0.0 Mobile Safari/537.36")
    h = dict(HEADERS)
    try:
        netloc = urlparse(url).netloc
    except Exception:
        netloc = ""
    if any(d in netloc for d in ["nytimes.com", "washingtonpost.com"]):
        h["User-Agent"] = ua_mobile
        h["Referer"] = "https://news.google.com/"
    return h

def is_valid_url(u: str) -> bool:
    if not u: return False
    p = urlparse(u)
    return p.scheme in ("http", "https") and bool(p.netloc)

def strip_tracking_params(url: str) -> str:
    try:
        p = urlparse(url)
        qs = parse_qs(p.query)
        keep = {k: v for k, v in qs.items()
                if not re.match(r'^(utm_|fbclid|gclid|gclsrc|mc_cid|mc_eid|_hsenc|_hsmi|ref|ref_src|spm)$', k)}
        q = "&".join([f"{k}={v[0]}" for k, v in keep.items() if v])
        return urlunparse((p.scheme, p.netloc, p.path, p.params, q, ""))
    except Exception:
        return url

def normalize_url(base: str, href: str) -> str | None:
    if not href: return None
    absu = urljoin(base, href.strip())
    return strip_tracking_params(absu) if is_valid_url(absu) else None

# ----------------------------------------------------
# LINK FILTERS
def should_skip_url(u: str, site_name: str) -> bool:
    blocked_domains = ("facebook.com", "twitter.com", "x.com", "instagram.com", "t.me", "wa.me", "whatsapp.com", "consent.youtube.com")
    if any(d in u for d in blocked_domains):
        return True
    bad_parts = ("/signin", "/login", "/subscribe", "/registration", "/privacy", "/terms")
    if any(bp in u for bp in bad_parts):
        return True
    if "nytimes.com" in u and ("/live/" in u or "/interactive/" in u or "/video/" in u):
        return True
    return False

# ----------------------------------------------------
# LINK DISCOVERY
def get_links_from_listing(session, site):
    try:
        r = session.get(site["list_url"], timeout=TIMEOUT, headers=domain_headers(site["list_url"]))
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        raw = []
        for a in soup.select(site["link_selector"]):
            href = a.get("href")
            u = normalize_url(site["base"], href)
            if not u: continue
            if should_skip_url(u, site["name"]): continue
            raw.append(u)
            if len(raw) >= MAX_LINKS_PER_SITE * 2:
                break
        seen, out = set(), []
        for u in raw:
            if u not in seen:
                out.append(u); seen.add(u)
            if len(out) >= MAX_LINKS_PER_SITE:
                break
        return out
    except requests.RequestException:
        return []

def get_links_from_rss(session, rss_url, base=""):
    if not rss_url:
        return []
    feeds = rss_url if isinstance(rss_url, list) else [rss_url]
    links_raw = []
    for feed in feeds:
        try:
            r = session.get(feed, timeout=TIMEOUT, headers=domain_headers(feed))
            r.raise_for_status()
            root = ET.fromstring(r.content)

            for item in root.findall(".//item"):
                link_el = item.find("link")
                link = link_el.text.strip() if (link_el is not None and link_el.text) else None
                if not link:
                    guid = item.find("guid")
                    if guid is not None and guid.text and guid.text.strip().startswith("http"):
                        link = guid.text.strip()
                if link:
                    u = normalize_url(base, link)
                    if u and not should_skip_url(u, "rss"):
                        links_raw.append(u)
                if len(links_raw) >= MAX_LINKS_PER_SITE:
                    break

            for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                for link_el in entry.findall("{http://www.w3.org/2005/Atom}link"):
                    href = link_el.get("href")
                    if href:
                        u = normalize_url(base, href)
                        if u and not should_skip_url(u, "rss"):
                            links_raw.append(u)
                    if len(links_raw) >= MAX_LINKS_PER_SITE:
                        break
                if len(links_raw) >= MAX_LINKS_PER_SITE:
                    break

        except Exception:
            continue

    seen, links = set(), []
    for u in links_raw:
        if u not in seen:
            links.append(u); seen.add(u)
    return links[:MAX_LINKS_PER_SITE]

# ----------------------------------------------------
# ARTICLE CHECK & EXTRACT
def is_article_page(soup, url=None):
    og = soup.select_one('meta[property="og:type"]')
    if og and og.get("content", "").lower() == "article":
        return True

    for s in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(s.string or "")
            items = data if isinstance(data, list) else [data]
            for obj in items:
                if not isinstance(obj, dict): continue
                graph = obj.get("@graph")
                if isinstance(graph, list):
                    for g in graph:
                        t = str(g.get("@type", "")).lower()
                        if t in {"newsarticle", "article"}:
                            return True
                t = str(obj.get("@type", "")).lower()
                if t in {"newsarticle", "article"}:
                    return True
        except Exception:
            continue

    has_article = soup.find("article") is not None
    has_h1 = soup.find("h1") is not None
    long_ps = [p for p in soup.find_all("p") if len(p.get_text(strip=True)) > 60]
    if has_article and has_h1 and len(long_ps) >= 3:
        return True

    if url and ("bbc.com" in url) and ("/news/" in url) and (has_h1 or len(long_ps) >= 3):
        return True
    if url and ("nytimes.com" in url):
        if soup.select_one('section[name="articleBody"]'):
            ps = soup.select('section[name="articleBody"] p')
            if len([p for p in ps if len(p.get_text(strip=True)) > 60]) >= 3:
                return True
    return False

def extract_title(soup):
    og = soup.select_one('meta[property="og:title"]')
    if og and og.get("content"):
        return og["content"].strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else None

def extract_content(soup):
    def is_noise(t):
        low = t.lower()
        bad = ["copyright", "advertisement", "subscribe", "sign up", "newsletter"]
        return any(b in low for b in bad)

    body_section = soup.select_one('section[name="articleBody"]')
    if body_section:
        ps = [p.get_text(" ", strip=True) for p in body_section.select("p")]
        ps = [t for t in ps if len(t) > 60 and not is_noise(t)]
        if ps:
            return "\n\n".join(ps)

    art = soup.find("article")
    candidates = art.find_all("p") if art else soup.find_all("p")
    paras = [p.get_text(" ", strip=True) for p in candidates]
    paras = [t for t in paras if len(t) > 60 and not is_noise(t)]
    return "\n\n".join(paras) if paras else None

# ----------------------------------------------------
# FETCH ARTICLE
def fetch_article(session, url):
    t0 = time.time()

    def ok_payload(soup, final_url):
        title = extract_title(soup)
        body = extract_content(soup)
        if not title or not body:
            return None
        t_sec = round(time.time() - t0, 3)
        return {
            "url": final_url,
            "title": title,
            "content": body,
            "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "t_total_sec": t_sec,
            "h1": " ".join([h.get_text(" ", strip=True) for h in soup.find_all("h1")]) or title,
            "h2": " ".join([h.get_text(" ", strip=True) for h in soup.find_all("h2")]),
        }

    try:
        if not is_valid_url(url):
            print(f"    skip reason: invalid-url | {url}")
            return None

        if "nytimes.com" in url:
            if any(seg in url for seg in ["/live/", "/interactive/", "/video/"]):
                print(f"    skip reason: nyt-live-or-interactive | {url}")
                return None
            amp_url = url[:-5] + ".amp.html" if url.endswith(".html") else (url.rstrip("/") + ".amp.html")
            try:
                r_amp = session.get(amp_url, timeout=TIMEOUT, headers=domain_headers(amp_url))
                if r_amp.status_code == 200 and "text/html" in (r_amp.headers.get("Content-Type", "")):
                    soup_amp = BeautifulSoup(r_amp.text, "html.parser")
                    if is_article_page(soup_amp, amp_url):
                        payload = ok_payload(soup_amp, amp_url)
                        if payload: return payload
            except requests.RequestException:
                pass

        if "washingtonpost.com" in url:
            amp_url = url + ("&" if "?" in url else "?") + "outputType=amp"
            try:
                r_amp = session.get(amp_url, timeout=TIMEOUT, headers=domain_headers(amp_url))
                if r_amp.status_code == 200 and "text/html" in (r_amp.headers.get("Content-Type", "")):
                    soup_amp = BeautifulSoup(r_amp.text, "html.parser")
                    if is_article_page(soup_amp, amp_url):
                        payload = ok_payload(soup_amp, amp_url)
                        if payload: return payload
            except requests.RequestException:
                pass

        r = session.get(url, timeout=TIMEOUT, headers=domain_headers(url))
        if r.status_code == 200 and "text/html" in (r.headers.get("Content-Type", "")):
            soup = BeautifulSoup(r.text, "html.parser")
            if is_article_page(soup, url):
                payload = ok_payload(soup, url)
                if payload: return payload

        alt = "https://r.jina.ai/" + url
        try:
            r_alt = session.get(alt, timeout=TIMEOUT)
            if r_alt.status_code == 200:
                soup_alt = BeautifulSoup(r_alt.text, "html.parser")
                if is_article_page(soup_alt, url):
                    payload = ok_payload(soup_alt, url)
                    if payload: return payload
        except requests.RequestException:
            pass

        print(f"    skip reason: bad-status-or-content-type({r.status_code if 'r' in locals() else 'NA'}) | {url}")
        return None

    except requests.RequestException as e:
        try:
            alt = "https://r.jina.ai/" + url
            r_alt = session.get(alt, timeout=TIMEOUT)
            if r_alt.status_code == 200:
                soup_alt = BeautifulSoup(r_alt.text, "html.parser")
                if is_article_page(soup_alt, url):
                    payload = ok_payload(soup_alt, url)
                    if payload: return payload
        except requests.RequestException:
            pass
        print(f"    skip reason: exception {e.__class__.__name__} | {url}")
        return None

# ----------------------------------------------------
# STORAGE (CSV)
CSV_PATH = r"./data/raw/data.csv"

def load_existing():
    """
    Load previous JSON (if exists) and CSV (if exists)
    to continue IDs. No dedup is applied anymore.
    """
    existing = []
    seen_titles = set()
    seen_urls = set()
    max_id = 0

    if os.path.isfile(CSV_PATH):
        try:
            with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
                r = csv.DictReader(f)
                for row in r:
                    existing.append({
                        "id": int(row.get("id") or 0) if row.get("id") else None,
                        "source": row.get("source") or "",
                        "url": (row.get("url") or "").strip(),
                        "title": (row.get("title") or "").strip(),
                        "fetched_at": row.get("fetched_at") or "",
                        "t_total_sec": float(row.get("t_total_sec") or 0) if row.get("t_total_sec") else 0,
                        "content": row.get("content") or "",
                        "h1": row.get("h1") or "",
                        "h2": row.get("h2") or "",
                    })
                    try:
                        iid = int(row.get("id") or 0)
                        if iid > max_id: max_id = iid
                    except Exception:
                        pass
        except Exception:
            pass

    return existing, seen_titles, seen_urls, max_id

def save_csv(path, rows):
    keys = ["id", "source", "url", "title", "fetched_at", "t_total_sec", "content", "h1", "h2"]
    if not rows:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in keys})

# ----------------------------------------------------
# MAIN
def main():
    session = make_session()

    existing_rows, _seen_titles, _seen_urls, max_id = load_existing()
    print(f"Loaded existing articles: {len(existing_rows)}, max_id={max_id}")

    all_articles = list(existing_rows)
    next_id = max_id + 1

    for site in SITES:
        print(f"\n=== {site['name'].upper()} ===")
        links = get_links_from_rss(session, site.get("rss"), site.get("base", "")) or \
                get_links_from_listing(session, site)
        links = [strip_tracking_params(u) for u in links if is_valid_url(u)][:MAX_LINKS_PER_SITE]
        print(f"Found links: {len(links)}")

        count_ok = 0
        for i, u in enumerate(links, 1):
            art = fetch_article(session, u)
            if art:
                art["id"] = next_id; next_id += 1
                art["source"] = site["name"]
                all_articles.append(art)
                count_ok += 1
                print(f"[+][{site['name']}] {count_ok}/{i} ok ({art['t_total_sec']}s) id={art['id']}")
            else:
                print(f"[-][{site['name']}] {i} skipped")
            time.sleep(REQUEST_DELAY_SEC)

    print(f"\nTOTAL articles after merge: {len(all_articles)}")

    # Save CSV
    try:
        save_csv(CSV_PATH, all_articles)
        print(f"Saved CSV : {CSV_PATH}")
    except Exception as e:
        print(f"Error saving CSV: {e}")

main()
