#!/usr/bin/env python3
"""
データベース初期化スクリプト

使用方法:
  python init_db.py              # データベース初期化
  python init_db.py --reset      # データベースリセット
  python init_db.py --check      # データベース状態確認
"""

import sys
import os
import argparse

# アプリケーションルートをPythonパスに追加
app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, app_root)

from database import init_db, reset_db, get_db_connection, DATABASE_PATH

def check_database():
    """データベースの状態をチェック"""
    if not os.path.exists(DATABASE_PATH):
        print(f"❌ Database does not exist: {DATABASE_PATH}")
        return False
    
    try:
        conn = get_db_connection()
        
        # テーブル一覧を取得
        tables = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """).fetchall()
        
        print(f"✅ Database exists: {DATABASE_PATH}")
        print(f"📊 Tables ({len(tables)}):")
        
        for table in tables:
            table_name = table['name']
            count = conn.execute(f"SELECT COUNT(*) as count FROM {table_name}").fetchone()
            print(f"  - {table_name}: {count['count']} records")
        
        # 設定情報を表示
        print("\n⚙️  Current Settings:")
        settings = conn.execute("""
            SELECT key, value, description 
            FROM settings 
            WHERE is_sensitive = FALSE 
            ORDER BY category, key
        """).fetchall()
        
        for setting in settings:
            print(f"  - {setting['key']}: {setting['value']} ({setting['description']})")
        
        # 管理者情報を表示
        print("\n👥 Admin Users:")
        admins = conn.execute("""
            SELECT email, added_at, is_active 
            FROM admin_users 
            ORDER BY added_at
        """).fetchall()
        
        for admin in admins:
            status = "Active" if admin['is_active'] else "Inactive"
            print(f"  - {admin['email']} ({status}) - Added: {admin['added_at']}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Database check failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Database management script')
    parser.add_argument('--reset', action='store_true', help='Reset database (delete and recreate)')
    parser.add_argument('--check', action='store_true', help='Check database status')
    
    args = parser.parse_args()
    
    try:
        if args.reset:
            print("🔄 Resetting database...")
            reset_db()
            print("✅ Database reset completed successfully!")
            
        elif args.check:
            print("🔍 Checking database status...")
            if check_database():
                print("✅ Database check completed successfully!")
            else:
                print("❌ Database check failed!")
                sys.exit(1)
                
        else:
            print("🚀 Initializing database...")
            init_db()
            print("✅ Database initialization completed successfully!")
            
            # マイグレーション実行
            print("🔄 Running database migrations...")
            from database.migrations import run_all_migrations
            
            conn = get_db_connection()
            try:
                run_all_migrations(conn)
                print("✅ Database migrations completed successfully!")
            except Exception as e:
                print(f"❌ Migration failed: {e}")
                raise
            finally:
                conn.close()
            
            # 初期化後の状態確認
            print("\n" + "="*50)
            check_database()
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()