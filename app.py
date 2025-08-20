import re
import json
import time
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
import streamlit as st

# ------------------------------
# CONFIG / FALLBACKS
# ------------------------------
SCRAPER_API_KEY = ""  # optional fallback; leave empty if you don't have one

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0 Safari/537.36"
    )
}

# ------------------------------
# FETCHERS
# ------------------------------
def fetch_html(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.text
        st.warning(f"First attempt failed: HTTP {r.status_code}")
    except Exception as e:
        st.warning(f"Error during normal fetch: {e}")

    if SCRAPER_API_KEY:
        try:
            api_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={url}"
            r = requests.get(api_url, timeout=30)
            if r.status_code == 200:
                return r.text
            st.error(f"ScraperAPI failed: HTTP {r.status_code}")
        except Exception as e:
            st.error(f"ScraperAPI error: {e}")
    return None


def fetch_resource_head(url: str, timeout=10):
    try:
        r = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        return r
    except Exception:
        return None


def try_get_json_ld(soup: BeautifulSoup):
    items = []
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(tag.get_text(strip=True))
            if isinstance(data, list):
                items.extend(data)
            else:
                items.append(data)
        except Exception:
            continue
    return items

# ------------------------------
# HELPERS
# ------------------------------
def visible_text(soup: BeautifulSoup) -> str:
    # Remove scripts/styles/noscript
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    # Remove nav/footer/aside to reduce boilerplate noise (best-effort)
    for t in soup(["nav", "footer", "aside"]):
        t.decompose()
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def flesch_reading_ease(text: str) -> float:
    # Basic syllable estimate: count vowel groups
    sentences = re.split(r"[.!?]+", text)
    sentences = [s for s in sentences if s.strip()]
    words = re.findall(r"\b\w+\b", text)
    if not words or not sentences:
        return 0.0
    def syllables(w):
        w = w.lower()
        groups = re.findall(r"[aeiouy]+", w)
        return max(1, len(groups))
    total_syll = sum(syllables(w) for w in words)
    asl = len(words) / max(1, len(sentences))
    asw = total_syll / max(1, len(words))
    score = 206.835 - (1.015 * asl) - (84.6 * asw)
    return round(score, 2)


def detect_content_type(url: str, soup: BeautifulSoup, text: str, json_ld: list[str]) -> str:
    u = url.lower()
    # URL patterns
    if "/blog/" in u or "/article" in u:
        return "Blog Post"
    if "/product" in u or "/shop/" in u:
        return "Product Page"
    if "/services" in u or "/service" in u or "solutions" in text[:600].lower():
        return "Service Page"
    if "/faq" in u:
        return "FAQ Page"
    if re.search(r"/(pricing|price)\b", u):
        return "Landing Page"

    # JSON-LD types
    types = []
    for item in json_ld:
        t = item.get("@type") if isinstance(item, dict) else None
        if isinstance(t, list):
            types.extend(t)
        elif isinstance(t, str):
            types.append(t)
    types = [str(t) for t in types]
    if "Product" in types:
        return "Product Page"
    if "FAQPage" in types:
        return "FAQ Page"
    if "Article" in types or "BlogPosting" in types or soup.find("article"):
        # Very long? Pillar page
        wc = count_words(text)
        if wc >= 2000 and len(soup.find_all(["h2", "h3"])) >= 6:
            return "Pillar Page"
        return "Blog Post"

    # Heuristics
    wc = count_words(text)
    h2h3 = len(soup.find_all(["h2", "h3"]))
    if wc >= 2200 and h2h3 >= 6:
        return "Pillar Page"
    if len(soup.find_all("h1")) == 1 and "get a quote" in text.lower():
        return "Service Page"
    # Home?
    if urlparse(url).path in ["", "/", "/home", "/index.html"]:
        return "Home Page"

    return "Landing Page"


def tokens(s: str):
    return [t.lower() for t in re.findall(r"[a-z0-9]+", s.lower())]


def url_slug_keywords(url: str, primary_kw: str) -> int:
    path = urlparse(url).path
    slug_parts = tokens(path)
    kw_parts = tokens(primary_kw)
    return len(set(slug_parts) & set(kw_parts))


def pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 2)

