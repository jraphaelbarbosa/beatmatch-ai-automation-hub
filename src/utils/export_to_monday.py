import os
import sys
import json
import urllib.request
import urllib.error
import logging
from dotenv import load_dotenv

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.utils.db import get_connection
from src.reconciler import transition_status

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s] - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("export_to_monday")

load_dotenv()

MONDAY_API_TOKEN = os.getenv("MONDAY_API_TOKEN")
MONDAY_BOARD_ID = os.getenv("MONDAY_BOARD_ID")
MONDAY_URL = "https://api.monday.com/v2"

# Mock Mode configuration
is_config_missing = not MONDAY_API_TOKEN or not MONDAY_BOARD_ID or "your_monday_" in MONDAY_API_TOKEN

def call_monday_api(query, variables=None):
    headers = {
        "Authorization": MONDAY_API_TOKEN,
        "Content-Type": "application/json",
        "API-Version": "2023-10"
    }
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
        
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(MONDAY_URL, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            res_data = response.read().decode("utf-8")
            return json.loads(res_data)
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        raise RuntimeError(f"HTTP Error {e.code}: {error_msg}")
    except Exception as e:
        raise RuntimeError(f"Connection failure: {e}")

def get_board_columns():
    """
    Queries Monday.com to map column titles to their unique column IDs.
    """
    query = """
    query ($board_ids: [ID!]) {
      boards (ids: $board_ids) {
        columns {
          id
          title
        }
      }
    }
    """
    try:
      result = call_monday_api(query, {"board_ids": [str(MONDAY_BOARD_ID)]})
      if "errors" in result:
          logger.error(f"Error fetching columns: {result['errors']}")
          return {}
      boards = result.get("data", {}).get("boards", [])
      if not boards:
          return {}
      
      # Return dict mapping title.lower() -> id
      return {col["title"].lower(): col["id"] for col in boards[0]["columns"]}
    except Exception as e:
      logger.error(f"Failed to query columns from Monday.com: {e}")
      return {}

def run_export():
    logger.info("🎬 Starting Monday.com Export Process...")
    
    if is_config_missing:
        logger.warning("⚠️ Monday.com credentials are not configured or are placeholders. Running in MOCK MODE.")
        return mock_export()

    # 1. Resolve Monday.com columns
    logger.info("📂 Resolving Monday.com column mapping IDs...")
    column_mapping = get_board_columns()
    if not column_mapping:
        logger.error("❌ Failed to resolve column mappings from Monday.com. Aborting.")
        return False
        
    logger.info(f"✓ Mapped {len(column_mapping)} columns from board ID {MONDAY_BOARD_ID}.")

    # 2. Fetch 'ready_for_sipa' artists from Supabase
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        query = """
            SELECT spotify_id, name, genres, followers, popularity, spotify_url, instagram_url, twitter_url, youtube_channel, scouting_source, monthly_listeners, max_song_views
            FROM public.artists
            WHERE status = 'ready_for_sipa'
            ORDER BY popularity DESC
            LIMIT 50;
        """
        cursor.execute(query)
        records = cursor.fetchall()
        
        if not records:
            logger.info("✅ No artists ready to be exported (status = 'ready_for_sipa').")
            return True
            
        logger.info(f"📋 Found {len(records)} artists ready for export.")
        
        success_count = 0
        for r in records:
            spotify_id, name, genres, followers, popularity, spotify_url, instagram_url, twitter_url, youtube_channel, scouting_source, monthly_listeners, max_song_views = r
            
            # Map column values using resolved Monday column IDs
            # Monday.com API v2 column value formats depend on the column type:
            # - text/numbers: passed directly
            # - link: object {"url": "...", "text": "..."}
            # - status: label string or index
            
            column_values = {}
            
            # Match columns by title
            mappings = {
                "spotify id": spotify_id,
                "popularity": popularity,
                "followers": followers,
                "monthly listeners": monthly_listeners,
                "max song views": max_song_views,
                "scouting source": scouting_source,
                "top track 1": spotify_url,  # Fallback: put spotify_url here if tracks are empty
            }
            
            if instagram_url:
                mappings["instagram"] = {"url": instagram_url, "text": "Instagram Profile"}
            if twitter_url:
                mappings["twitter"] = {"url": twitter_url, "text": "Twitter Profile"}
                
            for title, value in mappings.items():
                col_id = column_mapping.get(title)
                if col_id:
                    column_values[col_id] = value
                    
            logger.info(f"Exporting artist '{name}'...")
            
            # Create item mutation
            create_query = """
            mutation ($boardId: ID!, $itemName: String!, $columnValues: JSON!) {
              create_item (board_id: $boardId, item_name: $itemName, column_values: $columnValues, create_labels_if_missing: true) {
                id
              }
            }
            """
            
            variables = {
                "boardId": str(MONDAY_BOARD_ID),
                "itemName": name,
                "columnValues": json.dumps(column_values)
            }
            
            result = call_monday_api(create_query, variables)
            if "errors" in result:
                logger.error(f"❌ Monday.com API error creating item for '{name}': {result['errors']}")
                continue
                
            item_id = result.get("data", {}).get("create_item", {}).get("id")
            if not item_id:
                logger.error(f"❌ Failed to obtain item ID for artist '{name}'.")
                continue
                
            # Create rich HTML update block
            genres_str = ", ".join(genres) if genres else "Unknown"
            update_body = f"""
            <h3>🎵 Discovered Artist: {name}</h3>
            <p><strong>Primary Niche:</strong> {genres_str}</p>
            <p><strong>Scouting Channel:</strong> {scouting_source.upper()}</p>
            <hr/>
            <h4>📊 Performance Metrics</h4>
            <ul>
                <li><strong>Spotify Popularity:</strong> {popularity}/100</li>
                <li><strong>Spotify Followers:</strong> {followers:,}</li>
                <li><strong>Spotify Monthly Listeners:</strong> {f"{monthly_listeners:,}" if monthly_listeners else "N/A"}</li>
                <li><strong>Max Song Views/Streams:</strong> {f"{max_song_views:,}" if max_song_views else "N/A"}</li>
            </ul>
            <hr/>
            <h4>🔗 Verified Social Handles</h4>
            <ul>
                <li><strong>Instagram:</strong> <a href="{instagram_url or '#'}">{instagram_url or 'N/A'}</a></li>
                <li><strong>Twitter:</strong> <a href="{twitter_url or '#'}">{twitter_url or 'N/A'}</a></li>
                <li><strong>Spotify:</strong> <a href="{spotify_url or '#'}">{spotify_url or 'N/A'}</a></li>
                <li><strong>YouTube:</strong> <a href="{youtube_channel or '#'}">{youtube_channel or 'N/A'}</a></li>
            </ul>
            """
            
            update_query = """
            mutation ($itemId: ID!, $body: String!) {
              create_update (item_id: $itemId, body: $body) {
                id
              }
            }
            """
            
            update_result = call_monday_api(update_query, {"itemId": str(item_id), "body": update_body})
            if "errors" in update_result:
                logger.warning(f"⚠️ Monday.com failed to add update bubble for '{name}': {update_result['errors']}")
                
            # Transition status in Supabase to 'processed'
            transition_status(spotify_id, "processed")
            success_count += 1
            
        logger.info(f"🏁 Finished Export Process. {success_count}/{len(records)} artists successfully exported to Monday.com.")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database/Export failure: {e}")
        return False
    finally:
        conn.close()

def mock_export():
    logger.info("ℹ️ Running in Mock Mode. Simulating Monday.com export...")
    logger.info("✓ Resolving mock column mapping IDs...")
    logger.info("✓ Mocked item creation for 'Lil Shifty' (ID: mock_101).")
    logger.info("✓ Mocked update bubble created with rich HTML artist details.")
    logger.info("🏁 Mock Export Process Completed successfully.")
    return True

if __name__ == "__main__":
    run_export()
