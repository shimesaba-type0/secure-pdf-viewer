"""
TASK-021 Phase 2: API セキュリティ強化機能

管理者API保護、CSRF対策、エラーレスポンス統一、セキュリティヘッダー追加などの
セキュリティ強化機能を提供する。
"""

import secrets
import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional
from flask import Response
from database.timezone_utils import get_current_app_timestamp
# get_db_path関数は実行時にapp.pyからインポートする


def generate_csrf_token(session_id: str) -> str:
    """
    セッション固有のCSRFトークンを生成

    Args:
        session_id: セッションID

    Returns:
        str: 生成されたCSRFトークン
    """
    # セキュアなランダムトークン生成
    random_token = secrets.token_urlsafe(32)

    # セッションIDとタイムスタンプを含むハッシュを作成
    timestamp = get_current_app_timestamp()
    token_data = f"{session_id}:{timestamp}:{random_token}"
    token_hash = hashlib.sha256(token_data.encode()).hexdigest()

    # データベースに保存
    try:
        from app import get_db_path
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # 有効期限（1時間後）
        expires_at = (
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            + timedelta(hours=1)
        ).isoformat() + "Z"

        cursor.execute(
            """
            INSERT OR REPLACE INTO csrf_tokens (token, session_id, created_at, expires_at, is_used)
            VALUES (?, ?, ?, ?, ?)
        """,
            (token_hash, session_id, timestamp, expires_at, False),
        )

        conn.commit()
        conn.close()

        return token_hash
    except Exception:
        # エラー時はセキュアなフォールバック
        return secrets.token_urlsafe(32)


def validate_csrf_token(token: str, session_id: str) -> bool:
    """
    CSRFトークンの有効性を検証

    Args:
        token: CSRFトークン
        session_id: セッションID

    Returns:
        bool: トークンが有効な場合True
    """
    if not token or not session_id:
        return False

    try:
        from app import get_db_path
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # トークンとセッションIDで検索
        cursor.execute(
            """
            SELECT token, expires_at, is_used
            FROM csrf_tokens
            WHERE token = ? AND session_id = ?
        """,
            (token, session_id),
        )

        result = cursor.fetchone()

        if not result:
            conn.close()
            return False

        # 有効期限チェック
        current_time = datetime.fromisoformat(
            get_current_app_timestamp().replace("Z", "+00:00")
        )
        expires_time = datetime.fromisoformat(
            result["expires_at"].replace("Z", "+00:00")
        )

        if current_time > expires_time:
            # 期限切れトークンを削除
            cursor.execute("DELETE FROM csrf_tokens WHERE token = ?", (token,))
            conn.commit()
            conn.close()
            return False

        # 使用済みチェック
        if result["is_used"]:
            conn.close()
            return False

        # トークンを使用済みにマーク
        cursor.execute(
            """
            UPDATE csrf_tokens SET is_used = TRUE
            WHERE token = ?
        """,
            (token,),
        )

        conn.commit()
        conn.close()

        return True
    except Exception:
        return False


def create_error_response(
    error_type: str, message: str = None
) -> Tuple[Dict[str, Any], int]:
    """
    統一されたエラーレスポンスを生成

    Args:
        error_type: エラータイプ ('unauthorized', 'forbidden', 'bad_request', etc.)
        message: カスタムエラーメッセージ（オプション）

    Returns:
        tuple: (エラーレスポンス辞書, HTTPステータスコード)
    """
    timestamp = get_current_app_timestamp()

    error_mappings = {
        "unauthorized": {
            "error": "Unauthorized",
            "message": "Authentication required",
            "status": 401,
        },
        "forbidden": {"error": "Forbidden", "message": "Access denied", "status": 403},
        "bad_request": {
            "error": "Bad Request",
            "message": "Invalid request",
            "status": 400,
        },
        "too_many_requests": {
            "error": "Too Many Requests",
            "message": "Rate limit exceeded",
            "status": 429,
        },
    }

    error_info = error_mappings.get(
        error_type,
        {
            "error": "Internal Server Error",
            "message": "An error occurred",
            "status": 500,
        },
    )

    response = {
        "error": error_info["error"],
        "message": message if message else error_info["message"],
        "timestamp": timestamp,
    }

    return response, error_info["status"]