# ------------------------------
# SCORING (YOUR FRAMEWORK)
# ------------------------------
def score_content_pillar(content_type: str, text: str, primary_kw: str, lsi_terms: list[str], originality_pct: float | None):
    """
    Returns: (score_obtained, score_available, details, suggestions)
    """
    score = 0.0
    available = 0.0
    suggestions = []
    details = {}

    wc = count_words(text)
    details["Word Count"] = wc

    # Ideal word counts
    ideal_wc = {
        "Blog Post": (1200, 2000),
        "Pillar Page": (2000, 4000),
        "Product Page": (500, 800),
        "Service Page": (700, 1200),
        "FAQ Page": (300, 700),
        "Landing Page": (400, 900),
        "Home Page": (400, 1200),
        "News Article": (600, 1000),
    }
    # 3 marks
    available += 3
    low, high = ideal_wc.get(content_type, (600, 1500))
    if low <= wc <= high:
        score += 3
        details["Word Count Score"] = "3 / 3"
    elif (low * 0.85) <= wc <= (high * 1.15):
        score += 2
        details["Word Count Score"] = "2 / 3"
        suggestions.append(f"Adjust word count toward {low}-{high} words.")
    else:
        details["Word Count Score"] = "0 / 3"
        suggestions.append(f"Word count far from ideal ({low}-{high}).")

    # Keyword density (3 marks)
    available += 3
    primary_kw = primary_kw.strip()
    dens = 0.0
    if primary_kw and wc > 0:
        occurrences = len(re.findall(re.escape(primary_kw), text, flags=re.I))
        dens = (occurrences / wc) * 100.0
    details["Keyword Density (%)]"] = round(dens, 2)

    density_ranges = {
        "Blog Post": (1.0, 2.5),
        "Pillar Page": (0.8, 1.5),
        "Product Page": (1.5, 3.0),
        "Service Page": (1.0, 2.0),
        "Landing Page": (0.5, 1.2),
        "FAQ Page": (0.8, 1.5),
        "Home Page": (0.8, 1.8),
        "News Article": (0.8, 1.8),
    }
    dens_low, dens_high = density_ranges.get(content_type, (0.8, 2.0))
    if dens_low <= dens <= dens_high:
        score += 3
        details["Keyword Density Score"] = "3 / 3"
    elif (dens_low - 0.2) <= dens <= (dens_high + 0.2):
        score += 2
        details["Keyword Density Score"] = "2 / 3"
        suggestions.append(f"Align keyword density to {dens_low}-{dens_high}%.")
    else:
        details["Keyword Density Score"] = "0 / 3"
        suggestions.append(f"Keyword density outside {dens_low}-{dens_high}%.")

    # Keyword placement (5 marks)
    available += 5
    placement_score = 0
    # Title, meta, intro(=first 100 words), H1, H2/H3 presence
    intro = " ".join(text.split()[:100]).lower()
    h1s = [h.get_text(" ").strip().lower() for h in soup_global.find_all("h1")]
    h2h3s = [h.get_text(" ").strip().lower() for h in soup_global.find_all(["h2", "h3"])]

    if primary_kw:
        if primary_kw.lower() in (soup_global.title.get_text(" ").lower() if soup_global.title else ""):
            placement_score += 1
        meta_tag = soup_global.find("meta", attrs={"name": "description"})
        if meta_tag and primary_kw.lower() in meta_tag.get("content", "").lower():
            placement_score += 1
        if primary_kw.lower() in intro:
            placement_score += 1
        if any(primary_kw.lower() in h for h in h1s):
            placement_score += 1
        if any(primary_kw.lower() in h for h in h2h3s):
            placement_score += 1

    score += placement_score
    details["Keyword Placement Score"] = f"{placement_score} / 5"
    if placement_score < 5:
        suggestions.append("Place primary keyword in title, meta description, intro, H1 and at least one H2/H3.")

    # LSI terms (3 marks)
    available += 3
    lsi_terms = [t.strip() for t in lsi_terms if t.strip()]
    lsi_score = 0
    if lsi_terms:
        hits = sum(1 for t in lsi_terms if re.search(re.escape(t), text, flags=re.I))
        # Target per content type
        lsi_ratio = {
            "Blog Post": 400,
            "Pillar Page": 300,
            "Product Page": 400,
            "Service Page": 400,
            "FAQ Page": 350,
            "Landing Page": 500,
            "Home Page": 450,
            "News Article": 400,
        }
        per = lsi_ratio.get(content_type, 400)
        ideal_terms = max(1, round(wc / per))
        coverage = (hits / ideal_terms) if ideal_terms > 0 else 0
        details["LSI Target"] = ideal_terms
        details["LSI Hits"] = hits
        if coverage >= 1.0:
            lsi_score = 3
        elif coverage >= 0.7:
            lsi_score = 2
        else:
            lsi_score = 0
        if coverage < 1.0:
            suggestions.append(f"Add more related terms (target ≈ {ideal_terms}, found {hits}).")
    else:
        details["LSI Target"] = "N/A (no terms provided)"
        lsi_score = 0
        suggestions.append("Provide a list of LSI/related terms for stronger topical coverage.")
    score += lsi_score
    details["LSI Score"] = f"{lsi_score} / 3"

    # Readability (3 marks)
    available += 3
    fre = flesch_reading_ease(text)
    details["Flesch Reading Ease"] = fre
    thresholds = {
        "Blog Post": 60, "Pillar Page": 55, "Product Page": 65, "Service Page": 60,
        "FAQ Page": 70, "Landing Page": 65, "Home Page": 60, "News Article": 60,
    }
    th = thresholds.get(content_type, 60)
    if fre >= th:
        score += 3
        details["Readability Score"] = "3 / 3"
    elif fre >= (th - 10):
        score += 2
        details["Readability Score"] = "2 / 3"
        suggestions.append(f"Improve readability to ≥ {th} (shorter sentences, simpler words).")
    else:
        details["Readability Score"] = "0 / 3"
        suggestions.append(f"Low readability ({fre}). Aim for ≥ {th}.")

    # Originality (3 marks) – optional input
    available += 3
    if originality_pct is None:
        details["Originality Score"] = "Excluded (no % provided)"
        available -= 3  # exclude from denominator
    else:
        if originality_pct >= 95:
            score += 3
            details["Originality Score"] = f"3 / 3 ({originality_pct}%)"
        elif originality_pct >= 85:
            score += 2
            details["Originality Score"] = f"2 / 3 ({originality_pct}%)"
            suggestions.append("Increase originality to ≥ 95%.")
        else:
            details["Originality Score"] = f"0 / 3 ({originality_pct}%)"
            suggestions.append("Originality too low; rewrite to avoid duplication.")

    return score, available, details, suggestions


