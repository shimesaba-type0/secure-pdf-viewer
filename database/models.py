"""
データベースモデル定義とテーブル作成
"""
import sqlite3

def create_tables(db):
    """全てのテーブルを作成"""
    
    # アクセスログテーブル
    db.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            email_hash TEXT,
            ip_address TEXT,
            user_agent TEXT,
            device_type TEXT,
            screen_resolution TEXT,
            access_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            endpoint TEXT,
            method TEXT,
            status_code INTEGER
        )
    ''')
    
    # イベントログテーブル
    db.execute('''
        CREATE TABLE IF NOT EXISTS event_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            email_hash TEXT,
            event_type TEXT,
            event_data JSON,
            timestamp INTEGER,
            ip_address TEXT,
            device_info JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 認証失敗ログテーブル
    db.execute('''
        CREATE TABLE IF NOT EXISTS auth_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT,
            attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            failure_type TEXT,
            email_attempted TEXT,
            device_type TEXT
        )
    ''')
    
    # IP制限テーブル
    db.execute('''
        CREATE TABLE IF NOT EXISTS ip_blocks (
            ip_address TEXT PRIMARY KEY,
            blocked_until TIMESTAMP,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # システム設定テーブル
    db.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            value_type TEXT DEFAULT 'string',
            description TEXT,
            category TEXT DEFAULT 'general',
            is_sensitive BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT
        )
    ''')
    
    # 設定変更履歴テーブル
    db.execute('''
        CREATE TABLE IF NOT EXISTS settings_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT NOT NULL,
            change_reason TEXT,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT
        )
    ''')
    
    # 管理者権限テーブル
    db.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            added_by TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # セッション統計テーブル
    db.execute('''
        CREATE TABLE IF NOT EXISTS session_stats (
            session_id TEXT PRIMARY KEY,
            email_hash TEXT,
            start_time INTEGER,
            end_time INTEGER,
            total_active_time INTEGER,
            total_inactive_time INTEGER,
            page_views INTEGER,
            reactivation_count INTEGER,
            ip_address TEXT,
            device_type TEXT,
            orientation_changes INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # インデックス作成
    create_indexes(db)


def create_indexes(db):
    """パフォーマンス向上のためのインデックス作成"""
    
    indexes = [
        'CREATE INDEX IF NOT EXISTS idx_access_logs_session_id ON access_logs(session_id)',
        'CREATE INDEX IF NOT EXISTS idx_access_logs_time ON access_logs(access_time)',
        'CREATE INDEX IF NOT EXISTS idx_event_logs_session_id ON event_logs(session_id)',
        'CREATE INDEX IF NOT EXISTS idx_event_logs_type ON event_logs(event_type)',
        'CREATE INDEX IF NOT EXISTS idx_auth_failures_ip ON auth_failures(ip_address)',
        'CREATE INDEX IF NOT EXISTS idx_auth_failures_time ON auth_failures(attempt_time)',
        'CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key)',
        'CREATE INDEX IF NOT EXISTS idx_settings_category ON settings(category)',
        'CREATE INDEX IF NOT EXISTS idx_settings_history_key ON settings_history(setting_key)',
        'CREATE INDEX IF NOT EXISTS idx_settings_history_changed_at ON settings_history(changed_at)',
        'CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email)',
        'CREATE INDEX IF NOT EXISTS idx_session_stats_start_time ON session_stats(start_time)',
    ]
    
    for index_sql in indexes:
        db.execute(index_sql)


def insert_initial_data(db):
    """初期データの挿入"""
    
    # 既存の設定をチェック
    existing_settings = db.execute('SELECT COUNT(*) as count FROM settings').fetchone()
    
    if existing_settings['count'] == 0:
        # 初期設定データ
        initial_settings = [
            ('shared_password', 'demo123', 'string', '事前共有パスワード', 'auth', True),
            ('publish_start', None, 'datetime', '公開開始日時', 'publish', False),
            ('publish_end', None, 'datetime', '公開終了日時', 'publish', False),
            ('system_status', 'active', 'string', 'システム状態（active/unpublished）', 'system', False),
            ('session_timeout', '259200', 'integer', 'セッション有効期限（秒）', 'auth', False),
            ('max_login_attempts', '5', 'integer', '最大ログイン試行回数', 'security', False),
            ('lockout_duration', '1800', 'integer', 'ロックアウト時間（秒）', 'security', False),
            ('force_logout_after', '0', 'integer', '強制ログアウト実行時刻', 'system', False),
            ('mail_otp_expiry', '600', 'integer', 'OTP有効期限（秒）', 'mail', False),
            ('analytics_retention_days', '90', 'integer', 'ログ保持期間（日）', 'system', False),
            ('author_name', 'Default_Author', 'string', 'ウォーターマーク表示用著作者名', 'watermark', False),
            ('mobile_breakpoint', '480', 'integer', 'モバイル判定ブレークポイント（px）', 'responsive', False),
            ('tablet_breakpoint', '768', 'integer', 'タブレット判定ブレークポイント（px）', 'responsive', False),
            ('enable_touch_optimizations', 'true', 'boolean', 'タッチ操作最適化有効', 'responsive', False),
        ]
        
        for setting in initial_settings:
            db.execute('''
                INSERT INTO settings (key, value, value_type, description, category, is_sensitive)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', setting)
        
        print("Initial settings data inserted.")
    
    # 既存の管理者をチェック
    existing_admins = db.execute('SELECT COUNT(*) as count FROM admin_users').fetchone()
    
    if existing_admins['count'] == 0:
        # デフォルト管理者を追加（実際の運用では変更必要）
        db.execute('''
            INSERT INTO admin_users (email, added_by, is_active)
            VALUES (?, ?, ?)
        ''', ('admin@example.com', 'system', True))
        
        print("Default admin user created.")


def get_setting(db, key, default=None):
    """設定値を取得"""
    db.row_factory = sqlite3.Row
    row = db.execute('SELECT value, value_type FROM settings WHERE key = ?', (key,)).fetchone()
    if not row:
        return default
    
    value = row['value']
    value_type = row['value_type']
    
    # 型変換
    if value is None:
        return default
    elif value_type == 'integer':
        return int(value)
    elif value_type == 'boolean':
        return value.lower() in ('true', '1', 'yes')
    elif value_type == 'json':
        import json
        return json.loads(value)
    else:
        return value


def set_setting(db, key, value, updated_by='system'):
    """設定値を更新"""
    # 現在の値を取得（履歴用）
    db.row_factory = sqlite3.Row
    current_row = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    old_value = current_row['value'] if current_row else None
    
    # 設定を更新
    db.execute('''
        UPDATE settings 
        SET value = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
        WHERE key = ?
    ''', (str(value), updated_by, key))
    
    # 履歴に記録
    db.execute('''
        INSERT INTO settings_history (setting_key, old_value, new_value, changed_by)
        VALUES (?, ?, ?, ?)
    ''', (key, old_value, str(value), updated_by))


def log_access(db, session_id, email_hash, ip_address, user_agent, endpoint, method, status_code, device_type=None, screen_resolution=None):
    """アクセスログを記録"""
    db.execute('''
        INSERT INTO access_logs (session_id, email_hash, ip_address, user_agent, device_type, screen_resolution, endpoint, method, status_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, email_hash, ip_address, user_agent, device_type, screen_resolution, endpoint, method, status_code))


def log_event(db, session_id, email_hash, event_type, event_data, ip_address, device_info=None):
    """イベントログを記録"""
    import json
    import time
    
    db.execute('''
        INSERT INTO event_logs (session_id, email_hash, event_type, event_data, timestamp, ip_address, device_info)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, email_hash, event_type, json.dumps(event_data), int(time.time()), ip_address, json.dumps(device_info) if device_info else None))


def log_auth_failure(db, ip_address, failure_type, email_attempted=None, device_type=None):
    """認証失敗ログを記録"""
    db.execute('''
        INSERT INTO auth_failures (ip_address, failure_type, email_attempted, device_type)
        VALUES (?, ?, ?, ?)
    ''', (ip_address, failure_type, email_attempted, device_type))