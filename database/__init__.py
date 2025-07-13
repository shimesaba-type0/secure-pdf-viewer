import sqlite3
import os
from contextlib import contextmanager

DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'database.db')

def get_db_connection():
    """データベース接続を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # 辞書形式でアクセス可能
    return conn

@contextmanager
def get_db():
    """データベース接続のコンテキストマネージャー"""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """データベースを初期化"""
    from .models import create_tables, insert_initial_data
    
    # instanceディレクトリが存在しない場合は作成
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    
    with get_db() as db:
        create_tables(db)
        insert_initial_data(db)
    
    print(f"Database initialized at: {DATABASE_PATH}")

def reset_db():
    """データベースをリセット（開発用）"""
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
    init_db()
    print("Database reset completed.")