def score_html_pillar(soup: BeautifulSoup, content_type: str):
    score = 0.0
    available = 10.0
    suggestions = []
    details = {}

    # Title length (1)
    title = soup.title.get_text(" ").strip() if soup.title else ""
    tl = len(title)
    details["Title Length"] = tl
    if tl <= 60 and tl >= 10:
        score += 1
        details["Title Score"] = "1 / 1"
    elif 61 <= tl <= 65 or 8 <= tl < 10:
        score += 0.5
        details["Title Score"] = "0.5 / 1"
        suggestions.append("Adjust title to ≤ 60 chars and descriptive.")
    else:
        details["Title Score"] = "0 / 1"
        suggestions.append("Fix title: missing or outside ideal length.")

    # Meta description (1)
    meta_desc = soup.find("meta", attrs={"name": "description"})
    md = meta_desc.get("content", "").strip() if meta_desc else ""
    details["Meta Description Length"] = len(md)
    if 150 <= len(md) <= 160:
        score += 1
        details["Meta Description Score"] = "1 / 1"
    elif 140 <= len(md) <= 170:
        score += 0.5
        details["Meta Description Score"] = "0.5 / 1"
        suggestions.append("Refine meta to 150–160 chars with primary keyword.")
    else:
        details["Meta Description Score"] = "0 / 1"
        suggestions.append("Add a meta description (150–160 chars).")

    # H1 (2)
    h1s = soup.find_all("h1")
    details["H1 Count"] = len(h1s)
    if len(h1s) == 1:
        score += 2
        details["H1 Score"] = "2 / 2"
    elif len(h1s) > 1:
        score += 1
        details["H1 Score"] = "1 / 2"
        suggestions.append("Use exactly one H1.")
    else:
        details["H1 Score"] = "0 / 2"
        suggestions.append("Add a descriptive H1.")

    # H2+ structure (2)
    need_map = {
        "Blog Post": 2, "Pillar Page": 5, "Product Page": 1, "Service Page": 2,
        "FAQ Page": 3, "Landing Page": 1, "Home Page": 2, "News Article": 2
    }
    needed = need_map.get(content_type, 2)
    h2plus = len(soup.find_all(["h2", "h3", "h4"]))
    details["H2+ Count"] = h2plus
    if h2plus >= needed:
        score += 2
        details["H2+ Score"] = "2 / 2"
    elif h2plus == max(0, needed - 1):
        score += 1
        details["H2+ Score"] = "1 / 2"
        suggestions.append(f"Add more subheadings (target ≥ {needed}).")
    else:
        details["H2+ Score"] = "0 / 2"
        suggestions.append(f"Add subheadings (need ≥ {needed}).")

    # Alt text coverage (2)
    imgs = soup.find_all("img")
    with_alt = sum(1 for i in imgs if i.get("alt") and i.get("alt").strip())
    coverage = pct(with_alt, len(imgs)) if imgs else 100.0
    details["Alt Coverage %"] = coverage
    if coverage >= 90:
        score += 2
        details["Alt Score"] = "2 / 2"
    elif coverage >= 70:
        score += 1
        details["Alt Score"] = "1 / 2"
        suggestions.append("Increase image alt coverage to ≥ 90%.")
    else:
        details["Alt Score"] = "0 / 2"
        suggestions.append("Add descriptive alt text to images.")

    # Schema type (2)
    schema_ok = False
    json_ld = try_get_json_ld(soup)
    target_schema = {
        "Blog Post": ["Article", "BlogPosting"],
        "Pillar Page": ["Article", "WebPage"],
        "Product Page": ["Product"],
        "Service Page": ["Service", "LocalBusiness", "Organization"],
        "FAQ Page": ["FAQPage"],
        "Landing Page": ["WebPage"],
        "Home Page": ["WebPage", "Organization"],
        "News Article": ["NewsArticle", "Article"],
    }.get(content_type, ["WebPage"])
    found_types = []
    for item in json_ld:
        t = item.get("@type") if isinstance(item, dict) else None
        if isinstance(t, list):
            found_types.extend([str(x) for x in t])
        elif isinstance(t, str):
            found_types.append(t)
    if any(t in target_schema for t in found_types):
        schema_ok = True
    details["Schema Found"] = ", ".join(found_types) if found_types else "None"
    if schema_ok:
        score += 2
        details["Schema Score"] = "2 / 2"
    elif found_types:
        score += 1
        details["Schema Score"] = "1 / 2"
        suggestions.append(f"Adjust schema to {', '.join(target_schema)}.")
    else:
        details["Schema Score"] = "0 / 2"
        suggestions.append(f"Add structured data ({', '.join(target_schema)}).")

    return score, available, details, suggestions


