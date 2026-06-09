import os
import sys
import re
import logging
from dotenv import load_dotenv

# Reconfigure stdout to accept UTF-8 to prevent 'charmap' errors on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure project root is in the path for absolute imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.reconciler import insert_discovered_lead
from src.utils.gemini_classifier import classify_lead_with_gemini

# Broad pre-filter regex to optimize Gemini API calls
BROAD_PROMO_REGEX = re.compile(
    r"(my|meu|minha|escuta|check|ouça|song|music|track|beat|canal|sing|rap|artist|sound|look at|da uma olhada|escutar|ouvir|vocal|letra)",
    re.IGNORECASE
)

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s] - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("apify_yt")

# Load Environment Variables
load_dotenv()

APIFY_TOKEN = os.getenv("APIFY_TOKEN")
is_token_missing = not APIFY_TOKEN or "your_apify_token" in APIFY_TOKEN

# Regex patterns for self-promotion
SELF_PROMO_REGEX = re.compile(
    r"(my music|check my track|escuta meu som|my beat|meu som|meu beat|"
    r"check my channel|ouça minha|escuta minha|my song|my sound|listen to my|"
    r"check out my|check my playlist|da uma olhada no meu)",
    re.IGNORECASE
)

# Default fallback YouTube videos (e.g. popular Lofi / Instrumental Beats videos)
DEFAULT_VIDEO_URLS = [
    "https://www.youtube.com/watch?v=jfKfPfyJRdk",  # Lofi Girl
    "https://www.youtube.com/watch?v=5qap5aO4i9A"   # Lofi Hip Hop Radio
]

def discover_target_videos(queries=None, min_views=30000):
    """
    Queries YouTube API to search for type-beat videos (e.g. Drake, Kendrick, Griselda).
    Filters for videos published in the last year (365 days) with at least min_views.
    """
    yt_key = os.getenv("YOUTUBE_API_KEY")
    if not yt_key or "your_youtube_api" in yt_key or "AIzaSy" not in yt_key:
        logger.warning("⚠️ YOUTUBE_API_KEY is not configured or is a placeholder. Using default static video URLs.")
        return DEFAULT_VIDEO_URLS
        
    search_queries = queries or [
        "kendrick lamar type beat",
        "griselda westside gunn type beat",
        "underground hip hop type beat",
        "underground boombap type beat",
        "chill drill type beat",
        "drake type beat"
    ]
    
    from datetime import datetime, timedelta
    import urllib.request
    import urllib.parse
    import json
    
    # Target date: 1 year ago in RFC 3339 format (ISO 8601)
    published_after = (datetime.utcnow() - timedelta(days=365)).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    video_urls = []
    seen_video_ids = set()
    
    for q in search_queries:
        logger.info(f"🔍 Searching YouTube for: '{q}' (published after {published_after})...")
        try:
            encoded_query = urllib.parse.quote(q)
            search_url = (
                f"https://www.googleapis.com/youtube/v3/search"
                f"?part=snippet&q={encoded_query}&type=video"
                f"&publishedAfter={published_after}&key={yt_key}&maxResults=20"
            )
            
            req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                
            video_ids = []
            for item in data.get("items", []):
                vid_id = item.get("id", {}).get("videoId")
                if vid_id and vid_id not in seen_video_ids:
                    video_ids.append(vid_id)
                    seen_video_ids.add(vid_id)
                    
            if not video_ids:
                continue
                
            # Fetch view counts for these videos
            ids_str = ",".join(video_ids)
            stats_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={ids_str}&key={yt_key}"
            
            req_stats = urllib.request.Request(stats_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_stats) as resp_stats:
                stats_data = json.loads(resp_stats.read().decode("utf-8"))
                
            for item in stats_data.get("items", []):
                vid_id = item.get("id")
                view_count = item.get("statistics", {}).get("viewCount")
                if view_count:
                    views = int(view_count)
                    if views >= min_views:
                        video_url = f"https://www.youtube.com/watch?v={vid_id}"
                        video_urls.append(video_url)
                        logger.info(f"🎥 Discovered type-beat video: {video_url} | Views: {views:,}")
                        
        except Exception as e:
            logger.warning(f"⚠️ YouTube search failed for query '{q}': {e}")
            continue
            
    if not video_urls:
        logger.warning("⚠️ No dynamically discovered videos met the criteria. Falling back to default video URLs.")
        return DEFAULT_VIDEO_URLS
        
    return list(set(video_urls))

