import streamlit as st
import pandas as pd
from apify_client import ApifyClient
import google.generativeai as genai

# --- 1. App Configuration & UI Layout ---
st.set_page_config(page_title="VibeCheck 2026", page_icon="📈", layout="wide")

def local_css(file_name):
    st.markdown(f'<style>{file_name}</style>', unsafe_allow_html=True)

# Sidebar for credentials
with st.sidebar:
    st.header("🔑 Authentication")
    apify_key = st.text_input("Apify API Token", type="password", help="Get this from apify.com")
    gemini_key = st.text_input("Gemini API Key", type="password", help="Get this from Google AI Studio")
    st.divider()
    st.info("Current Mode: 50-Point Vibe Test Enabled")

# --- 2. Main Interface ---
st.title("🎵 TikTok Vibe Checker")
st.subheader("Analyze sentiment, find top comments, and check Data Stabilization.")

video_url = st.text_input("Enter TikTok Video URL:", placeholder="https://www.tiktok.com/@creator/video/123456789")

if st.button("🚀 Run Analysis"):
    if not apify_key or not gemini_key:
        st.warning("Please enter your API keys in the sidebar to proceed.")
    elif not video_url:
        st.error("Please provide a valid TikTok URL.")
    else:
        with st.status("Initializing 50-point test...") as status:
            try:
                # Step 1: Scrape Data
                status.update(label="Scraping comments via Apify...", state="running")
                client = ApifyClient(apify_key)
                # Using the TikTok Scraper (clockworks/tiktok-comments-scraper)
                run_input = {"postURLs": [video_url], "commentsPerPost": 100, "maxRepliesPerComment": 0}
                run = client.actor("clockworks/tiktok-comments-scraper").call(run_input=run_input)
                
                raw_data = list(client.dataset(run["defaultDatasetId"]).iterate_items())
                df = pd.DataFrame(raw_data)

                if df.empty:
                    st.error("No comments found. The video might be restricted.")
                else:
                    # Step 2: AI Vibe Analysis
                    status.update(label="Analyzing sentiment and vibe...", state="running")
                    genai.configure(api_key=gemini_key)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    # Prepare comment text for the LLM
                    comments_text = "\n".join([f"[{c.get('diggCount', 0)} likes]: {c.get('text', '')}" for c in raw_data[:50]])
                    
                    prompt = f"""
                    You are a 'TikTok Vibe Checker'. Based on these comments:
                    {comments_text}
                    
                    Please provide the following:
                    1. **Overall Vibe Summary**: A witty 2-sentence summary of the comment section energy.
                    2. **The 'Best' Comment**: The most insightful or hilarious one.
                    3. **The 'Worst' Comment**: The most toxic or 'vibe-killing' one.
                    4. **Top 3 Recurring Themes**: What are people actually talking about?
                    5. **Data Stabilization**: Rate how consistent the vibe is from 0% to 100% (e.g., if everyone agrees, it's 95%. If it's a war zone, it's 10%).
                    """
                    
                    response = model.generate_content(prompt)
                    
                    # Step 3: Display results
                    status.update(label="Analysis Complete!", state="complete")
                    
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.markdown("### ✨ Vibe Report")
                        st.markdown(response.text)
                    
                    with col2:
                        st.markdown("### 📊 Metrics")
                        st.metric("Total Comments Analyzed", len(df))
                        # Simple logic for average likes as a secondary metric
                        avg_likes = df['diggCount'].mean() if 'diggCount' in df else 0
                        st.metric("Avg Likes per Comment", round(avg_likes, 1))

                    with st.expander("📂 View Raw Comment Data"):
                        st.dataframe(df[['uniqueId', 'text', 'diggCount']])

            except Exception as e:
                st.error(f"An error occurred: {str(e)}")

# --- 3. Roadmap & Future Features ---
st.divider()
st.write("### 🛠️ Potential Features in the Future")
st.checkbox("Comment sentiment heatmaps")
st.checkbox("Emoji density analysis")
st.checkbox("Data Stabilization indicator", value=True, disabled=True) # Successfully implemented
