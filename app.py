import streamlit as st
import requests
from bs4 import BeautifulSoup

# Title
st.title("🔍 On-Page SEO Audit Tool")

# URL Input
url = st.text_input("Enter the page URL:")

if st.button("Run Audit") and url:
    try:
        # Fetch HTML
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            st.error(f"Failed to fetch page: {response.status_code}")
        else:
            soup = BeautifulSoup(response.text, 'html.parser')

            # Title Tag
            title_tag = soup.title.string if soup.title else "No Title Found"
            title_length = len(title_tag) if title_tag else 0

            # Meta Description
            meta_desc_tag = soup.find("meta", attrs={"name": "description"})
            meta_desc = meta_desc_tag["content"] if meta_desc_tag else "No Meta Description"
            meta_length = len(meta_desc) if meta_desc else 0

            # H1 Count
            h1_tags = soup.find_all("h1")
            h1_count = len(h1_tags)

            # Display Results
            st.subheader("SEO Audit Results")
            st.write(f"**Title:** {title_tag} ({title_length} characters)")
            st.write(f"**Meta Description:** {meta_desc} ({meta_length} characters)")
            st.write(f"**H1 Count:** {h1_count}")

    except Exception as e:
        st.error(f"Error: {e}")

