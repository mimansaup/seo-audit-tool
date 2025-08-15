import streamlit as st
import requests
from urllib.parse import urlparse

# --------------------------
# SCORING FUNCTIONS
# --------------------------
def score_word_count(word_count):
    if word_count >= 1500:
        return 5
    elif 1000 <= word_count < 1500:
        return 3
    elif 500 <= word_count < 1000:
        return 2
    else:
        return 0

def score_keyword_density(density):
    if 1.0 <= density <= 2.5:
        return 5
    elif 0.5 <= density < 1.0 or 2.5 < density <= 3.0:
        return 3
    else:
        return 0

# Example scoring for one pillar — repeat for all
def pillar1_content(url):
    # Placeholder: In the real version, you'd scrape the page & calculate
    # Here we'll use mock data for demonstration
    word_count = 1200  # mock value
    keyword_density = 1.8  # mock value
    score = score_word_count(word_count) + score_keyword_density(keyword_density)
    return score, {
        "Word Count": f"{word_count} words",
        "Keyword Density": f"{keyword_density}%",
        "Score": score
    }

def pillar2_html():
    # Mock data
    score = 8  # out of 10
    return score, {
        "Title Tag": "Present",
        "Meta Description": "Present",
        "Score": score
    }

def pillar3_url_links():
    score = 9
    return score, {
        "URL Length": "45 chars",
        "Internal Links": 10,
        "Score": score
    }

def pillar4_performance():
    score = 26
    return score, {
        "LCP": "2.4s",
        "FID": "80ms",
        "CLS": "0.08",
        "Score": score
    }

def pillar5_mobile_ux():
    score = 27
    return score, {
        "Responsive": "Yes",
        "Font Size": "16px",
        "Score": score
    }

# --------------------------
# STREAMLIT UI
# --------------------------
st.set_page_config(page_title="On-Page SEO Audit Tool", layout="wide")
st.title("🔍 On-Page SEO Audit Tool")

url = st.text_input("Enter a URL to audit:")

if st.button("Run Audit"):
    if not url.startswith("http"):
        st.error("Please enter a valid URL including http:// or https://")
    else:
        st.subheader("Audit Results")

        # Pillar 1
        p1_score, p1_details = pillar1_content(url)
        st.markdown(f"**Pillar 1: Content Quality — {p1_score}/25**")
        st.json(p1_details)

        # Pillar 2
        p2_score, p2_details = pillar2_html()
        st.markdown(f"**Pillar 2: HTML Tags — {p2_score}/15**")
        st.json(p2_details)

        # Pillar 3
        p3_score, p3_details = pillar3_url_links()
        st.markdown(f"**Pillar 3: URL & Link Structure — {p3_score}/10**")
        st.json(p3_details)

        # Pillar 4
        p4_score, p4_details = pillar4_performance()
        st.markdown(f"**Pillar 4: Page Performance — {p4_score}/30**")
        st.json(p4_details)

        # Pillar 5
        p5_score, p5_details = pillar5_mobile_ux()
        st.markdown(f"**Pillar 5: Mobile Friendliness & UX — {p5_score}/30**")
        st.json(p5_details)

        total_score = p1_score + p2_score + p3_score + p4_score + p5_score
        st.markdown(f"### ✅ Total SEO Score: {total_score}/110")