def score_url_links_pillar(url: str, soup: BeautifulSoup, primary_kw: str):
    score = 0.0
    available = 10.0
    suggestions = []
    details = {}

    # URL length (2)
    path_full = urlparse(url).path or "/"
    url_chars = len(url.replace("https://", "").replace("http://", ""))
    details["URL Length (chars)"] = url_chars
    if 30 <= url_chars <= 65:
        score += 2
        details["URL Length Score"] = "2 / 2"
    elif 25 <= url_chars < 30 or 66 <= url_chars <= 75:
        score += 1
        details["URL Length Score"] = "1 / 2"
        suggestions.append("Optimize URL length to 30–65 chars.")
    else:
        details["URL Length Score"] = "0 / 2"
        suggestions.append("URL too short/long; aim for 30–65 chars.")

    # Keywords in URL (1)
    k_in_url = url_slug_keywords(url, primary_kw) if primary_kw else 0
    details["Keywords in URL"] = k_in_url
    if 1 <= k_in_url <= 2:
        score += 1
        details["Keywords in URL Score"] = "1 / 1"
    else:
        details["Keywords in URL Score"] = "0 / 1"
        suggestions.append("Include 1–2 primary keywords in the URL slug.")

    # Canonical (1)
    can = soup.find("link", rel=lambda x: x and "canonical" in x.lower())
    details["Canonical Tag"] = can.get("href") if can else "Missing"
    if can and can.get("href"):
        score += 1
        details["Canonical Score"] = "1 / 1"
    else:
        details["Canonical Score"] = "0 / 1"
        suggestions.append("Add a correct canonical tag.")

    # Internal / External links (2 + 2)
    a_tags = soup.find_all("a", href=True)
    domain = urlparse(url).netloc
    internals, externals = 0, 0
    for a in a_tags:
        href = a["href"]
        if href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        full = urljoin(url, href)
        if urlparse(full).netloc == domain:
            internals += 1
        else:
            externals += 1
    details["Internal Links"] = internals
    details["External Links"] = externals

    # Content-type-agnostic ranges (best-effort)
    if 2 <= internals <= 15:
        score += 2
        details["Internal Links Score"] = "2 / 2"
    elif internals in [1, 16, 17]:
        score += 1
        details["Internal Links Score"] = "1 / 2"
        suggestions.append("Keep internal links within 2–15 and ensure relevance.")
    else:
        details["Internal Links Score"] = "0 / 2"
        suggestions.append("Add relevant internal links (aim 2–15).")

    if 1 <= externals <= 5:
        score += 2
        details["External Links Score"] = "2 / 2"
    elif externals == 0 or externals > 5:
        score += 1 if externals > 0 else 0
        details["External Links Score"] = ("1 / 2" if externals > 0 else "0 / 2")
        suggestions.append("Use 1–5 authoritative external links.")
    else:
        details["External Links Score"] = "0 / 2"

    # Broken links (2)
    broken = 0
    check_sample = a_tags[:15]  # limit for speed
    for a in check_sample:
        full = urljoin(url, a["href"])
        r = fetch_resource_head(full, timeout=6)
        if not r or r.status_code >= 400:
            broken += 1
    details["Broken Links (sample of ~15)"] = broken
    if broken == 0:
        score += 2
        details["Broken Links Score"] = "2 / 2"
    elif broken == 1:
        score += 1
        details["Broken Links Score"] = "1 / 2"
        suggestions.append("Fix the broken link found.")
    else:
        details["Broken Links Score"] = "0 / 2"
        suggestions.append("Fix broken links (check all anchors).")

    return score, available, details, suggestions


