"""
データベースモデル定義とテーブル作成
"""
import sqlite3
from config.timezone import get_app_now, get_app_datetime_string


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
        timestamp_columns = ["created_at"]

    # 時刻カラムを追加
    current_time = get_app_datetime_string()
    final_columns = list(columns)
    final_values = list(values)

    for ts_col in timestamp_columns:
        if ts_col not in final_columns:
            final_columns.append(ts_col)
            final_values.append(current_time)

    # SQL生成
    placeholders = ", ".join(["?"] * len(final_columns))
    columns_str = ", ".join(final_columns)
    sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"

    return db.execute(sql, final_values)


def update_with_app_timestamp(
    db,
    table,
    set_columns,
    set_values,
    where_clause,
    where_values=None,
    timestamp_columns=None,
):
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
        timestamp_columns = ["updated_at"]
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
    set_clause = ", ".join([f"{col} = ?" for col in final_columns])
    sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"

    return db.execute(sql, final_values + where_values)


def create_tables(db):
    """全てのテーブルを作成"""

    # アクセスログテーブル
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            email_hash TEXT,
            ip_address TEXT,
            user_agent TEXT,
            device_type TEXT,
            screen_resolution TEXT,
            access_time TEXT,
            endpoint TEXT,
            method TEXT,
            status_code INTEGER
        )
    """
    )

    # イベントログテーブル
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS event_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            email_hash TEXT,
            event_type TEXT,
            event_data JSON,
            timestamp INTEGER,
            ip_address TEXT,
            device_info JSON,
            created_at TEXT
        )
    """
    )

    # 認証失敗ログテーブル
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT,
            attempt_time TEXT,
            failure_type TEXT,
            email_attempted TEXT,
            device_type TEXT
        )
    """
    )

    # IP制限テーブル
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS ip_blocks (
            ip_address TEXT PRIMARY KEY,
            blocked_until TIMESTAMP,
            reason TEXT,
            created_at TEXT
        )
    """
    )

    # システム設定テーブル
    db.execute(
        """
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
    """
    )

    # 設定変更履歴テーブル
    db.execute(
        """
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
    """
    )

    # 管理者権限テーブル
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            added_by TEXT,
            added_at TEXT,
            updated_at TEXT,
            is_active BOOLEAN DEFAULT TRUE
        )
    """
    )

    # セッション統計テーブル
    db.execute(
        """
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
            last_updated TEXT,
            memo TEXT DEFAULT ''
        )
    """
    )

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

    # admin_usersテーブルにupdated_atカラムを追加（管理者権限システム）
    try:
        db.execute("ALTER TABLE admin_users ADD COLUMN updated_at TEXT DEFAULT NULL")
        print("admin_users テーブルに updated_at カラムを追加しました")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            print(f"updated_at カラム追加エラー: {e}")
        # カラムが既に存在する場合は無視

    # セキュリティイベントテーブル
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            event_type TEXT NOT NULL,
            event_details TEXT,
            risk_level TEXT DEFAULT 'low',
            ip_address TEXT,
            user_agent TEXT,
            occurred_at TEXT,
            pdf_file_path TEXT,
            session_id TEXT
        )
    """
    )

    # OTPトークンテーブル
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS otp_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp_code TEXT NOT NULL,
            session_id TEXT,
            ip_address TEXT,
            created_at TEXT,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            used_at TIMESTAMP NULL
        )
    """
    )

    # 管理者セッションテーブル（TASK-021 Sub-Phase 1A）
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_sessions (
            session_id TEXT PRIMARY KEY,
            admin_email TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_verified_at TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            security_flags JSON,
            verification_token TEXT
        )
    """
    )

    # CSRFトークンテーブル（TASK-021 Phase 2A）
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS csrf_tokens (
            token TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            is_used BOOLEAN DEFAULT FALSE
        )
    """
    )

    # レート制限テーブル（TASK-021 Phase 2B）
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL,
            user_id TEXT NOT NULL,
            request_count INTEGER DEFAULT 1,
            window_start TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(endpoint, user_id, window_start)
        )
    """
    )

    # セキュリティ違反ログテーブル（TASK-021 Phase 2B）
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS security_violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            violation_type TEXT NOT NULL,
            details JSON NOT NULL,
            ip_address TEXT,
            created_at TEXT NOT NULL
        )
    """
    )

    # 管理者操作監査ログテーブル（TASK-021 Phase 3A）
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_email TEXT NOT NULL,
            action_type TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            action_details JSON,
            before_state JSON,
            after_state JSON,
            ip_address TEXT NOT NULL,
            user_agent TEXT,
            session_id TEXT,
            admin_session_id TEXT,
            created_at TEXT NOT NULL,
            risk_level TEXT DEFAULT 'low',
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT,
            request_id TEXT
        )
    """
    )

    # インデックス作成
    create_indexes(db)