def scrape_youtube_comments(video_urls=None, max_comments=100):
    """
    Queries YouTube Data API v3 to fetch comment threads for the target videos.
    If YOUTUBE_API_KEY is missing, falls back to Mock Mode.
    """
    yt_key = os.getenv("YOUTUBE_API_KEY")
    if not yt_key or "your_youtube_api" in yt_key or "AIzaSy" not in yt_key:
        logger.warning("⚠️ YOUTUBE_API_KEY is not configured or is invalid. Running in MOCK MODE.")
        return get_mock_comments()

    urls = video_urls or DEFAULT_VIDEO_URLS
    comments_found = []
    
    import urllib.request
    import urllib.parse
    import json
    
    for url in urls:
        video_id_match = re.search(r"v=([a-zA-Z0-9_-]+)", url)
        if not video_id_match:
            continue
        video_id = video_id_match.group(1)
        
        logger.info(f"📥 Fetching YouTube comments via API for video ID: {video_id}...")
        try:
            api_url = (
                f"https://www.googleapis.com/youtube/v3/commentThreads"
                f"?part=snippet&videoId={video_id}&maxResults={max_comments}&key={yt_key}"
            )
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                
            for item in data.get("items", []):
                snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                author = snippet.get("authorDisplayName")
                channel_url = snippet.get("authorChannelUrl")
                text = snippet.get("textOriginal") or snippet.get("textDisplay")
                published_at = snippet.get("publishedAt")
                
                if author and text:
                    comments_found.append({
                        "author": author,
                        "authorChannelUrl": channel_url,
                        "comment": text,
                        "publishedAt": published_at
                    })
        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch comments via API for video {video_id}: {e}")
            continue
            
    logger.info(f"✅ Retrieved {len(comments_found)} comments via YouTube Data API.")
    if not comments_found:
        logger.warning("⚠️ No comments retrieved. Falling back to MOCK MODE.")
        return get_mock_comments()
        
    return comments_found

def get_mock_comments():
    """
    Returns simulated comments for local testing and validation.
    """
    logger.info("ℹ️ Generating mock YouTube comments...")
    return [
        {
            "authorDisplayName": "Lil Shifty",
            "authorChannelUrl": "https://www.youtube.com/channel/UC_lilshifty_mock",
            "text": "Yo guys, I am an independent artist trying to make it. Check my track out! Let me know what you think.",
            "publishedAt": "2026-06-07T02:00:00Z"
        },
        {
            "authorDisplayName": "BeatMaker99",
            "authorChannelUrl": "https://www.youtube.com/channel/UC_beatmaker99_mock",
            "text": "Nice mix! Escuta meu som também no meu canal, acabei de soltar um beat de trap novo.",
            "publishedAt": "2026-06-07T02:05:00Z"
        },
        {
            "authorDisplayName": "LofiChillOut",
            "authorChannelUrl": "https://www.youtube.com/channel/UC_lofi_chill_mock",
            "text": "This lofi radio is amazing to study to. Keep up the good work!",
            "publishedAt": "2026-06-07T02:10:00Z"
        },
        {
            "authorDisplayName": "MC Da Leste",
            "authorChannelUrl": "https://www.youtube.com/channel/UC_mcdaleste_mock",
            "text": "Muito bom mano! Quem puder dar uma olhada no meu som agradeço de verdade.",
            "publishedAt": "2026-06-07T02:15:00Z"
        }
    ]

def filter_and_insert_comments(comments):
    """
    Filters comments using Gemini 2.5 Flash Talent Classification and pushes leads to Supabase.
    """
    promo_count = 0
    inserted_count = 0
    
    for item in comments:
        text = item.get("comment") or item.get("text", "")
        author_name = item.get("author") or item.get("authorDisplayName", "Unknown Author")
        
        # Build author channel url
        author_url = item.get("authorChannelUrl", "")
        if not author_url and author_name != "Unknown Author":
            if author_name.startswith("@"):
                author_url = f"https://www.youtube.com/{author_name}"
            else:
                author_url = f"https://www.youtube.com/@{author_name}"
        
        # Broad pre-filter to optimize Gemini API quota
        if not BROAD_PROMO_REGEX.search(text) and not ("http" in text or "spotify" in text or "soundcloud" in text):
            continue
            
        # Semantic evaluation via Gemini 2.5 Flash
        ai_res = classify_lead_with_gemini(text)
        
        if ai_res.get("is_artist_promotion"):
            promo_count += 1
            extracted_name = ai_res.get("artist_name") or author_name
            logger.info(f"🎯 AI detected Artist Promotion from '{extracted_name}' (Original: '{author_name}'): \"{text[:60]}...\"")
            
            # Insert lead into the reconciliation queue
            result = insert_discovered_lead(
                name=extracted_name,
                youtube_channel=author_url,
                source="youtube_comment"
            )
            if result:
                inserted_count += 1
                
    logger.info(f"📊 Filtering Summary: Checked {len(comments)} comments. Found {promo_count} self-promos. Successfully inserted {inserted_count} leads.")
    return inserted_count

def main():
    logger.info("🎬 Starting YouTube Scraper Job...")
    # 1. Dynamically discover type beat videos meeting criteria
    video_urls = discover_target_videos()
    logger.info(f"📂 Found {len(video_urls)} dynamically discovered type-beat videos to scrape.")
    
    # 2. Run comments scraper on discovered videos (limit to top 5 to optimize time)
    comments = scrape_youtube_comments(video_urls=video_urls[:5], max_comments=50)
    
    # 3. Filter comments and push leads
    filter_and_insert_comments(comments)
    logger.info("🏁 YouTube Scraper Job Completed.")

if __name__ == "__main__":
    main()