def get_pagespeed_metrics(url: str, api_key: str):
    # Returns dict or None
    try:
        endpoint = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        params = {
            "url": url,
            "strategy": "mobile",
        }
        if api_key:
            params["key"] = api_key
        r = requests.get(endpoint, params=params, timeout=45)
        if r.status_code != 200:
            return None
        data = r.json()
        # Lighthouse audits
        audits = data.get("lighthouseResult", {}).get("audits", {})
        lcp = audits.get("largest-contentful-paint", {}).get("numericValue")
        cls = audits.get("cumulative-layout-shift", {}).get("numericValue")
        fid_like = audits.get("interactive", {}).get("numericValue")  # not FID, but we note
        # Convert ms to s for LCP
        lcp = (lcp / 1000.0) if isinstance(lcp, (int, float)) else None
        # CLS already unitless
        # FID proxy (Total Blocking Time sometimes available)
        tbt = audits.get("total-blocking-time", {}).get("numericValue")
        return {
            "lcp": lcp,
            "cls": cls,
            "tbt_ms": tbt,
            "interactive_ms": fid_like,
        }
    except Exception:
        return None


def score_performance_pillar(url: str, soup: BeautifulSoup, psi_key: str):
    score = 0.0
    available = 30.0
    suggestions = []
    details = {}

    # Try PSI
    psi = get_pagespeed_metrics(url, psi_key) if psi_key else None
    if psi:
        lcp = psi.get("lcp")
        cls = psi.get("cls")
        tbt = psi.get("tbt_ms")
        # Heuristic FID proxy from TBT
        fid_est = None
        if isinstance(tbt, (int, float)):
            fid_est = max(0, min(300, tbt * 0.5))  # rough proxy
        details["LCP (s)"] = lcp
        details["CLS"] = cls
        details["FID (est. ms)"] = round(fid_est, 0) if fid_est is not None else "N/A"

        # LCP scoring (6)
        ideal_lcp = 2.5
        if lcp is not None:
            if lcp <= ideal_lcp:
                score += 6
                details["LCP Score"] = "6 / 6"
            elif lcp <= ideal_lcp + 0.5:
                score += 4
                details["LCP Score"] = "4 / 6"
                suggestions.append("Improve LCP by optimizing hero image/fonts and server TTFB.")
            else:
                details["LCP Score"] = "0 / 6"
                suggestions.append("High LCP; compress images, enable caching/CDN, reduce JS.")
        else:
            details["LCP Score"] = "0 / 6"
            suggestions.append("Could not read LCP from PSI.")

        # FID/TBT scoring (5)
        if fid_est is not None and fid_est <= 100:
            score += 5
            details["FID Score"] = "5 / 5"
        elif fid_est is not None and fid_est <= 200:
            score += 3
            details["FID Score"] = "3 / 5"
            suggestions.append("Reduce main-thread work; split bundles; defer non-critical JS.")
        else:
            details["FID Score"] = "0 / 5"
            suggestions.append("High input delay; audit JS and reduce long tasks.")

        # CLS scoring (5)
        if cls is not None and cls <= 0.1:
            score += 5
            details["CLS Score"] = "5 / 5"
        elif cls is not None and cls <= 0.25:
            score += 3
            details["CLS Score"] = "3 / 5"
            suggestions.append("Stabilize layout; set width/height for images/ads; avoid shifts.")
        else:
            details["CLS Score"] = "0 / 5"
            suggestions.append("Large layout shift; reserve space for media and late content.")

        # Total Load Time (6) from PSI interactive_ms (fallback)
        interactive = psi.get("interactive_ms")
        if isinstance(interactive, (int, float)):
            sec = interactive / 1000.0
            details["Total Load (s)"] = round(sec, 2)
            if sec <= 3.0:
                score += 6
                details["Load Time Score"] = "6 / 6"
            elif sec <= 4.0:
                score += 3
                details["Load Time Score"] = "3 / 6"
                suggestions.append("Reduce overall JS/CSS, enable compression & HTTP/2.")
            else:
                details["Load Time Score"] = "0 / 6"
                suggestions.append("Slow load; audit network waterfall for heavy assets.")
        else:
            available -= 6
            details["Load Time Score"] = "Excluded (no PSI interactive)"
    else:
        # Heuristic fallback (labelled)
        details["Performance Mode"] = "Heuristic (no PSI key)"
        # LCP heuristic: hero image presence + page weight proxy by images HEAD
        imgs = soup.find_all("img")
        total_img_kb = 0
        checked = 0
        for img in imgs[:8]:  # limit
            src = img.get("src") or img.get("data-src")
            if not src:
                continue
            full = urljoin(url, src)
            r = fetch_resource_head(full, timeout=6)
            if r and "content-length" in r.headers:
                try:
                    total_img_kb += int(r.headers["content-length"]) / 1024.0
                    checked += 1
                except Exception:
                    continue
        details["Image Weight (sample KB)"] = round(total_img_kb, 1)

        # LCP (6): penalize heavy above-the-fold images (very rough)
        if total_img_kb <= 300:
            score += 4
            details["LCP Heuristic Score"] = "4 / 6"
        elif total_img_kb <= 600:
            score += 2
            details["LCP Heuristic Score"] = "2 / 6"
            suggestions.append("Compress/resize images; use AVIF/WebP.")
        else:
            details["LCP Heuristic Score"] = "0 / 6"
            suggestions.append("Large image payload; optimize hero & critical media.")

        # FID proxy (5): inline script size
        scripts = soup.find_all("script")
        inline_bytes = sum(len(s.get_text() or "") for s in scripts if not s.get("src"))
        if inline_bytes <= 20000:
            score += 4
            details["FID Heuristic Score"] = "4 / 5"
        elif inline_bytes <= 50000:
            score += 2
            details["FID Heuristic Score"] = "2 / 5"
            suggestions.append("Reduce inline JS; defer non-critical tasks.")
        else:
            details["FID Heuristic Score"] = "0 / 5"
            suggestions.append("Heavy inline JS; split & defer.")

        # CLS proxy (5): imgs without dimensions
        imgs_no_dim = sum(1 for i in imgs if not (i.get("width") and i.get("height")))
        if imgs_no_dim == 0:
            score += 4
            details["CLS Heuristic Score"] = "4 / 5"
        elif imgs_no_dim <= 2:
            score += 2
            details["CLS Heuristic Score"] = "2 / 5"
            suggestions.append("Set width/height on images to avoid layout shift.")
        else:
            details["CLS Heuristic Score"] = "0 / 5"
            suggestions.append("Many images without dimensions; reserve space.")

        # Load time proxy (6): count external resources
        links = soup.find_all("link", href=True)
        js_ext = [s for s in scripts if s.get("src")]
        css_ext = [l for l in links if l.get("rel") and "stylesheet" in " ".join(l.get("rel")).lower()]
        ext_count = len(js_ext) + len(css_ext)
        details["External JS+CSS Count"] = ext_count
        if ext_count <= 10:
            score += 4
            details["Load Time Heuristic Score"] = "4 / 6"
        elif ext_count <= 18:
            score += 2
            details["Load Time Heuristic Score"] = "2 / 6"
            suggestions.append("Reduce external requests; bundle/minify.")
        else:
            details["Load Time Heuristic Score"] = "0 / 6"
            suggestions.append("Too many external files; consolidate assets.")

        # Media optimization (8): image sizes & formats
        large_imgs = 0
        webp_avif = 0
        for img in imgs[:15]:
            src = img.get("src") or img.get("data-src")
            if not src:
                continue
            full = urljoin(url, src)
            r = fetch_resource_head(full, timeout=6)
            if r and "content-length" in r.headers:
                try:
                    size_kb = int(r.headers["content-length"]) / 1024.0
                    if size_kb > 150:
                        large_imgs += 1
                except Exception:
                    pass
            if src.lower().endswith((".webp", ".avif")):
                webp_avif += 1
        details["Large Images (>150KB, sample)"] = large_imgs
        details["Modern Formats (sample)"] = webp_avif
        media_score = 0
        if large_imgs == 0:
            media_score += 4
        elif large_imgs <= 2:
            media_score += 2
            suggestions.append("Compress images ≥150KB.")
        # modern formats bonus
        if webp_avif >= 2:
            media_score += 4
        elif webp_avif == 1:
            media_score += 2
            suggestions.append("Use AVIF/WebP for hero & gallery.")
        details["Media Heuristic Score"] = f"{media_score} / 8"
        score += min(media_score, 8)

    return score, available, details, suggestions


