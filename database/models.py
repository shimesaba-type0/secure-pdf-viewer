"""
データベースモデル定義とテーブル作成
"""
import sqlite3
import hashlib
from datetime import datetime
from config.timezone import get_app_now, get_app_datetime_string, localize_datetime

def insert_with_app_timestamp(db, table, columns, values, timestamp_columns=None):
    """
    アプリタイムゾーンの時刻でINSERTを実行
    
    Args:
        db: データベース接続
        table: テーブル名
        columns: カラム名のリスト
        values: 値のリスト
        timestamp_columns: 時刻を自動設定するカラム名のリスト（デフォルト: ['created_at']）
    """
    if timestamp_columns is None:
        timestamp_columns = ['created_at']
    
    # 時刻カラムを追加
    current_time = get_app_datetime_string()
    final_columns = list(columns)
    final_values = list(values)
    
    for ts_col in timestamp_columns:
        if ts_col not in final_columns:
            final_columns.append(ts_col)
            final_values.append(current_time)
    
    # SQL生成
    placeholders = ', '.join(['?'] * len(final_columns))
    columns_str = ', '.join(final_columns)
    sql = f'INSERT INTO {table} ({columns_str}) VALUES ({placeholders})'
    
    return db.execute(sql, final_values)

def update_with_app_timestamp(db, table, set_columns, set_values, where_clause, where_values=None, timestamp_columns=None):
    """
    アプリタイムゾーンの時刻でUPDATEを実行
    
    Args:
        db: データベース接続
        table: テーブル名
        set_columns: 更新するカラム名のリスト
        set_values: 更新する値のリスト
        where_clause: WHERE句
        where_values: WHERE句の値のリスト
        timestamp_columns: 時刻を自動設定するカラム名のリスト（デフォルト: ['updated_at']）
    """
    if timestamp_columns is None:
        timestamp_columns = ['updated_at']
    if where_values is None:
        where_values = []
    
    # 時刻カラムを追加
    current_time = get_app_datetime_string()
    final_columns = list(set_columns)
    final_values = list(set_values)
    
    for ts_col in timestamp_columns:
        if ts_col not in final_columns:
            final_columns.append(ts_col)
            final_values.append(current_time)
    
    # SQL生成
    set_clause = ', '.join([f'{col} = ?' for col in final_columns])
    sql = f'UPDATE {table} SET {set_clause} WHERE {where_clause}'
    
    return db.execute(sql, final_values + where_values)

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
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            memo TEXT DEFAULT ''
        )
    ''')
    
    # 既存テーブルにmemoカラムを追加（マイグレーション）
    try:
        db.execute('ALTER TABLE session_stats ADD COLUMN memo TEXT DEFAULT ""')
        print("session_stats テーブルに memo カラムを追加しました")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            print(f"memo カラム追加エラー: {e}")
        # カラムが既に存在する場合は無視
    
    # email_addressカラムを追加（メールアドレス表示問題解決）
    try:
        db.execute('ALTER TABLE session_stats ADD COLUMN email_address TEXT DEFAULT ""')
        print("session_stats テーブルに email_address カラムを追加しました")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            print(f"email_address カラム追加エラー: {e}")
        # カラムが既に存在する場合は無視
    
    # OTPトークンテーブル
    db.execute('''
        CREATE TABLE IF NOT EXISTS otp_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp_code TEXT NOT NULL,
            session_id TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            used_at TIMESTAMP NULL
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
        'CREATE INDEX IF NOT EXISTS idx_otp_tokens_email ON otp_tokens(email)',
        'CREATE INDEX IF NOT EXISTS idx_otp_tokens_expires_at ON otp_tokens(expires_at)',
        'CREATE INDEX IF NOT EXISTS idx_otp_tokens_used ON otp_tokens(used)',
    ]
    
    for index_sql in indexes:
        db.execute(index_sql)


def generate_initial_passphrase():
    """初期パスフレーズを安全に生成"""
    import secrets
    import string
    
    # 32文字の安全なランダムパスフレーズを生成
    chars = string.ascii_letters + string.digits + '_-'
    return ''.join(secrets.choice(chars) for _ in range(32))


