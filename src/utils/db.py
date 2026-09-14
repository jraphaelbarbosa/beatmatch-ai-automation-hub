import os
import time

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

def get_connection(retries=3, delay=2):
    """
    Returns a stable connection to the Supabase PostgreSQL database.
    Includes connection retry logic.
    """
    if not DATABASE_URL:
        raise ValueError("CRITICAL: DATABASE_URL environment variable is not configured.")
        
    # Standardize postgresql prefix for sqlalchemy / psycopg2
    pg_url = DATABASE_URL.replace("postgres://", "postgresql://")
    
    # Adjust port for Transaction Pooler if using standard Supabase port
    if ":5432" in pg_url:
        pg_url = pg_url.replace(":5432", ":6543")
        
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(pg_url)
            return conn
        except psycopg2.OperationalError as e:
            if attempt == retries:
                print(f"❌ Connection error on attempt {attempt}/{retries}: {e}")
                raise e
            print(f"⚠️ Connection failed. Retrying in {delay}s...")
            time.sleep(delay)

def execute_query(query, params=None, fetch=False):
    """
    Executes a query safely, ensuring that connections are properly closed.
    """
    conn = get_connection()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            if fetch:
                return cur.fetchall()
    finally:
        conn.close()