def score_mobile_pillar(url: str, soup: BeautifulSoup):
    score = 0.0
    available = 30.0
    suggestions = []
    details = {}

    # Viewport meta (4)
    vp = soup.find("meta", attrs={"name": "viewport"})
    vp_content = vp.get("content", "").lower() if vp else ""
    details['Viewport Meta'] = vp_content if vp else "Missing"
    if vp and "width=device-width" in vp_content and "initial-scale=1" in vp_content:
        score += 4
        details["Viewport Score"] = "4 / 4"
    elif vp and ("width=device-width" in vp_content or "initial-scale=1" in vp_content):
        score += 2
        details["Viewport Score"] = "2 / 4"
        suggestions.append("Complete viewport tag: width=device-width, initial-scale=1.")
    else:
        details["Viewport Score"] = "0 / 4"
        suggestions.append("Add viewport meta for mobile responsiveness.")

    # Responsive layout detection via @media presence in CSS (6)
    css_links = [l.get("href") for l in soup.find_all("link", rel=True, href=True) if "stylesheet" in " ".join(l.get("rel")).lower()]
    media_found = False
    for href in css_links[:3]:
        full = urljoin(url, href)
        try:
            r = requests.get(full, headers=HEADERS, timeout=10)
            if r.status_code == 200 and re.search(r"@media\s*\(max\-width|\(min\-width", r.text, flags=re.I):
                media_found = True
                break
        except Exception:
            continue
    details["Responsive CSS (@media)"] = "Yes" if media_found else "Not detected"
    if media_found:
        score += 6
        details["Responsive Score"] = "6 / 6"
    else:
        details["Responsive Score"] = "0 / 6"
        suggestions.append("Add responsive CSS media queries.")

    # Tap targets (5) – heuristic: check for buttons/links count and padding classes/hints
    buttons = soup.find_all(["button", "a", "input"])
    probable_ctas = sum(1 for b in buttons if "btn" in " ".join(b.get("class", [])).lower() or b.name == "button")
    details["CTA/Tap Elements (count)"] = probable_ctas
    if probable_ctas >= 3:
        score += 3
        details["Tap Target Size Score"] = "3 / 5"
    else:
        details["Tap Target Size Score"] = "1 / 5"
        suggestions.append("Ensure tappable elements are ≥48px and well spaced on mobile.")

    # Tap spacing (4) – heuristic via presence of CSS classes like gap-*, p-*, or margin utility
    html_txt = str(soup)[:200_000]
    spacing_hint = bool(re.search(r"(gap\-|padding|margin|px;|rem;)", html_txt, flags=re.I))
    details["Tap Spacing Hint"] = "Detected" if spacing_hint else "Not detected"
    if spacing_hint:
        score += 3
        details["Tap Spacing Score"] = "3 / 4"
    else:
        details["Tap Spacing Score"] = "1 / 4"
        suggestions.append("Increase spacing between links/buttons (≥8px).")

    # Font size (5) – heuristic: look for base 16px in CSS or <body> styles
    body = soup.find("body")
    inline_style = (body.get("style") if body else "") or ""
    base16 = "font-size:16px" in inline_style.replace(" ", "").lower()
    css_16 = False
    for href in css_links[:3]:
        try:
            r = requests.get(urljoin(url, href), headers=HEADERS, timeout=10)
            if r.status_code == 200 and re.search(r"font-size\s*:\s*1?6px", r.text, flags=re.I):
                css_16 = True
                break
        except Exception:
            continue
    details["Font Base ≥16px"] = "Yes" if (base16 or css_16) else "Not confirmed"
    if base16 or css_16:
        score += 4
        details["Font Size Score"] = "4 / 5"
    else:
        details["Font Size Score"] = "2 / 5"
        suggestions.append("Ensure body text is 16–22px on mobile; ≥90% readable.")

    # Popups (6) – heuristic: detect common modal patterns
    has_popup = bool(soup.find(attrs={"role": "dialog"}) or soup.find(class_=re.compile(r"(modal|popup|overlay)", re.I)))
    details["Popup Detected"] = "Yes" if has_popup else "No"
    if not has_popup:
        score += 6
        details["Popup Score"] = "6 / 6"
    else:
        score += 3
        details["Popup Score"] = "3 / 6"
        suggestions.append("Delay interstitials ≥3s, keep ≤25% viewport, trigger on user action.")

    return score, available, details, suggestions

