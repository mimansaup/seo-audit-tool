import streamlit as st
import requests
from bs4 import BeautifulSoup

# Optional: use ScraperAPI if site blocks requests
SCRAPER_API_KEY = ""  # Add your key if you have one

def fetch_html(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
        else:
            st.warning(f"First attempt failed: {response.status_code}")
    except Exception as e:
        st.warning(f"Error during normal fetch: {e}")

    # fallback
    if SCRAPER_API_KEY:
        try:
            api_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={url}"
            response = requests.get(api_url, timeout=15)
            if response.status_code == 200:
                return response.text
        except Exception as e:
            st.error(f"ScraperAPI error: {e}")
    return None


def seo_audit(url):
    html_content = fetch_html(url)
    if not html_content:
        return {"Error": "Failed to fetch page"}

    soup = BeautifulSoup(html_content, "html.parser")

    # --- Extract Data ---
    title = soup.title.string.strip() if soup.title else ""
    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag:
        meta_desc = meta_tag.get("content", "").strip()
    h1_count = len(soup.find_all("h1"))

    # --- Scoring Benchmarks (example from your framework) ---
    score = 0
    details = {}

    # Title length
    if 10 <= len(title) <= 60:
        score += 1
        details["Title Length"] = f"✅ {len(title)} (Good)"
    else:
        details["Title Length"] = f"⚠️ {len(title)} (Outside ideal range 10-60)"

    # Meta description
    if 150 <= len(meta_desc) <= 160:
        score += 1
        details["Meta Description"] = f"✅ {len(meta_desc)} (Good)"
    elif 100 <= len(meta_desc) <= 180:
        score += 0.5
        details["Meta Description"] = f"⚠️ {len(meta_desc)} (Acceptable but not ideal)"
    else:
        details["Meta Description"] = f"❌ {len(meta_desc)} (Missing or poor length)"

    # H1 count
    if h1_count == 1:
        score += 2
        details["H1 Count"] = f"✅ {h1_count} (Perfect)"
    elif h1_count > 1:
        score += 1
        details["H1 Count"] = f"⚠️ {h1_count} (Too many)"
    else:
        details["H1 Count"] = "❌ 0 (Missing)"

    # Final score summary
    details["Total Score (out of 4)"] = score

    return details


# --- Streamlit UI ---
st.title("🔍 On-Page SEO Audit Tool (Scored Report)")
url = st.text_input("Enter a URL:")

if st.button("Run Audit"):
    if url:
        results = seo_audit(url)
        for key, value in results.items():
            st.write(f"**{key}:** {value}")
    else:
        st.error("Please enter a valid URL.")
