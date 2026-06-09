import os
import sys
import argparse
from datetime import datetime
import pandas as pd

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.utils.db import get_connection

def run_sipa_engine(action, fake_action, dedup_strategy):
    print("=" * 70)
    print(f"[*] BEATMATCHAI AUTOMATION HUB - SIPA QUALITY ENGINE")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Execution Mode: {action.upper()}")
    print(f"Fake Action: {fake_action.upper()}")
    print(f"Deduplication Strategy: {dedup_strategy.upper()}")
    print("=" * 70)

    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Total initial records
    cursor.execute("SELECT COUNT(*) FROM public.artists")
    initial_count = cursor.fetchone()[0]
    print(f"[*] Total initial records in database: {initial_count}")

    # Load records to DataFrame
    df_artists = pd.read_sql_query(
        "SELECT spotify_id, name, followers, popularity, status FROM public.artists", 
        conn
    )
    
    # Clean followers and popularity (replace None with 0)
    df_artists['popularity'] = df_artists['popularity'].fillna(0).astype(int)
    df_artists['followers'] = df_artists['followers'].fillna(0).astype(int)

    # --- FASE 1: FAKE / INACTIVE DETECTION ---
    # Condition 1: Short names (1 character or less)
    cond_short_name = df_artists['name'].astype(str).str.len() <= 1
    
    # Condition 2: Generic terms
    generic_terms = ['rnb', 'rap', 'hip hop', 'pop', 'trap', 'genre', 'type beat']
    pattern = '|'.join(generic_terms)
    cond_generic = df_artists['name'].astype(str).str.lower().str.contains(pattern, regex=True, na=False)
    
    # Condition 3: Extremes of inactivity (Popularity == 0 and Followers < 5)
    cond_inactive = (df_artists['popularity'] == 0) & (df_artists['followers'] < 5)
    
    # Apply filters: (Short name OR Generic terms) AND Inactive
    fake_mask = (cond_short_name | cond_generic) & cond_inactive
    df_fakes = df_artists[fake_mask]
    fake_ids = df_fakes['spotify_id'].tolist()
    
    print(f"[*] Fakes/Inactives detected: {len(df_fakes)}")
    if len(df_fakes) > 0:
        print("\nSample of fake/inactive profiles:")
        print(df_fakes.head(10)[['spotify_id', 'name', 'popularity', 'followers', 'status']].to_string(index=False))
        print("-" * 50)

    # --- FASE 2: NAME DEDUPLICATION ---
    df_for_dedup = df_artists[~df_artists['spotify_id'].isin(fake_ids)].copy()
    df_for_dedup['name_lower'] = df_for_dedup['name'].astype(str).str.lower()
    
    # Identify duplicates
    dup_names = df_for_dedup[df_for_dedup.duplicated(subset=['name_lower'], keep=False)]
    unique_dup_names = dup_names['name_lower'].unique()
    print(f"[*] Total name duplicates found: {len(unique_dup_names)} name groups")
    
    ids_to_keep = []
    ids_to_delete_dup = []
    
    if len(unique_dup_names) > 0:
        # Sort so that best option comes first (higher popularity, then followers)
        df_sorted = df_for_dedup.sort_values(by=['name_lower', 'popularity', 'followers'], ascending=[True, False, False])
        
        # Best record of each group
        df_best = df_sorted.drop_duplicates(subset=['name_lower'], keep='first')
        best_ids = set(df_best['spotify_id'].tolist())
        
        # All other duplicate IDs will be deleted
        all_dup_ids = set(dup_names['spotify_id'].tolist())
        ids_to_delete_dup = list(all_dup_ids - best_ids)
        
        print(f"[*] Total duplicate records to remove: {len(ids_to_delete_dup)}")
        if len(ids_to_delete_dup) > 0:
            print("\nSample of duplicates to delete (preserving highest relevance):")
            sample_groups = unique_dup_names[:3]
            for g in sample_groups:
                group_df = df_sorted[df_sorted['name_lower'] == g]
                print(f"\nName Group: '{g.upper()}'")
                for _, r in group_df.iterrows():
                    action_tag = "[KEEP]" if r['spotify_id'] in best_ids else "[DELETE]"
                    print(f"  {action_tag} ID: {r['spotify_id']} | Popularity: {r['popularity']} | Followers: {r['followers']}")
            print("-" * 50)

    # --- FASE 3: APPLY ACTIONS ---
    if action == "dry-run":
        print("\n[!] DRY-RUN MODE: No database changes were executed.")
        projected_total = initial_count - len(ids_to_delete_dup)
        if fake_action == "delete":
            projected_total -= len(fake_ids)
            print(f"[-] Fakes projected for physical deletion: {len(fake_ids)}")
        else:
            print(f"[~] Fakes projected for marking as 'garbage' status: {len(fake_ids)}")
        
        print(f"[-] Duplicates projected for physical deletion: {len(ids_to_delete_dup)}")
        print(f"[*] Projected final database volume: {projected_total}")
    
    elif action == "apply":
        # 1. Handle Fakes
        if len(fake_ids) > 0:
            if fake_action == "delete":
                placeholders = ", ".join(["%s"] * len(fake_ids))
                cursor.execute(f"DELETE FROM public.artists WHERE spotify_id IN ({placeholders})", fake_ids)
                print(f"[OK] Success: {cursor.rowcount} fake records deleted physically.")
            elif fake_action == "mark":
                placeholders = ", ".join(["%s"] * len(fake_ids))
                cursor.execute(f"UPDATE public.artists SET status = 'garbage' WHERE spotify_id IN ({placeholders})", fake_ids)
                print(f"[OK] Success: {cursor.rowcount} fake records updated with status 'garbage'.")
        
        # 2. Handle Duplicates
        if len(ids_to_delete_dup) > 0:
            placeholders = ", ".join(["%s"] * len(ids_to_delete_dup))
            cursor.execute(f"DELETE FROM public.artists WHERE spotify_id IN ({placeholders})", ids_to_delete_dup)
            print(f"[OK] Success: {cursor.rowcount} duplicate records deleted physically.")
            
        # 3. Transition others from fully enriched state to ready_for_sipa
        cursor.execute("""
            UPDATE public.artists
            SET status = 'ready_for_sipa'
            WHERE (status = 'pending_enrichment' OR status = 'pending_instagram' OR status = 'pending_spotify')
              AND followers IS NOT NULL 
              AND popularity IS NOT NULL 
              AND instagram_url IS NOT NULL
              AND (monthly_listeners IS NULL OR monthly_listeners <= 8000)
              AND (max_song_views IS NULL OR max_song_views <= 10000);
        """)
        print(f"[OK] Success: {cursor.rowcount} successfully enriched artists marked as 'ready_for_sipa'.")

        conn.commit()
        
        # Final stats
        cursor.execute("SELECT COUNT(*) FROM public.artists")
        final_count = cursor.fetchone()[0]
        cursor.execute("SELECT status, COUNT(*) FROM public.artists GROUP BY status")
        status_dist = cursor.fetchall()
        
        print("\n" + "=" * 50)
        print("[SUCCESS] SIPA QUALITY ENGINE RELATIONAL REPORT")
        print(f"[*] Initial Volume: {initial_count}")
        print(f"[*] Final Volume: {final_count}")
        print(f"[*] Noise Reduction: {initial_count - final_count} ({((initial_count - final_count)/initial_count)*100:.2f}%)")
        print("\nFinal Status Distribution in Database:")
        for row in status_dist:
            print(f"  - [{row[0]}]: {row[1]} artists")
        print("=" * 50)
        
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SIPA Engine - Unified Pipeline Quality & Cleansing")
    parser.add_argument("--action", type=str, choices=["dry-run", "apply"], default="dry-run", 
                        help="Operation mode: dry-run or apply")
    parser.add_argument("--fake-action", type=str, choices=["delete", "mark"], default="mark",
                        help="Action for fakes: 'delete' or 'mark'")
    parser.add_argument("--dedup-strategy", type=str, choices=["keep-best"], default="keep-best",
                        help="Deduplication decision strategy")
    
    args = parser.parse_args()
    
    run_sipa_engine(
        action=args.action,
        fake_action=args.fake_action,
        dedup_strategy=args.dedup_strategy
    )
