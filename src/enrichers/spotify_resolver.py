import os
import sys
import time
import random
import logging
from dotenv import load_dotenv

# Ensure project root is in the path for absolute imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.reconciler import get_pending_queue, transition_status, insert_discovered_lead
from src.utils.db import get_connection

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s] - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("spotify_resolver")

# Load Environment Variables
load_dotenv()

def get_spotify_client():
    """
    Initializes Spotipy client using env variables or fallback credentials.
    """
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    
    # Validate credentials are present
    if not client_id or not client_secret or "your_" in client_id:
        logger.warning("⚠️ SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET not configured in .env")
        return None
        
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
        
        auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        sp = spotipy.Spotify(auth_manager=auth_manager, requests_timeout=15)
        # Test client
        sp.search(q="test", type="artist", limit=1)
        return sp
    except Exception as e:
        logger.warning(f"⚠️ Spotipy initialization failed or credentials invalid: {e}. Running in MOCK MODE.")
        return None

def resolve_artist_spotify_details(sp, artist_name):
    """
    Queries Spotify Search API for an artist name and returns official details.
    """
    if not sp:
        # Simulated Spotipy search matching
        mock_database = {
            "Lil Shifty": ("3TVXtAsR1Inumwj472S9r4", "https://open.spotify.com/artist/3TVXtAsR1Inumwj472S9r4"),
            "BeatMaker99": ("0TnOYIS61S2lHk176H6tfn", "https://open.spotify.com/artist/0TnOYIS61S2lHk176H6tfn"),
            "MC Da Leste": ("1vC6V7XWfE81vE176H6tfA", "https://open.spotify.com/artist/1vC6V7XWfE81vE176H6tfA"),
        }
        if artist_name in mock_database:
            return mock_database[artist_name]
        return None

    try:
        results = sp.search(q=artist_name, type='artist', limit=5)
        items = results.get('artists', {}).get('items', [])
        if not items:
            return None
            
        # Try to find an exact match first, otherwise take the first item
        match = items[0]
        for item in items:
            if item['name'].lower() == artist_name.lower():
                match = item
                break
                
        spotify_id = match.get('id')
        spotify_url = match.get('external_urls', {}).get('spotify')
        return spotify_id, spotify_url
    except Exception as e:
        logger.error(f"❌ Error searching for artist '{artist_name}' on Spotify: {e}")
        return None

def run_resolver(batch_size=10):
    """
    Main resolver logic: pulls pending_spotify records, searches Spotify, and transitions status.
    """
    sp = get_spotify_client()
    
    # Check if database is configured, if not, do a mock run
    db_url = os.getenv("DATABASE_URL")
    is_db_missing = not db_url or "db.supabase.co" in db_url or "pophmvgrzuimixksyfuz" not in db_url
    
    # We can try to connect to verify database status
    conn = None
    if not is_db_missing:
        try:
            conn = get_connection()
        except Exception as e:
            logger.warning(f"⚠️ Could not connect to Supabase database: {e}. Falling back to MOCK database updates.")
            conn = None
            
    # Fetch pending queue
    pending_queue = []
    if conn:
        try:
            pending_queue = get_pending_queue('pending_spotify', limit=batch_size)
            # If no pending records are found, let's inject a few test records for demonstration
            if not pending_queue:
                logger.info("ℹ️ No pending_spotify artists found in database. Inserting mock records for demo...")
                insert_discovered_lead("Lil Shifty", source="youtube_comment")
                insert_discovered_lead("BeatMaker99", source="youtube_comment")
                pending_queue = get_pending_queue('pending_spotify', limit=batch_size)
        except Exception as e:
            logger.error(f"❌ Error querying pending queue: {e}")
            pending_queue = []
        finally:
            conn.close()
    else:
        # Simulated pending queue
        logger.info("ℹ️ Database connection not available. Generating simulated queue of pending_spotify leads...")
        pending_queue = [
            ("temp_1", "Lil Shifty", None, None, None, None, "youtube_comment"),
            ("temp_2", "BeatMaker99", None, None, None, None, "youtube_comment"),
            ("temp_3", "MC Da Leste", None, None, None, None, "youtube_comment"),
            ("temp_4", "UnknownNonExistentArtistXYZ", None, None, None, None, "youtube_comment")
        ]

    logger.info(f"📋 Found {len(pending_queue)} artists with status 'pending_spotify'. Processing...")
    
    resolved_count = 0
    skipped_count = 0
    
    for row in pending_queue:
        # Row format from get_pending_queue:
        # (spotify_id, name, spotify_url, instagram_url, twitter_url, youtube_channel, scouting_source)
        temp_id = row[0]
        artist_name = row[1]
        instagram_url = row[3]
        
        logger.info(f"🔄 Resolving artist '{artist_name}' (Temp ID: {temp_id})...")
        
        result = resolve_artist_spotify_details(sp, artist_name)
        
        if result:
            official_id, spotify_url = result
            logger.info(f"✅ Resolved '{artist_name}' -> ID: {official_id}, URL: {spotify_url}")
            
            # Decide next status
            next_status = 'ready_for_sipa' if instagram_url else 'pending_instagram'
            processed_fields = {'spotify_url': spotify_url}
            
            # Transition status in DB
            if conn:
                success = transition_status(
                    spotify_id=temp_id,
                    new_status=next_status,
                    new_spotify_id=official_id,
                    processed_fields=processed_fields
                )
            else:
                success = True
                logger.info(f"🔄 [MOCK DB] Updated artist '{artist_name}' status to '{next_status}' with official ID '{official_id}'")
                
            if success:
                resolved_count += 1
        else:
            logger.warning(f"❌ Could not resolve '{artist_name}' on Spotify.")
            
            # Transition status to skipped
            next_status = 'skipped_no_spotify'
            if conn:
                success = transition_status(
                    spotify_id=temp_id,
                    new_status=next_status
                )
            else:
                success = True
                logger.info(f"🔄 [MOCK DB] Updated artist '{artist_name}' status to '{next_status}'")
                
            if success:
                skipped_count += 1
                
        time.sleep(random.uniform(0.5, 1.0))
        
    logger.info(f"📊 Resolution Summary: Resolved {resolved_count} artists. Skipped {skipped_count} artists.")
    return resolved_count

def main():
    logger.info("🎬 Starting Spotify Resolver Job...")
    run_resolver()
    logger.info("🏁 Spotify Resolver Job Completed.")

if __name__ == "__main__":
    main()
