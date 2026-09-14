import json
import logging
import os
import sys
import urllib.parse
import urllib.request

from dotenv import load_dotenv

# Ensure project root is in the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

logger = logging.getLogger("gemini_classifier")

load_dotenv()

def classify_lead_with_gemini(text):
    """
    Calls Google Gemini 2.5 Flash API to semantically classify a social media post/comment.
    Determines if it's an artist promotion and extracts the artist name.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key or "your_gemini" in gemini_key or "AIzaSy" not in gemini_key:
        logger.warning("⚠️ GEMINI_API_KEY is not configured. Falling back to default mock classification.")
        return {"is_artist_promotion": False, "artist_name": None, "reason": "No API key configured"}
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
    
    prompt = f"""
You are an expert music scout and talent A&R. Analyze the following social media post or comment.
Determine if the user is an emerging musical artist (singer, rapper, vocalist, songwriter) actively promoting their own music, song, track, or channel.

Comment/Post: "{text}"

Your analysis must filter out:
- Beatmakers, music producers, loopmakers, and engineers (e.g. "listen to my beats", "prod by me", "instrumental", "type beat").
- General listeners giving feedback (e.g. "nice song", "this is fire", "who is listening in 2026?").
- Spammers promoting products, playlists, or other accounts.

Return a JSON object with this exact structure:
{{
  "is_artist_promotion": true/false,
  "artist_name": "Name of the artist (or null if not found/applicable)",
  "reason": "Brief explanation of your decision"
}}
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = response.read().decode("utf-8")
            result = json.loads(res_data)
            
        # Extract text from response structure
        candidates = result.get("candidates", [])
        if not candidates:
            return {"is_artist_promotion": False, "artist_name": None, "reason": "No candidate returned by Gemini"}
            
        content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if not content_text:
            return {"is_artist_promotion": False, "artist_name": None, "reason": "Empty text part returned"}
            
        # Parse returned JSON
        classification = json.loads(content_text.strip())
        logger.info(f"🤖 Gemini classification: is_artist={classification.get('is_artist_promotion')} | artist_name={classification.get('artist_name')} | reason={classification.get('reason')}")
        return classification
        
    except Exception as e:
        logger.error(f"❌ Gemini classification failed: {e}")
        return {"is_artist_promotion": False, "artist_name": None, "reason": f"API call failed: {e}"}

if __name__ == "__main__":
    # Simple direct verification test
    logging.basicConfig(level=logging.INFO)
    print("Testing Gemini 2.5 Flash Classifier:")
    print("-" * 50)
    
    test_cases = [
        "Check my new track! I'm a rapper from NY, my artist name is Lil Kid",
        "Awesome mix, studing to this beat, keep it up!",
        "Hit me up if you need custom type beats, check my channel for beats",
    ]
    
    for text in test_cases:
        print(f"\nText: \"{text}\"")
        res = classify_lead_with_gemini(text)
        print(f"Result: {res}")