# ------------------------------
# MAIN AUDIT
# ------------------------------
def run_audit(url: str, primary_kw: str, lsi_csv: str, originality_pct_input: str, psi_key: str):
    html = fetch_html(url)
    if not html:
        return None, None

    soup = BeautifulSoup(html, "html.parser")
    global soup_global
    soup_global = soup  # used in content pillar placement

    text = visible_text(soup)
    json_ld = try_get_json_ld(soup)
    ctype = detect_content_type(url, soup, text, json_ld)

    # Convert inputs
    lsi_terms = [t.strip() for t in (lsi_csv or "").split(",") if t.strip()]
    originality_pct = None
    if originality_pct_input.strip():
        try:
            originality_pct = float(originality_pct_input.strip())
        except Exception:
            originality_pct = None

    # Pillars
    p1_s, p1_av, p1_d, p1_sug = score_content_pillar(ctype, text, primary_kw, lsi_terms, originality_pct)
    p2_s, p2_av, p2_d, p2_sug = score_html_pillar(soup, ctype)
    p3_s, p3_av, p3_d, p3_sug = score_url_links_pillar(url, soup, primary_kw)
    p4_s, p4_av, p4_d, p4_sug = score_performance_pillar(url, soup, psi_key)
    p5_s, p5_av, p5_d, p5_sug = score_mobile_pillar(url, soup)

    pillars = [
        ("Content Quality & Relevance", p1_s, p1_av, p1_d, p1_sug, 20),
        ("HTML Tag Optimization", p2_s, p2_av, p2_d, p2_sug, 10),
        ("URL & Link Structure", p3_s, p3_av, p3_d, p3_sug, 10),
        ("Page Performance", p4_s, p4_av, p4_d, p4_sug, 30),
        ("Mobile-Friendliness & UX", p5_s, p5_av, p5_d, p5_sug, 30),
    ]

    # Normalize each pillar to its max weight using available points (handles exclusions)
    total_weighted = 0.0
    total_possible = 0.0
    pillar_outputs = []
    for name, s, avail, det, sug, weight in pillars:
        if avail <= 0:
            norm = 0.0
        else:
            norm = (s / avail) * weight
        total_weighted += norm
        total_possible += weight
        pillar_outputs.append((name, s, avail, round(norm, 2), weight, det, sug))

    return ctype, pillar_outputs, total_weighted, total_possible

