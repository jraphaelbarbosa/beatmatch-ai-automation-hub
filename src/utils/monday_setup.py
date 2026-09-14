"""
Monday.com board initialization script for the BeatMatchAI Automation Hub.
Connects to the Monday.com GraphQL API, validates the target board ID, and
creates columns (Spotify ID, Popularity, Followers, Instagram, Twitter,
Top Tracks, Scouting Source, and Status) if they do not exist.
"""

import json
import os
import sys
import urllib.error
import urllib.request

from dotenv import load_dotenv

# Reconfigure stdout to accept UTF-8 to prevent 'charmap' errors on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def call_monday_api(token, query, variables=None):
    """
    Executes a POST request to Monday.com's API v2 using standard libraries.
    """
    url = "https://api.monday.com/v2"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "API-Version": "2023-10"
    }
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
        
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            res_data = response.read().decode("utf-8")
            return json.loads(res_data)
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        raise RuntimeError(f"HTTP Error {e.code}: {error_msg}")
    except Exception as e:
        raise RuntimeError(f"Connection failure: {e}")

def update_env_files(new_board_id):
    """
    Automatically updates the MONDAY_BOARD_ID in both .env and .env.production files.
    """
    env_files = [".env", ".env.production"]
    for env_file in env_files:
        if os.path.exists(env_file):
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Replace the board ID line
                lines = content.splitlines()
                updated = False
                for i, line in enumerate(lines):
                    if line.startswith("MONDAY_BOARD_ID="):
                        lines[i] = f"MONDAY_BOARD_ID={new_board_id}"
                        updated = True
                        break
                
                if not updated:
                    lines.append(f"MONDAY_BOARD_ID={new_board_id}")
                
                with open(env_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                print(f"📝 Updated MONDAY_BOARD_ID to {new_board_id} in local {env_file}")
            except Exception as e:
                print(f"⚠️ Error updating {env_file}: {e}")

def create_new_board(token, name="BeatMatch AI - qualified leads"):
    """
    Creates a new public board on Monday.com and returns its ID.
    """
    query = """
    mutation ($board_name: String!, $board_kind: BoardKind!) {
      create_board (board_name: $board_name, board_kind: $board_kind) {
        id
      }
    }
    """
    try:
        result = call_monday_api(token, query, {"board_name": name, "board_kind": "public"})
        if "errors" in result:
            print(f"Failed to create board: {result['errors']}", file=sys.stderr)
            return None
        board_id = result.get("data", {}).get("create_board", {}).get("id")
        print(f"🎉 Created brand new Monday.com board: '{name}' (ID: {board_id})")
        return board_id
    except Exception as e:
        print(f"Error creating board: {e}", file=sys.stderr)
        return None

def run_monday_setup():
    load_dotenv()
    
    token = os.getenv("MONDAY_API_TOKEN")
    board_id_str = os.getenv("MONDAY_BOARD_ID")
    
    # Check if variables are missing
    if not token or "your_monday_api_token" in token:
        print("Monday.com API Token is missing. Skipping Monday.com setup.")
        return True

    # Force create a new board if requested via argument or if board ID is empty
    force_new = "--new" in sys.argv or not board_id_str or "your_monday_board_id" in board_id_str
    
    if force_new:
        print("Creating a brand new Monday.com board for BeatMatch AI qualified leads...")
        new_id = create_new_board(token)
        if not new_id:
            print("Failed to create new board.", file=sys.stderr)
            return False
        board_id_str = str(new_id)
        update_env_files(board_id_str)
        
    print(f"Connecting to Monday.com board ID {board_id_str}...")
    
    # Query to fetch the board columns
    board_query = """
    query ($board_ids: [ID!]) {
      boards (ids: $board_ids) {
        id
        name
        columns {
          id
          title
          type
        }
      }
    }
    """
    
    try:
        result = call_monday_api(token, board_query, {"board_ids": [board_id_str]})
    except Exception as e:
        print(f"Error connecting to Monday.com API: {e}", file=sys.stderr)
        return False
        
    if "errors" in result:
        print(f"Monday.com API returned errors: {result['errors']}", file=sys.stderr)
        return False
        
    boards = result.get("data", {}).get("boards", [])
    if not boards:
        print(f"Error: Board with ID {board_id_str} was not found. Please verify the ID and token permissions.", file=sys.stderr)
        return False
        
    board = boards[0]
    print(f"Successfully connected to board: '{board['name']}' (ID: {board['id']})")
    
    # Define columns to ensure on the board
    columns_to_ensure = [
        {"title": "Spotify ID", "type": "text"},
        {"title": "Popularity", "type": "numbers"},
        {"title": "Followers", "type": "numbers"},
        {"title": "Monthly Listeners", "type": "numbers"},
        {"title": "Max Song Views", "type": "numbers"},
        {"title": "Instagram", "type": "link"},
        {"title": "Twitter", "type": "link"},
        {"title": "Top Track 1", "type": "text"},
        {"title": "Top Track 2", "type": "text"},
        {"title": "Top Track 3", "type": "text"},
        {"title": "Scouting Source", "type": "text"},
        {"title": "Status", "type": "status"},
    ]
    
    existing_cols = {col["title"].lower(): col for col in board["columns"]}
    
    creation_errors = 0
    for col in columns_to_ensure:
        title_lower = col["title"].lower()
        if title_lower in existing_cols:
            existing_type = existing_cols[title_lower]["type"]
            print(f"Column '{col['title']}' already exists (Type: '{existing_type}'). Skipping.")
        else:
            print(f"Creating missing column '{col['title']}' (Type: '{col['type']}')...")
            mutation_query = f"""
            mutation ($board_id: ID!, $title: String!) {{
              create_column (board_id: $board_id, title: $title, column_type: {col['type']}) {{
                id
                title
              }}
            }}
            """
            
            variables = {
                "board_id": board_id_str,
                "title": col["title"]
            }
            
            try:
                mutation_result = call_monday_api(token, mutation_query, variables)
                if "errors" in mutation_result:
                    print(f"Failed to create column '{col['title']}': {mutation_result['errors']}", file=sys.stderr)
                    creation_errors += 1
                else:
                    new_col = mutation_result.get("data", {}).get("create_column", {})
                    print(f"Created column '{new_col.get('title')}' successfully with ID '{new_col.get('id')}'.")
            except Exception as e:
                print(f"Network error creating column '{col['title']}': {e}", file=sys.stderr)
                creation_errors += 1
                
    if creation_errors > 0:
        print(f"Monday.com board setup completed with {creation_errors} error(s).", file=sys.stderr)
        return False
        
    print("Monday.com board setup verification and provisioning completed successfully!")
    return True

if __name__ == "__main__":
    success = run_monday_setup()
    if not success:
        sys.exit(1)
