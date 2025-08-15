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
        # First try normal request
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
        else:
            st.warning(f"First attempt failed: {response.status_code}")
    except Exception as e:
        st.warning(f"Error during normal fetch: {e}")

    # If blocked & ScraperAPI is available, use it
    if SCRAPER_API_KEY:
        try:
            api_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={url}"
            response = requests.get(api_url, timeout=15)
            if response.status_code == 200:
                return response.text
            else:
                st.error(f"ScraperAPI failed: {response.status_code}")
        except Exception as e:
            st.error(f"ScraperAPI error: {e}")

    return None


def seo_audit(url):
    html_content = fetch_html(url)
    if not html_content:
        return {"Error": "Failed to fetch page"}

    soup = BeautifulSoup(html_content, "html.parser")

    # Basic SEO checks
    title = soup.title.string.strip() if soup.title else "No title"
    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag:
        meta_desc = meta_tag.get("content", "").strip()

    h1_count = len(soup.find_all("h1"))

    return {
        "Title": title,
        "Title Length": len(title),
        "Meta Description": meta_desc,
        "Meta Description Length": len(meta_desc),
        "H1 Count": h1_count
    }


# Streamlit UI
st.title("🔍 On-Page SEO Audit Tool")
url = st.text_input("Enter a URL:")

if st.button("Run Audit"):
    if url:
        results = seo_audit(url)
        st.write(results)
    else:
        st.error("Please enter a valid URL.")
