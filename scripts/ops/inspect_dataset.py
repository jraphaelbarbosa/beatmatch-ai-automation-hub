import os
import sys
import json
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
client = ApifyClient(APIFY_TOKEN)

def dump_sample(dataset_id, filepath):
    try:
        items = client.dataset(dataset_id).list_items(limit=1).items
        if items:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(items[0], f, indent=2, ensure_ascii=False)
            print(f"Dumped sample to {filepath}")
        else:
            print("Dataset empty.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    dump_sample("Ugt3AgP9ehdLviZh1", "src/sample_item.json")