def insert_initial_data(db):
    """初期データの挿入"""
    
    # 既存の設定をチェック
    existing_settings = db.execute('SELECT COUNT(*) as count FROM settings').fetchone()
    
    if existing_settings['count'] == 0:
        # 初期パスフレーズを生成
        initial_passphrase = generate_initial_passphrase()
        print(f"初期パスフレーズが生成されました: {initial_passphrase}")
        print("このパスフレーズを安全に保存し、初回ログイン後に変更してください。")
        
        # 初期設定データ
        initial_settings = [
            ('shared_passphrase', initial_passphrase, 'string', '事前共有パスフレーズ（32-128文字、0-9a-zA-Z_-のみ）', 'auth', True),
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
            ('max_concurrent_sessions', '100', 'integer', '同時接続数制限（警告閾値）', 'security', False),
            ('session_limit_enabled', 'true', 'boolean', 'セッション数制限有効化', 'security', False),
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
    """設定値を更新または作成"""
    # 現在の値を取得（履歴用）
    db.row_factory = sqlite3.Row
    current_row = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    old_value = current_row['value'] if current_row else None
    
    if current_row:
        # 既存設定の更新
        db.execute('''
            UPDATE settings 
            SET value = ?, updated_at = ?, updated_by = ?
            WHERE key = ?
        ''', (str(value), get_app_datetime_string(), updated_by, key))
    else:
        # 新規設定の追加
        now_str = get_app_datetime_string()
        db.execute('''
            INSERT INTO settings (key, value, value_type, description, category, created_at, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (key, str(value), 'string', f'動的設定: {key}', 'session', now_str, now_str, updated_by))
    
    # 履歴に記録
    db.execute('''
        INSERT INTO settings_history (setting_key, old_value, new_value, changed_by)
        VALUES (?, ?, ?, ?)
    ''', (key, old_value, str(value), updated_by))


def log_access(db, session_id, email_hash, ip_address, user_agent, endpoint, method, status_code, device_type=None, screen_resolution=None):
    """アクセスログを記録"""
    db.execute('''
        INSERT INTO access_logs (session_id, email_hash, ip_address, user_agent, device_type, screen_resolution, endpoint, method, status_code, access_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, email_hash, ip_address, user_agent, device_type, screen_resolution, endpoint, method, status_code, get_app_datetime_string()))


def log_event(db, session_id, email_hash, event_type, event_data, ip_address, device_info=None):
    """イベントログを記録"""
    import json
    
    db.execute('''
        INSERT INTO event_logs (session_id, email_hash, event_type, event_data, timestamp, ip_address, device_info, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, email_hash, event_type, json.dumps(event_data), int(get_app_now().timestamp()), ip_address, json.dumps(device_info) if device_info else None, get_app_datetime_string()))


def log_auth_failure(db, ip_address, failure_type, email_attempted=None, device_type=None):
    """認証失敗ログを記録"""
    db.execute('''
        INSERT INTO auth_failures (ip_address, failure_type, email_attempted, device_type, attempt_time)
        VALUES (?, ?, ?, ?, ?)
    ''', (ip_address, failure_type, email_attempted, device_type, get_app_datetime_string()))


def log_security_event(db, user_email, event_type, event_details, risk_level='low', ip_address=None, user_agent=None, pdf_file_path=None, session_id=None):
    """セキュリティイベントログを記録"""
    import json
    
    # リスクレベルの検証
    valid_risk_levels = ['low', 'medium', 'high']
    if risk_level not in valid_risk_levels:
        risk_level = 'low'
    
    # イベントタイプの検証
    valid_event_types = [
        'pdf_view', 'download_attempt', 'print_attempt', 
        'direct_access', 'devtools_open', 'unauthorized_action', 
        'page_leave', 'screenshot_attempt', 'copy_attempt'
    ]
    if event_type not in valid_event_types:
        event_type = 'unauthorized_action'
        risk_level = 'high'
    
    db.execute('''
        INSERT INTO security_events 
        (user_email, event_type, event_details, risk_level, ip_address, user_agent, occurred_at, pdf_file_path, session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_email, 
        event_type, 
        json.dumps(event_details) if event_details else None,
        risk_level,
        ip_address,
        user_agent,
        get_app_datetime_string(),
        pdf_file_path,
        session_id
    ))


def get_security_events(db, user_email=None, event_type=None, risk_level=None, start_date=None, end_date=None, limit=50, offset=0):
    """セキュリティイベントログを取得"""
    db.row_factory = sqlite3.Row
    
    # WHERE句の構築
    where_conditions = []
    params = []
    
    if user_email:
        where_conditions.append("user_email = ?")
        params.append(user_email)
    
    if event_type:
        where_conditions.append("event_type = ?")
        params.append(event_type)
    
    if risk_level:
        where_conditions.append("risk_level = ?")
        params.append(risk_level)
    
    if start_date:
        where_conditions.append("occurred_at >= ?")
        params.append(start_date)
    
    if end_date:
        where_conditions.append("occurred_at <= ?")
        params.append(end_date)
    
    where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
    # クエリ実行
    query = f'''
        SELECT * FROM security_events
        {where_clause}
        ORDER BY occurred_at DESC
        LIMIT ? OFFSET ?
    '''
    params.extend([limit, offset])
    
    events = db.execute(query, params).fetchall()
    
    # 総件数も取得
    count_query = f'SELECT COUNT(*) as total FROM security_events{where_clause}'
    count_params = params[:-2]  # LIMIT, OFFSETを除く
    total = db.execute(count_query, count_params).fetchone()['total']
    
    return {
        'events': [dict(event) for event in events],
        'total': total,
        'has_more': total > offset + len(events)
    }


def get_security_event_stats(db, start_date=None, end_date=None):
    """セキュリティイベントの統計情報を取得"""
    db.row_factory = sqlite3.Row
    
    where_conditions = []
    params = []
    
    if start_date:
        where_conditions.append("occurred_at >= ?")
        params.append(start_date)
    
    if end_date:
        where_conditions.append("occurred_at <= ?")
        params.append(end_date)
    
    where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
    # リスクレベル別統計
    risk_stats = db.execute(f'''
        SELECT risk_level, COUNT(*) as count
        FROM security_events
        {where_clause}
        GROUP BY risk_level
        ORDER BY 
            CASE risk_level 
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
            END
    ''', params).fetchall()
    
    # イベントタイプ別統計
    event_stats = db.execute(f'''
        SELECT event_type, COUNT(*) as count
        FROM security_events
        {where_clause}
        GROUP BY event_type
        ORDER BY count DESC
    ''', params).fetchall()
    
    # 総件数
    total = db.execute(f'''
        SELECT COUNT(*) as total FROM security_events
        {where_clause}
    ''', params).fetchone()['total']
    
    return {
        'total': total,
        'risk_levels': {row['risk_level']: row['count'] for row in risk_stats},
        'event_types': {row['event_type']: row['count'] for row in event_stats}
    }