import psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()
        return conn, cur
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")
        return None, None

def execute_query(query, params=(), fetch_one=False, fetch_all=False, return_id=False):
    conn, cur = get_db_connection()
    if not conn:
        return None
    try:
        cur.execute(query, params)
        if return_id:
            result = cur.fetchone()[0]
            conn.commit()
            return result
        if fetch_one:
            result = cur.fetchone()
            return result
        if fetch_all:
            result = cur.fetchall()
            return result
        conn.commit()
        return True
    except psycopg2.Error as e:
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()

def init_db():
    conn, cur = get_db_connection()
    if conn:
        print("✅ Database initialized successfully!")
        cur.close()
        conn.close()
