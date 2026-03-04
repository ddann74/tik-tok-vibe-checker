import streamlit as st
import pandas as pd
from apify_client import ApifyClient
import google.generativeai as genai

# --- 1. App Configuration ---
st.set_page_config(page_title="VibeCheck 2026", page_icon="📈", layout="wide")

# --- 2. Secret Handling ---
# This part automatically pulls the keys from your Streamlit Cloud "Secrets"
try:
    APIFY_KEY = st.secrets["APIFY_KEY"]
    GEMINI_KEY = st.secrets["GEMINI_KEY"]
except Exception:
    st.error("🔑 API Keys not found! Please add them to 'Advanced Settings > Secrets' in the Streamlit Dashboard.")
    st.stop()

# --- 3. Main Interface ---
st.title("🎵 TikTok Vibe Checker")
st.subheader("Analyze sentiment and Data Stabilization.")

video_url = st.text_input("Enter TikTok Video URL:", placeholder="https://www.tiktok.com/@creator/video/123456789")

if st.button("🚀 Run Analysis"):
    if not video_url:
        st.error("Please provide a valid TikTok URL.")
    else:
        with st.status("Initializing 50-point test...") as status:
            try:
                # Step 1: Scrape Data
                status.update(label="Scraping comments via Apify...", state="running")
                client = ApifyClient(APIFY_KEY)
                
                # Using the TikTok Scraper
                run_input = {"postURLs": [video_url], "commentsPerPost": 50, "maxRepliesPerComment": 0}
                run = client.actor("clockworks/tiktok-comments-scraper").call(run_input=run_input)
                
                raw_data = list(client.dataset(run["defaultDatasetId"]).iterate_items())
                df = pd.DataFrame(raw_data)

                if df.empty:
                    st.error("No comments found. The video might be private or restricted.")
                else:
                    # Step 2: AI Vibe Analysis
                    status.update(label="Analyzing sentiment and vibe...", state="running")
                    genai.configure(api_key=GEMINI_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    comments_text = "\n".join([f"[{c.get('diggCount', 0)} likes]: {c.get('text', '')}" for c in raw_data[:30]])
                    
                    prompt = f"""
                    Analyze these TikTok comments:
                    {comments_text}
                    
                    Please provide:
                    1. **Overall Vibe Summary**: A witty 2-sentence summary.
                    2. **The 'Best' Comment**: Most insightful/funny.
                    3. **The 'Worst' Comment**: Most toxic/vibe-kill.
                    4. **Data Stabilization**: Rate consistency 0-100%.
                    """
                    
                    response = model.generate_content(prompt)
                    
                    # Step 3: Display Results
                    status.update(label="Analysis Complete!", state="complete")
                    st.markdown("### ✨ The Vibe Report")
                    st.markdown(response.text)
                    
                    st.metric("Comments Analyzed", len(df))

            except Exception as e:
                st.error(f"An error occurred: {str(e)}")

st.divider()
st.caption("Feature Status: Data Stabilization [ACTIVE]")