# ------------------------------
# STREAMLIT UI
# ------------------------------
st.set_page_config(page_title="On-Page SEO Audit (5-Pillar)", layout="wide")
st.title("On-Page SEO Audit (5-Pillar Framework)")

with st.sidebar:
    st.markdown("### Inputs")
    url = st.text_input("Page URL (include http/https)")
    primary_kw = st.text_input("Primary Keyword (for density/placement)", "")
    lsi_csv = st.text_area("LSI / Related Terms (comma-separated)", "")
    originality_pct_input = st.text_input("Originality % (optional, e.g., 97)")
    psi_key = st.text_input("PageSpeed Insights API Key (optional)", type="password")
    run = st.button("Run Audit")

if run:
    if not url or not url.startswith(("http://", "https://")):
        st.error("Please enter a valid URL including http:// or https://")
    else:
        with st.spinner("Auditing..."):
            result = run_audit(url, primary_kw, lsi_csv, originality_pct_input, psi_key)
        if not result:
            st.error("Failed to fetch/analyze the page.")
        else:
            content_type, pillars, total_weighted, total_possible = result
            st.success(f"Detected Content Type: **{content_type}**")
            st.markdown(f"### Overall Score: **{round(total_weighted, 2)} / {total_possible}**")

            cols = st.columns(2)
            for i, (name, raw_s, avail, norm, weight, det, sug) in enumerate(pillars):
                box = cols[i % 2]
                with box:
                    st.subheader(f"{name} — {round(norm,2)} / {weight}")
                    st.caption(f"Raw: {round(raw_s,2)} / {round(avail,2)}  |  Weight: {weight}")
                    st.json(det)
                    if sug:
                        st.markdown("**Recommendations:**")
                        for s in sug:
                            st.markdown(f"- {s}")

            st.markdown("---")
            st.caption("Notes: Performance without PSI uses heuristics; originality is optional and excluded from scoring if not provided.")
