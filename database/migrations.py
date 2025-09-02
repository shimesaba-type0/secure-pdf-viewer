"""
データベースマイグレーション管理
"""
import sqlite3
import re


def validate_passphrase(passphrase):
    """
    パスフレーズの有効性を検証
    - 32文字以上128文字以下
    - ASCII文字 (0-9, a-z, A-Z, _, -) のみ
    """
    if not passphrase:
        return False, "パスフレーズが空です"
    
    # 文字数チェック
    if len(passphrase) < 32:
        return False, "パスフレーズは32文字以上である必要があります"
    
    if len(passphrase) > 128:
        return False, "パスフレーズは128文字以下である必要があります"
    
    # 文字種チェック（ASCII: 0-9, a-z, A-Z, _, -）
    allowed_pattern = re.compile(r'^[0-9a-zA-Z_-]+$')
    if not allowed_pattern.match(passphrase):
        return False, "パスフレーズは0-9, a-z, A-Z, _, - の文字のみ使用可能です"
    
    return True, "有効なパスフレーズです"


def migrate_password_to_passphrase(db):
    """
    shared_password を shared_passphrase に移行
    """
    # 現在の shared_password 設定を取得
    db.row_factory = sqlite3.Row
    current_setting = db.execute(
        'SELECT value FROM settings WHERE key = ?', 
        ('shared_password',)
    ).fetchone()
    
    if current_setting:
        current_password = current_setting['value']
        
        # 現在のパスワードがパスフレーズ要件を満たしているかチェック
        is_valid, message = validate_passphrase(current_password)
        
        if is_valid:
            # 有効な場合はそのまま移行
            new_passphrase = current_password
        else:
            # 無効な場合はデフォルトのパスフレーズを使用
            new_passphrase = 'default_passphrase_32chars_minimum_length_example'
            print(f"現在のパスワード '{current_password}' は無効です: {message}")
            print(f"デフォルトパスフレーズ '{new_passphrase}' を使用します")
        
        # 新しい shared_passphrase 設定を作成
        db.execute('''
            INSERT OR REPLACE INTO settings (key, value, value_type, description, category, is_sensitive)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            'shared_passphrase',
            new_passphrase,
            'string',
            '事前共有パスフレーズ（32-128文字、0-9a-zA-Z_-のみ）',
            'auth',
            True
        ))
        
        # 古い shared_password 設定を削除
        db.execute('DELETE FROM settings WHERE key = ?', ('shared_password',))
        
        # 変更履歴を記録
        db.execute('''
            INSERT INTO settings_history (setting_key, old_value, new_value, changed_by, change_reason)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            'shared_passphrase',
            current_password,
            new_passphrase,
            'migration_system',
            'Password to passphrase migration'
        ))
        
        print(f"Migration completed: shared_password -> shared_passphrase")
        return True
    
    else:
        # shared_password が存在しない場合、デフォルトのパスフレーズを作成
        default_passphrase = 'default_passphrase_32chars_minimum_length_example'
        db.execute('''
            INSERT OR REPLACE INTO settings (key, value, value_type, description, category, is_sensitive)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            'shared_passphrase',
            default_passphrase,
            'string',
            '事前共有パスフレーズ（32-128文字、0-9a-zA-Z_-のみ）',
            'auth',
            True
        ))
        
        print(f"Created default passphrase setting: {default_passphrase}")
        return True


def run_migration_001(db):
    """
    Migration 001: パスワードからパスフレーズへの移行
    """
    print("Running Migration 001: Password to Passphrase")
    
    try:
        # トランザクション開始
        db.execute('BEGIN TRANSACTION')
        
        # マイグレーション実行
        migrate_password_to_passphrase(db)
        
        # マイグレーション記録テーブルがない場合は作成
        db.execute('''
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                applied_at TEXT,
                description TEXT
            )
        ''')
        
        # マイグレーション実行記録
        db.execute('''
            INSERT OR REPLACE INTO migrations (name, description)
            VALUES (?, ?)
        ''', ('001_password_to_passphrase', 'Migrate shared_password to shared_passphrase with validation'))
        
        # コミット
        db.execute('COMMIT')
        print("Migration 001 completed successfully")
        
    except Exception as e:
        # ロールバック
        db.execute('ROLLBACK')
        print(f"Migration 001 failed: {str(e)}")
        raise


def run_migration_002(db):
    """
    Migration 002: セキュリティイベントログ機能追加
    """
    print("Running Migration 002: Security Event Logging")
    
    try:
        # トランザクション開始
        db.execute('BEGIN TRANSACTION')
        
        # access_logs テーブルの存在を確認
        table_exists = db.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='access_logs'
        """).fetchone()
        
        if table_exists:
            # access_logs テーブルに新しいカラムを追加
            try:
                db.execute('ALTER TABLE access_logs ADD COLUMN user_email TEXT')
                print("Added user_email column to access_logs")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
                print("user_email column already exists in access_logs")
            
            try:
                db.execute('ALTER TABLE access_logs ADD COLUMN duration_seconds INTEGER')
                print("Added duration_seconds column to access_logs")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
                print("duration_seconds column already exists in access_logs")
            
            try:
                db.execute('ALTER TABLE access_logs ADD COLUMN pdf_file_path TEXT')
                print("Added pdf_file_path column to access_logs")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
                print("pdf_file_path column already exists in access_logs")
        else:
            print("access_logs table does not exist, skipping column additions")
        
        # security_events テーブルを作成
        db.execute('''
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK (event_type IN (
                    'pdf_view', 'download_attempt', 'print_attempt', 
                    'direct_access', 'devtools_open', 'unauthorized_action', 
                    'page_leave', 'screenshot_attempt', 'copy_attempt'
                )),
                event_details JSON,
                risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')) DEFAULT 'low',
                ip_address TEXT,
                user_agent TEXT,
                occurred_at TEXT,
                pdf_file_path TEXT,
                session_id TEXT
            )
        ''')
        print("Created security_events table")
        
        # インデックス作成
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_security_events_user_email ON security_events(user_email)',
            'CREATE INDEX IF NOT EXISTS idx_security_events_event_type ON security_events(event_type)',
            'CREATE INDEX IF NOT EXISTS idx_security_events_risk_level ON security_events(risk_level)',
            'CREATE INDEX IF NOT EXISTS idx_security_events_occurred_at ON security_events(occurred_at)',
            'CREATE INDEX IF NOT EXISTS idx_security_events_pdf_file_path ON security_events(pdf_file_path)',
            'CREATE INDEX IF NOT EXISTS idx_security_events_session_id ON security_events(session_id)',
            'CREATE INDEX IF NOT EXISTS idx_access_logs_user_email ON access_logs(user_email)',
            'CREATE INDEX IF NOT EXISTS idx_access_logs_pdf_file_path ON access_logs(pdf_file_path)'
        ]
        
        for index_sql in indexes:
            db.execute(index_sql)
        print("Created security event indexes")
        
        # マイグレーション実行記録
        db.execute('''
            INSERT OR REPLACE INTO migrations (name, description)
            VALUES (?, ?)
        ''', ('002_security_event_logging', 'Add security event logging tables and indexes'))
        
        # コミット
        db.execute('COMMIT')
        print("Migration 002 completed successfully")
        
    except Exception as e:
        # ロールバック
        db.execute('ROLLBACK')
        print(f"Migration 002 failed: {str(e)}")
        raise


def get_applied_migrations(db):
    """適用済みマイグレーションを取得"""
    try:
        db.row_factory = sqlite3.Row
        return [row['name'] for row in db.execute('SELECT name FROM migrations ORDER BY applied_at').fetchall()]
    except sqlite3.OperationalError:
        # migrationsテーブルが存在しない場合
        return []


def run_all_migrations(db):
    """全てのマイグレーションを実行"""
    applied_migrations = get_applied_migrations(db)
    
    # 利用可能なマイグレーション
    available_migrations = [
        ('001_password_to_passphrase', run_migration_001),
        ('002_security_event_logging', run_migration_002),
    ]
    
    for migration_name, migration_func in available_migrations:
        if migration_name not in applied_migrations:
            print(f"Applying migration: {migration_name}")
            migration_func(db)
        else:
            print(f"Migration already applied: {migration_name}")
    
    print("All migrations completed")


if __name__ == '__main__':
    # テスト用
    import os
    db_path = '/tmp/test_migration.db'
    
    # テストデータベース作成
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        # テスト用の初期データを作成
        conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT,
                value_type TEXT DEFAULT 'string',
                description TEXT,
                category TEXT DEFAULT 'general',
                is_sensitive BOOLEAN DEFAULT FALSE,
                created_at TEXT,
                updated_at TEXT,
                updated_by TEXT
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS settings_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                changed_by TEXT NOT NULL,
                change_reason TEXT,
                changed_at TEXT,
                ip_address TEXT
            )
        ''')
        
        # テスト用の古いパスワード設定
        conn.execute('''
            INSERT OR REPLACE INTO settings (key, value, value_type, description, category, is_sensitive)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('shared_password', 'demo123', 'string', '事前共有パスワード', 'auth', True))
        
        conn.commit()
        
        # マイグレーション実行
        run_all_migrations(conn)
        
        # 結果確認
        result = conn.execute('SELECT key, value FROM settings WHERE key = ?', ('shared_passphrase',)).fetchone()
        if result:
            print(f"Migration test successful: {result['key']} = {result['value']}")
        else:
            print("Migration test failed: shared_passphrase not found")
            
    finally:
        conn.close()
        # テストファイル削除
        if os.path.exists(db_path):
            os.remove(db_path)