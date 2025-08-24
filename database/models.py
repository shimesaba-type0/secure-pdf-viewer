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
    row = db.execute("SELECT value, value_type FROM settings WHERE key = ?", (key,)).fetchone()
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
    current_row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
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


def log_event(db, session_id, email_hash, event_type, event_data, ip_address, device_info=None):
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


def log_auth_failure(db, ip_address, failure_type, email_attempted=None, device_type=None):
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

    where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""

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

    where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""

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
            log_admin_operation("add_admin", email, added_by, {"new_admin_email": email})

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


def create_admin_session(admin_email, session_id, ip_address, user_agent, security_flags=None):
    """
    管理者セッションを作成

    Args:
        admin_email: 管理者メールアドレス
        session_id: セッションID
        ip_address: IPアドレス
        user_agent: ユーザーエージェント
        security_flags: セキュリティフラグ（dict）

    Returns:
        bool: 作成に成功した場合True
    """
    import json
    import secrets

    if not admin_email or not session_id:
        return False

    from database import get_db

    try:
        with get_db() as db:
            # 検証トークン生成
            verification_token = secrets.token_urlsafe(32)

            # セキュリティフラグのJSON化
            flags_json = json.dumps(security_flags) if security_flags else None

            # 現在時刻
            current_time = get_app_datetime_string()

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

            db.commit()
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
                    print(f"Admin session IP mismatch: expected {session['ip_address']}, got {current_ip}")
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