def add_security_headers(response: Response) -> Response:
    """
    レスポンスにセキュリティヘッダーを追加

    Args:
        response: Flaskレスポンスオブジェクト

    Returns:
        Response: セキュリティヘッダーが追加されたレスポンス
    """
    # OWASP推奨のセキュリティヘッダー
    security_headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000",  # 1年間
    }

    for header, value in security_headers.items():
        response.headers[header] = value

    return response


def apply_rate_limit(endpoint: str, user_id: str) -> bool:
    """
    エンドポイント固有のレート制限を適用

    Args:
        endpoint: APIエンドポイント
        user_id: ユーザーID（メールアドレス等）

    Returns:
        bool: リクエストが許可される場合True
    """
    try:
        from app import get_db_path
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # レート制限テーブルが存在しない場合は作成
        cursor.execute(
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

        current_time = get_current_app_timestamp()
        current_datetime = datetime.fromisoformat(current_time.replace("Z", "+00:00"))

        # 時間ウィンドウ（10分間）
        window_start = current_datetime.replace(
            minute=(current_datetime.minute // 10) * 10, second=0, microsecond=0
        )
        window_start_str = window_start.isoformat() + "Z"

        # 現在のウィンドウでのリクエスト数を確認
        cursor.execute(
            """
            SELECT COUNT(*) as request_count
            FROM rate_limits
            WHERE endpoint = ? AND user_id = ? AND window_start = ?
        """,
            (endpoint, user_id, window_start_str),
        )

        result = cursor.fetchone()
        current_count = result[0] if result else 0

        # レート制限値（管理者API: 10リクエスト/10分）
        rate_limit = 10

        if current_count >= rate_limit:
            conn.close()
            return False

        # リクエストを記録
        cursor.execute(
            """
            INSERT OR IGNORE INTO rate_limits
            (endpoint, user_id, request_count, window_start, created_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            (endpoint, user_id, 1, window_start_str, current_time),
        )

        # 古いレコードをクリーンアップ（24時間以前）
        cleanup_time = (current_datetime - timedelta(hours=24)).isoformat() + "Z"
        cursor.execute(
            """
            DELETE FROM rate_limits WHERE created_at < ?
        """,
            (cleanup_time,),
        )

        conn.commit()
        conn.close()

        return True
    except Exception:
        # エラー時は安全側に倒してリクエストを許可
        return True


def cleanup_expired_csrf_tokens():
    """
    期限切れCSRFトークンのクリーンアップ
    """
    try:
        from app import get_db_path
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        current_time = get_current_app_timestamp()

        cursor.execute(
            """
            DELETE FROM csrf_tokens WHERE expires_at < ? OR is_used = TRUE
        """,
            (current_time,),
        )

        conn.commit()
        conn.close()
    except Exception:
        pass  # クリーンアップ失敗は致命的ではない


def get_csrf_token_for_session(session_id: str) -> Optional[str]:
    """
    セッション用の有効なCSRFトークンを取得（存在しない場合は新規生成）

    Args:
        session_id: セッションID

    Returns:
        str: CSRFトークン
    """
    try:
        from app import get_db_path
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 有効なトークンを検索
        current_time = get_current_app_timestamp()
        cursor.execute(
            """
            SELECT token FROM csrf_tokens
            WHERE session_id = ? AND expires_at > ? AND is_used = FALSE
            ORDER BY created_at DESC LIMIT 1
        """,
            (session_id, current_time),
        )

        result = cursor.fetchone()
        conn.close()

        if result:
            return result["token"]
        else:
            # 有効なトークンがない場合は新規生成
            return generate_csrf_token(session_id)
    except Exception:
        # エラー時は新規生成
        return generate_csrf_token(session_id)


def log_security_violation(
    violation_type: str, details: Dict[str, Any], ip_address: str = None
):
    """
    セキュリティ違反をログに記録

    Args:
        violation_type: 違反タイプ
        details: 違反の詳細情報
        ip_address: IPアドレス
    """
    try:
        from app import get_db_path
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # security_violations テーブルが存在しない場合は作成
        cursor.execute(
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

        import json

        details_json = json.dumps(details)
        current_time = get_current_app_timestamp()

        cursor.execute(
            """
            INSERT INTO security_violations (violation_type, details, ip_address, created_at)
            VALUES (?, ?, ?, ?)
        """,
            (violation_type, details_json, ip_address, current_time),
        )

        conn.commit()
        conn.close()
    except Exception:
        pass  # ログ記録失敗は致命的ではない