def create_indexes(db):
    """パフォーマンス向上のためのインデックス作成"""

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_access_logs_session_id ON access_logs(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_access_logs_time ON access_logs(access_time)",
        "CREATE INDEX IF NOT EXISTS idx_event_logs_session_id ON event_logs(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_event_logs_type ON event_logs(event_type)",
        "CREATE INDEX IF NOT EXISTS idx_auth_failures_ip ON auth_failures(ip_address)",
        "CREATE INDEX IF NOT EXISTS idx_auth_failures_time ON auth_failures(attempt_time)",
        "CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key)",
        "CREATE INDEX IF NOT EXISTS idx_settings_category ON settings(category)",
        "CREATE INDEX IF NOT EXISTS idx_settings_history_key ON settings_history(setting_key)",
        "CREATE INDEX IF NOT EXISTS idx_settings_history_changed_at ON settings_history(changed_at)",
        "CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email)",
        "CREATE INDEX IF NOT EXISTS idx_session_stats_start_time ON session_stats(start_time)",
        "CREATE INDEX IF NOT EXISTS idx_security_events_user_email ON security_events(user_email)",
        "CREATE INDEX IF NOT EXISTS idx_security_events_event_type ON security_events(event_type)",
        "CREATE INDEX IF NOT EXISTS idx_security_events_occurred_at ON security_events(occurred_at)",
        "CREATE INDEX IF NOT EXISTS idx_otp_tokens_email ON otp_tokens(email)",
        "CREATE INDEX IF NOT EXISTS idx_otp_tokens_expires_at ON otp_tokens(expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_otp_tokens_used ON otp_tokens(used)",
        # 管理者セッション用インデックス（TASK-021 Sub-Phase 1A）
        "CREATE INDEX IF NOT EXISTS idx_admin_sessions_admin_email ON admin_sessions(admin_email)",
        "CREATE INDEX IF NOT EXISTS idx_admin_sessions_created_at ON admin_sessions(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_admin_sessions_last_verified_at ON admin_sessions(last_verified_at)",
        "CREATE INDEX IF NOT EXISTS idx_admin_sessions_is_active ON admin_sessions(is_active)",
        # 管理者操作監査ログ用インデックス（TASK-021 Phase 3A）
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_admin_email ON admin_actions(admin_email)",
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_action_type ON admin_actions(action_type)",
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_resource_type ON admin_actions(resource_type)",
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_created_at ON admin_actions(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_risk_level ON admin_actions(risk_level)",
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_session_id ON admin_actions(admin_session_id)",
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_ip_address ON admin_actions(ip_address)",
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_email_time ON admin_actions(admin_email, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_type_time ON admin_actions(action_type, created_at)",
    ]

    for index_sql in indexes:
        db.execute(index_sql)


def generate_initial_passphrase():
    """初期パスフレーズを安全に生成"""
    import secrets
    import string

    # 32文字の安全なランダムパスフレーズを生成
    chars = string.ascii_letters + string.digits + "_-"
    return "".join(secrets.choice(chars) for _ in range(32))


def insert_initial_data(db):
    """初期データの挿入"""

    # 既存の設定をチェック
    existing_settings = db.execute("SELECT COUNT(*) as count FROM settings").fetchone()

    if existing_settings["count"] == 0:
        # 初期パスフレーズを生成
        initial_passphrase = generate_initial_passphrase()
        print(f"初期パスフレーズが生成されました: {initial_passphrase}")
        print("このパスフレーズを安全に保存し、初回ログイン後に変更してください。")

        # 初期設定データ
        initial_settings = [
            (
                "shared_passphrase",
                initial_passphrase,
                "string",
                "事前共有パスフレーズ（32-128文字、0-9a-zA-Z_-のみ）",
                "auth",
                True,
            ),
            ("publish_start", None, "datetime", "公開開始日時", "publish", False),
            ("publish_end", None, "datetime", "公開終了日時", "publish", False),
            (
                "system_status",
                "active",
                "string",
                "システム状態（active/unpublished）",
                "system",
                False,
            ),
            ("session_timeout", "259200", "integer", "セッション有効期限（秒）", "auth", False),
            ("max_login_attempts", "5", "integer", "最大ログイン試行回数", "security", False),
            ("lockout_duration", "1800", "integer", "ロックアウト時間（秒）", "security", False),
            ("force_logout_after", "0", "integer", "強制ログアウト実行時刻", "system", False),
            ("mail_otp_expiry", "600", "integer", "OTP有効期限（秒）", "mail", False),
            ("analytics_retention_days", "90", "integer", "ログ保持期間（日）", "system", False),
            (
                "author_name",
                "Default_Author",
                "string",
                "ウォーターマーク表示用著作者名",
                "watermark",
                False,
            ),
            (
                "mobile_breakpoint",
                "480",
                "integer",
                "モバイル判定ブレークポイント（px）",
                "responsive",
                False,
            ),
            (
                "tablet_breakpoint",
                "768",
                "integer",
                "タブレット判定ブレークポイント（px）",
                "responsive",
                False,
            ),
            (
                "enable_touch_optimizations",
                "true",
                "boolean",
                "タッチ操作最適化有効",
                "responsive",
                False,
            ),
            (
                "max_concurrent_sessions",
                "100",
                "integer",
                "同時接続数制限（警告閾値）",
                "security",
                False,
            ),
            (
                "session_limit_enabled",
                "true",
                "boolean",
                "セッション数制限有効化",
                "security",
                False,
            ),
            # 管理者セッション用セキュリティ設定（TASK-021 Sub-Phase 1A）
            (
                "admin_session_timeout",
                "1800",
                "integer",
                "管理者セッション有効期限（秒）",
                "security",
                False,
            ),
            (
                "admin_session_verification_interval",
                "300",
                "integer",
                "セッション再検証間隔（秒）",
                "security",
                False,
            ),
            (
                "admin_session_ip_binding",
                "true",
                "boolean",
                "IPアドレス固定有効化",
                "security",
                False,
            ),
        ]

        for setting in initial_settings:
            db.execute(
                """
                INSERT INTO settings (key, value, value_type, description, category, is_sensitive)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                setting,
            )

        print("Initial settings data inserted.")

    # 既存の管理者をチェック
    existing_admins = db.execute("SELECT COUNT(*) as count FROM admin_users").fetchone()

    if existing_admins["count"] == 0:
        # .envからADMIN_EMAILを取得して初期管理者を追加
        import os

        admin_email = os.getenv("ADMIN_EMAIL")
        if admin_email:
            db.execute(
                """
                INSERT INTO admin_users (email, added_by, is_active)
                VALUES (?, ?, ?)
            """,
                (admin_email, "system", True),
            )
            print(f"Initial admin user created: {admin_email}")
        else:
            print("Warning: ADMIN_EMAIL not found in environment variables")


def get_setting(db, key, default=None):
    """設定値を取得"""
    db.row_factory = sqlite3.Row
    row = db.execute(
        "SELECT value, value_type FROM settings WHERE key = ?", (key,)
    ).fetchone()
    if not row:
        return default

    value = row["value"]
    value_type = row["value_type"]

    # 型変換
    if value is None:
        return default
    elif value_type == "integer":
        return int(value)
    elif value_type == "boolean":
        return value.lower() in ("true", "1", "yes")
    elif value_type == "json":
        import json

        return json.loads(value)
    else:
        return value


def set_setting(db, key, value, updated_by="system"):
    """設定値を更新または作成"""
    # 現在の値を取得（履歴用）
    db.row_factory = sqlite3.Row
    current_row = db.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    old_value = current_row["value"] if current_row else None

    if current_row:
        # 既存設定の更新
        db.execute(
            """
            UPDATE settings 
            SET value = ?, updated_at = ?, updated_by = ?
            WHERE key = ?
        """,
            (str(value), get_app_datetime_string(), updated_by, key),
        )
    else:
        # 新規設定の追加
        now_str = get_app_datetime_string()
        db.execute(
            """
            INSERT INTO settings (key, value, value_type, description, category, created_at, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                key,
                str(value),
                "string",
                f"動的設定: {key}",
                "session",
                now_str,
                now_str,
                updated_by,
            ),
        )

    # 履歴に記録
    db.execute(
        """
        INSERT INTO settings_history (setting_key, old_value, new_value, changed_by)
        VALUES (?, ?, ?, ?)
    """,
        (key, old_value, str(value), updated_by),
    )


def log_access(
    db,
    session_id,
    email_hash,
    ip_address,
    user_agent,
    endpoint,
    method,
    status_code,
    device_type=None,
    screen_resolution=None,
):
    """アクセスログを記録"""
    db.execute(
        """
        INSERT INTO access_logs (session_id, email_hash, ip_address, user_agent, device_type, screen_resolution, endpoint, method, status_code, access_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            session_id,
            email_hash,
            ip_address,
            user_agent,
            device_type,
            screen_resolution,
            endpoint,
            method,
            status_code,
            get_app_datetime_string(),
        ),
    )


def log_event(
    db, session_id, email_hash, event_type, event_data, ip_address, device_info=None
):
    """イベントログを記録"""
    import json

    db.execute(
        """
        INSERT INTO event_logs (session_id, email_hash, event_type, event_data, timestamp, ip_address, device_info, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            session_id,
            email_hash,
            event_type,
            json.dumps(event_data),
            int(get_app_now().timestamp()),
            ip_address,
            json.dumps(device_info) if device_info else None,
            get_app_datetime_string(),
        ),
    )


def log_auth_failure(
    db, ip_address, failure_type, email_attempted=None, device_type=None
):
    """認証失敗ログを記録"""
    db.execute(
        """
        INSERT INTO auth_failures (ip_address, failure_type, email_attempted, device_type, attempt_time)
        VALUES (?, ?, ?, ?, ?)
    """,
        (
            ip_address,
            failure_type,
            email_attempted,
            device_type,
            get_app_datetime_string(),
        ),
    )


def log_security_event(
    db,
    user_email,
    event_type,
    event_details,
    risk_level="low",
    ip_address=None,
    user_agent=None,
    pdf_file_path=None,
    session_id=None,
):
    """セキュリティイベントログを記録"""
    import json

    # リスクレベルの検証
    valid_risk_levels = ["low", "medium", "high"]
    if risk_level not in valid_risk_levels:
        risk_level = "low"

    # イベントタイプの検証
    valid_event_types = [
        "pdf_view",
        "download_attempt",
        "print_attempt",
        "direct_access",
        "devtools_open",
        "unauthorized_action",
        "page_leave",
        "screenshot_attempt",
        "copy_attempt",
        "admin_operation",
    ]
    if event_type not in valid_event_types:
        event_type = "unauthorized_action"
        risk_level = "high"

    db.execute(
        """
        INSERT INTO security_events 
        (user_email, event_type, event_details, risk_level, ip_address, user_agent, occurred_at, pdf_file_path, session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            user_email,
            event_type,
            json.dumps(event_details) if event_details else None,
            risk_level,
            ip_address,
            user_agent,
            get_app_datetime_string(),
            pdf_file_path,
            session_id,
        ),
    )


def get_security_events(
    db,
    user_email=None,
    event_type=None,
    risk_level=None,
    start_date=None,
    end_date=None,
    limit=50,
    offset=0,
):
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

    where_clause = (
        " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    )

    # クエリ実行
    query = f"""
        SELECT * FROM security_events
        {where_clause}
        ORDER BY occurred_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    events = db.execute(query, params).fetchall()

    # 総件数も取得
    count_query = f"SELECT COUNT(*) as total FROM security_events{where_clause}"
    count_params = params[:-2]  # LIMIT, OFFSETを除く
    total = db.execute(count_query, count_params).fetchone()["total"]

    return {
        "events": [dict(event) for event in events],
        "total": total,
        "has_more": total > offset + len(events),
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

    where_clause = (
        " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    )

    # リスクレベル別統計
    risk_stats = db.execute(
        f"""
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
    """,
        params,
    ).fetchall()

    # イベントタイプ別統計
    event_stats = db.execute(
        f"""
        SELECT event_type, COUNT(*) as count
        FROM security_events
        {where_clause}
        GROUP BY event_type
        ORDER BY count DESC
    """,
        params,
    ).fetchall()

    # 総件数
    total = db.execute(
        f"""
        SELECT COUNT(*) as total FROM security_events
        {where_clause}
    """,
        params,
    ).fetchone()["total"]

    return {
        "total": total,
        "risk_levels": {row["risk_level"]: row["count"] for row in risk_stats},
        "event_types": {row["event_type"]: row["count"] for row in event_stats},
    }


def get_access_logs(db, filters=None, page=1, limit=20):
    """アクセスログを取得（フィルタ・ページネーション対応）"""
    where_conditions = []
    params = []

    if filters:
        if filters.get("user_email"):
            where_conditions.append("user_email LIKE ?")
            params.append(f"%{filters['user_email']}%")

        if filters.get("ip_address"):
            where_conditions.append("ip_address LIKE ?")
            params.append(f"%{filters['ip_address']}%")

        if filters.get("start_date"):
            where_conditions.append("access_time >= ?")
            params.append(f"{filters['start_date']} 00:00:00")

        if filters.get("end_date"):
            where_conditions.append("access_time <= ?")
            params.append(f"{filters['end_date']} 23:59:59")

        if filters.get("endpoint"):
            where_conditions.append("endpoint LIKE ?")
            params.append(f"%{filters['endpoint']}%")

    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

    # 総件数を取得
    total_query = f"SELECT COUNT(*) as total FROM access_logs {where_clause}"
    total = db.execute(total_query, params).fetchone()["total"]

    # ページネーション計算
    offset = (page - 1) * limit
    has_more = total > offset + limit

    # ログを取得
    logs_query = f"""
        SELECT 
            session_id,
            email_hash,
            user_email,
            ip_address,
            user_agent,
            endpoint,
            method,
            status_code,
            access_time,
            duration_seconds,
            pdf_file_path
        FROM access_logs 
        {where_clause}
        ORDER BY access_time DESC
        LIMIT ? OFFSET ?
    """

    logs = db.execute(logs_query, params + [limit, offset]).fetchall()

    return {
        "logs": [dict(log) for log in logs],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_more": has_more,
        },
    }


def get_access_logs_stats(db, filters=None):
    """アクセスログの統計情報を取得"""
    where_conditions = []
    params = []

    if filters:
        if filters.get("start_date"):
            where_conditions.append("access_time >= ?")
            params.append(f"{filters['start_date']} 00:00:00")

        if filters.get("end_date"):
            where_conditions.append("access_time <= ?")
            params.append(f"{filters['end_date']} 23:59:59")

    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

    # エンドポイント別統計
    endpoint_stats = db.execute(
        f"""
        SELECT endpoint, COUNT(*) as count
        FROM access_logs
        {where_clause}
        GROUP BY endpoint
        ORDER BY count DESC
        LIMIT 10
    """,
        params,
    ).fetchall()

    # ステータスコード別統計
    status_stats = db.execute(
        f"""
        SELECT status_code, COUNT(*) as count
        FROM access_logs
        {where_clause}
        GROUP BY status_code
        ORDER BY count DESC  
    """,
        params,
    ).fetchall()

    # メソッド別統計
    method_stats = db.execute(
        f"""
        SELECT method, COUNT(*) as count
        FROM access_logs
        {where_clause}
        GROUP BY method
        ORDER BY count DESC
    """,
        params,
    ).fetchall()

    # 総件数
    total = db.execute(
        f"""
        SELECT COUNT(*) as total FROM access_logs
        {where_clause}
    """,
        params,
    ).fetchone()["total"]

    return {
        "total": total,
        "endpoints": {row["endpoint"]: row["count"] for row in endpoint_stats},
        "status_codes": {str(row["status_code"]): row["count"] for row in status_stats},
        "methods": {row["method"]: row["count"] for row in method_stats},
    }


# 管理者権限システム関数群


def is_admin(email):
    """
    メールアドレスが有効な管理者かチェック

    Args:
        email: チェック対象のメールアドレス

    Returns:
        bool: 有効な管理者の場合True
    """
    if not email:
        return False

    from database import get_db

    with get_db() as db:
        db.row_factory = sqlite3.Row
        result = db.execute(
            """
            SELECT id FROM admin_users 
            WHERE email = ? AND is_active = TRUE
        """,
            (email,),
        ).fetchone()

        return result is not None


def add_admin_user(email, added_by):
    """
    新規管理者を追加

    Args:
        email: 追加する管理者のメールアドレス
        added_by: 追加操作を行った管理者のメールアドレス

    Returns:
        bool: 追加に成功した場合True
    """
    if not email or not added_by:
        print(f"add_admin_user: Invalid params - email={email}, added_by={added_by}")
        return False

    from database import get_db

    with get_db() as db:
        db.row_factory = sqlite3.Row

        # 既存チェック
        existing = db.execute(
            """
            SELECT id FROM admin_users WHERE email = ?
        """,
            (email,),
        ).fetchone()

        if existing:
            print(f"add_admin_user: User already exists - {email}")
            return False

        # 管理者数上限チェック（最大6人）
        current_count = db.execute(
            """
            SELECT COUNT(*) as count FROM admin_users WHERE is_active = TRUE
        """,
            (),
        ).fetchone()["count"]

        print(f"add_admin_user: Current admin count = {current_count}")

        if current_count >= 6:
            print(f"add_admin_user: Admin limit reached - {current_count}")
            return False

        try:
            # 新規管理者追加
            insert_with_app_timestamp(
                db,
                "admin_users",
                ["email", "added_by", "is_active"],
                [email, added_by, True],
                timestamp_columns=["added_at"],
            )

            # 操作ログ記録
            log_admin_operation(
                "add_admin", email, added_by, {"new_admin_email": email}
            )

            print(f"add_admin_user: Successfully added {email}")
            return True

        except sqlite3.Error as e:
            print(f"add_admin_user: Database error - {e}")
            return False


def get_admin_users():
    """
    管理者一覧を取得

    Returns:
        list: 管理者情報のリスト
    """
    from database import get_db

    with get_db() as db:
        db.row_factory = sqlite3.Row

        admins = db.execute(
            """
            SELECT id, email, added_by, added_at, is_active
            FROM admin_users
            ORDER BY added_at ASC
        """
        ).fetchall()

        return [dict(admin) for admin in admins]


def update_admin_status(admin_id, is_active):
    """
    管理者のアクティブ状態を更新

    Args:
        admin_id: 管理者ID
        is_active: アクティブ状態（True/False）

    Returns:
        bool: 更新に成功した場合True
    """
    from database import get_db

    with get_db() as db:
        db.row_factory = sqlite3.Row

        # 現在の管理者情報を取得
        admin = db.execute(
            """
            SELECT email, is_active FROM admin_users WHERE id = ?
        """,
            (admin_id,),
        ).fetchone()

        if not admin:
            return False

        # 最後の管理者を無効化しようとしていないかチェック
        if not is_active:
            active_count = db.execute(
                """
                SELECT COUNT(*) as count FROM admin_users 
                WHERE is_active = TRUE AND id != ?
            """,
                (admin_id,),
            ).fetchone()["count"]

            if active_count == 0:
                return False  # 最後の管理者は無効化できない

        try:
            # ステータス更新
            update_with_app_timestamp(
                db,
                "admin_users",
                ["is_active"],
                [is_active],
                "id = ?",
                [admin_id],
                timestamp_columns=["updated_at"],
            )

            # 操作ログ記録
            operation = "activate_admin" if is_active else "deactivate_admin"
            log_admin_operation(
                operation,
                admin["email"],
                "system",
                {"admin_id": admin_id, "new_status": is_active},
            )

            db.commit()
            return True

        except sqlite3.Error:
            return False


def delete_admin_user(admin_id, permanent=False):
    """
    管理者を削除（論理削除または物理削除）

    Args:
        admin_id: 管理者ID
        permanent: 物理削除する場合True

    Returns:
        bool: 削除に成功した場合True
    """
    from database import get_db

    with get_db() as db:
        db.row_factory = sqlite3.Row

        # 現在の管理者情報を取得
        admin = db.execute(
            """
            SELECT email, is_active FROM admin_users WHERE id = ?
        """,
            (admin_id,),
        ).fetchone()

        if not admin:
            return False

        # アクティブな管理者が1人だけの場合は削除不可
        active_admins = db.execute(
            """
            SELECT COUNT(*) as count FROM admin_users WHERE is_active = TRUE
        """
        ).fetchone()["count"]

        if active_admins == 1 and admin["is_active"]:
            return False  # 最後の管理者は削除できない

        try:
            if permanent:
                # 物理削除
                db.execute("DELETE FROM admin_users WHERE id = ?", (admin_id,))
                operation = "delete_admin_permanent"
            else:
                # 論理削除（無効化）
                update_with_app_timestamp(
                    db,
                    "admin_users",
                    ["is_active"],
                    [False],
                    "id = ?",
                    [admin_id],
                    timestamp_columns=["updated_at"],
                )
                operation = "delete_admin_logical"

            # 操作ログ記録
            log_admin_operation(
                operation,
                admin["email"],
                "system",
                {"admin_id": admin_id, "permanent": permanent},
            )

            db.commit()
            return True

        except sqlite3.Error:
            return False


def log_admin_operation(operation, target_email, operator_email, details=None):
    """
    管理者操作ログの記録

    Args:
        operation: 操作種別
        target_email: 操作対象の管理者メール
        operator_email: 操作者のメール
        details: 詳細情報（dict）
    """
    if details is None:
        details = {}

    # セキュリティイベントとして記録
    event_details = {
        "operation": operation,
        "target_email": target_email,
        "operator_email": operator_email,
        "timestamp": get_app_datetime_string(),
        **details,
    }

    from database import get_db

    with get_db() as db:
        try:
            log_security_event(
                db,
                user_email=operator_email,
                event_type="admin_operation",
                event_details=event_details,
                risk_level="medium",
            )
        except sqlite3.Error:
            # security_eventsテーブルが存在しない場合はログをスキップ
            pass


# 管理者セッション管理関数群（TASK-021 Sub-Phase 1A）


def create_admin_session(
    admin_email, session_id, ip_address, user_agent, security_flags=None, conn=None
):
    """
    管理者セッションを作成

    Args:
        admin_email: 管理者メールアドレス
        session_id: セッションID
        ip_address: IPアドレス
        user_agent: ユーザーエージェント
        security_flags: セキュリティフラグ（dict）
        conn: 既存のデータベース接続（Noneの場合は新しい接続を作成）

    Returns:
        bool: 作成に成功した場合True
    """
    import json
    import secrets

    if not admin_email or not session_id:
        return False

    from database import get_db

    try:
        # 検証トークン生成
        verification_token = secrets.token_urlsafe(32)

        # セキュリティフラグのJSON化
        flags_json = json.dumps(security_flags) if security_flags else None

        # 現在時刻
        current_time = get_app_datetime_string()

        if conn:
            # 既存の接続を使用（トランザクションは呼び出し側で管理）
            conn.execute(
                """
                INSERT INTO admin_sessions 
                (session_id, admin_email, created_at, last_verified_at, ip_address, 
                 user_agent, is_active, security_flags, verification_token)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    admin_email,
                    current_time,
                    current_time,
                    ip_address,
                    user_agent,
                    True,
                    flags_json,
                    verification_token,
                ),
            )
            return True
        else:
            # 新しい接続を作成（独立したトランザクション）
            with get_db() as db:
                db.execute(
                    """
                    INSERT INTO admin_sessions 
                    (session_id, admin_email, created_at, last_verified_at, ip_address, 
                     user_agent, is_active, security_flags, verification_token)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        admin_email,
                        current_time,
                        current_time,
                        ip_address,
                        user_agent,
                        True,
                        flags_json,
                        verification_token,
                    ),
                )
                return True

    except sqlite3.Error as e:
        print(f"create_admin_session error: {e}")
        return False


def verify_admin_session(session_id, current_ip=None, current_ua=None):
    """
    管理者セッションを検証

    Args:
        session_id: セッションID
        current_ip: 現在のIPアドレス（検証用）
        current_ua: 現在のユーザーエージェント（検証用）

    Returns:
        dict: セッションデータ（検証失敗時はNone）
    """
    import json

    if not session_id:
        return None

    from database import get_db

    try:
        with get_db() as db:
            db.row_factory = sqlite3.Row

            session = db.execute(
                """
                SELECT * FROM admin_sessions 
                WHERE session_id = ? AND is_active = TRUE
                """,
                (session_id,),
            ).fetchone()

            if not session:
                return None

            # セキュリティフラグチェック
            security_flags = {}
            if session["security_flags"]:
                try:
                    security_flags = json.loads(session["security_flags"])
                except json.JSONDecodeError:
                    security_flags = {}

            # IPアドレス検証（設定有効時）
            if security_flags.get("ip_binding_enabled", False) and current_ip:
                if session["ip_address"] != current_ip:
                    print(
                        f"Admin session IP mismatch: expected {session['ip_address']}, got {current_ip}"
                    )
                    return None

            # ユーザーエージェント検証（設定有効時）
            if security_flags.get("ua_verification_enabled", False) and current_ua:
                if session["user_agent"] != current_ua:
                    print("Admin session UA mismatch")
                    return None

            return dict(session)

    except sqlite3.Error as e:
        print(f"verify_admin_session error: {e}")
        return None


def update_admin_session_verification(session_id):
    """
    管理者セッションの検証時刻を更新

    Args:
        session_id: セッションID

    Returns:
        bool: 更新に成功した場合True
    """
    if not session_id:
        return False

    from database import get_db

    try:
        with get_db() as db:
            result = db.execute(
                """
                UPDATE admin_sessions 
                SET last_verified_at = ?
                WHERE session_id = ? AND is_active = TRUE
                """,
                (get_app_datetime_string(), session_id),
            )

            db.commit()
            return result.rowcount > 0

    except sqlite3.Error as e:
        print(f"update_admin_session_verification error: {e}")
        return False


def delete_admin_session(session_id):
    """
    管理者セッションを削除

    Args:
        session_id: セッションID

    Returns:
        bool: 削除に成功した場合True
    """
    if not session_id:
        return False

    from database import get_db

    try:
        with get_db() as db:
            result = db.execute(
                """
                DELETE FROM admin_sessions WHERE session_id = ?
                """,
                (session_id,),
            )

            db.commit()
            return result.rowcount > 0

    except sqlite3.Error as e:
        print(f"delete_admin_session error: {e}")
        return False


def get_admin_session_info(session_id):
    """
    管理者セッション情報を取得

    Args:
        session_id: セッションID

    Returns:
        dict: セッション情報（存在しない場合はNone）
    """
    if not session_id:
        return None

    from database import get_db

    try:
        with get_db() as db:
            db.row_factory = sqlite3.Row

            session = db.execute(
                """
                SELECT * FROM admin_sessions WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

            return dict(session) if session else None

    except sqlite3.Error as e:
        print(f"get_admin_session_info error: {e}")
        return None


def cleanup_expired_admin_sessions():
    """
    期限切れの管理者セッションをクリーンアップ

    Returns:
        int: 削除されたセッション数
    """
    from database import get_db

    try:
        with get_db() as db:
            # 管理者セッションタイムアウト取得（デフォルト30分）
            timeout_seconds = get_setting(db, "admin_session_timeout", 1800)

            # 期限切れ時刻を計算
            from config.timezone import get_app_now, add_app_timedelta

            cutoff_time = add_app_timedelta(get_app_now(), seconds=-timeout_seconds)
            cutoff_str = cutoff_time.strftime("%Y-%m-%d %H:%M:%S")

            result = db.execute(
                """
                DELETE FROM admin_sessions 
                WHERE last_verified_at < ?
                """,
                (cutoff_str,),
            )

            deleted_count = result.rowcount
            db.commit()

            if deleted_count > 0:
                print(f"Cleaned up {deleted_count} expired admin sessions")

            return deleted_count

    except sqlite3.Error as e:
        print(f"cleanup_expired_admin_sessions error: {e}")
        return 0


# ===== セッションハイジャック対策機能 (Sub-Phase 1D) =====


def regenerate_admin_session_id(old_session_id, new_session_id):
    """
    管理者セッションIDを再生成（セッション固定攻撃対策）

    Args:
        old_session_id: 古いセッションID
        new_session_id: 新しいセッションID

    Returns:
        bool: 再生成成功時True
    """
    if not old_session_id or not new_session_id:
        return False

    from database import get_db
    import json
    from config.timezone import get_app_datetime_string, get_app_now

    try:
        with get_db() as db:
            db.row_factory = sqlite3.Row

            # 古いセッション情報を取得
            old_session = db.execute(
                "SELECT * FROM admin_sessions WHERE session_id = ? AND is_active = TRUE",
                (old_session_id,),
            ).fetchone()

            if not old_session:
                print(
                    f"regenerate_admin_session_id: old session not found: {old_session_id}"
                )
                return False

            # セキュリティフラグに再生成履歴を追加
            security_flags = {}
            if old_session["security_flags"]:
                try:
                    security_flags = json.loads(old_session["security_flags"])
                except json.JSONDecodeError:
                    security_flags = {}

            security_flags["session_regenerated"] = True
            security_flags["regenerated_at"] = get_app_datetime_string()
            security_flags["old_session_id"] = old_session_id[:8] + "..."  # 部分的にログ

            # 新しい検証トークンを生成
            import secrets

            verification_token = secrets.token_urlsafe(32)

            # 新しいセッションIDでデータ更新
            db.execute(
                """
                UPDATE admin_sessions 
                SET session_id = ?, 
                    last_verified_at = ?, 
                    security_flags = ?,
                    verification_token = ?
                WHERE session_id = ?
                """,
                (
                    new_session_id,
                    get_app_datetime_string(),
                    json.dumps(security_flags),
                    verification_token,
                    old_session_id,
                ),
            )

            db.commit()
            print(
                f"Admin session ID regenerated: {old_session_id[:8]}... -> {new_session_id[:8]}..."
            )
            return True

    except sqlite3.Error as e:
        print(f"regenerate_admin_session_id error: {e}")
        return False


def verify_session_environment(session_id, current_ip, current_ua):
    """
    セッション環境の詳細検証（ハイジャック検出）

    Args:
        session_id: セッションID
        current_ip: 現在のIPアドレス
        current_ua: 現在のユーザーエージェント

    Returns:
        dict: 検証結果 {valid: bool, risk_level: str, warnings: list}
    """
    if not session_id:
        return {
            "valid": False,
            "risk_level": "high",
            "warnings": ["Invalid session ID"],
        }

    from database import get_db
    import json
    from config.timezone import get_app_now, to_app_timezone
    from datetime import timedelta

    try:
        with get_db() as db:
            db.row_factory = sqlite3.Row

            session = db.execute(
                "SELECT * FROM admin_sessions WHERE session_id = ? AND is_active = TRUE",
                (session_id,),
            ).fetchone()

            if not session:
                return {
                    "valid": False,
                    "risk_level": "high",
                    "warnings": ["Session not found"],
                }

            warnings = []
            risk_level = "low"

            # セキュリティフラグ解析
            security_flags = {}
            if session["security_flags"]:
                try:
                    security_flags = json.loads(session["security_flags"])
                except json.JSONDecodeError:
                    security_flags = {}

            # IPアドレス検証
            if session["ip_address"] and current_ip:
                if session["ip_address"] != current_ip:
                    warnings.append(
                        f"IP address changed: {session['ip_address']} -> {current_ip}"
                    )
                    risk_level = (
                        "high"
                        if security_flags.get("ip_binding_enabled", False)
                        else "medium"
                    )

            # ユーザーエージェント検証
            if session["user_agent"] and current_ua:
                # 基本的な一致チェック（完全一致でなく主要部分の一致）
                stored_ua_parts = session["user_agent"].split()[:3]  # 最初の3要素
                current_ua_parts = current_ua.split()[:3]

                if stored_ua_parts != current_ua_parts:
                    warnings.append("User agent changed significantly")
                    risk_level = "medium" if risk_level == "low" else risk_level

            # 検証間隔チェック
            if session["last_verified_at"]:
                try:
                    # アプリケーション統一タイムゾーンで時刻を解析
                    from config.timezone import to_app_timezone
                    from datetime import datetime as dt

                    last_verified = to_app_timezone(
                        dt.fromisoformat(session["last_verified_at"])
                    )
                    verification_interval = int(
                        get_setting(db, "admin_session_verification_interval", 300)
                    )

                    if get_app_now() - last_verified > timedelta(
                        seconds=verification_interval * 2
                    ):
                        warnings.append("Long verification interval detected")
                        risk_level = "medium" if risk_level == "low" else risk_level
                except ValueError:
                    warnings.append("Invalid last verification timestamp")
                    risk_level = "medium" if risk_level == "low" else risk_level

            # 異常なアクセスパターン検出
            created_at = to_app_timezone(dt.fromisoformat(session["created_at"]))
            session_age = get_app_now() - created_at

            # 非常に新しいセッションでの重要操作は要注意
            if session_age < timedelta(minutes=1):
                warnings.append("Very new session detected")
                risk_level = "medium" if risk_level == "low" else risk_level

            # 長時間セッション
            max_session_age = timedelta(hours=8)  # 8時間
            if session_age > max_session_age:
                warnings.append("Long-running session detected")
                risk_level = "medium" if risk_level == "low" else risk_level

            # セッション再生成履歴チェック
            if security_flags.get("session_regenerated", False):
                regenerated_at = security_flags.get("regenerated_at")
                if regenerated_at:
                    try:
                        regen_time = to_app_timezone(dt.fromisoformat(regenerated_at))
                        if get_app_now() - regen_time < timedelta(minutes=5):
                            warnings.append("Recently regenerated session")
                    except ValueError:
                        pass

            # 最終判定
            valid = risk_level != "high"

            result = {
                "valid": valid,
                "risk_level": risk_level,
                "warnings": warnings,
                "session_age_hours": session_age.total_seconds() / 3600,
                "ip_match": session["ip_address"] == current_ip if current_ip else None,
                "has_verification_token": bool(session["verification_token"])
                if session["verification_token"]
                else False,
            }

            return result

    except sqlite3.Error as e:
        print(f"verify_session_environment error: {e}")
        return {
            "valid": False,
            "risk_level": "high",
            "warnings": [f"Database error: {str(e)}"],
        }


def detect_session_anomalies(admin_email, session_id, current_ip, current_ua):
    """
    セッション異常パターンの検出

    Args:
        admin_email: 管理者メールアドレス
        session_id: セッションID
        current_ip: 現在のIPアドレス
        current_ua: 現在のユーザーエージェント

    Returns:
        dict: 異常検出結果 {anomalies_detected: bool, anomaly_types: list, action_required: str}
    """
    if not admin_email or not session_id:
        return {
            "anomalies_detected": True,
            "anomaly_types": ["invalid_input"],
            "action_required": "block",
        }

    from database import get_db
    import json
    from config.timezone import get_app_now, to_app_timezone
    from datetime import timedelta, datetime as dt

    try:
        with get_db() as db:
            db.row_factory = sqlite3.Row

            # 現在のセッション情報
            current_session = db.execute(
                "SELECT * FROM admin_sessions WHERE session_id = ? AND admin_email = ?",
                (session_id, admin_email),
            ).fetchone()

            if not current_session:
                return {
                    "anomalies_detected": True,
                    "anomaly_types": ["session_not_found"],
                    "action_required": "block",
                }

            # 同一管理者の他のアクティブセッション
            other_sessions = db.execute(
                """
                SELECT * FROM admin_sessions 
                WHERE admin_email = ? AND session_id != ? AND is_active = TRUE
                """,
                (admin_email, session_id),
            ).fetchall()

            anomalies = []
            action_required = "allow"

            # 複数同時セッション検出（3セッションまで許可）
            total_sessions = len(other_sessions) + 1

            if total_sessions == 2:
                anomalies.append("multiple_active_sessions")
                action_required = "warn"  # 2セッションは警告のみ
            elif total_sessions == 3:
                anomalies.append("multiple_active_sessions")
                action_required = "warn"  # 3セッションも警告のみ
            elif total_sessions > 3:
                anomalies.append("excessive_multiple_sessions")
                action_required = "block"  # 4セッション以上はブロック

                # 異なるIPからの過剰セッション
                current_ip_sessions = [
                    s for s in other_sessions if s["ip_address"] == current_ip
                ]
                if len(current_ip_sessions) != len(other_sessions):
                    anomalies.append("multiple_ip_excessive_sessions")
                    action_required = "block"

            # 短時間での複数セッション作成
            recent_threshold = get_app_now() - timedelta(minutes=10)
            recent_sessions = []

            for session in [current_session] + list(other_sessions):
                try:
                    created_at = to_app_timezone(
                        dt.fromisoformat(session["created_at"])
                    )
                    if created_at > recent_threshold:
                        recent_sessions.append(session)
                except ValueError:
                    continue

            # 短時間での大量セッション作成（5個以上でブロック）
            if len(recent_sessions) > 4:
                anomalies.append("rapid_session_creation")
                action_required = "block"

            # 地理的に不可能なアクセス（簡易版 - IPの変化を検出）
            if current_ip and current_session["ip_address"]:
                if current_ip != current_session["ip_address"]:
                    # IPが変わった時間間隔をチェック
                    try:
                        last_verified = to_app_timezone(
                            dt.fromisoformat(current_session["last_verified_at"])
                        )
                        time_diff = get_app_now() - last_verified

                        # 5分以内のIP変更は怪しい
                        if time_diff < timedelta(minutes=5):
                            anomalies.append("rapid_ip_change")
                            action_required = "block"
                    except ValueError:
                        pass

            # ユーザーエージェント急変
            if current_ua and current_session["user_agent"]:
                stored_ua = current_session["user_agent"]
                # ブラウザ名の大幅な変更を検出
                stored_browser = (
                    stored_ua.split("/")[0]
                    if "/" in stored_ua
                    else stored_ua.split()[0]
                )
                current_browser = (
                    current_ua.split("/")[0]
                    if "/" in current_ua
                    else current_ua.split()[0]
                )

                if stored_browser != current_browser:
                    anomalies.append("browser_change")
                    action_required = "warn"

            # 夜間アクセス（オプション - 簡易実装）
            current_hour = get_app_now().hour
            if current_hour < 6 or current_hour > 22:  # 22:00-06:00
                # セキュリティフラグで夜間制限が有効かチェック
                security_flags = {}
                if current_session["security_flags"]:
                    try:
                        security_flags = json.loads(current_session["security_flags"])
                    except json.JSONDecodeError:
                        pass

                if security_flags.get("night_access_restricted", False):
                    anomalies.append("night_access_restricted")
                    action_required = "warn"

            result = {
                "anomalies_detected": len(anomalies) > 0,
                "anomaly_types": anomalies,
                "action_required": action_required,
                "active_sessions_count": len(other_sessions) + 1,
                "session_age_minutes": (
                    get_app_now()
                    - to_app_timezone(dt.fromisoformat(current_session["created_at"]))
                ).total_seconds()
                / 60,
            }

            return result

    except sqlite3.Error as e:
        print(f"detect_session_anomalies error: {e}")
        return {
            "anomalies_detected": True,
            "anomaly_types": ["database_error"],
            "action_required": "block",
        }


def admin_complete_logout(admin_email, session_id):
    """
    管理者の完全ログアウト処理

    以下の処理を順序立てて実行する：
    1. admin_sessionsからの削除
    2. session_statsからの削除
    3. 関連OTPトークンの削除（存在する場合）
    4. セキュリティログ記録

    Args:
        admin_email (str): 管理者メールアドレス
        session_id (str): セッションID

    Returns:
        bool: 完全ログアウトが成功した場合True、失敗した場合False
    """
    try:
        from database import get_db

        with get_db() as conn:
            # 1. admin_sessionsテーブルから削除前に存在チェック
            cursor = conn.execute(
                "SELECT admin_email FROM admin_sessions WHERE session_id = ? AND admin_email = ?",
                (session_id, admin_email),
            )
            session_exists = cursor.fetchone()

            if not session_exists:
                print(
                    f"Session not found for admin logout: {session_id} for {admin_email}"
                )
                return False

            # ログ記録用の現在時刻
            from database.timezone_utils import get_current_app_timestamp

            logout_time = get_current_app_timestamp()

            # 2. admin_sessionsテーブルからの削除
            cursor = conn.execute(
                "DELETE FROM admin_sessions WHERE session_id = ? AND admin_email = ?",
                (session_id, admin_email),
            )
            admin_session_deleted = cursor.rowcount > 0

            # 3. session_statsテーブルからの削除
            cursor = conn.execute(
                "DELETE FROM session_stats WHERE session_id = ?", (session_id,)
            )
            session_stats_deleted = cursor.rowcount > 0

            # 4. 関連OTPトークンの削除（テーブルが存在する場合）
            otp_deleted = False
            try:
                cursor = conn.execute(
                    "DELETE FROM otp_tokens WHERE session_id = ?", (session_id,)
                )
                otp_deleted = True
                otp_count = cursor.rowcount
            except sqlite3.OperationalError:
                # otp_tokensテーブルが存在しない場合
                otp_count = 0

            # トランザクション確定
            conn.commit()

            # 5. セキュリティログ記録
            print(
                f"Admin complete logout executed: email={admin_email}, "
                f"session_id={session_id}, time={logout_time}, "
                f"admin_session_deleted={admin_session_deleted}, "
                f"session_stats_deleted={session_stats_deleted}, "
                f"otp_tokens_deleted={otp_count}"
            )

            return admin_session_deleted

    except sqlite3.Error as e:
        print(f"admin_complete_logout database error: {e}")
        return False
    except Exception as e:
        print(f"admin_complete_logout error: {e}")
        return False


def cleanup_related_tokens(session_id):
    """
    セッション関連トークンのクリーンアップ

    Args:
        session_id (str): セッションID

    Returns:
        bool: クリーンアップが成功した場合True
    """
    try:
        from database import get_db

        with get_db() as conn:
            # OTPトークンのクリーンアップ
            try:
                cursor = conn.execute(
                    "DELETE FROM otp_tokens WHERE session_id = ?", (session_id,)
                )
                otp_deleted = cursor.rowcount
            except sqlite3.OperationalError:
                # otp_tokensテーブルが存在しない場合
                otp_deleted = 0

            # 将来的な拡張用：その他のトークンテーブルもここでクリーンアップ
            # TODO: refresh_tokens, api_tokens等のクリーンアップ追加予定

            conn.commit()

            print(
                f"Token cleanup completed for session {session_id}: otp_tokens={otp_deleted}"
            )
            return True

    except sqlite3.Error as e:
        print(f"cleanup_related_tokens database error: {e}")
        return False
    except Exception as e:
        print(f"cleanup_related_tokens error: {e}")
        return False


def invalidate_admin_session_completely(session_id):
    """
    管理者セッションの完全無効化

    admin_complete_logout()の一部機能として、
    セッションIDのみでの完全削除を行う

    Args:
        session_id (str): セッションID

    Returns:
        bool: 無効化が成功した場合True
    """
    try:
        from database import get_db

        with get_db() as conn:
            # 管理者セッションの確認
            cursor = conn.execute(
                "SELECT admin_email FROM admin_sessions WHERE session_id = ?",
                (session_id,),
            )
            session_info = cursor.fetchone()

            if not session_info:
                print(f"Session not found for invalidation: {session_id}")
                return False

            admin_email = session_info[0]

        # admin_complete_logout()を使用して完全ログアウトを実行
        result = admin_complete_logout(admin_email, session_id)

        if result:
            print(
                f"Session {session_id} completely invalidated for admin {admin_email}"
            )

        return result

    except sqlite3.Error as e:
        print(f"invalidate_admin_session_completely database error: {e}")
        return False
    except Exception as e:
        print(f"invalidate_admin_session_completely error: {e}")
        return False


# ===== 管理者監査ログ機能 (Phase 3A) =====


def log_admin_action(
    admin_email,
    action_type,
    resource_type=None,
    resource_id=None,
    action_details=None,
    before_state=None,
    after_state=None,
    ip_address=None,
    user_agent=None,
    session_id=None,
    admin_session_id=None,
    success=True,
    error_message=None,
    request_id=None,
):
    """
    管理者操作をログに記録

    Args:
        admin_email (str): 管理者メールアドレス
        action_type (str): 操作種別
        resource_type (str): リソース種別
        resource_id (str): リソースID
        action_details (dict): 操作詳細
        before_state (dict): 操作前状態
        after_state (dict): 操作後状態
        ip_address (str): IPアドレス
        user_agent (str): ユーザーエージェント
        session_id (str): セッションID
        admin_session_id (str): 管理者セッションID
        success (bool): 操作成功フラグ
        error_message (str): エラーメッセージ
        request_id (str): リクエスト追跡ID

    Returns:
        bool: 記録成功時True
    """
    if not admin_email or not action_type:
        print("log_admin_action: admin_email and action_type are required")
        return False

    try:
        from database import get_db
        import json
        from config.timezone import get_app_datetime_string
        import secrets

        with get_db() as db:
            # リクエストIDが未設定の場合は生成
            if not request_id:
                request_id = secrets.token_urlsafe(16)

            # リスクレベルを自動判定
            risk_level = get_risk_level_for_action(action_type)

            # JSONデータの準備
            action_details_json = json.dumps(action_details) if action_details else None
            before_state_json = json.dumps(before_state) if before_state else None
            after_state_json = json.dumps(after_state) if after_state else None

            # ログ記録
            insert_with_app_timestamp(
                db,
                "admin_actions",
                [
                    "admin_email",
                    "action_type",
                    "resource_type",
                    "resource_id",
                    "action_details",
                    "before_state",
                    "after_state",
                    "ip_address",
                    "user_agent",
                    "session_id",
                    "admin_session_id",
                    "risk_level",
                    "success",
                    "error_message",
                    "request_id",
                ],
                [
                    admin_email,
                    action_type,
                    resource_type,
                    resource_id,
                    action_details_json,
                    before_state_json,
                    after_state_json,
                    ip_address,
                    user_agent,
                    session_id,
                    admin_session_id,
                    risk_level,
                    success,
                    error_message,
                    request_id,
                ],
                timestamp_columns=["created_at"],
            )

            db.commit()

            print(f"Admin action logged: {admin_email} -> {action_type} ({risk_level})")
            return True

    except sqlite3.Error as e:
        print(f"log_admin_action database error: {e}")
        return False
    except Exception as e:
        print(f"log_admin_action error: {e}")
        return False


def get_admin_actions(
    admin_email=None,
    action_type=None,
    resource_type=None,
    start_date=None,
    end_date=None,
    risk_level=None,
    success=None,
    page=1,
    limit=50,
):
    """
    管理者監査ログを取得

    Args:
        admin_email (str): 管理者メールでフィルタ
        action_type (str): 操作種別でフィルタ
        resource_type (str): リソース種別でフィルタ
        start_date (str): 開始日時でフィルタ
        end_date (str): 終了日時でフィルタ
        risk_level (str): リスクレベルでフィルタ
        success (bool): 成功/失敗でフィルタ
        page (int): ページ番号
        limit (int): 1ページあたりの件数

    Returns:
        dict: {actions: list, total: int, page: int, limit: int}
    """
    try:
        from database import get_db

        with get_db() as db:
            db.row_factory = sqlite3.Row

            # WHERE句とパラメータの構築
            where_clauses = []
            params = []

            if admin_email:
                where_clauses.append("admin_email = ?")
                params.append(admin_email)

            if action_type:
                where_clauses.append("action_type = ?")
                params.append(action_type)

            if resource_type:
                where_clauses.append("resource_type = ?")
                params.append(resource_type)

            if start_date:
                where_clauses.append("created_at >= ?")
                params.append(start_date)

            if end_date:
                where_clauses.append("created_at <= ?")
                params.append(end_date)

            if risk_level:
                where_clauses.append("risk_level = ?")
                params.append(risk_level)

            if success is not None:
                where_clauses.append("success = ?")
                params.append(success)

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            # 総件数取得
            count_sql = f"SELECT COUNT(*) FROM admin_actions {where_sql}"
            total = db.execute(count_sql, params).fetchone()[0]

            # データ取得（ページネーション）
            offset = (page - 1) * limit
            data_sql = f"""
                SELECT * FROM admin_actions {where_sql} 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """

            actions = db.execute(data_sql, params + [limit, offset]).fetchall()

            return {
                "actions": [dict(action) for action in actions],
                "total": total,
                "page": page,
                "limit": limit,
            }

    except sqlite3.Error as e:
        print(f"get_admin_actions database error: {e}")
        return {"actions": [], "total": 0, "page": page, "limit": limit}
    except Exception as e:
        print(f"get_admin_actions error: {e}")
        return {"actions": [], "total": 0, "page": page, "limit": limit}


def get_admin_action_stats(period="7d", group_by="action_type"):
    """
    管理者操作統計を取得

    Args:
        period (str): 集計期間 ("7d", "30d", "90d")
        group_by (str): グループ化項目 ("action_type", "risk_level", "admin_email")

    Returns:
        dict: {stats: list, total: int, period: str}
    """
    try:
        from database import get_db
        from config.timezone import get_app_now, add_app_timedelta

        with get_db() as db:
            db.row_factory = sqlite3.Row

            # 期間の計算
            if period == "7d":
                days = -7
            elif period == "30d":
                days = -30
            elif period == "90d":
                days = -90
            else:
                days = -7

            start_time = add_app_timedelta(get_app_now(), days=days)
            start_date_str = start_time.strftime("%Y-%m-%d %H:%M:%S")

            # GROUP BY句の設定
            valid_group_by = [
                "action_type",
                "risk_level",
                "admin_email",
                "resource_type",
            ]
            if group_by not in valid_group_by:
                group_by = "action_type"

            # 統計クエリ
            sql = f"""
                SELECT {group_by}, COUNT(*) as count, 
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                       SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as error_count
                FROM admin_actions 
                WHERE created_at >= ?
                GROUP BY {group_by}
                ORDER BY count DESC
            """

            stats = db.execute(sql, [start_date_str]).fetchall()

            # 総件数
            total_sql = "SELECT COUNT(*) FROM admin_actions WHERE created_at >= ?"
            total = db.execute(total_sql, [start_date_str]).fetchone()[0]

            return {
                "stats": [dict(stat) for stat in stats],
                "total": total,
                "period": period,
                "group_by": group_by,
            }

    except sqlite3.Error as e:
        print(f"get_admin_action_stats database error: {e}")
        return {"stats": [], "total": 0, "period": period, "group_by": group_by}
    except Exception as e:
        print(f"get_admin_action_stats error: {e}")
        return {"stats": [], "total": 0, "period": period, "group_by": group_by}


def get_risk_level_for_action(action_type):
    """
    操作種別からリスクレベルを判定

    Args:
        action_type (str): 操作種別

    Returns:
        str: リスクレベル ("low", "medium", "high", "critical")
    """
    risk_mapping = {
        # 低リスク
        "admin_login": "low",
        "user_view": "low",
        "log_view": "low",
        "setting_view": "low",
        "incident_view": "low",
        # 中リスク
        "user_update": "medium",
        "setting_update": "medium",
        "log_export": "medium",
        "api_call": "medium",
        "session_regenerate": "medium",
        # 高リスク
        "user_delete": "high",
        "permission_change": "high",
        "backup_restore": "high",
        "emergency_stop": "high",
        "incident_resolve": "high",
        "admin_logout": "high",
        # 重要リスク
        "system_maintenance": "critical",
        "security_config": "critical",
        "bulk_operation": "critical",
        "backup_create": "critical",
        "configuration_import": "critical",
        "pdf_security_config": "critical",
    }

    return risk_mapping.get(action_type, "medium")


def delete_admin_actions_before_date(cutoff_date):
    """
    指定日時より古い管理者操作ログを削除（クリーンアップ用）

    Args:
        cutoff_date (str): カットオフ日時

    Returns:
        int: 削除された件数
    """
    try:
        from database import get_db

        with get_db() as db:
            result = db.execute(
                "DELETE FROM admin_actions WHERE created_at < ?",
                [cutoff_date],
            )

            deleted_count = result.rowcount
            db.commit()

            print(f"Deleted {deleted_count} admin action logs before {cutoff_date}")
            return deleted_count

    except sqlite3.Error as e:
        print(f"delete_admin_actions_before_date database error: {e}")
        return 0
    except Exception as e:
        print(f"delete_admin_actions_before_date error: {e}")
        return 0
