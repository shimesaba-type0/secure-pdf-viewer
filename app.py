from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    Response,
    send_from_directory,
)
import os
import uuid
from datetime import datetime, timedelta
import pytz
import re
from config.timezone import (
    get_app_now,
    get_app_datetime_string,
    localize_datetime,
    to_app_timezone,
    parse_datetime_local,
    format_for_display,
    get_app_timezone,
    compare_app_datetimes,
    add_app_timedelta,
)
from werkzeug.utils import secure_filename
import sqlite3
import hashlib
import logging
from logging.handlers import RotatingFileHandler

# ロガー設定
logger = logging.getLogger(__name__)
from database.models import (
    get_setting,
    set_setting,
    is_admin,
    create_admin_session,
    verify_admin_session,
    admin_complete_logout,
    log_admin_action,
)
from database.backup import BackupManager
import threading
import time

# グローバル変数
backup_manager = None
from database.utils import RateLimitManager, is_ip_blocked
from auth.passphrase import PassphraseManager
from security.pdf_url_security import PDFURLSecurity
from security.api_security import (
    generate_csrf_token,
    validate_csrf_token,
    create_error_response,
    add_security_headers,
    apply_rate_limit,
    log_security_violation,
    cleanup_expired_csrf_tokens,
)
from config.pdf_security_settings import (
    get_pdf_security_config,
    initialize_pdf_security_settings,
    is_referrer_allowed,
    set_pdf_security_config,
    validate_allowed_domains,
)
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import json
import time
import threading
from queue import Queue, Empty

# タイムゾーン統一管理システムを使用
# JST = pytz.timezone('Asia/Tokyo')  # 廃止: config.timezoneを使用

from functools import wraps


def require_admin_api_access(f):
    """管理者API専用デコレータ（TASK-021 Phase 2A: CSRF保護付き）

    強化されたAPI保護機能：
    1. 管理者セッション検証
    2. レート制限適用
    3. CSRF保護（POSTリクエスト）
    4. セキュリティヘッダー追加
    5. セキュリティ違反ログ記録
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. 基本認証確認
        if not session.get("authenticated"):
            log_security_violation(
                "unauthorized_api_access",
                {"endpoint": request.endpoint, "method": request.method},
                request.remote_addr,
            )
            response_data, status = create_error_response("unauthorized")
            response = jsonify(response_data)
            response.status_code = status
            return add_security_headers(response)

        email = session.get("email")
        session_id = session.get("session_id")

        # 2. 管理者権限確認
        if not email or not is_admin(email):
            log_security_violation(
                "forbidden_api_access",
                {
                    "endpoint": request.endpoint,
                    "email": email,
                    "method": request.method,
                },
                request.remote_addr,
            )
            response_data, status = create_error_response("forbidden")
            response = jsonify(response_data)
            response.status_code = status
            return add_security_headers(response)

        # 3. レート制限確認
        if not apply_rate_limit(request.endpoint, email):
            log_security_violation(
                "rate_limit_exceeded",
                {"endpoint": request.endpoint, "email": email},
                request.remote_addr,
            )
            response_data, status = create_error_response("too_many_requests")
            response = jsonify(response_data)
            response.status_code = status
            return add_security_headers(response)

        # 4. CSRF保護（POST、PUT、DELETE等）
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            csrf_token = request.headers.get("X-CSRF-Token") or request.form.get(
                "csrf_token"
            )
            if not csrf_token or not validate_csrf_token(csrf_token, session_id):
                log_security_violation(
                    "csrf_validation_failed",
                    {
                        "endpoint": request.endpoint,
                        "method": request.method,
                        "email": email,
                    },
                    request.remote_addr,
                )
                response_data, status = create_error_response(
                    "forbidden", "CSRF token validation failed"
                )
                response = jsonify(response_data)
                response.status_code = status
                return add_security_headers(response)

        # 5. 管理者セッション検証（既存のrequire_admin_sessionロジック使用）
        client_ip = request.environ.get("HTTP_X_FORWARDED_FOR", request.remote_addr)
        if client_ip and "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()

        user_agent = request.headers.get("User-Agent", "")
        admin_session_data = verify_admin_session(session_id, client_ip, user_agent)

        if not admin_session_data:
            log_security_violation(
                "invalid_admin_session",
                {
                    "endpoint": request.endpoint,
                    "email": email,
                    "session_id": session_id,
                },
                request.remote_addr,
            )
            response_data, status = create_error_response(
                "unauthorized", "Invalid admin session"
            )
            response = jsonify(response_data)
            response.status_code = status
            return add_security_headers(response)

        # 6. API関数実行
        try:
            result = f(*args, **kwargs)

            # レスポンスがFlask Responseオブジェクトの場合
            if isinstance(result, Response):
                return add_security_headers(result)

            # タプル形式の場合 (data, status_code)
            if isinstance(result, tuple) and len(result) == 2:
                data, status_code = result
                response = jsonify(data)
                response.status_code = status_code
                return add_security_headers(response)

            # 単純なデータの場合
            response = jsonify(result) if not isinstance(result, Response) else result
            return add_security_headers(response)

        except Exception as e:
            log_security_violation(
                "api_execution_error",
                {"endpoint": request.endpoint, "error": str(e), "email": email},
                request.remote_addr,
            )
            response_data, status = create_error_response(
                "bad_request", "API execution failed"
            )
            response = jsonify(response_data)
            response.status_code = status
            return add_security_headers(response)

    return decorated_function


def require_admin_session(f):
    """管理者セッション必須デコレータ（Sub-Phase 1C: 強化版）

    強化された管理者権限チェック：
    1. 基本認証確認
    2. 管理者権限確認
    3. admin_sessionsテーブル確認
    4. セッション環境検証
    5. 検証時刻更新
    """
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. 基本認証確認
        if not session.get("authenticated"):
            return redirect("/auth/login")

        email = session.get("email")
        session_id = session.get("session_id")

        # 2. 管理者権限確認
        if not email or not is_admin(email):
            return render_template("error.html", error="管理者権限が必要です"), 403

        # 3. admin_sessionsテーブル確認とセッション環境検証
        if session_id:
            client_ip = request.environ.get("HTTP_X_FORWARDED_FOR", request.remote_addr)
            if client_ip and "," in client_ip:
                client_ip = client_ip.split(",")[0].strip()

            user_agent = request.headers.get("User-Agent", "")

            # 4. 強化されたセッション検証
            admin_session_data = verify_admin_session(session_id, client_ip, user_agent)

            if not admin_session_data:
                # 管理者セッションが無効な場合
                session.clear()
                return (
                    render_template("error.html", error="管理者セッションが無効です。再度ログインしてください。"),
                    401,
                )

            # Sub-Phase 1D: セッション環境検証と異常検出
            from database.models import (
                verify_session_environment,
                detect_session_anomalies,
            )

            # セッション環境の詳細検証
            env_result = verify_session_environment(session_id, client_ip, user_agent)
            print(
                f"[SECURITY] Session environment check: {env_result['risk_level']} - {env_result['warnings']}"
            )

            if not env_result["valid"]:
                session.clear()
                return (
                    render_template(
                        "error.html",
                        error=f"セッションセキュリティ違反が検出されました: {', '.join(env_result['warnings'])}",
                    ),
                    403,
                )

            # 異常パターン検出
            anomaly_result = detect_session_anomalies(
                email, session_id, client_ip, user_agent
            )
            print(
                f"[SECURITY] Session anomaly check: {anomaly_result['action_required']} - {anomaly_result['anomaly_types']}"
            )

            if anomaly_result["action_required"] == "block":
                session.clear()
                return (
                    render_template(
                        "error.html",
                        error=f"セッション異常が検出されました: {', '.join(anomaly_result['anomaly_types'])}",
                    ),
                    403,
                )
            elif anomaly_result["action_required"] == "warn":
                # 警告レベルの場合は継続するが、ログに記録
                print(
                    f"[WARNING] Session anomaly warning for {email}: {anomaly_result['anomaly_types']}"
                )

            # 5. セッション検証時刻の更新（verify_admin_session内で実行済み）
            # セキュリティログ記録（将来実装）

        else:
            # セッションIDが存在しない場合
            return (
                render_template("error.html", error="有効なセッションがありません。ログインしてください。"),
                401,
            )

        return f(*args, **kwargs)

    return decorated_function


# Sub-Phase 1C: 既存デコレータを強化版に統合
# require_admin_permission は require_admin_session の別名として定義
require_admin_permission = require_admin_session


# ========================================
# TASK-021 Phase 3B: 管理者操作デコレータ機能
# ========================================

# 操作種別とリスクレベルの定義
ADMIN_ACTION_TYPES = {
    # セッション管理
    "admin_login": "管理者ログイン",
    "admin_logout": "管理者ログアウト",
    "session_regenerate": "セッションID再生成",
    # ユーザー管理
    "user_view": "ユーザー情報閲覧",
    "user_create": "ユーザー作成",
    "user_update": "ユーザー情報更新",
    "user_delete": "ユーザー削除",
    "permission_change": "権限変更",
    # システム設定
    "setting_view": "設定値閲覧",
    "setting_update": "設定値変更",
    "security_config": "セキュリティ設定変更",
    "pdf_security_config": "PDF設定変更",
    # ログ・監査
    "log_view": "ログ閲覧",
    "log_export": "ログエクスポート",
    "incident_view": "インシデント閲覧",
    "incident_resolve": "インシデント解決",
    # システム運用
    "backup_create": "バックアップ作成",
    "backup_restore": "バックアップ復元",
    "system_maintenance": "システムメンテナンス",
    "emergency_stop": "緊急停止",
    # API操作
    "api_call": "API呼び出し",
    "bulk_operation": "一括操作",
    "data_export": "データエクスポート",
    "configuration_import": "設定インポート",
}

RESOURCE_TYPES = {
    "user": "ユーザー",
    "session": "セッション",
    "setting": "設定",
    "log": "ログ",
    "backup": "バックアップ",
    "pdf": "PDF文書",
    "api_endpoint": "APIエンドポイント",
    "admin_panel": "管理画面",
    "security_policy": "セキュリティポリシー",
}

RISK_LEVELS = {
    "low": {
        "name": "低リスク",
        "actions": ["admin_login", "user_view", "log_view", "setting_view"],
        "color": "#28a745",
    },
    "medium": {
        "name": "中リスク",
        "actions": ["user_update", "setting_update", "log_export"],
        "color": "#ffc107",
    },
    "high": {
        "name": "高リスク",
        "actions": [
            "user_delete",
            "permission_change",
            "backup_restore",
            "emergency_stop",
        ],
        "color": "#dc3545",
    },
    "critical": {
        "name": "重要リスク",
        "actions": ["system_maintenance", "security_config", "bulk_operation"],
        "color": "#6f42c1",
    },
}


def classify_risk_level(action_type: str) -> str:
    """操作種別からリスクレベルを分類"""
    for risk_level, config in RISK_LEVELS.items():
        if action_type in config["actions"]:
            return risk_level
    return "medium"  # デフォルト


def capture_current_state(resource_type: str, kwargs: dict) -> dict:
    """操作対象の現在状態をキャプチャ"""
    try:
        state = {
            "resource_type": resource_type,
            "captured_at": get_app_datetime_string(),
            "parameters": kwargs,
        }

        # リソース種別に応じた詳細情報取得
        if resource_type == "user":
            user_id = kwargs.get("user_id")
            if user_id:
                state["user_id"] = user_id
                state["user_details"] = f"User ID: {user_id}"

        elif resource_type == "setting":
            setting_key = kwargs.get("setting_key")
            if setting_key:
                try:
                    current_value = get_setting(setting_key)
                    state["setting_key"] = setting_key
                    state["current_value"] = current_value
                except Exception:
                    state["setting_key"] = setting_key
                    state["current_value"] = None

        elif resource_type == "session":
            session_id = kwargs.get("session_id")
            if session_id:
                state["session_id"] = session_id

        return state

    except Exception as e:
        # エラーが発生した場合でも基本情報は返す
        return {
            "resource_type": resource_type,
            "captured_at": get_app_datetime_string(),
            "capture_error": str(e),
            "parameters": kwargs,
        }


def log_admin_operation(
    action_type: str,
    resource_type: str = None,
    capture_state: bool = False,
    risk_level: str = None,
):
    """
    管理者操作を自動記録するデコレータ

    Args:
        action_type: 操作種別
        resource_type: リソース種別
        capture_state: 操作前後の状態をキャプチャするか
        risk_level: リスクレベル（指定しない場合は自動分類）

    使用例:
        @app.route('/admin/api/update-user', methods=['POST'])
        @require_admin_session
        @log_admin_operation("user_update", "user", capture_state=True, risk_level="medium")
        def update_user():
            # ユーザー更新処理
            pass
    """
    from functools import wraps
    import json

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 操作前状態の記録
            before_state = None
            if capture_state and resource_type:
                before_state = capture_current_state(resource_type, kwargs)

            # リクエスト情報の収集
            admin_email = session.get("email")
            ip_address = request.environ.get(
                "HTTP_X_FORWARDED_FOR", request.remote_addr
            )
            if ip_address and "," in ip_address:
                ip_address = ip_address.split(",")[0].strip()

            user_agent = request.headers.get("User-Agent", "")
            session_id = session.get("session_id")
            admin_session_id = session.get("admin_session_id")

            # リスクレベル決定
            final_risk_level = risk_level or classify_risk_level(action_type)

            try:
                # 実際の処理実行
                result = f(*args, **kwargs)

                # 操作後状態の記録
                after_state = None
                if capture_state and resource_type:
                    after_state = capture_current_state(resource_type, kwargs)

                # 成功ログ記録
                log_admin_action(
                    admin_email=admin_email,
                    action_type=action_type,
                    resource_type=resource_type,
                    action_details=json.dumps(
                        {"args": list(args), "kwargs": kwargs}, ensure_ascii=False
                    ),
                    before_state=json.dumps(before_state, ensure_ascii=False)
                    if before_state
                    else None,
                    after_state=json.dumps(after_state, ensure_ascii=False)
                    if after_state
                    else None,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    session_id=session_id,
                    admin_session_id=admin_session_id,
                    risk_level=final_risk_level,
                    success=True,
                )

                print(
                    f"[AUDIT] Admin action logged: {admin_email} - {action_type} ({final_risk_level}) - SUCCESS"
                )

                return result

            except Exception as e:
                # エラーログ記録
                log_admin_action(
                    admin_email=admin_email,
                    action_type=action_type,
                    resource_type=resource_type,
                    action_details=json.dumps(
                        {"args": list(args), "kwargs": kwargs}, ensure_ascii=False
                    ),
                    before_state=json.dumps(before_state, ensure_ascii=False)
                    if before_state
                    else None,
                    after_state=None,  # エラーが発生した場合は after_state は記録しない
                    ip_address=ip_address,
                    user_agent=user_agent,
                    session_id=session_id,
                    admin_session_id=admin_session_id,
                    risk_level=final_risk_level,
                    success=False,
                    error_message=str(e),
                )

                print(
                    f"[AUDIT] Admin action logged: {admin_email} - {action_type} ({final_risk_level}) - ERROR: {str(e)}"
                )

                # 元の例外を再発生
                raise

        return decorated_function

    return decorator


def get_consistent_hash(text):
    """
    一貫したハッシュ値を生成する関数
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get_db_path():
    """
    データベースパスを取得（テスト環境対応）
    """
    return app.config.get("DATABASE", "instance/database.db")


def check_session_limit():
    """
    セッション数制限をチェックする
    Returns:
        dict: {'allowed': bool, 'current_count': int, 'max_limit': int, 'warning': str}
    """
    try:
        # テスト環境では設定されたDATABASEパスを使用
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row

        # 制限機能が有効かチェック
        limit_enabled = get_setting(conn, "session_limit_enabled", True)
        if not limit_enabled:
            conn.close()
            return {
                "allowed": True,
                "current_count": 0,
                "max_limit": 0,
                "warning": None,
            }

        # 現在のアクティブセッション数を取得
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as active_sessions FROM session_stats")
        result = cursor.fetchone()
        current_sessions = result["active_sessions"] if result else 0

        # 制限値を取得
        max_sessions = int(get_setting(conn, "max_concurrent_sessions", 100))

        conn.close()

        # 制限チェック
        if current_sessions >= max_sessions:
            return {
                "allowed": False,
                "current_count": current_sessions,
                "max_limit": max_sessions,
                "warning": f"同時接続数制限に達しています（{current_sessions}/{max_sessions}）",
            }
        elif current_sessions >= max_sessions * 0.8:  # 80%以上で警告
            return {
                "allowed": True,
                "current_count": current_sessions,
                "max_limit": max_sessions,
                "warning": f"同時接続数制限に近づいています（{current_sessions}/{max_sessions}）",
            }
        else:
            return {
                "allowed": True,
                "current_count": current_sessions,
                "max_limit": max_sessions,
                "warning": None,
            }

    except Exception as e:
        print(f"Session limit check error: {e}")
        # エラー時は制限を無効として処理
        return {"allowed": True, "current_count": 0, "max_limit": 0, "warning": None}


def detect_device_type(user_agent):
    """
    User-Agentからデバイスタイプを判定する
    Returns: 'mobile', 'tablet', 'desktop', 'other'
    """
    if not user_agent:
        return "other"

    user_agent = user_agent.lower()

    # モバイルデバイスの判定
    mobile_keywords = [
        "mobile",
        "android",
        "iphone",
        "ipod",
        "blackberry",
        "windows phone",
        "opera mini",
        "fennec",
    ]

    # タブレットの判定（iPadは特別扱い）
    tablet_keywords = ["ipad", "tablet", "kindle", "silk", "playbook"]

    # デスクトップブラウザの判定
    desktop_keywords = ["windows nt", "macintosh", "linux", "x11"]

    # タブレット判定（モバイルより先に判定）
    if any(keyword in user_agent for keyword in tablet_keywords):
        return "tablet"

    # Android タブレットの特別判定（Androidでmobileが含まれていない場合はタブレット）
    if "android" in user_agent and "mobile" not in user_agent:
        return "tablet"

    # モバイル判定
    if any(keyword in user_agent for keyword in mobile_keywords):
        return "mobile"

    # デスクトップ判定
    if any(keyword in user_agent for keyword in desktop_keywords):
        return "desktop"

    return "other"


def is_session_expired():
    """
    セッションが有効期限切れかどうかをチェックする
    Returns:
        bool: True if expired, False if valid
    """
    if not session.get("authenticated"):
        return True

    auth_time_str = session.get("auth_completed_at")
    if not auth_time_str:
        return True

    try:
        # ISO形式の日時文字列をパース（naive datetime想定）
        auth_time = datetime.fromisoformat(auth_time_str)
        # アプリタイムゾーンで解釈
        auth_time = localize_datetime(auth_time)
        now = get_app_now()

        # 72時間（259200秒）の有効期限をチェック
        try:
            from database.models import get_setting as db_get_setting

            conn = sqlite3.connect(get_db_path())
            session_timeout = db_get_setting(
                conn, "session_timeout", 259200
            )  # デフォルト72時間
            conn.close()
        except:
            session_timeout = 259200  # エラー時のフォールバック
        time_diff = (now - auth_time).total_seconds()

        return time_diff > session_timeout
    except (ValueError, TypeError):
        # 日時パースエラーの場合は期限切れとみなす
        return True


def clear_expired_session():
    """
    期限切れセッションをクリアする
    """
    session.clear()
    flash("セッションの有効期限が切れました。再度ログインしてください。", "warning")


def check_session_integrity():
    """
    セッションの整合性をチェックする
    Returns:
        bool: True if valid, False if invalid
    """
    if not session.get("authenticated"):
        print("DEBUG: Session integrity check failed - not authenticated")
        return False

    # 両方の認証ステップが完了しているかチェック
    if not session.get("passphrase_verified") or not session.get("email"):
        print(
            f"DEBUG: Session integrity check failed - passphrase_verified: {session.get('passphrase_verified')}, email: {session.get('email')}"
        )
        return False

    session_id = session.get("session_id")
    if not session_id:
        print("DEBUG: Session integrity check failed - no session_id")
        return False

    # データベースのセッション統計と照合
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # セッションIDがデータベースに存在するかチェック
        cursor.execute(
            "SELECT start_time, email_hash FROM session_stats WHERE session_id = ?",
            (session_id,),
        )
        db_session = cursor.fetchone()

        conn.close()

        if not db_session:
            # データベースにセッション記録がない場合は無効
            print(
                f"DEBUG: Session integrity check failed - no database record for session_id: {session_id}"
            )
            return False

        # 認証完了時刻とデータベース記録の整合性チェック
        auth_time_str = session.get("auth_completed_at")
        if auth_time_str:
            try:
                auth_time = datetime.fromisoformat(auth_time_str)
                # タイムゾーン統一システムを使用してデータベース時刻を変換
                db_start_time_naive = datetime.fromtimestamp(db_session[0])
                db_start_time = localize_datetime(db_start_time_naive)

                # 時刻の差が5分以上の場合は異常とみなす
                time_diff = abs((auth_time - db_start_time).total_seconds())
                if time_diff > 300:  # 5分
                    print(
                        f"DEBUG: Session integrity check failed - time mismatch: {time_diff} seconds"
                    )
                    return False
            except (ValueError, TypeError) as e:
                print(
                    f"DEBUG: Session integrity check failed - time parsing error: {e}"
                )
                return False

        # メールアドレスのハッシュ値をチェック
        email = session.get("email")
        if email:
            expected_hash = get_consistent_hash(email)
            if expected_hash != db_session[1]:
                print(
                    f"DEBUG: Session integrity check failed - email hash mismatch: expected {expected_hash}, got {db_session[1]}"
                )
                return False

        print("DEBUG: Session integrity check passed")
        return True
    except Exception as e:
        print(f"DEBUG: Session integrity check failed - exception: {e}")
        return False


def require_valid_session():
    """
    有効なセッションを要求するデコレーター用の関数
    """
    if is_session_expired():
        clear_expired_session()
        return redirect(url_for("login"))

    # セッション整合性チェック
    if not check_session_integrity():
        session.clear()
        flash("セッションの整合性に問題があります。再度ログインしてください。", "warning")
        return redirect(url_for("login"))

    return None


def _check_pdf_download_prevention(filename, session_id, client_ip):
    """
    PDF直接ダウンロード防止チェック

    Args:
        filename (str): PDFファイル名
        session_id (str): セッションID
        client_ip (str): クライアントIP

    Returns:
        Response: 拒否時のレスポンス、正常時はNone
    """
    # データベースから設定を取得
    pdf_config = get_pdf_security_config()

    # 機能が無効化されている場合はスキップ
    if not pdf_config.get("enabled", True):
        return None

    # Referrerヘッダーチェック
    referer = request.headers.get("Referer", "")
    if not referer:
        error_msg = "Access denied: Invalid referrer (missing)"
        print(
            f"PDF access denied: {error_msg} (IP: {client_ip}, Session: {session_id})"
        )

        if pdf_config.get("log_blocked_attempts", True):
            pdf_security.log_pdf_access(
                filename=filename,
                session_id=session_id,
                ip_address=client_ip,
                success=False,
                error_message="invalid_referrer",
                referer="NONE",
                user_agent=request.headers.get("User-Agent", "NONE"),
            )

        return jsonify({"error": error_msg}), 403

    # 許可されたドメインのチェック（IP範囲対応）
    allowed_domains_raw = pdf_config.get(
        "allowed_referrer_domains", "localhost,127.0.0.1"
    )
    if isinstance(allowed_domains_raw, str):
        allowed_domains = [
            domain.strip()
            for domain in allowed_domains_raw.split(",")
            if domain.strip()
        ]
    else:
        allowed_domains = (
            allowed_domains_raw
            if isinstance(allowed_domains_raw, list)
            else ["localhost", "127.0.0.1"]
        )

    # 現在のホストも許可リストに追加
    if request.host not in allowed_domains:
        allowed_domains.append(request.host)

    if not is_referrer_allowed(referer, allowed_domains):
        error_msg = f"Access denied: Invalid referrer ({referer})"
        print(
            f"PDF access denied: {error_msg} (IP: {client_ip}, Session: {session_id})"
        )

        if pdf_config.get("log_blocked_attempts", True):
            pdf_security.log_pdf_access(
                filename=filename,
                session_id=session_id,
                ip_address=client_ip,
                success=False,
                error_message="invalid_referrer",
                referer=referer,
                user_agent=request.headers.get("User-Agent", "NONE"),
            )

        return jsonify({"error": "Access denied: Invalid referrer"}), 403

    # User-Agentヘッダーチェック（設定で有効な場合のみ）
    if pdf_config.get("user_agent_check_enabled", True):
        user_agent = request.headers.get("User-Agent", "")
        if not user_agent:
            error_msg = "Access denied: Invalid client (missing user agent)"
            print(
                f"PDF access denied: {error_msg} (IP: {client_ip}, Session: {session_id})"
            )

            if pdf_config.get("log_blocked_attempts", True):
                pdf_security.log_pdf_access(
                    filename=filename,
                    session_id=session_id,
                    ip_address=client_ip,
                    success=False,
                    error_message="blocked_user_agent",
                    referer=referer,
                    user_agent="NONE",
                )

            return jsonify({"error": "Access denied: Invalid client"}), 403

        # ブロックされるUser-Agentのチェック
        blocked_agents_raw = pdf_config.get(
            "blocked_user_agents",
            "wget,curl,python-requests,urllib,httpx,aiohttp,Guzzle,cURL-PHP,Java/,Apache-HttpClient,OkHttp,node-fetch,axios,got,HttpClient,.NET Framework,Go-http-client,Ruby,faraday,httparty,reqwest,ureq,libcurl",
        )
        if isinstance(blocked_agents_raw, str):
            blocked_agents = [
                agent.strip()
                for agent in blocked_agents_raw.split(",")
                if agent.strip()
            ]
        else:
            blocked_agents = (
                blocked_agents_raw if isinstance(blocked_agents_raw, list) else []
            )

        for blocked_agent in blocked_agents:
            if blocked_agent.lower() in user_agent.lower():
                error_msg = f"Access denied: Blocked user agent ({user_agent})"
                print(
                    f"PDF access denied: {error_msg} (IP: {client_ip}, Session: {session_id})"
                )

                if pdf_config.get("log_blocked_attempts", True):
                    pdf_security.log_pdf_access(
                        filename=filename,
                        session_id=session_id,
                        ip_address=client_ip,
                        success=False,
                        error_message="blocked_user_agent",
                        referer=referer,
                        user_agent=user_agent,
                    )

                return jsonify({"error": "Access denied: Invalid client"}), 403

    # すべてのチェックをパス
    return None


def invalidate_all_sessions():
    """
    全てのセッションを無効化する独立関数
    Returns:
        dict: 実行結果の詳細情報
    """
    print(
        f"*** SCHEDULED SESSION INVALIDATION EXECUTED AT {get_jst_datetime_string()} ***"
    )
    deleted_sessions = 0
    deleted_otps = 0

    try:
        import sqlite3

        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # 全てのセッション統計データを削除
        cursor.execute("SELECT COUNT(*) FROM session_stats")
        total_sessions = cursor.fetchone()[0]

        cursor.execute("DELETE FROM session_stats")
        deleted_sessions = cursor.rowcount

        # 全てのOTPトークンも削除
        cursor.execute("SELECT COUNT(*) FROM otp_tokens")
        total_otps = cursor.fetchone()[0]

        cursor.execute("DELETE FROM otp_tokens")
        deleted_otps = cursor.rowcount

        conn.commit()
        conn.close()

        print(
            f"Database cleanup completed: Removed {deleted_sessions} sessions and {deleted_otps} OTP tokens"
        )

    except Exception as e:
        error_msg = f"データベースクリーンアップエラー: {e}"
        print(error_msg)

    # リクエストコンテキスト内でのみFlaskセッションをクリア
    try:
        from flask import has_request_context

        if has_request_context():
            session.clear()
            print("Flask session cleared (in request context)")
        else:
            print("Flask session clear skipped (not in request context)")
    except Exception as e:
        print(f"Flask session clear error: {e}")

    # SSE通知は必ず送信（データベースエラーがあっても）
    try:
        # 全クライアントにセッション無効化を通知
        broadcast_sse_event(
            "session_invalidated",
            {
                "message": "予定された時刻になったため、システムからログアウトされました。再度ログインしてください。",
                "deleted_sessions": deleted_sessions,
                "deleted_otps": deleted_otps,
                "redirect_url": "/auth/login",
                "clear_session": True,  # クライアント側でもセッションストレージをクリア
            },
        )
        print(f"SSE session invalidation notification sent to clients")
    except Exception as e:
        print(f"SSE notification error: {e}")

    result = {
        "success": True,
        "deleted_sessions": deleted_sessions,
        "deleted_otps": deleted_otps,
        "timestamp": get_jst_datetime_string(),
        "message": f"全セッション無効化完了: {deleted_sessions}セッション、{deleted_otps}OTPトークンを削除",
    }

    print(f"Session invalidation completed: {result['message']}")
    return result


def cleanup_expired_sessions():
    """
    期限切れセッションの定期クリーンアップ処理
    """
    try:
        import sqlite3

        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # 72時間以上古いセッション統計データを削除
        try:
            session_timeout = get_setting("session_timeout", 259200)  # デフォルト72時間
        except:
            session_timeout = 259200  # エラー時のフォールバック
        cutoff_time = add_app_timedelta(get_app_now(), seconds=-session_timeout)
        cutoff_timestamp = int(cutoff_time.timestamp())

        # 古いセッション統計を削除
        cursor.execute(
            """
            DELETE FROM session_stats 
            WHERE start_time < ?
        """,
            (cutoff_timestamp,),
        )

        deleted_sessions = cursor.rowcount

        # 古いOTPトークンも一緒にクリーンアップ（24時間以上古いもの）
        old_otp_cutoff = add_app_timedelta(get_app_now(), hours=-24)
        cursor.execute(
            """
            DELETE FROM otp_tokens 
            WHERE created_at < ?
        """,
            (old_otp_cutoff.isoformat(),),
        )

        deleted_otps = cursor.rowcount

        conn.commit()
        conn.close()

        if deleted_sessions > 0 or deleted_otps > 0:
            print(
                f"Session cleanup: Removed {deleted_sessions} expired sessions and {deleted_otps} old OTP tokens"
            )

    except Exception as e:
        print(f"Session cleanup error: {e}")


def setup_session_invalidation_scheduler(datetime_str):
    """
    設定時刻セッション無効化のスケジューラーを設定
    Args:
        datetime_str (str): 日時文字列（YYYY-MM-DDTHH:MM形式）
    """
    try:
        # 既存のスケジュールをクリア
        try:
            scheduler.remove_job("session_invalidation")
        except:
            pass  # ジョブが存在しない場合は無視

        # 日時文字列をdatetimeオブジェクトに変換
        target_datetime = datetime.fromisoformat(datetime_str)

        # アプリタイムゾーンに変換
        target_datetime = localize_datetime(target_datetime)

        # 現在時刻と比較して過去の日時でないかチェック（5分の猶予を追加）
        now_app = get_app_now()
        grace_period = timedelta(minutes=5)
        if target_datetime <= add_app_timedelta(now_app, minutes=-5):
            raise ValueError("過去の日時は設定できません")

        # 指定日時に一度だけ実行するスケジュールを追加
        scheduler.add_job(
            func=invalidate_all_sessions,
            trigger="date",
            run_date=target_datetime,
            id="session_invalidation",
            replace_existing=True,
        )

        print(f"Session invalidation scheduled for {target_datetime}")

    except Exception as e:
        print(f"Failed to schedule session invalidation: {e}")
        raise


def get_jst_now():
    """現在のJST時刻を取得"""
    # 旧版本との互換性のためにget_app_now()を使用
    return get_app_now()


def get_jst_datetime_string():
    """現在のJST時刻を文字列で取得（データベース保存用）"""
    # 旧版本との互換性のためにget_app_datetime_string()を使用
    return get_app_datetime_string()
    return get_jst_now().strftime("%Y-%m-%d %H:%M:%S")


def cleanup_security_logs():
    """期限切れのセキュリティログをクリーンアップ"""
    try:
        # 環境変数または設定から保存期間を取得（デフォルト90日）
        retention_days = int(os.environ.get("LOG_RETENTION_DAYS", "90"))

        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # 期限切れのセキュリティイベントログを削除
        cursor.execute(
            """
            DELETE FROM security_events 
            WHERE occurred_at < datetime('now', '-{} days')
        """.format(
                retention_days
            )
        )
        deleted_security_events = cursor.rowcount

        # 期限切れのアクセスログも削除（user_emailが追加されたもの）
        cursor.execute(
            """
            DELETE FROM access_logs 
            WHERE access_time < datetime('now', '-{} days')
        """.format(
                retention_days
            )
        )
        deleted_access_logs = cursor.rowcount

        # 期限切れの認証失敗ログも削除
        cursor.execute(
            """
            DELETE FROM auth_failures 
            WHERE attempt_time < datetime('now', '-{} days')
        """.format(
                retention_days
            )
        )
        deleted_auth_failures = cursor.rowcount

        # 期限切れのイベントログも削除
        cursor.execute(
            """
            DELETE FROM event_logs 
            WHERE created_at < datetime('now', '-{} days')
        """.format(
                retention_days
            )
        )
        deleted_event_logs = cursor.rowcount

        conn.commit()
        conn.close()

        total_deleted = (
            deleted_security_events
            + deleted_access_logs
            + deleted_auth_failures
            + deleted_event_logs
        )

        if total_deleted > 0:
            cleanup_message = (
                f"Log cleanup completed: Removed {deleted_security_events} security events, "
                f"{deleted_access_logs} access logs, {deleted_auth_failures} auth failures, "
                f"{deleted_event_logs} event logs (retention: {retention_days} days)"
            )
            print(cleanup_message)

            # 管理者にSSE通知（オプション）
            try:
                broadcast_sse_event(
                    "log_cleanup",
                    {
                        "message": f"ログクリーンアップ完了: {total_deleted}件のログを削除",
                        "deleted_security_events": deleted_security_events,
                        "deleted_access_logs": deleted_access_logs,
                        "deleted_auth_failures": deleted_auth_failures,
                        "deleted_event_logs": deleted_event_logs,
                        "retention_days": retention_days,
                        "timestamp": get_app_datetime_string(),
                    },
                )
            except Exception as e:
                print(f"SSE notification error during log cleanup: {e}")
        else:
            print(f"Log cleanup: No logs older than {retention_days} days found")

        return {
            "success": True,
            "deleted_security_events": deleted_security_events,
            "deleted_access_logs": deleted_access_logs,
            "deleted_auth_failures": deleted_auth_failures,
            "deleted_event_logs": deleted_event_logs,
            "total_deleted": total_deleted,
            "retention_days": retention_days,
            "timestamp": get_app_datetime_string(),
        }

    except Exception as e:
        error_msg = f"Security log cleanup error: {e}"
        print(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "timestamp": get_app_datetime_string(),
        }


# SSE用のクライアント管理
sse_clients = set()
sse_lock = threading.Lock()


def add_sse_client(client_queue):
    """SSEクライアントを追加"""
    with sse_lock:
        sse_clients.add(client_queue)
        print(f"SSE client connected. Total clients: {len(sse_clients)}")


def remove_sse_client(client_queue):
    """SSEクライアントを削除"""
    with sse_lock:
        sse_clients.discard(client_queue)
        print(f"SSE client disconnected. Total clients: {len(sse_clients)}")


def broadcast_sse_event(event_type, data):
    """全SSEクライアントにイベントを送信"""
    print(f"Broadcasting SSE event '{event_type}' to {len(sse_clients)} clients")
    with sse_lock:
        dead_clients = set()
        for client_queue in sse_clients.copy():
            try:
                client_queue.put(
                    {
                        "event": event_type,
                        "data": data,
                        "timestamp": get_jst_datetime_string(),
                    },
                    timeout=1,
                )
                print(f"  -> Event sent to client")
            except Exception as e:
                print(f"  -> Failed to send to client: {e}")
                dead_clients.add(client_queue)

        # 切断されたクライアントを削除
        for dead_client in dead_clients:
            sse_clients.discard(dead_client)


app = Flask(__name__, static_folder="static")
app.config["SECRET_KEY"] = os.environ.get(
    "FLASK_SECRET_KEY", "dev-secret-key-change-this"
)
app.config["UPLOAD_FOLDER"] = "static/pdfs"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

# ログ設定
if not os.path.exists("logs"):
    os.makedirs("logs")

# ログファイルの設定（ローテーション付き）
file_handler = RotatingFileHandler(
    "logs/app.log", maxBytes=10 * 1024 * 1024, backupCount=5
)
file_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
    )
)
file_handler.setLevel(logging.INFO)
# ルートロガーに設定して全モジュールのログをapp.logに出力
logging.getLogger().addHandler(file_handler)
logging.getLogger().setLevel(logging.INFO)
# Flaskアプリロガーにも設定（既存の互換性維持）
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

# Ensure upload directory exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def setup_initial_admin():
    """初期管理者を設定"""
    try:
        from database.models import add_admin_user, get_admin_users
        from database import init_db

        # データベース初期化
        init_db()

        # 既存の管理者をチェック
        existing_admins = get_admin_users()

        # 環境変数からADMIN_EMAILを取得
        admin_email = os.getenv("ADMIN_EMAIL")

        if admin_email:
            # 指定されたメールアドレスが既に管理者かチェック
            is_existing_admin = any(
                admin["email"] == admin_email for admin in existing_admins
            )

            if not is_existing_admin:
                # 初期管理者を追加
                success = add_admin_user(admin_email, "system")
                if success:
                    logger.info(f"初期管理者を設定しました: {admin_email}")
                    print(f"初期管理者を設定しました: {admin_email}")
                else:
                    logger.error(f"初期管理者の設定に失敗しました: {admin_email}")
            else:
                logger.info(f"管理者は既に設定済みです: {admin_email}")
        else:
            if not existing_admins:
                logger.warning("ADMIN_EMAIL環境変数が設定されていません。管理者が設定されていません。")
                print("Warning: ADMIN_EMAIL環境変数が設定されていません。")

    except Exception as e:
        logger.error(f"初期管理者設定エラー: {str(e)}")
        print(f"初期管理者設定エラー: {str(e)}")


# 初期管理者設定を実行
setup_initial_admin()


# テンプレート用コンテキストプロセッサ
@app.context_processor
def inject_user_context():
    """テンプレートで使用するユーザー情報を注入"""
    email = session.get("email")
    return {"is_admin_user": is_admin(email) if email else False}


# カスタム静的ファイルハンドラー（PDFアクセス制御用）
@app.route("/static/pdfs/<path:filename>")
def blocked_pdf_access(filename):
    """直接PDF静的ファイルアクセスをブロック"""
    return (
        jsonify(
            {
                "error": "Forbidden - 直接PDFアクセスは無効化されています",
                "message": "署名付きURLを使用してアクセスしてください",
                "blocked_file": filename,
            }
        ),
        403,
    )


# Initialize scheduler for auto-unpublish functionality
scheduler = BackgroundScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# セッションクリーンアップを毎時間実行するようにスケジュール
scheduler.add_job(
    func=cleanup_expired_sessions,
    trigger="interval",
    hours=1,
    id="session_cleanup",
    replace_existing=True,
)

# セキュリティログクリーンアップを毎日深夜2時に実行
cleanup_hour = int(os.environ.get("LOG_CLEANUP_HOUR", "2"))  # デフォルト深夜2時
scheduler.add_job(
    func=cleanup_security_logs,
    trigger="cron",
    hour=cleanup_hour,
    minute=0,
    id="security_log_cleanup",
    replace_existing=True,
)
print(f"Security log cleanup scheduled for {cleanup_hour:02d}:00 daily")

# CSRFトークンクリーンアップジョブ（TASK-021 Phase 2A）
scheduler.add_job(
    func=cleanup_expired_csrf_tokens,
    trigger="interval",
    hours=1,
    id="csrf_token_cleanup",
    replace_existing=True,
)
print("CSRF token cleanup scheduled every hour")

# PDF URL Security instance
pdf_security = PDFURLSecurity()


def auto_unpublish_all_pdfs():
    """指定時刻に全てのPDFの公開を停止する"""
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # 全てのPDFを非公開にする
        cursor.execute(
            """
            UPDATE pdf_files 
            SET is_published = FALSE, unpublished_date = ? 
            WHERE is_published = TRUE
        """,
            (get_jst_datetime_string(),),
        )

        # publish_end設定をクリア
        cursor.execute(
            """
            UPDATE settings 
            SET value = NULL, updated_at = ?, updated_by = 'scheduler'
            WHERE key = 'publish_end'
        """,
            (get_app_datetime_string(),),
        )

        conn.commit()
        conn.close()

        print(f"Auto-unpublish completed at {get_app_now()}")

        # SSEで全クライアントに通知
        broadcast_sse_event(
            "pdf_unpublished",
            {
                "message": "公開が自動的に停止されました",
                "reason": "scheduled",
                "timestamp": get_jst_datetime_string(),
            },
        )

    except Exception as e:
        print(f"Auto-unpublish failed: {e}")


def schedule_auto_unpublish(end_datetime):
    """公開終了日時にスケジュールを設定"""
    # 既存のスケジュールをクリア
    try:
        scheduler.remove_job("auto_unpublish")
    except:
        pass  # ジョブが存在しない場合は無視

    # 新しいスケジュールを追加
    scheduler.add_job(
        func=auto_unpublish_all_pdfs,
        trigger="date",
        run_date=end_datetime,
        id="auto_unpublish",
    )
    print(f"Scheduled auto-unpublish for {end_datetime}")


def restore_scheduled_unpublish():
    """アプリ起動時に既存の公開終了設定を復元"""
    try:
        conn = sqlite3.connect(get_db_path())
        publish_end_str = get_setting(conn, "publish_end", None)
        conn.close()

        if publish_end_str:
            publish_end_dt = datetime.fromisoformat(publish_end_str)
            # データベースからの値をアプリタイムゾーンで解釈
            publish_end_dt = localize_datetime(publish_end_dt)

            # 設定時刻がまだ未来の場合のみスケジュールを復元
            if publish_end_dt > get_jst_now():
                schedule_auto_unpublish(publish_end_dt)
            else:
                # 設定時刻が過去の場合は自動停止を実行
                print("Publish end time is in the past, executing auto-unpublish now")
                auto_unpublish_all_pdfs()

    except Exception as e:
        print(f"Failed to restore scheduled unpublish: {e}")


# アプリ起動時にスケジュールを復元
restore_scheduled_unpublish()

# ===== Phase 2: バックアップスケジューリング機能 =====


def execute_scheduled_backup():
    """スケジュール実行されるバックアップ処理"""
    try:
        logger.info("定期バックアップ実行開始")
        backup_manager = BackupManager()

        # バックアップ実行判定
        if not backup_manager.should_run_backup():
            logger.info("バックアップ実行条件を満たしていないため、スキップします")
            return

        # 自動バックアップ実行
        backup_name = backup_manager.create_backup(backup_type="auto")
        logger.info(f"定期バックアップ完了: {backup_name}")

        # 古いバックアップのクリーンアップ実行
        cleanup_count = backup_manager.cleanup_old_backups()
        if cleanup_count > 0:
            logger.info(f"古いバックアップクリーンアップ完了: {cleanup_count}個削除")

    except Exception as e:
        logger.error(f"定期バックアップ実行エラー: {str(e)}")


def setup_backup_schedule():
    """バックアップスケジュールを設定"""
    try:
        backup_manager = BackupManager()
        settings = backup_manager.get_backup_settings()

        # 既存のバックアップジョブを削除
        if scheduler.get_job("scheduled_backup"):
            scheduler.remove_job("scheduled_backup")

        # 自動バックアップが有効な場合のみスケジュール設定
        if settings.get("auto_backup_enabled", False):
            backup_time = settings.get("backup_time", "02:00")
            backup_interval = settings.get("backup_interval", "daily")

            hour, minute = map(int, backup_time.split(":"))

            if backup_interval == "daily":
                # 日次バックアップ
                scheduler.add_job(
                    func=execute_scheduled_backup,
                    trigger="cron",
                    hour=hour,
                    minute=minute,
                    id="scheduled_backup",
                    replace_existing=True,
                )
                logger.info(f"日次バックアップスケジュール設定: 毎日 {backup_time}")

            elif backup_interval == "weekly":
                # 週次バックアップ（月曜日実行）
                scheduler.add_job(
                    func=execute_scheduled_backup,
                    trigger="cron",
                    day_of_week=0,  # 月曜日
                    hour=hour,
                    minute=minute,
                    id="scheduled_backup",
                    replace_existing=True,
                )
                logger.info(f"週次バックアップスケジュール設定: 毎週月曜日 {backup_time}")

            print(f"Backup schedule configured: {backup_interval} at {backup_time}")
        else:
            logger.info("自動バックアップが無効のため、スケジュールは設定されません")

    except Exception as e:
        logger.error(f"バックアップスケジュール設定エラー: {str(e)}")


def refresh_backup_schedule():
    """バックアップスケジュールを再読み込み（設定変更時に呼び出し）"""
    setup_backup_schedule()


# アプリ起動時にバックアップスケジュールを初期化
setup_backup_schedule()


def check_and_handle_expired_publish():
    """フォールバック: アクセス時に公開終了時刻をチェック"""
    try:
        conn = sqlite3.connect(get_db_path())
        publish_end_str = get_setting(conn, "publish_end", None)
        conn.close()

        if publish_end_str:
            publish_end_dt = datetime.fromisoformat(publish_end_str)
            # データベースからの値をアプリタイムゾーンで解釈
            publish_end_dt = localize_datetime(publish_end_dt)

            # 公開終了時刻が過去の場合は自動停止を実行
            if publish_end_dt <= get_jst_now():
                print(
                    f"Detected expired publish end time: {publish_end_dt}, executing auto-unpublish"
                )
                auto_unpublish_all_pdfs()
                return True  # 停止処理を実行した

    except Exception as e:
        print(f"Failed to check expired publish: {e}")

    return False  # 停止処理は実行されなかった


@app.route("/favicon.ico")
def favicon():
    """Favicon handler to prevent 404 errors"""
    return send_from_directory("static", "favicon.ico", mimetype="image/x-icon")


@app.route("/")
def index():
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return redirect(url_for("login"))

    # フォールバック: 公開終了時刻をチェック
    check_and_handle_expired_publish()

    # Get list of uploaded PDF files for viewer
    pdf_files = get_pdf_files()

    # Get published PDF for auto-load
    published_pdf = get_published_pdf()

    # Get current author name setting for watermark and publish end time
    conn = sqlite3.connect("instance/database.db")
    author_name = get_setting(conn, "author_name", "Default_Author")

    # Get publish end datetime setting
    publish_end_str = get_setting(conn, "publish_end", None)
    publish_end_datetime_formatted = None

    if publish_end_str:
        try:
            publish_end_dt = datetime.fromisoformat(publish_end_str)
            # Handle timezone if not present
            if publish_end_dt.tzinfo is None:
                publish_end_dt = localize_datetime(publish_end_dt)

            # Convert to app timezone and format for display
            publish_end_app_tz = to_app_timezone(publish_end_dt)
            publish_end_datetime_formatted = publish_end_app_tz.strftime(
                "%Y年%m月%d日 %H:%M"
            )
        except ValueError:
            publish_end_datetime_formatted = None

    conn.close()

    return render_template(
        "viewer.html",
        pdf_files=pdf_files,
        published_pdf=published_pdf,
        author_name=author_name,
        publish_end_datetime_formatted=publish_end_datetime_formatted,
    )


@app.route("/auth/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # クライアントIPを取得
        client_ip = request.environ.get("HTTP_X_FORWARDED_FOR", request.remote_addr)
        if client_ip and "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()

        # IP制限チェック
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row

        if is_ip_blocked(conn, client_ip):
            conn.close()
            return render_template(
                "login.html", error="IPアドレスが制限されています。しばらく時間をおいてから再試行してください。"
            )

        password = request.form.get("password")

        # レート制限マネージャーを初期化
        rate_limiter = RateLimitManager(conn)

        # パスフレーズ認証を実行
        passphrase_manager = PassphraseManager(conn)

        try:
            if passphrase_manager.verify_passphrase(password):
                # パスフレーズ認証成功時に古いセッション情報を完全にクリア
                session.clear()
                session["passphrase_verified"] = True
                session["login_time"] = get_app_now().isoformat()
                print(f"DEBUG: login - passphrase verified, session cleared and reset")
                conn.close()
                return redirect(url_for("email_input"))
            else:
                # 認証失敗を記録（レート制限チェック）
                device_type = detect_device_type(request.headers.get("User-Agent", ""))
                blocked = rate_limiter.record_auth_failure(
                    ip_address=client_ip,
                    failure_type="passphrase",
                    email_attempted=None,
                    device_type=device_type,
                )

                conn.commit()
                conn.close()

                if blocked:
                    return redirect(url_for("blocked"))
                else:
                    return render_template("login.html", error="パスフレーズが正しくありません")
        except Exception as e:
            conn.close()
            return render_template("login.html", error="認証エラーが発生しました")

    return render_template("login.html")


@app.route("/auth/email", methods=["GET", "POST"])
def email_input():
    # パスフレーズ認証が完了しているかチェック
    if not session.get("passphrase_verified"):
        return redirect(url_for("login"))

    # 既に完全認証済みの場合は整合性をチェック
    # ただし、OTP認証が完了している場合のみ（session_idとauth_completed_atが存在）
    if (
        session.get("authenticated")
        and session.get("session_id")
        and session.get("auth_completed_at")
    ):
        print(
            f"DEBUG: email_input - checking session integrity for session_id: {session.get('session_id')}"
        )
        if check_session_integrity():
            return redirect(url_for("index"))
        else:
            # 整合性に問題がある場合はセッションをクリア
            print(f"DEBUG: email_input - clearing session due to integrity failure")
            session.clear()
            flash("セッションの整合性に問題があります。再度ログインしてください。", "warning")
            return redirect(url_for("login"))
    else:
        print(
            f"DEBUG: email_input - skipping integrity check: authenticated={session.get('authenticated')}, session_id={session.get('session_id')}, auth_completed_at={session.get('auth_completed_at')}"
        )

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        # バリデーション
        if not email:
            return render_template("email_input.html", error="メールアドレスを入力してください")

        # 簡単なメールアドレス形式チェック
        import re

        email_pattern = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
        if not re.match(email_pattern, email):
            return render_template(
                "email_input.html", error="有効なメールアドレスを入力してください", email=email
            )

        try:
            # データベース接続
            conn = sqlite3.connect(get_db_path())
            conn.row_factory = sqlite3.Row

            # OTP生成（6桁）
            import secrets

            otp_code = "".join([str(secrets.randbelow(10)) for _ in range(6)])

            # 有効期限設定（10分後）
            import datetime

            expires_at = add_app_timedelta(get_app_now(), minutes=10)

            # 古いOTPを無効化（同じメールアドレスの未使用OTP）
            conn.execute(
                """
                UPDATE otp_tokens 
                SET used = TRUE, used_at = ? 
                WHERE email = ? AND used = FALSE
            """,
                (get_app_datetime_string(), email),
            )

            # 新しいOTPをデータベースに保存
            conn.execute(
                """
                INSERT INTO otp_tokens (email, otp_code, session_id, ip_address, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    email,
                    otp_code,
                    session.get("session_id", ""),
                    request.remote_addr,
                    expires_at.isoformat(),
                ),
            )

            conn.commit()

            # メール送信
            from mail.email_service import EmailService

            email_service = EmailService()

            if email_service.send_otp_email(email, otp_code):
                # セッションにメールアドレスを保存
                session["email"] = email
                conn.close()
                return redirect(url_for("verify_otp"))
            else:
                conn.close()
                return render_template(
                    "email_input.html",
                    error="メール送信に失敗しました。しばらく時間をおいて再試行してください。",
                    email=email,
                )

        except Exception as e:
            if "conn" in locals():
                conn.close()
            return render_template(
                "email_input.html",
                error="システムエラーが発生しました。しばらく時間をおいて再試行してください。",
                email=email,
            )

    return render_template("email_input.html")


@app.route("/auth/verify-otp", methods=["GET", "POST"])
def verify_otp():
    # パスフレーズ認証とメールアドレスが設定されているかチェック
    if not session.get("passphrase_verified") or not session.get("email"):
        return redirect(url_for("login"))

    # 既に完全認証済みの場合は整合性をチェック
    # ただし、OTP認証が完了している場合のみ（session_idとauth_completed_atが存在）
    if (
        session.get("authenticated")
        and session.get("session_id")
        and session.get("auth_completed_at")
    ):
        if check_session_integrity():
            return redirect(url_for("index"))
        else:
            # 整合性に問題がある場合はセッションをクリア
            session.clear()
            flash("セッションの整合性に問題があります。再度ログインしてください。", "warning")
            return redirect(url_for("login"))

    email = session.get("email")

    if request.method == "POST":
        otp_code = request.form.get("otp_code", "").strip()

        # バリデーション
        if not otp_code:
            return render_template(
                "verify_otp.html", email=email, error="OTPコードを入力してください"
            )

        if len(otp_code) != 6 or not otp_code.isdigit():
            return render_template(
                "verify_otp.html", email=email, error="6桁の数字を入力してください"
            )

        try:
            # クライアントIPを取得
            client_ip = request.environ.get("HTTP_X_FORWARDED_FOR", request.remote_addr)
            if client_ip and "," in client_ip:
                client_ip = client_ip.split(",")[0].strip()

            # データベース接続
            conn = sqlite3.connect(get_db_path())
            conn.row_factory = sqlite3.Row

            # IP制限チェック
            if is_ip_blocked(conn, client_ip):
                conn.close()
                return render_template(
                    "verify_otp.html",
                    email=email,
                    error="IPアドレスが制限されています。しばらく時間をおいてから再試行してください。",
                )

            # レート制限マネージャーを初期化
            rate_limiter = RateLimitManager(conn)

            # 有効なOTPを検索
            otp_record = conn.execute(
                """
                SELECT id, otp_code, expires_at, used 
                FROM otp_tokens 
                WHERE email = ? AND otp_code = ? AND used = FALSE
                ORDER BY created_at DESC
                LIMIT 1
            """,
                (email, otp_code),
            ).fetchone()

            if not otp_record:
                # OTP認証失敗を記録（レート制限チェック）
                device_type = detect_device_type(request.headers.get("User-Agent", ""))
                blocked = rate_limiter.record_auth_failure(
                    ip_address=client_ip,
                    failure_type="otp",
                    email_attempted=email,
                    device_type=device_type,
                )

                conn.commit()
                conn.close()

                if blocked:
                    return redirect(url_for("blocked"))
                else:
                    return render_template(
                        "verify_otp.html",
                        email=email,
                        error="無効なOTPコードです。正しいコードを入力してください。",
                    )

            # 有効期限チェック
            expires_at = datetime.fromisoformat(otp_record["expires_at"])
            now = get_app_now()

            if now > expires_at:
                # 期限切れOTPを無効化
                conn.execute(
                    """
                    UPDATE otp_tokens 
                    SET used = TRUE, used_at = ? 
                    WHERE id = ?
                """,
                    (get_app_datetime_string(), otp_record["id"]),
                )
                conn.commit()
                conn.close()
                return render_template(
                    "verify_otp.html",
                    email=email,
                    error="OTPコードの有効期限が切れています。再送信してください。",
                )

            # OTPを使用済みにマーク
            conn.execute(
                """
                UPDATE otp_tokens 
                SET used = TRUE, used_at = ? 
                WHERE id = ?
            """,
                (get_app_datetime_string(), otp_record["id"]),
            )
            conn.commit()

            # セッション制限チェック（認証完了前）
            session_limit_check = check_session_limit()
            if not session_limit_check["allowed"]:
                conn.close()
                error_message = f"接続数制限に達しています。現在 {session_limit_check['current_count']}/{session_limit_check['max_limit']} セッションが利用中です。しばらく時間をおいてから再度お試しください。"
                return render_template(
                    "verify_otp.html", email=email, error=error_message
                )

            # 認証完了
            session["authenticated"] = True
            session["email"] = email
            session["auth_completed_at"] = get_app_now().isoformat()

            # セッション統計を更新
            session_id = session.get("session_id", str(uuid.uuid4()))
            session["session_id"] = session_id

            # User-Agentからデバイスタイプを判定
            user_agent = request.headers.get("User-Agent", "")
            device_type = detect_device_type(user_agent)

            conn.execute(
                """
                INSERT OR REPLACE INTO session_stats 
                (session_id, email_hash, email_address, start_time, ip_address, device_type, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    session_id,
                    get_consistent_hash(email),
                    email,
                    int(now.timestamp()),
                    request.remote_addr,
                    device_type,
                    get_app_datetime_string(),
                ),
            )

            # 管理者の場合は管理者セッションも作成
            print(f"DEBUG: Checking if {email} is admin: {is_admin(email)}")
            if is_admin(email):
                client_ip = request.environ.get(
                    "HTTP_X_FORWARDED_FOR", request.remote_addr
                )
                if client_ip and "," in client_ip:
                    client_ip = client_ip.split(",")[0].strip()

                print(
                    f"DEBUG: Creating admin session for {email} with session_id {session_id}"
                )
                admin_session_result = create_admin_session(
                    admin_email=email,
                    session_id=session_id,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    security_flags={"login_method": "otp", "device_type": device_type},
                    conn=conn,  # 既存のデータベース接続を渡す
                )
                print(f"DEBUG: Admin session creation result: {admin_session_result}")

                # Phase 3B: 管理者ログイン操作のログ記録
                if admin_session_result and admin_session_result.get("success"):
                    log_admin_action(
                        admin_email=email,
                        action_type="admin_login",
                        resource_type="session",
                        action_details='{"login_method": "otp", "device_type": "'
                        + device_type
                        + '"}',
                        ip_address=client_ip,
                        user_agent=user_agent,
                        session_id=session_id,
                        admin_session_id=admin_session_result.get("admin_session_id"),
                        risk_level="low",
                        success=True,
                    )
                    print(f"[AUDIT] Admin login logged: {email} - SUCCESS")

            conn.commit()
            conn.close()

            # セッション制限警告のSSE通知を送信
            if session_limit_check.get("warning"):
                try:
                    sse_queue.put(
                        {
                            "type": "session_limit_warning",
                            "data": {
                                "message": session_limit_check["warning"],
                                "current_count": session_limit_check["current_count"],
                                "max_limit": session_limit_check["max_limit"],
                                "usage_percentage": round(
                                    (
                                        session_limit_check["current_count"]
                                        / session_limit_check["max_limit"]
                                    )
                                    * 100,
                                    1,
                                ),
                            },
                        }
                    )
                except:
                    pass  # SSE失敗は無視

            return redirect(url_for("index"))

        except Exception as e:
            if "conn" in locals():
                conn.close()
            return render_template(
                "verify_otp.html",
                email=email,
                error="システムエラーが発生しました。しばらく時間をおいて再試行してください。",
            )

    return render_template("verify_otp.html", email=email)


@app.route("/auth/resend-otp", methods=["POST"])
def resend_otp():
    # パスフレーズ認証とメールアドレスが設定されているかチェック
    if not session.get("passphrase_verified") or not session.get("email"):
        return {"success": False, "error": "認証セッションが無効です"}, 400

    email = session.get("email")

    try:
        # データベース接続
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row

        # OTP生成（6桁）
        import secrets

        otp_code = "".join([str(secrets.randbelow(10)) for _ in range(6)])

        # 有効期限設定（10分後）
        import datetime

        expires_at = add_app_timedelta(get_app_now(), minutes=10)

        # 古いOTPを無効化（同じメールアドレスの未使用OTP）
        conn.execute(
            """
            UPDATE otp_tokens 
            SET used = TRUE, used_at = ? 
            WHERE email = ? AND used = FALSE
        """,
            (get_app_datetime_string(), email),
        )

        # 新しいOTPをデータベースに保存
        conn.execute(
            """
            INSERT INTO otp_tokens (email, otp_code, session_id, ip_address, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                email,
                otp_code,
                session.get("session_id", ""),
                request.remote_addr,
                expires_at.isoformat(),
            ),
        )

        conn.commit()

        # メール送信
        from mail.email_service import EmailService

        email_service = EmailService()

        if email_service.send_otp_email(email, otp_code):
            conn.close()
            return {"success": True, "message": "認証コードを再送信しました"}
        else:
            conn.close()
            return {"success": False, "error": "メール送信に失敗しました"}, 500

    except Exception as e:
        if "conn" in locals():
            conn.close()
        return {"success": False, "error": "システムエラーが発生しました"}, 500


@app.route("/auth/logout")
def logout():
    try:
        # デバッグ: セッション内容の詳細確認
        print(f"DEBUG: Logout process started")
        print(f"DEBUG: Session keys: {list(session.keys())}")

        # 管理者セッションの場合は完全ログアウト処理を実行
        session_id = session.get("session_id")  # "id" → "session_id" に修正
        user_email = session.get("email")

        print(f"DEBUG: session_id = {session_id}")
        print(f"DEBUG: user_email = {user_email}")

        if user_email:
            admin_check = is_admin(user_email)
            print(f"DEBUG: is_admin({user_email}) = {admin_check}")

        if session_id and user_email and is_admin(user_email):
            print(
                f"DEBUG: Admin logout detected for {user_email}, session_id: {session_id}"
            )

            # Phase 3B: 管理者ログアウト操作のログ記録（ログアウト前に記録）
            try:
                client_ip = request.environ.get(
                    "HTTP_X_FORWARDED_FOR", request.remote_addr
                )
                if client_ip and "," in client_ip:
                    client_ip = client_ip.split(",")[0].strip()

                user_agent = request.headers.get("User-Agent", "")
                admin_session_id = session.get("admin_session_id")

                log_admin_action(
                    admin_email=user_email,
                    action_type="admin_logout",
                    resource_type="session",
                    action_details='{"logout_type": "manual"}',
                    ip_address=client_ip,
                    user_agent=user_agent,
                    session_id=session_id,
                    admin_session_id=admin_session_id,
                    risk_level="low",
                    success=True,
                )
                print(f"[AUDIT] Admin logout logged: {user_email} - SUCCESS")
            except Exception as log_error:
                print(f"WARNING: Failed to log admin logout: {log_error}")

            # 管理者の完全ログアウト処理
            logout_success = admin_complete_logout(user_email, session_id)

            if logout_success:
                print(f"DEBUG: Admin complete logout successful for {user_email}")
            else:
                print(f"WARNING: Admin complete logout failed for {user_email}")
        else:
            print(
                f"DEBUG: Skipping admin complete logout - session_id: {bool(session_id)}, user_email: {bool(user_email)}, is_admin: {is_admin(user_email) if user_email else False}"
            )

        # 通常のFlaskセッション削除
        session.clear()

        print(f"DEBUG: Session cleared for logout")
        return redirect(url_for("login"))

    except Exception as e:
        print(f"ERROR: Logout process failed: {e}")
        # エラーが発生してもセッションはクリアする
        session.clear()
        return redirect(url_for("login"))


@app.route("/admin")
@require_admin_permission
def admin():
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return redirect(url_for("login"))

    # フォールバック: 公開終了時刻をチェック
    check_and_handle_expired_publish()

    # Get list of uploaded PDF files
    pdf_files = get_pdf_files()

    # Get current author name setting
    conn = sqlite3.connect("instance/database.db")
    author_name = get_setting(conn, "author_name", "Default_Author")

    # Get current publish end datetime setting
    publish_end_str = get_setting(conn, "publish_end", None)
    publish_end_datetime = None
    publish_end_datetime_formatted = None

    if publish_end_str:
        try:
            publish_end_dt = datetime.fromisoformat(publish_end_str)
            # データベースからの値をアプリタイムゾーンで解釈
            publish_end_dt = localize_datetime(publish_end_dt)

            # アプリタイムゾーンに変換してからフォーマット
            publish_end_jst = to_app_timezone(publish_end_dt)
            # datetime-local input format: YYYY-MM-DDTHH:MM
            publish_end_datetime = publish_end_jst.strftime("%Y-%m-%dT%H:%M")
            # Display format
            publish_end_datetime_formatted = publish_end_jst.strftime("%Y年%m月%d日 %H:%M")
        except ValueError:
            publish_end_datetime = None
            publish_end_datetime_formatted = None

    # Get current published PDF's publish date and recent publication info
    current_published_pdf = None
    publish_start_formatted = None
    last_unpublish_formatted = None

    # 現在公開中のPDFを探す
    for pdf in pdf_files:
        if pdf.get("is_published"):
            current_published_pdf = pdf
            break

    # 現在公開中のPDFの開始日時
    if current_published_pdf and current_published_pdf.get("published_date"):
        try:
            published_dt = datetime.fromisoformat(
                current_published_pdf["published_date"]
            )
            if published_dt.tzinfo is None:
                published_dt = localize_datetime(published_dt)
            published_jst = to_app_timezone(published_dt)
            publish_start_formatted = published_jst.strftime("%Y年%m月%d日 %H:%M")
        except (ValueError, TypeError):
            publish_start_formatted = None

    # 最近停止したPDFの停止日時を取得（現在公開中でない場合）
    if not current_published_pdf:
        for pdf in pdf_files:
            if pdf.get("unpublished_date"):
                try:
                    unpublished_dt = datetime.fromisoformat(pdf["unpublished_date"])
                    if unpublished_dt.tzinfo is None:
                        unpublished_dt = localize_datetime(unpublished_dt)
                    unpublished_jst = to_app_timezone(unpublished_dt)
                    last_unpublish_formatted = unpublished_jst.strftime(
                        "%Y年%m月%d日 %H:%M"
                    )
                    break  # 最初に見つかった（最新の）停止日時を使用
                except (ValueError, TypeError):
                    continue

    # Get session invalidation schedule setting
    conn = sqlite3.connect("instance/database.db")
    scheduled_invalidation_datetime_str = get_setting(
        conn, "scheduled_invalidation_datetime", None
    )
    conn.close()

    scheduled_invalidation_datetime = None
    scheduled_invalidation_datetime_formatted = None
    scheduled_invalidation_seconds = "00"  # デフォルト秒

    if scheduled_invalidation_datetime_str:
        try:
            target_dt = datetime.fromisoformat(scheduled_invalidation_datetime_str)

            # アプリタイムゾーンに変換
            target_jst = localize_datetime(target_dt)

            # 現在時刻と比較して過去の設定かチェック
            now_jst = get_app_now()
            if target_jst <= now_jst:
                # 過去の設定なので削除
                conn_cleanup = sqlite3.connect("instance/database.db")
                cursor_cleanup = conn_cleanup.cursor()
                cursor_cleanup.execute(
                    "DELETE FROM settings WHERE key = ?",
                    ("scheduled_invalidation_datetime",),
                )
                conn_cleanup.commit()
                conn_cleanup.close()
                print(f"Removed expired session invalidation schedule: {target_jst}")

                # 表示用変数をリセット
                scheduled_invalidation_datetime = None
                scheduled_invalidation_datetime_formatted = None
                scheduled_invalidation_seconds = "00"
            else:
                # 未来の設定なので表示
                # datetime-local input format: YYYY-MM-DDTHH:MM (秒は除く)
                scheduled_invalidation_datetime = target_dt.strftime("%Y-%m-%dT%H:%M")
                # 秒の値を抽出
                scheduled_invalidation_seconds = f"{target_dt.second:02d}"
                # Display format
                scheduled_invalidation_datetime_formatted = target_jst.strftime(
                    "%Y年%m月%d日 %H:%M:%S"
                )

        except ValueError:
            scheduled_invalidation_datetime = None
            scheduled_invalidation_datetime_formatted = None
            scheduled_invalidation_seconds = "00"

    # Get session limit settings
    conn = sqlite3.connect("instance/database.db")
    max_concurrent_sessions = get_setting(conn, "max_concurrent_sessions", 100)
    session_limit_enabled = get_setting(conn, "session_limit_enabled", True)
    conn.close()

    return render_template(
        "admin.html",
        pdf_files=pdf_files,
        author_name=author_name,
        publish_end_datetime=publish_end_datetime,
        publish_end_datetime_formatted=publish_end_datetime_formatted,
        publish_start_formatted=publish_start_formatted,
        last_unpublish_formatted=last_unpublish_formatted,
        current_published_pdf=current_published_pdf,
        scheduled_invalidation_datetime=scheduled_invalidation_datetime,
        scheduled_invalidation_datetime_formatted=scheduled_invalidation_datetime_formatted,
        scheduled_invalidation_seconds=scheduled_invalidation_seconds,
        max_concurrent_sessions=max_concurrent_sessions,
        session_limit_enabled=session_limit_enabled,
    )


@app.route("/admin/sessions")
def sessions():
    """セッション一覧ページ"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    return render_template("sessions.html")


@app.route("/admin/sessions/<session_id>")
def session_detail(session_id):
    """セッション詳細ページ"""
    session_check = require_valid_session()
    if session_check:
        return session_check

    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # セッション情報を取得
        cursor.execute(
            """
            SELECT 
                session_id,
                email_hash,
                email_address,
                start_time,
                ip_address,
                device_type,
                last_updated,
                memo
            FROM session_stats 
            WHERE session_id = ?
        """,
            (session_id,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return "セッションが見つかりません", 404

        (
            session_id,
            email_hash,
            stored_email_address,
            start_time,
            ip_address,
            device_type,
            last_updated,
            memo,
        ) = row

        # フォールバック用のメールアドレス取得
        if not stored_email_address:
            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT email FROM otp_tokens ORDER BY created_at DESC"
            )
            emails = cursor.fetchall()

            email_hash_map = {}
            for email_row in emails:
                email = email_row[0]
                email_hash_calc = get_consistent_hash(email)
                email_hash_map[email_hash_calc] = email

            email_address = email_hash_map.get(email_hash, f"不明({email_hash[:8]})")
            conn.close()
        else:
            email_address = stored_email_address

        # 開始時刻を日本時間に変換
        start_dt = datetime.fromtimestamp(start_time, tz=get_app_timezone())
        start_jst = start_dt

        # 残り時間と経過時間を計算
        now = get_app_now()
        elapsed = now - start_jst
        elapsed_hours = round(elapsed.total_seconds() / 3600, 1)

        # 72時間から経過時間を引いて残り時間を計算
        session_timeout = 72 * 3600  # 72時間を秒に変換
        remaining_seconds = session_timeout - elapsed.total_seconds()

        if remaining_seconds > 0:
            remaining_hours = int(remaining_seconds // 3600)
            remaining_minutes = int((remaining_seconds % 3600) // 60)
            remaining_time = f"{remaining_hours}時間{remaining_minutes}分"
        else:
            remaining_time = "期限切れ"

        session_data = {
            "session_id": session_id,
            "email_address": email_address,
            "device_type": device_type,
            "start_time": start_jst.strftime("%Y-%m-%d %H:%M:%S"),
            "remaining_time": remaining_time,
            "elapsed_hours": elapsed_hours,
            "memo": memo or "",
        }

        return render_template("session_detail.html", session=session_data)

    except Exception as e:
        print(f"セッション詳細取得エラー: {e}")
        return "エラーが発生しました", 500


@app.route("/admin/upload-pdf", methods=["POST"])
def upload_pdf():
    if not session.get("authenticated"):
        return redirect(url_for("login"))

    if "pdf_file" not in request.files:
        flash("ファイルが選択されていません")
        return redirect(url_for("admin"))

    file = request.files["pdf_file"]
    if file.filename == "":
        flash("ファイルが選択されていません")
        return redirect(url_for("admin"))

    if file and allowed_file(file.filename):
        original_filename = file.filename

        # Generate unique filename using UUID
        file_extension = original_filename.rsplit(".", 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        try:
            file.save(filepath)

            # Get actual file size
            file_size = os.path.getsize(filepath)

            # Add to database with both original and stored filename
            add_pdf_to_db(original_filename, unique_filename, filepath, file_size)

            flash(f'ファイル "{original_filename}" がアップロードされました')
        except Exception as e:
            flash(f"アップロードに失敗しました: {str(e)}")
    else:
        flash("PDFファイルのみアップロード可能です")

    return redirect(url_for("admin"))


@app.route("/admin/preview-pdf/<int:pdf_id>")
def admin_preview_pdf(pdf_id):
    """管理画面用PDFプレビュー - 署名付きURLにリダイレクト"""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        pdf_info = cursor.execute(
            "SELECT stored_filename FROM pdf_files WHERE id = ?", (pdf_id,)
        ).fetchone()

        if not pdf_info:
            conn.close()
            return jsonify({"error": "ファイルが見つかりません"}), 404

        # 管理者向けの署名付きURL生成（セッションIDを使用）
        session_id = session.get("session_id")
        if not session_id:
            conn.close()
            return jsonify({"error": "セッションIDが見つかりません"}), 400

        try:
            url_result = pdf_security.generate_signed_url(
                filename=pdf_info["stored_filename"], session_id=session_id, conn=conn
            )

            conn.close()

            if "signed_url" in url_result:
                # 署名付きURLにリダイレクト
                return redirect(url_result["signed_url"])
            else:
                return jsonify({"error": "URLの生成に失敗しました"}), 500

        except Exception as e:
            conn.close()
            return jsonify({"error": f"署名付きURL生成エラー: {str(e)}"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/delete-pdf/<int:pdf_id>", methods=["POST"])
def delete_pdf(pdf_id):
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        # Get file info from database
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        pdf_info = cursor.execute(
            "SELECT * FROM pdf_files WHERE id = ?", (pdf_id,)
        ).fetchone()

        if not pdf_info:
            return jsonify({"error": "ファイルが見つかりません"}), 404

        # Delete file from filesystem
        if os.path.exists(pdf_info["file_path"]):
            os.remove(pdf_info["file_path"])

        # Delete from database
        cursor.execute("DELETE FROM pdf_files WHERE id = ?", (pdf_id,))
        conn.commit()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/publish-pdf/<int:pdf_id>", methods=["POST"])
def publish_pdf(pdf_id):
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # Check if PDF exists
        pdf_info = cursor.execute(
            "SELECT id FROM pdf_files WHERE id = ?", (pdf_id,)
        ).fetchone()

        if not pdf_info:
            return jsonify({"error": "ファイルが見つかりません"}), 404

        # Unpublish all other PDFs (only one can be published at a time)
        cursor.execute(
            """
            UPDATE pdf_files 
            SET is_published = FALSE, unpublished_date = ? 
            WHERE is_published = TRUE
        """,
            (get_jst_datetime_string(),),
        )

        # Publish the selected PDF
        cursor.execute(
            """
            UPDATE pdf_files 
            SET is_published = TRUE, published_date = ?, unpublished_date = NULL 
            WHERE id = ?
        """,
            (get_jst_datetime_string(), pdf_id),
        )

        conn.commit()
        conn.close()

        # SSEで全クライアントに通知（公開開始）
        broadcast_sse_event(
            "pdf_published",
            {
                "message": "PDFが公開されました",
                "reason": "manual",
                "timestamp": get_jst_datetime_string(),
            },
        )

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/unpublish-pdf/<int:pdf_id>", methods=["POST"])
def unpublish_pdf(pdf_id):
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # Unpublish the PDF
        cursor.execute(
            """
            UPDATE pdf_files 
            SET is_published = FALSE, unpublished_date = ? 
            WHERE id = ?
        """,
            (get_jst_datetime_string(), pdf_id),
        )

        conn.commit()
        conn.close()

        # SSEで全クライアントに通知（手動停止）
        broadcast_sse_event(
            "pdf_unpublished",
            {
                "message": "公開が手動で停止されました",
                "reason": "manual",
                "timestamp": get_jst_datetime_string(),
            },
        )

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/update-passphrase", methods=["POST"])
def update_passphrase():
    if not session.get("authenticated"):
        return redirect(url_for("login"))

    new_passphrase = request.form.get("new_passphrase", "").strip()
    confirm_passphrase = request.form.get("confirm_passphrase", "").strip()

    if not new_passphrase:
        flash("新しいパスフレーズを入力してください")
        return redirect(url_for("admin"))

    if new_passphrase != confirm_passphrase:
        flash("パスフレーズが一致しません")
        return redirect(url_for("admin"))

    try:
        conn = sqlite3.connect(get_db_path())
        passphrase_manager = PassphraseManager(conn)

        # パスフレーズを更新
        passphrase_manager.update_passphrase(new_passphrase)
        conn.commit()
        conn.close()

        # パスフレーズ変更後もセッションを維持
        flash("パスフレーズが更新されました。既存のセッションは維持されます。", "success")
        return redirect(url_for("admin"))

    except ValueError as e:
        flash(f"パスフレーズの更新に失敗しました: {str(e)}")
    except Exception as e:
        flash(f"システムエラーが発生しました: {str(e)}")

    return redirect(url_for("admin"))


@app.route("/admin/update-author", methods=["POST"])
def update_author():
    if not session.get("authenticated"):
        return redirect(url_for("login"))

    author_name = request.form.get("author_name", "").strip()

    if not author_name:
        flash("著作者名を入力してください")
        return redirect(url_for("admin"))

    if len(author_name) > 100:
        flash("著作者名は100文字以内で入力してください")
        return redirect(url_for("admin"))

    try:
        conn = sqlite3.connect(get_db_path())
        set_setting(conn, "author_name", author_name, "admin")
        conn.commit()
        conn.close()

        flash(f'著作者名を "{author_name}" に更新しました')
    except Exception as e:
        flash(f"更新に失敗しました: {str(e)}")

    return redirect(url_for("admin"))


@app.route("/admin/update-publish-end", methods=["POST"])
def update_publish_end():
    if not session.get("authenticated"):
        return redirect(url_for("login"))

    publish_end_datetime = request.form.get("publish_end_datetime", "").strip()

    try:
        conn = sqlite3.connect(get_db_path())

        if publish_end_datetime:
            # Convert datetime-local format to JST aware datetime
            # datetime-localをアプリタイムゾーンで解釈
            publish_end_dt = parse_datetime_local(publish_end_datetime)

            # Validate that the datetime is in the future
            if publish_end_dt <= get_jst_now():
                flash("公開終了日時は現在時刻より後の時刻を設定してください")
                return redirect(url_for("admin"))

            # Save to database as ISO format string
            set_setting(conn, "publish_end", publish_end_dt.isoformat(), "admin")
            conn.commit()

            # Schedule auto-unpublish
            schedule_auto_unpublish(publish_end_dt)

            formatted_time = publish_end_dt.strftime("%Y年%m月%d日 %H:%M")
            flash(f"公開終了日時を {formatted_time} に設定しました（自動停止スケジュール済み）")
        else:
            # Clear the setting
            set_setting(conn, "publish_end", None, "admin")
            conn.commit()

            # Remove scheduled auto-unpublish
            try:
                scheduler.remove_job("auto_unpublish")
            except:
                pass  # ジョブが存在しない場合は無視

            flash("公開終了日時設定をクリアしました（無制限公開、自動停止解除済み）")

        conn.close()

    except ValueError:
        flash("日時の形式が正しくありません")
    except Exception as e:
        flash(f"設定の更新に失敗しました: {str(e)}")

    return redirect(url_for("admin"))


@app.route("/admin/update-session-limits", methods=["POST"])
def update_session_limits():
    """セッション制限設定を更新"""
    if not session.get("authenticated"):
        flash("認証が必要です")
        return redirect(url_for("login"))

    try:
        max_concurrent_sessions = request.form.get("max_concurrent_sessions", "100")
        session_limit_enabled = "session_limit_enabled" in request.form

        # 数値検証
        try:
            max_sessions = int(max_concurrent_sessions)
            if max_sessions < 1 or max_sessions > 1000:
                flash("同時接続数制限は1-1000の範囲で設定してください")
                return redirect(url_for("admin"))
        except ValueError:
            flash("同時接続数制限は数値で入力してください")
            return redirect(url_for("admin"))

        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row

        # 設定を更新
        set_setting(conn, "max_concurrent_sessions", str(max_sessions), "admin")
        set_setting(
            conn, "session_limit_enabled", str(session_limit_enabled).lower(), "admin"
        )

        conn.close()

        # SSE通知を送信（設定変更を通知）
        try:
            sse_queue.put(
                {
                    "type": "session_limit_updated",
                    "data": {
                        "max_sessions": max_sessions,
                        "enabled": session_limit_enabled,
                    },
                }
            )
        except:
            pass  # SSE失敗は無視

        flash(
            f'セッション制限設定を更新しました（制限: {max_sessions}セッション、監視: {"有効" if session_limit_enabled else "無効"}）'
        )

    except Exception as e:
        flash(f"設定の更新に失敗しました: {str(e)}")

    return redirect(url_for("admin"))


@app.route("/admin/api/csrf-token")
@require_admin_session
@log_admin_operation("api_call", "security_policy", risk_level="low")
def get_csrf_token():
    """管理者用CSRFトークン取得API"""
    session_id = session.get("session_id")
    if not session_id:
        return jsonify({"error": "No active session"}), 401

    try:
        from security.api_security import get_csrf_token_for_session

        csrf_token = get_csrf_token_for_session(session_id)
        return jsonify({"csrf_token": csrf_token})
    except Exception as e:
        return jsonify({"error": "Failed to generate CSRF token"}), 500


@app.route("/admin/api/session-limit-status")
def get_session_limit_status():
    """セッション制限状況を取得"""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row

        # 現在のアクティブセッション数を取得
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as active_sessions FROM session_stats")
        result = cursor.fetchone()
        current_sessions = result["active_sessions"] if result else 0

        # 設定値を取得
        max_sessions = get_setting(conn, "max_concurrent_sessions", 100)
        enabled = get_setting(conn, "session_limit_enabled", True)

        conn.close()

        return jsonify(
            {
                "success": True,
                "current_sessions": current_sessions,
                "max_sessions": int(max_sessions),
                "enabled": enabled,
                "usage_percentage": round(
                    (current_sessions / int(max_sessions)) * 100, 1
                ),
                "is_warning": current_sessions >= int(max_sessions) * 0.8,
                "is_critical": current_sessions >= int(max_sessions),
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/admin/invalidate-all-sessions", methods=["POST"])
def manual_invalidate_all_sessions():
    """手動で全セッション無効化を実行"""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        result = invalidate_all_sessions()
        if result["success"]:
            flash(result["message"], "success")
            return jsonify(result)
        else:
            flash(result["message"], "error")
            return jsonify(result), 500
    except Exception as e:
        error_msg = f"全セッション無効化の実行に失敗しました: {str(e)}"
        flash(error_msg, "error")
        return jsonify({"error": error_msg}), 500


@app.route("/admin/emergency-stop", methods=["POST"])
def emergency_stop():
    """緊急停止機能: 全PDF公開停止 + 全セッション無効化"""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        import time

        # 実行開始時刻を記録
        start_time = time.time()
        timestamp = get_jst_datetime_string()

        print(f"*** EMERGENCY STOP INITIATED AT {timestamp} ***")

        # ログ記録用
        unpublished_pdfs = 0
        deleted_sessions = 0
        deleted_otps = 0
        errors = []

        # Step 1: 全PDF公開停止（既存関数を使用）
        try:
            # 現在公開中のPDF数を事前に取得
            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM pdf_files WHERE is_published = TRUE")
            unpublished_pdfs = cursor.fetchone()[0]
            conn.close()

            # 既存の全PDF公開停止関数を呼び出し
            auto_unpublish_all_pdfs()
            print(f"緊急停止: {unpublished_pdfs}件のPDFを公開停止しました")

        except Exception as e:
            error_msg = f"PDF公開停止でエラー: {str(e)}"
            errors.append(error_msg)
            print(f"ERROR: {error_msg}")

        # Step 2: 全セッション無効化（既存関数を使用）
        try:
            result = invalidate_all_sessions()
            if result["success"]:
                deleted_sessions = result.get("deleted_sessions", 0)
                deleted_otps = result.get("deleted_otps", 0)
                print(f"緊急停止: {deleted_sessions}セッション, {deleted_otps}OTPを削除しました")
            else:
                errors.append(f"セッション無効化エラー: {result.get('message', '不明なエラー')}")
        except Exception as e:
            error_msg = f"セッション無効化でエラー: {str(e)}"
            errors.append(error_msg)
            print(f"ERROR: {error_msg}")

        # Step 3: SSE通知送信
        try:
            send_sse_event(
                {
                    "type": "emergency_stop",
                    "message": "🚨 緊急停止が実行されました - 全PDF公開停止・全セッション無効化",
                    "unpublished_pdfs": unpublished_pdfs,
                    "deleted_sessions": deleted_sessions,
                    "deleted_otps": deleted_otps,
                    "timestamp": timestamp,
                    "clear_session": True,
                }
            )
            print("緊急停止: SSE通知を送信しました")
        except Exception as e:
            print(f"WARNING: SSE通知送信エラー (処理は継続): {str(e)}")

        # Step 4: 実行ログの記録
        try:
            execution_time = round(time.time() - start_time, 2)
            log_entry = f"EMERGENCY_STOP|{timestamp}|PDFs:{unpublished_pdfs}|Sessions:{deleted_sessions}|OTPs:{deleted_otps}|Time:{execution_time}s"
            if errors:
                log_entry += f"|Errors:{len(errors)}"

            # 簡易ログファイルに記録
            try:
                with open("instance/emergency_log.txt", "a", encoding="utf-8") as f:
                    f.write(f"{log_entry}\n")
            except:
                print("WARNING: ファイルログ記録に失敗しました")

            print(f"緊急停止完了 (実行時間: {execution_time}秒)")

        except Exception as e:
            print(f"WARNING: ログ記録エラー: {str(e)}")

        # 結果の返却
        if len(errors) == 0:
            flash("🚨 緊急停止が正常に実行されました", "success")
            return jsonify(
                {
                    "success": True,
                    "message": "緊急停止が完了しました",
                    "unpublished_pdfs": unpublished_pdfs,
                    "deleted_sessions": deleted_sessions,
                    "deleted_otps": deleted_otps,
                    "timestamp": timestamp,
                    "execution_time": round(time.time() - start_time, 2),
                }
            )
        else:
            flash("⚠️ 緊急停止は実行されましたが、一部でエラーが発生しました", "warning")
            return jsonify(
                {
                    "success": True,
                    "message": f"緊急停止は実行されましたが、{len(errors)}件のエラーが発生しました",
                    "unpublished_pdfs": unpublished_pdfs,
                    "deleted_sessions": deleted_sessions,
                    "deleted_otps": deleted_otps,
                    "timestamp": timestamp,
                    "errors": errors,
                    "execution_time": round(time.time() - start_time, 2),
                }
            )

    except Exception as e:
        error_msg = f"緊急停止の実行に失敗しました: {str(e)}"
        print(f"CRITICAL ERROR: {error_msg}")
        flash(error_msg, "error")
        return jsonify({"error": error_msg}), 500


@app.route("/admin/schedule-session-invalidation", methods=["POST"])
def schedule_session_invalidation():
    """設定時刻セッション無効化のスケジュール設定"""
    if not session.get("authenticated"):
        return redirect(url_for("login"))

    try:
        invalidation_datetime = request.form.get("invalidation_datetime", "").strip()
        invalidation_seconds = request.form.get("invalidation_seconds", "00").strip()

        if invalidation_datetime:
            # 秒を追加して完全な日時文字列を作成（YYYY-MM-DDTHH:MM:SS）
            complete_datetime_str = f"{invalidation_datetime}:{invalidation_seconds}"

            # 日時の形式チェック（YYYY-MM-DDTHH:MM:SS）
            target_datetime = datetime.fromisoformat(complete_datetime_str)

            # 過去の日時チェック
            now = get_app_now()
            if target_datetime <= now:
                flash("過去の日時は設定できません。未来の日時を指定してください。", "error")
                return redirect(url_for("admin"))

            # データベースに設定を保存（秒まで含む完全な日時文字列）
            conn = sqlite3.connect(get_db_path())
            set_setting(
                conn, "scheduled_invalidation_datetime", complete_datetime_str, "admin"
            )
            conn.commit()
            conn.close()

            # スケジューラーを設定
            setup_session_invalidation_scheduler(complete_datetime_str)

            # 表示用に日時をフォーマット
            target_jst = localize_datetime(target_datetime)
            formatted_datetime = target_jst.strftime("%Y年%m月%d日 %H:%M:%S")

            flash(f"設定時刻セッション無効化を {formatted_datetime} に設定しました", "success")
        else:
            flash("無効化日時を入力してください", "error")

    except ValueError as e:
        if "過去の日時" in str(e):
            flash("過去の日時は設定できません。未来の日時を指定してください。", "error")
        else:
            flash("日時の形式が正しくありません（YYYY-MM-DDTHH:MM形式で入力してください）", "error")
    except Exception as e:
        flash(f"スケジュール設定に失敗しました: {str(e)}", "error")

    return redirect(url_for("admin"))


@app.route("/admin/clear-session-invalidation-schedule", methods=["POST"])
def clear_session_invalidation_schedule():
    """設定時刻セッション無効化のスケジュール解除"""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        # データベースから設定を削除
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM settings WHERE key = ?", ("scheduled_invalidation_datetime",)
        )
        deleted_rows = cursor.rowcount
        conn.commit()
        conn.close()

        print(f"Schedule cleared: deleted {deleted_rows} settings")

        # スケジューラーのジョブを削除
        try:
            scheduler.remove_job("session_invalidation")
            print("Scheduler job 'session_invalidation' removed successfully")
        except Exception as e:
            print(f"Scheduler job removal: {e} (job may not exist)")

        flash("設定時刻セッション無効化のスケジュールを解除しました", "success")
        return jsonify({"success": True, "message": "スケジュールを解除しました"})

    except Exception as e:
        error_msg = f"スケジュール解除に失敗しました: {str(e)}"
        flash(error_msg, "error")
        return jsonify({"error": error_msg}), 500


@app.route("/api/generate-pdf-url", methods=["POST"])
def generate_pdf_url():
    """公開PDFの署名付きURL生成API"""
    # セッション認証チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        # 現在公開中のPDFを取得
        published_pdf = get_published_pdf()
        if not published_pdf:
            return jsonify({"error": "公開中のPDFが見つかりません"}), 404

        session_id = session.get("session_id")
        if not session_id:
            return jsonify({"error": "セッションIDが見つかりません"}), 400

        # データベース接続を取得して署名付きURLを生成
        conn = sqlite3.connect(get_db_path())

        try:
            url_result = pdf_security.generate_signed_url(
                filename=published_pdf["stored_name"], session_id=session_id, conn=conn
            )

            conn.close()

            return jsonify(
                {
                    "success": True,
                    "signed_url": url_result["signed_url"],
                    "expires_at": url_result["expires_at"],
                    "pdf_info": {
                        "name": published_pdf["name"],
                        "size": published_pdf["size"],
                    },
                }
            )

        except Exception as e:
            conn.close()
            raise e

    except Exception as e:
        return jsonify({"error": f"署名付きURL生成エラー: {str(e)}"}), 500


@app.route("/api/session-info")
def get_session_info():
    """ウォーターマーク用のセッション情報を取得"""
    # セッション有効期限チェック
    if is_session_expired():
        return jsonify({"error": "Session expired"}), 401

    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        # セッションから直接メールアドレスとセッションIDを取得
        email = session.get("email", "unknown@example.com")
        session_id = session.get("session_id", "SID-FALLBACK")

        return jsonify({"session_id": session_id, "email": email, "success": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/api/active-sessions")
@require_admin_api_access
@log_admin_operation("log_view", "session", risk_level="medium")
def get_active_sessions():
    """管理画面用：アクティブセッション一覧を取得"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # session_timeout設定値を取得
        try:
            session_timeout = get_setting("session_timeout", 259200)  # デフォルト72時間
        except:
            session_timeout = 259200  # エラー時のフォールバック

        # 有効期限内のセッションのみ取得
        cutoff_timestamp = int(
            add_app_timedelta(get_app_now(), seconds=-session_timeout).timestamp()
        )

        cursor.execute(
            """
            SELECT 
                session_id,
                email_hash,
                email_address,
                start_time,
                ip_address,
                device_type,
                last_updated,
                memo
            FROM session_stats 
            WHERE start_time > ?
            ORDER BY start_time DESC
        """,
            (cutoff_timestamp,),
        )

        rows = cursor.fetchall()

        # 全てのOTPトークンからメールアドレスを取得してハッシュマッピングを作成
        cursor.execute("SELECT DISTINCT email FROM otp_tokens ORDER BY created_at DESC")
        emails = cursor.fetchall()

        email_hash_map = {}
        for email_row in emails:
            email = email_row[0]
            email_hash = get_consistent_hash(email)
            email_hash_map[email_hash] = email

        conn.close()

        sessions = []
        for row in rows:
            (
                session_id,
                email_hash,
                stored_email_address,
                start_time,
                ip_address,
                device_type,
                last_updated,
                memo,
            ) = row

            # 保存されたemail_addressを使用、なければハッシュマップから取得
            email_address = stored_email_address or email_hash_map.get(
                email_hash, f"不明({email_hash[:8]})"
            )

            # 開始時刻を日本時間に変換
            start_dt = datetime.fromtimestamp(start_time, tz=get_app_timezone())
            start_jst = start_dt

            # 最終更新時刻がある場合は変換（文字列形式での格納を想定）
            last_updated_formatted = None
            if last_updated:
                try:
                    last_updated_dt = datetime.fromisoformat(
                        last_updated.replace("Z", "+00:00")
                    )
                    last_updated_jst = to_app_timezone(last_updated_dt)
                    last_updated_formatted = last_updated_jst.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                except:
                    last_updated_formatted = last_updated

            # セッション経過時間を計算
            elapsed_seconds = (get_app_now() - start_dt).total_seconds()
            remaining_seconds = session_timeout - elapsed_seconds

            # 残り時間を時分秒形式で表示
            if remaining_seconds > 0:
                hours = int(remaining_seconds // 3600)
                minutes = int((remaining_seconds % 3600) // 60)
                remaining_time = f"{hours}時間{minutes}分"
            else:
                remaining_time = "期限切れ"

            sessions.append(
                {
                    "session_id": session_id,
                    "email_address": email_address,
                    "email_hash": email_hash,
                    "start_time": start_jst.strftime("%Y-%m-%d %H:%M:%S"),
                    "ip_address": ip_address,
                    "device_type": device_type,
                    "last_updated": last_updated_formatted,
                    "remaining_time": remaining_time,
                    "elapsed_hours": round(elapsed_seconds / 3600, 1),
                    "memo": memo or "",
                }
            )

        return jsonify(
            {
                "sessions": sessions,
                "total_count": len(sessions),
                "session_timeout_hours": round(session_timeout / 3600, 1),
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/api/update-session-memo", methods=["POST"])
@require_admin_api_access
@log_admin_operation("user_update", "session", capture_state=True, risk_level="medium")
def update_session_memo():
    """セッションのメモを更新"""
    session_check = require_valid_session()
    if session_check:
        return session_check

    try:
        data = request.get_json()
        session_id = data.get("session_id")
        memo = data.get("memo", "").strip()

        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        # メモの長さ制限
        if len(memo) > 500:
            return jsonify({"error": "メモは500文字以内で入力してください"}), 400

        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # セッションが存在するかチェック
        cursor.execute(
            "SELECT session_id FROM session_stats WHERE session_id = ?", (session_id,)
        )
        if not cursor.fetchone():
            conn.close()
            return jsonify({"error": "セッションが見つかりません"}), 404

        # メモを更新
        cursor.execute(
            """
            UPDATE session_stats 
            SET memo = ?, last_updated = ? 
            WHERE session_id = ?
        """,
            (memo, get_app_datetime_string(), session_id),
        )

        conn.commit()
        conn.close()

        return jsonify(
            {
                "success": True,
                "message": "メモを更新しました",
                "session_id": session_id,
                "memo": memo,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/api/pdf-security-settings", methods=["GET"])
@require_admin_api_access
@log_admin_operation("setting_view", "pdf", risk_level="low")
def get_pdf_security_settings():
    """PDF セキュリティ設定を取得"""
    session_check = require_valid_session()
    if session_check:
        return session_check

    try:
        config = get_pdf_security_config()
        return jsonify({"success": True, "settings": config})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/api/pdf-security-settings", methods=["POST"])
@require_admin_api_access
@log_admin_operation(
    "pdf_security_config", "pdf", capture_state=True, risk_level="critical"
)
def update_pdf_security_settings():
    """PDF セキュリティ設定を更新"""
    session_check = require_valid_session()
    if session_check:
        return session_check

    try:
        data = request.get_json()

        # 入力検証
        if "allowed_referrer_domains" in data:
            domains = data["allowed_referrer_domains"]
            if isinstance(domains, str):
                # 文字列の場合はカンマ区切りで分割
                domains = [d.strip() for d in domains.split(",") if d.strip()]
                data["allowed_referrer_domains"] = domains

            # ドメインリストの妥当性チェック
            validation = validate_allowed_domains(domains)
            if not validation["valid"]:
                return (
                    jsonify(
                        {"error": "不正な設定値が含まれています", "details": validation["errors"]}
                    ),
                    400,
                )

        if "blocked_user_agents" in data:
            agents = data["blocked_user_agents"]
            if isinstance(agents, str):
                # 文字列の場合はカンマ区切りで分割
                agents = [a.strip() for a in agents.split(",") if a.strip()]
                data["blocked_user_agents"] = agents

        # 設定を更新
        success = set_pdf_security_config(data, "admin_web")

        if success:
            return jsonify({"success": True, "message": "PDF セキュリティ設定を更新しました"})
        else:
            return jsonify({"error": "設定の更新に失敗しました"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/api/pdf-security-validate", methods=["POST"])
@require_admin_api_access
@log_admin_operation("setting_view", "pdf", risk_level="low")
def validate_pdf_security_settings():
    """PDF セキュリティ設定の妥当性チェック"""
    session_check = require_valid_session()
    if session_check:
        return session_check

    try:
        data = request.get_json()
        domains = data.get("allowed_referrer_domains", [])

        if isinstance(domains, str):
            domains = [d.strip() for d in domains.split(",") if d.strip()]

        validation = validate_allowed_domains(domains)

        return jsonify({"success": True, "validation": validation})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/secure/pdf/<token>")
def secure_pdf_delivery(token):
    """セキュアなPDF配信エンドポイント"""
    # セッション認証チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized - セッション認証が必要です"}), 401

    current_session_id = session.get("session_id")
    client_ip = request.remote_addr

    try:
        # トークンを検証
        verification_result = pdf_security.verify_signed_url(token)

        if not verification_result["valid"]:
            error_msg = verification_result.get("error", "不明なエラー")
            print(
                f"PDF URL verification failed: {error_msg} (IP: {client_ip}, Session: {current_session_id})"
            )

            # アクセスログに失敗を記録
            pdf_security.log_pdf_access(
                filename="UNKNOWN",
                session_id=current_session_id,
                ip_address=client_ip,
                success=False,
                error_message=error_msg,
            )

            return jsonify({"error": f"アクセス拒否: {error_msg}"}), 403

        filename = verification_result["filename"]
        token_session_id = verification_result["session_id"]

        # セッションIDの照合
        if current_session_id != token_session_id:
            error_msg = f"セッションIDが一致しません (current: {current_session_id}, token: {token_session_id})"
            print(f"PDF access denied: {error_msg} (IP: {client_ip})")

            pdf_security.log_pdf_access(
                filename=filename,
                session_id=current_session_id,
                ip_address=client_ip,
                success=False,
                error_message="セッションID不一致",
            )

            return jsonify({"error": "セッション不一致によりアクセスが拒否されました"}), 403

        # PDF直接ダウンロード防止チェック
        prevention_check = _check_pdf_download_prevention(
            filename, current_session_id, client_ip
        )
        if prevention_check:
            return prevention_check

        # ファイルの存在確認
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        if not os.path.exists(file_path):
            error_msg = f"ファイルが見つかりません: {filename}"
            print(
                f"PDF file not found: {error_msg} (IP: {client_ip}, Session: {current_session_id})"
            )

            pdf_security.log_pdf_access(
                filename=filename,
                session_id=current_session_id,
                ip_address=client_ip,
                success=False,
                error_message="ファイル不存在",
            )

            return jsonify({"error": "ファイルが見つかりません"}), 404

        # ワンタイムアクセス制御の処理（将来の拡張用）
        if verification_result.get("one_time"):
            # 実装時にはここでワンタイムトークンの使用済みマーキング処理を追加
            pass

        # アクセスログに成功を記録
        pdf_security.log_pdf_access(
            filename=filename,
            session_id=current_session_id,
            ip_address=client_ip,
            success=True,
            referer=request.headers.get("Referer", "NONE"),
            user_agent=request.headers.get("User-Agent", "NONE"),
        )

        print(
            f"PDF access granted: {filename} (IP: {client_ip}, Session: {current_session_id})"
        )

        # セキュリティヘッダーを設定してPDFファイルを配信
        def generate():
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(8192)  # 8KB chunks
                    if not chunk:
                        break
                    yield chunk

        response = Response(
            generate(),
            content_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "frame-ancestors 'self'",
                "X-Robots-Tag": "noindex, nofollow, nosnippet, noarchive",
            },
        )

        return response

    except Exception as e:
        import traceback

        error_msg = f"PDF配信エラー: {str(e)}"
        app.logger.error(
            f"PDF delivery error: {error_msg} (IP: {client_ip}, Session: {current_session_id})"
        )
        app.logger.error("Full traceback:")
        app.logger.error(traceback.format_exc())
        print(
            f"PDF delivery error: {error_msg} (IP: {client_ip}, Session: {current_session_id})"
        )
        print("Full traceback:")
        traceback.print_exc()

        pdf_security.log_pdf_access(
            filename="ERROR",
            session_id=current_session_id,
            ip_address=client_ip,
            success=False,
            error_message=error_msg,
        )

        return jsonify({"error": "ファイル配信エラーが発生しました"}), 500


@app.route("/api/events")
def sse_stream():
    """Server-Sent Events ストリーム"""
    # セッション有効期限チェック
    if is_session_expired():
        return jsonify({"error": "Session expired"}), 401

    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    def event_stream():
        client_queue = Queue()
        add_sse_client(client_queue)

        try:
            # 接続確立時のハートビート
            yield f"data: {json.dumps({'event': 'connected', 'message': 'SSE接続が確立されました'})}\n\n"

            while True:
                try:
                    # キューからイベントを取得（30秒タイムアウト）
                    event_data = client_queue.get(timeout=30)
                    yield f"event: {event_data['event']}\n"
                    yield f"data: {json.dumps(event_data['data'])}\n\n"
                except Empty:
                    # タイムアウト時はハートビートを送信
                    yield f"data: {json.dumps({'event': 'heartbeat', 'timestamp': get_jst_datetime_string()})}\n\n"
                except Exception:
                    # その他のエラーは無視して継続
                    break

        except (GeneratorExit, ConnectionError, BrokenPipeError):
            # クライアント切断時は静かに終了
            pass
        except Exception:
            # その他のエラーも静かに終了
            pass
        finally:
            # クライアントを確実に削除
            try:
                remove_sse_client(client_queue)
            except:
                pass

    return Response(
        event_stream(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx用
        },
    )


@app.route("/admin/security-logs")
def admin_security_logs():
    """セキュリティログ分析画面"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return redirect(url_for("login"))

    # 管理者権限チェック（一時的に無効化 - 機能確認用）
    # try:
    #     conn = sqlite3.connect(get_db_path())
    #     from database.utils import is_admin_user
    #     if not is_admin_user(conn, session.get('email')):
    #         conn.close()
    #         flash('管理者権限が必要です', 'error')
    #         return redirect(url_for('admin'))
    #     conn.close()
    # except Exception as e:
    #     logging.error(f"Admin check error in security logs: {e}")
    #     flash('権限確認でエラーが発生しました', 'error')
    #     return redirect(url_for('admin'))

    return render_template("security_logs.html")


@app.route("/admin/blocked-ips")
def admin_blocked_ips():
    """制限IP一覧取得API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return jsonify({"error": "Unauthorized"}), 401

    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        rate_limiter = RateLimitManager(conn)

        blocked_ips = rate_limiter.get_blocked_ips()
        conn.close()

        return jsonify({"success": True, "blocked_ips": blocked_ips})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/admin/unblock-ip", methods=["POST"])
def admin_unblock_ip():
    """個別IP制限解除API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return jsonify({"error": "Unauthorized"}), 401

    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = request.get_json()
        ip_address = data.get("ip_address")

        if not ip_address:
            return jsonify({"success": False, "error": "IPアドレスが指定されていません"}), 400

        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        rate_limiter = RateLimitManager(conn)

        # 管理者情報（実際の実装では認証情報から取得）
        admin_user = session.get("email", "admin")

        success = rate_limiter.unblock_ip_manual(ip_address, admin_user)

        if success:
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": f"IP {ip_address} の制限を解除しました"})
        else:
            conn.close()
            return jsonify({"success": False, "error": "指定されたIPアドレスは制限されていません"}), 404

    except Exception as e:
        if "conn" in locals():
            conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/admin/rate-limit-stats")
def admin_rate_limit_stats():
    """レート制限統計情報取得API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return jsonify({"error": "Unauthorized"}), 401

    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        rate_limiter = RateLimitManager(conn)

        stats = rate_limiter.get_rate_limit_stats()

        # 期限切れIP制限を自動クリーンアップ
        cleanup_count = rate_limiter.cleanup_expired_blocks()
        stats["cleanup_count"] = cleanup_count

        conn.commit()
        conn.close()

        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        if "conn" in locals():
            conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() == "pdf"


def get_pdf_files():
    try:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        files = cursor.execute(
            """
            SELECT id, original_filename, stored_filename, file_path, file_size, 
                   upload_date, is_published, published_date, unpublished_date
            FROM pdf_files 
            ORDER BY upload_date DESC
        """
        ).fetchall()

        conn.close()

        result = []
        for file in files:
            # フォーマット済み日時を作成
            published_formatted = None
            unpublished_formatted = None

            if file["published_date"]:
                try:
                    published_dt = datetime.fromisoformat(file["published_date"])
                    if published_dt.tzinfo is None:
                        published_dt = localize_datetime(published_dt)
                    published_jst = to_app_timezone(published_dt)
                    published_formatted = published_jst.strftime("%Y年%m月%d日 %H:%M")
                except (ValueError, TypeError):
                    published_formatted = None

            if file["unpublished_date"]:
                try:
                    unpublished_dt = datetime.fromisoformat(file["unpublished_date"])
                    if unpublished_dt.tzinfo is None:
                        unpublished_dt = localize_datetime(unpublished_dt)
                    unpublished_jst = to_app_timezone(unpublished_dt)
                    unpublished_formatted = unpublished_jst.strftime("%Y年%m月%d日 %H:%M")
                except (ValueError, TypeError):
                    unpublished_formatted = None

            result.append(
                {
                    "id": file["id"],
                    "name": file["original_filename"],
                    "stored_name": file["stored_filename"],
                    "path": file["file_path"],
                    "size": format_file_size(file["file_size"]),
                    "upload_date": file["upload_date"],
                    "is_published": bool(file["is_published"])
                    if file["is_published"] is not None
                    else False,
                    "published_date": file["published_date"],
                    "unpublished_date": file["unpublished_date"],
                    "published_formatted": published_formatted,
                    "unpublished_formatted": unpublished_formatted,
                }
            )

        return result
    except Exception as e:
        print(f"Error getting PDF files: {e}")
        return []


def add_pdf_to_db(original_filename, stored_filename, filepath, file_size):
    conn = sqlite3.connect("instance/database.db")
    cursor = conn.cursor()

    # Create table if it doesn't exist - updated schema
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pdf_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            is_published BOOLEAN DEFAULT FALSE,
            upload_date TEXT
        )
    """
    )

    # Check if we need to migrate old data
    try:
        cursor.execute("SELECT filename FROM pdf_files LIMIT 1")
        # Old schema exists, need to migrate
        try:
            cursor.execute("ALTER TABLE pdf_files ADD COLUMN original_filename TEXT")
            cursor.execute("ALTER TABLE pdf_files ADD COLUMN stored_filename TEXT")
            cursor.execute(
                "ALTER TABLE pdf_files ADD COLUMN is_published BOOLEAN DEFAULT FALSE"
            )
            # Update existing records
            cursor.execute(
                """
                UPDATE pdf_files 
                SET original_filename = filename, stored_filename = filename, is_published = FALSE
                WHERE original_filename IS NULL
            """
            )
        except sqlite3.OperationalError:
            # Columns already exist
            pass
    except sqlite3.OperationalError:
        # New schema or migration already done
        pass

    cursor.execute(
        """
        INSERT INTO pdf_files (original_filename, stored_filename, file_path, file_size)
        VALUES (?, ?, ?, ?)
    """,
        (original_filename, stored_filename, filepath, file_size),
    )

    conn.commit()
    conn.close()


def format_file_size(size_bytes):
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB"]
    i = 0
    size = float(size_bytes)

    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1

    return f"{size:.1f} {size_names[i]}"


def get_published_pdf():
    """Get the currently published PDF file"""
    try:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        published_file = cursor.execute(
            """
            SELECT id, original_filename, stored_filename, file_path, file_size, upload_date
            FROM pdf_files 
            WHERE is_published = TRUE
            LIMIT 1
        """
        ).fetchone()

        conn.close()

        if published_file:
            return {
                "id": published_file["id"],
                "name": published_file["original_filename"],
                "stored_name": published_file["stored_filename"],
                "path": published_file["file_path"],
                "size": format_file_size(published_file["file_size"]),
                "upload_date": published_file["upload_date"],
            }
        return None
    except Exception as e:
        print(f"Error getting published PDF: {e}")
        return None


def initialize_scheduled_tasks():
    """
    アプリ起動時に設定済みのスケジュールタスクを復元
    """
    try:
        conn = sqlite3.connect(get_db_path())

        # セッション無効化スケジュールの復元（新形式）
        scheduled_datetime = get_setting(conn, "session_invalidation_datetime", None)
        if scheduled_datetime:
            # 過去の日時でないかチェック
            try:
                target_dt = datetime.fromisoformat(scheduled_datetime)
                now = get_app_now()
                # 5分以上前の場合のみ期限切れとして削除
                time_diff = (target_dt - now).total_seconds()
                if time_diff > -300:  # 5分前まではまだ有効とみなす
                    if time_diff > 0:
                        setup_session_invalidation_scheduler(scheduled_datetime)
                        print(f"Restored session invalidation schedule: {target_dt}")
                    else:
                        print(
                            f"Session invalidation schedule recently expired: {target_dt} (keeping for safety)"
                        )
                else:
                    # 5分以上前の場合は設定を削除
                    set_setting(conn, "session_invalidation_datetime", None, "system")
                    conn.commit()
                    print(f"Removed expired session invalidation schedule: {target_dt}")
            except ValueError:
                # 不正な形式の場合は設定を削除
                set_setting(conn, "session_invalidation_datetime", None, "system")
                conn.commit()
                print("Removed invalid session invalidation schedule")

        # 旧形式の設定があれば削除（migration）
        old_schedule = get_setting(conn, "session_invalidation_time", None)
        if old_schedule:
            set_setting(conn, "session_invalidation_time", None, "system")
            conn.commit()
            print("Migrated old session invalidation schedule format")

        conn.close()

    except Exception as e:
        print(f"Failed to initialize scheduled tasks: {e}")


# 起動時にスケジュールタスクを初期化
initialize_scheduled_tasks()


def cleanup_expired_schedules():
    """期限切れのスケジュール設定をクリーンアップ"""
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # 期限切れの設定を取得
        cursor.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("scheduled_invalidation_datetime",),
        )
        result = cursor.fetchone()

        if result:
            try:
                target_dt = datetime.fromisoformat(result[0])
                if target_dt.tzinfo is None:
                    target_app_tz = localize_datetime(target_dt)
                else:
                    target_app_tz = to_app_timezone(target_dt)

                now_app_tz = get_app_now()
                if target_app_tz <= now_app_tz:
                    # 期限切れなので削除
                    cursor.execute(
                        "DELETE FROM settings WHERE key = ?",
                        ("scheduled_invalidation_datetime",),
                    )
                    conn.commit()
                    print(
                        f"Removed expired session invalidation schedule on startup: {target_jst}"
                    )
            except ValueError:
                # 無効な日時形式の設定も削除
                cursor.execute(
                    "DELETE FROM settings WHERE key = ?",
                    ("scheduled_invalidation_datetime",),
                )
                conn.commit()
                print("Removed invalid session invalidation schedule on startup")

        conn.close()
    except Exception as e:
        print(f"Error during schedule cleanup: {e}")


# ブロックインシデント管理API
@app.route("/admin/api/block-incidents")
@require_admin_api_access
@log_admin_operation("incident_view", "log", risk_level="medium")
def get_block_incidents():
    """ブロックインシデント一覧取得API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return jsonify({"error": "Unauthorized"}), 401

    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        from database.utils import BlockIncidentManager

        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        incident_manager = BlockIncidentManager(conn)

        # 最新50件のインシデントを取得（未解決を優先）
        all_incidents = incident_manager.get_all_incidents(50)

        # UTCからJSTに変換
        for incident in all_incidents:
            if incident.get("created_at"):
                try:
                    # UTCとして解釈してJSTに変換
                    utc_time = datetime.strptime(
                        incident["created_at"], "%Y-%m-%d %H:%M:%S"
                    )
                    jst_time = to_app_timezone(pytz.utc.localize(utc_time))
                    incident["created_at"] = jst_time.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass  # 変換エラーの場合は元の値を保持

            if incident.get("resolved_at"):
                try:
                    utc_time = datetime.strptime(
                        incident["resolved_at"], "%Y-%m-%d %H:%M:%S"
                    )
                    jst_time = to_app_timezone(pytz.utc.localize(utc_time))
                    incident["resolved_at"] = jst_time.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

        conn.close()

        return jsonify({"status": "success", "incidents": all_incidents})
    except Exception as e:
        if "conn" in locals():
            conn.close()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/admin/api/incident-stats")
@require_admin_api_access
@log_admin_operation("log_view", "log", risk_level="medium")
def get_incident_stats():
    """インシデント統計情報取得API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return jsonify({"error": "Unauthorized"}), 401

    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        from database.utils import BlockIncidentManager

        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        incident_manager = BlockIncidentManager(conn)

        stats = incident_manager.get_incident_stats()
        conn.close()

        return jsonify({"status": "success", "stats": stats})
    except Exception as e:
        if "conn" in locals():
            conn.close()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/admin/api/incident-search", methods=["GET"])
@require_admin_api_access
@log_admin_operation("incident_view", "log", risk_level="medium")
def api_incident_search():
    """インシデントID検索API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return jsonify({"error": "Unauthorized"}), 401

    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        import re

        # インシデントIDパラメータ取得
        incident_id = request.args.get("incident_id", "").strip()

        if not incident_id:
            return jsonify({"success": False, "error": "インシデントIDが指定されていません"})

        # インシデントID形式検証
        if not re.match(r"^BLOCK-\d{14}-[A-Z0-9]{4}$", incident_id):
            return jsonify({"success": False, "error": "無効なインシデントID形式です"})

        # データベース接続
        from database.utils import BlockIncidentManager

        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        incident_manager = BlockIncidentManager(conn)

        # インシデント検索
        incident = incident_manager.get_incident_by_id(incident_id)

        if not incident:
            conn.close()
            return jsonify({"success": False, "error": "インシデントが見つかりません"})

        # 結果をdict形式に変換
        incident_data = dict(incident)
        conn.close()

        return jsonify({"success": True, "incident": incident_data})

    except Exception as e:
        if "conn" in locals():
            conn.close()
        return jsonify({"success": False, "error": f"検索エラーが発生しました: {str(e)}"}), 500


@app.route("/admin/api/resolve-incident", methods=["POST"])
@require_admin_api_access
@log_admin_operation("incident_resolve", "log", capture_state=True, risk_level="high")
def resolve_incident():
    """インシデント解除API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return jsonify({"error": "Unauthorized"}), 401

    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = request.get_json()
        if not data or "incident_id" not in data:
            return jsonify({"status": "error", "message": "インシデントIDが必要です"}), 400

        incident_id = data["incident_id"]
        admin_notes = data.get("admin_notes", "")
        admin_user = session.get("email", "admin")

        from database.utils import BlockIncidentManager, RateLimitManager

        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row

        incident_manager = BlockIncidentManager(conn)
        rate_limiter = RateLimitManager(conn)

        # インシデント情報を取得
        incident = incident_manager.get_incident_by_id(incident_id)
        if not incident:
            conn.close()
            return jsonify({"status": "error", "message": "インシデントが見つかりません"}), 404

        if incident["resolved"]:
            conn.close()
            return jsonify({"status": "error", "message": "このインシデントは既に解決済みです"}), 400

        # インシデントを解除
        success = incident_manager.resolve_incident(
            incident_id, admin_user, admin_notes
        )
        if not success:
            conn.close()
            return jsonify({"status": "error", "message": "インシデントの解除に失敗しました"}), 500

        # 関連するIP制限も解除
        ip_address = incident["ip_address"]
        rate_limiter.unblock_ip_manual(ip_address, admin_user)

        conn.commit()
        conn.close()

        return jsonify(
            {"status": "success", "message": f"インシデント {incident_id} を解除しました"}
        )

    except Exception as e:
        if "conn" in locals():
            conn.close()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/blocked")
def blocked():
    """IP制限時のブロック表示画面"""
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()

    try:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row

        # IP制限情報を取得
        block_info = conn.execute(
            """
            SELECT blocked_until, reason, created_at FROM ip_blocks 
            WHERE ip_address = ? AND datetime(blocked_until) > datetime('now')
        """,
            (client_ip,),
        ).fetchone()

        if not block_info:
            # 制限されていない場合はログインページにリダイレクト
            conn.close()
            return redirect(url_for("login"))

        # 認証失敗回数を取得
        from database.utils import check_auth_failures

        failure_count = check_auth_failures(conn, client_ip, 10)

        # インシデントIDを取得（最新の未解決インシデント）
        incident_id = None
        from database.utils import BlockIncidentManager

        incident_manager = BlockIncidentManager(conn)
        incidents = incident_manager.get_incidents_by_ip(client_ip)
        for incident in incidents:
            if not incident["resolved"]:
                incident_id = incident["incident_id"]
                break

        # 時刻をJSTに変換
        blocked_until_utc = datetime.strptime(
            block_info["blocked_until"], "%Y-%m-%d %H:%M:%S"
        )
        blocked_until_jst = to_app_timezone(pytz.utc.localize(blocked_until_utc))

        conn.close()

        return render_template(
            "blocked.html",
            failure_count=failure_count,
            block_reason=block_info["reason"],
            blocked_until_jst=blocked_until_jst.strftime("%Y年%m月%d日 %H:%M:%S"),
            incident_id=incident_id,
        )

    except Exception as e:
        print(f"Error in blocked route: {e}")
        return render_template(
            "blocked.html",
            failure_count=5,
            block_reason="認証失敗回数が制限値に達しました",
            blocked_until_jst="不明",
            incident_id=None,
        )


@app.route("/blocked/demo")
def blocked_demo():
    """開発者用：ブロック画面のデモ表示"""
    # 開発環境でのみ利用可能
    if not app.debug:
        return redirect(url_for("login"))

    # サンプルデータでブロック画面を表示
    from datetime import datetime, timedelta
    import pytz

    now_app = get_app_now()
    blocked_until = add_app_timedelta(now_app, minutes=25)  # 25分後に解除

    return render_template(
        "blocked.html",
        failure_count=5,
        block_reason="レート制限に達しました: 10分間で5回の認証失敗",
        blocked_until_jst=blocked_until.strftime("%Y年%m月%d日 %H:%M:%S"),
        incident_id="BLOCK-20250726140530-A4B2",
    )


@app.route("/admin/incident-search-demo")
def incident_search_demo():
    """インシデント検索機能のデモページ"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return redirect(url_for("login"))

    try:
        from database.utils import BlockIncidentManager

        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        incident_manager = BlockIncidentManager(conn)

        # サンプルインシデント一覧を取得（最新10件）
        incidents = incident_manager.get_all_incidents(limit=10)

        # デバッグ用ログ
        print(f"Demo page: Found {len(incidents)} incidents")
        for incident in incidents:
            print(f"  - {incident['incident_id']} | {incident['ip_address']}")
        conn.close()

        return render_template("incident_search_demo.html", sample_incidents=incidents)

    except Exception as e:
        if "conn" in locals():
            conn.close()
        return f"Error loading demo page: {str(e)}", 500


# セキュリティイベントログAPI
@app.route("/api/security-event", methods=["POST"])
def record_security_event():
    """セキュリティイベントを記録するAPI"""
    # 認証チェック
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401

    # セッション有効期限チェック
    if is_session_expired():
        return jsonify({"error": "Session expired"}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON data"}), 400

        # 必須フィールドのチェック
        event_type = data.get("event_type")
        if not event_type:
            return jsonify({"error": "event_type is required"}), 400

        # セッション情報から基本データを取得
        user_email = session.get("email", "unknown")
        session_id = session.get("session_id")

        # リクエスト情報を取得
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if client_ip:
            client_ip = client_ip.split(",")[0].strip()
        user_agent = request.headers.get("User-Agent", "")

        # イベント詳細情報
        event_details = data.get("event_details", {})
        event_details["timestamp"] = int(get_app_now().timestamp() * 1000)
        event_details["client_timestamp"] = data.get("client_timestamp")

        # リスクレベルの決定
        risk_level = data.get("risk_level")
        if not risk_level:
            # イベントタイプに基づいてリスクレベルを自動設定
            high_risk_events = [
                "download_attempt",
                "print_attempt",
                "devtools_open",
                "unauthorized_action",
            ]
            medium_risk_events = ["direct_access", "screenshot_attempt", "copy_attempt"]

            if event_type in high_risk_events:
                risk_level = "high"
            elif event_type in medium_risk_events:
                risk_level = "medium"
            else:
                risk_level = "low"

        # PDFファイルパス
        pdf_file_path = data.get("pdf_file_path")

        # データベースに記録
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row

        from database.models import log_security_event

        log_security_event(
            db=conn,
            user_email=user_email,
            event_type=event_type,
            event_details=event_details,
            risk_level=risk_level,
            ip_address=client_ip,
            user_agent=user_agent,
            pdf_file_path=pdf_file_path,
            session_id=session_id,
        )

        conn.commit()
        conn.close()

        # 高リスクイベントの場合は管理者に通知（将来実装）
        if risk_level == "high":
            # TODO: 管理者通知機能
            pass

        return jsonify({"status": "success", "message": "Security event recorded"}), 201

    except Exception as e:
        if "conn" in locals():
            conn.close()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Failed to record security event: {str(e)}",
                }
            ),
            500,
        )


def check_admin_access():
    """管理者アクセスをチェックする共通関数"""
    try:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        from database.utils import is_admin_user

        user_email = session.get("email")
        if not user_email or not is_admin_user(conn, user_email):
            conn.close()
            return False, jsonify({"error": "Admin access required"}), 403
        conn.close()
        return True, None, None
    except Exception as e:
        return False, jsonify({"error": "Admin check failed"}), 500


@app.route("/api/logs/security-events", methods=["GET"])
def get_security_events_api():
    """セキュリティイベントログを取得するAPI（管理者専用）"""
    # 管理者チェック（一時的に無効化 - 機能確認用）
    # is_admin, error_response, status_code = check_admin_access()
    # if not is_admin:
    #     return error_response, status_code

    try:
        # クエリパラメータを取得
        user_email = request.args.get("user_email")
        event_type = request.args.get("event_type")
        risk_level = request.args.get("risk_level")
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        page = int(request.args.get("page", 1))
        limit = min(int(request.args.get("limit", 50)), 100)  # 最大100件

        offset = (page - 1) * limit

        # データベースから取得
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row

        from database.models import get_security_events

        result = get_security_events(
            db=conn,
            user_email=user_email,
            event_type=event_type,
            risk_level=risk_level,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        conn.close()

        return jsonify(
            {
                "status": "success",
                "data": {
                    "events": result["events"],
                    "pagination": {
                        "page": page,
                        "limit": limit,
                        "total": result["total"],
                        "has_more": result["has_more"],
                    },
                },
            }
        )

    except Exception as e:
        if "conn" in locals():
            conn.close()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Failed to get security events: {str(e)}",
                }
            ),
            500,
        )


@app.route("/api/logs/security-events/stats", methods=["GET"])
def get_security_events_stats_api():
    """セキュリティイベントの統計情報を取得するAPI（管理者専用）"""
    # 管理者チェック（一時的に無効化 - 機能確認用）
    # is_admin, error_response, status_code = check_admin_access()
    # if not is_admin:
    #     return error_response, status_code

    try:
        # 日付範囲パラメータ
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")

        # データベースから取得
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row

        from database.models import get_security_event_stats

        stats = get_security_event_stats(
            db=conn, start_date=start_date, end_date=end_date
        )

        conn.close()

        return jsonify({"status": "success", "data": stats})

    except Exception as e:
        if "conn" in locals():
            conn.close()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Failed to get security event stats: {str(e)}",
                }
            ),
            500,
        )


@app.route("/api/logs/access-logs", methods=["GET"])
def get_access_logs_api():
    """アクセスログを取得するAPI（管理者専用）"""
    # 管理者チェック（一時的に無効化 - 機能確認用）
    # is_admin, error_response, status_code = check_admin_access()
    # if not is_admin:
    #     return error_response, status_code

    try:
        # フィルターパラメータを取得
        filters = {}
        if request.args.get("user_email"):
            filters["user_email"] = request.args.get("user_email").strip()
        if request.args.get("ip_address"):
            filters["ip_address"] = request.args.get("ip_address").strip()
        if request.args.get("start_date"):
            filters["start_date"] = request.args.get("start_date")
        if request.args.get("end_date"):
            filters["end_date"] = request.args.get("end_date")
        if request.args.get("endpoint"):
            filters["endpoint"] = request.args.get("endpoint").strip()

        # ページネーションパラメータ
        page = int(request.args.get("page", 1))
        limit = min(int(request.args.get("limit", 20)), 100)  # 最大100件

        # データベース接続
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row

        # アクセスログを取得
        from database.models import get_access_logs

        result = get_access_logs(conn, filters, page, limit)

        conn.close()

        return jsonify({"status": "success", "data": result})

    except Exception as e:
        if "conn" in locals():
            conn.close()
        return (
            jsonify(
                {"status": "error", "message": f"Failed to get access logs: {str(e)}"}
            ),
            500,
        )


@app.route("/api/logs/access-logs/stats", methods=["GET"])
def get_access_logs_stats_api():
    """アクセスログの統計情報を取得するAPI（管理者専用）"""
    # 管理者チェック（一時的に無効化 - 機能確認用）
    # is_admin, error_response, status_code = check_admin_access()
    # if not is_admin:
    #     return error_response, status_code

    try:
        # フィルターパラメータを取得
        filters = {}
        if request.args.get("start_date"):
            filters["start_date"] = request.args.get("start_date")
        if request.args.get("end_date"):
            filters["end_date"] = request.args.get("end_date")

        # データベース接続
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row

        # 統計情報を取得
        from database.models import get_access_logs_stats

        stats = get_access_logs_stats(conn, filters)

        conn.close()

        return jsonify({"status": "success", "data": stats})

    except Exception as e:
        if "conn" in locals():
            conn.close()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Failed to get access log stats: {str(e)}",
                }
            ),
            500,
        )


# ================================
# バックアップAPI エンドポイント
# ================================

# バックアップ実行状況を管理するためのグローバル変数
backup_status_queue = Queue()
backup_in_progress = threading.Lock()

# 復旧実行状況を管理するためのグローバル変数（Phase 3）
restore_progress = {"status": "idle", "message": "復旧は実行されていません", "progress": 0}


@app.route("/admin/backup/create", methods=["POST"])
def create_backup():
    """バックアップ作成API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return redirect(url_for("login"))

    try:
        # 同時実行防止
        if not backup_in_progress.acquire(blocking=False):
            return jsonify({"status": "error", "message": "バックアップが既に実行中です"}), 409

        try:
            from database.backup import BackupManager

            # アプリケーションのルートディレクトリを取得
            app_root = os.path.dirname(os.path.abspath(__file__))

            # 明示的にパスを指定してBackupManagerを初期化
            db_path = os.path.join(app_root, "instance", "database.db")
            backup_dir = os.path.join(app_root, "backups")
            env_path = os.path.join(app_root, ".env")
            pdf_dir = os.path.join(app_root, "static", "pdfs")
            logs_dir = os.path.join(app_root, "logs")
            instance_dir = os.path.join(app_root, "instance")

            backup_manager = BackupManager(
                db_path=db_path,
                backup_dir=backup_dir,
                env_path=env_path,
                pdf_dir=pdf_dir,
                logs_dir=logs_dir,
                instance_dir=instance_dir,
            )

            # バックアップ実行
            def run_backup():
                try:
                    backup_name = backup_manager.create_backup()
                    backup_status_queue.put(
                        {
                            "status": "completed",
                            "backup_name": backup_name,
                            "message": "バックアップが正常に完了しました",
                        }
                    )
                except Exception as e:
                    backup_status_queue.put(
                        {
                            "status": "error",
                            "message": f"バックアップ実行中にエラーが発生しました: {str(e)}",
                        }
                    )
                finally:
                    backup_in_progress.release()

            # 非同期でバックアップ実行
            backup_thread = threading.Thread(target=run_backup)
            backup_thread.daemon = True
            backup_thread.start()

            return jsonify({"status": "in_progress", "message": "バックアップ実行を開始しました"})

        except Exception as e:
            backup_in_progress.release()
            raise e

    except Exception as e:
        return jsonify({"status": "error", "message": f"バックアップ開始エラー: {str(e)}"}), 500


@app.route("/admin/backup/list", methods=["GET"])
def list_backups():
    """バックアップ一覧取得API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return redirect(url_for("login"))

    try:
        global backup_manager

        if backup_manager is None:
            from database.backup import BackupManager

            app_root = os.path.dirname(os.path.abspath(__file__))
            backup_manager = BackupManager(app_root)

        backups = backup_manager.list_backups()

        return jsonify({"status": "success", "data": backups})

    except Exception as e:
        return jsonify({"status": "error", "message": f"バックアップ一覧取得エラー: {str(e)}"}), 500


@app.route("/admin/backup/download/<backup_name>")
def download_backup(backup_name):
    """バックアップダウンロードAPI"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return redirect(url_for("login"))

    try:
        from database.backup import BackupManager
        from flask import send_file
        import re

        # パストラバーサル対策: ファイル名の検証
        if not re.match(r"^[a-zA-Z0-9_-]+$", backup_name):
            return jsonify({"status": "error", "message": "不正なバックアップ名です"}), 400

        app_root = os.path.dirname(os.path.abspath(__file__))
        backup_manager = BackupManager(app_root)

        backup_path = backup_manager.get_backup_path(backup_name)

        if not backup_path or not os.path.exists(backup_path):
            return jsonify({"status": "error", "message": "バックアップファイルが見つかりません"}), 404

        # セキュリティチェック: パスがバックアップディレクトリ内にあることを確認
        backup_dir = os.path.join(app_root, "backups")
        if not os.path.commonpath([backup_path, backup_dir]) == backup_dir:
            return jsonify({"status": "error", "message": "不正なファイルパスです"}), 400

        return send_file(
            backup_path,
            as_attachment=True,
            download_name=f"{backup_name}.tar.gz",
            mimetype="application/gzip",
        )

    except Exception as e:
        return jsonify({"status": "error", "message": f"ダウンロードエラー: {str(e)}"}), 500


@app.route("/admin/backup/delete/<backup_name>", methods=["DELETE"])
def delete_backup(backup_name):
    """バックアップ削除API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return redirect(url_for("login"))

    try:
        from database.backup import BackupManager
        import re

        # パストラバーサル対策: ファイル名の検証
        if not re.match(r"^[a-zA-Z0-9_-]+$", backup_name):
            return jsonify({"status": "error", "message": "不正なバックアップ名です"}), 400

        app_root = os.path.dirname(os.path.abspath(__file__))
        backup_manager = BackupManager(app_root)

        success = backup_manager.delete_backup(backup_name)

        if success:
            return jsonify({"status": "success", "message": "バックアップファイルを削除しました"})
        else:
            return jsonify({"status": "error", "message": "バックアップファイルが見つかりません"}), 404

    except Exception as e:
        return jsonify({"status": "error", "message": f"削除エラー: {str(e)}"}), 500


@app.route("/admin/backup/status")
def backup_status():
    """バックアップ実行状況取得API (Server-Sent Events)"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return redirect(url_for("login"))

    def generate_status():
        """SSE用ステータス生成器"""
        try:
            # 初期状態を送信
            if backup_in_progress.locked():
                yield f"data: {json.dumps({'status': 'in_progress', 'message': 'バックアップ実行中...'})}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'idle', 'message': 'アイドル状態'})}\n\n"

            # キューからステータス更新を取得
            timeout_count = 0
            while timeout_count < 30:  # 30秒でタイムアウト
                try:
                    status = backup_status_queue.get(timeout=1)
                    yield f"data: {json.dumps(status)}\n\n"

                    # 完了またはエラーで終了
                    if status["status"] in ["completed", "error"]:
                        break

                except Empty:
                    timeout_count += 1
                    # ハートビート送信
                    if timeout_count % 10 == 0:
                        current_status = (
                            "in_progress" if backup_in_progress.locked() else "idle"
                        )
                        yield f"data: {json.dumps({'status': current_status, 'message': 'ステータス確認中...'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': f'ステータス取得エラー: {str(e)}'})}\n\n"

    return Response(
        generate_status(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ===== Phase 2: 定期バックアップ・世代管理API =====


@app.route("/admin/backup/settings", methods=["GET"])
def get_backup_settings():
    """バックアップ設定取得API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return jsonify({"status": "error", "message": "認証が必要です"}), 401

    try:
        # BackupManager初期化
        backup_manager = BackupManager(
            db_path=get_db_path(),
            backup_dir=os.path.join(os.path.dirname(app.instance_path), "backups"),
        )

        settings = backup_manager.get_backup_settings()
        return jsonify({"status": "success", "data": settings})

    except Exception as e:
        logger.error(f"バックアップ設定取得エラー: {str(e)}")
        return jsonify({"status": "error", "message": f"設定取得エラー: {str(e)}"}), 500


@app.route("/admin/backup/settings", methods=["POST"])
def update_backup_settings():
    """バックアップ設定更新API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return jsonify({"status": "error", "message": "認証が必要です"}), 401

    try:
        # リクエストデータ取得
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "設定データが必要です"}), 400

        # BackupManager初期化
        backup_manager = BackupManager(
            db_path=get_db_path(),
            backup_dir=os.path.join(os.path.dirname(app.instance_path), "backups"),
        )

        # 設定更新
        backup_manager.update_backup_settings(data)

        # スケジュール更新
        refresh_backup_schedule()

        # 更新後の設定を返す
        updated_settings = backup_manager.get_backup_settings()

        logger.info(f"バックアップ設定更新完了: {data}")
        return jsonify(
            {"status": "success", "message": "設定が更新されました", "data": updated_settings}
        )

    except ValueError as e:
        logger.warning(f"バックアップ設定妥当性エラー: {str(e)}")
        return jsonify({"status": "error", "message": f"設定値エラー: {str(e)}"}), 400

    except Exception as e:
        logger.error(f"バックアップ設定更新エラー: {str(e)}")
        return jsonify({"status": "error", "message": f"設定更新エラー: {str(e)}"}), 500


@app.route("/admin/backup/cleanup", methods=["POST"])
def cleanup_backups():
    """バックアップクリーンアップAPI（世代管理）"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return jsonify({"status": "error", "message": "認証が必要です"}), 401

    try:
        # リクエストデータ取得
        data = request.get_json() or {}
        max_backups = data.get("max_backups")

        # BackupManager初期化
        backup_manager = BackupManager(
            db_path=get_db_path(),
            backup_dir=os.path.join(os.path.dirname(app.instance_path), "backups"),
        )

        # クリーンアップ実行
        deleted_count = backup_manager.cleanup_old_backups(max_backups=max_backups)

        logger.info(f"バックアップクリーンアップ完了: {deleted_count}個削除")
        return jsonify(
            {
                "status": "success",
                "message": f"{deleted_count}個のバックアップを削除しました",
                "data": {"deleted_count": deleted_count},
            }
        )

    except Exception as e:
        logger.error(f"バックアップクリーンアップエラー: {str(e)}")
        return jsonify({"status": "error", "message": f"クリーンアップエラー: {str(e)}"}), 500


@app.route("/admin/backup/statistics", methods=["GET"])
def get_backup_statistics():
    """バックアップ統計情報取得API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return jsonify({"status": "error", "message": "認証が必要です"}), 401

    try:
        # BackupManager初期化
        backup_manager = BackupManager(
            db_path=get_db_path(),
            backup_dir=os.path.join(os.path.dirname(app.instance_path), "backups"),
        )

        stats = backup_manager.get_backup_statistics()

        # 次回自動バックアップ時刻も取得
        next_backup_time = backup_manager.get_next_backup_time()
        if next_backup_time:
            stats["next_auto_backup"] = next_backup_time.isoformat()
        else:
            stats["next_auto_backup"] = None

        return jsonify({"status": "success", "data": stats})

    except Exception as e:
        logger.error(f"バックアップ統計取得エラー: {str(e)}")
        return jsonify({"status": "error", "message": f"統計取得エラー: {str(e)}"}), 500


@app.route("/admin/backup/check-schedule", methods=["GET"])
def check_backup_schedule():
    """自動バックアップスケジュール確認API"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return jsonify({"status": "error", "message": "認証が必要です"}), 401

    try:
        # BackupManager初期化
        backup_manager = BackupManager(
            db_path=get_db_path(),
            backup_dir=os.path.join(os.path.dirname(app.instance_path), "backups"),
        )

        should_run = backup_manager.should_run_backup()
        next_run_time = backup_manager.get_next_backup_time()
        settings = backup_manager.get_backup_settings()

        # スケジューラージョブの状態確認
        scheduled_job = scheduler.get_job("scheduled_backup")
        job_scheduled = scheduled_job is not None

        result = {
            "should_run_now": should_run,
            "next_run_time": next_run_time.isoformat() if next_run_time else None,
            "auto_backup_enabled": settings.get("auto_backup_enabled", False),
            "backup_interval": settings.get("backup_interval", "daily"),
            "backup_time": settings.get("backup_time", "02:00"),
            "scheduler_job_active": job_scheduled,
            "next_scheduled_run": scheduled_job.next_run_time.isoformat()
            if scheduled_job and scheduled_job.next_run_time
            else None,
        }

        return jsonify({"status": "success", "data": result})

    except Exception as e:
        logger.error(f"バックアップスケジュール確認エラー: {str(e)}")
        return jsonify({"status": "error", "message": f"スケジュール確認エラー: {str(e)}"}), 500


# バックアップ復旧API（Phase 3）
@app.route("/admin/backup/restore", methods=["POST"])
def restore_backup():
    """
    バックアップからシステムを復旧

    明示的文字列認証による安全確認システム
    """
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return jsonify({"status": "error", "message": "認証が必要です"}), 401

    try:
        data = request.get_json()

        if not data:
            return jsonify({"status": "error", "message": "リクエストデータが不正です"}), 400

        backup_name = data.get("backup_name")
        confirmation_text = data.get("confirmation_text", "").strip()

        # 必須パラメータチェック
        if not backup_name:
            return jsonify({"status": "error", "message": "バックアップ名が指定されていません"}), 400

        # 明示的文字列認証
        expected_confirmation = "復旧を実行します"
        if confirmation_text != expected_confirmation:
            logger.warning(
                f"復旧認証失敗: 期待値='{expected_confirmation}', 入力値='{confirmation_text}'"
            )
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"確認文字列が正しくありません。正確に「{expected_confirmation}」と入力してください",
                    }
                ),
                403,
            )

        # パス・トラバーサル対策
        if not re.match(r"^[a-zA-Z0-9_\-]+$", backup_name):
            return jsonify({"status": "error", "message": "不正なバックアップ名です"}), 400

        logger.info(
            f"復旧実行開始: バックアップ={backup_name}, 実行者={session.get('username', 'unknown')}"
        )

        # 復旧進行状況管理用のグローバル変数更新
        global restore_progress
        restore_progress = {
            "status": "in_progress",
            "message": "復旧前チェック実行中...",
            "progress": 10,
            "backup_name": backup_name,
            "start_time": get_app_now().isoformat(),
            "step": "initializing",
        }

        def run_restore():
            """復旧実行（別スレッド）"""
            global restore_progress, backup_manager
            try:
                # 復旧進行状況更新
                restore_progress.update(
                    {
                        "message": "復旧前セーフティネット作成中...",
                        "progress": 20,
                        "step": "pre_backup",
                    }
                )

                # BackupManagerで復旧実行
                result = backup_manager.restore_from_backup(backup_name)

                if result["success"]:
                    restore_progress.update(
                        {
                            "status": "completed",
                            "message": "復旧が完了しました",
                            "progress": 100,
                            "step": "completed",
                            "result": result,
                        }
                    )
                    logger.info(f"復旧完了: {backup_name}")
                else:
                    restore_progress.update(
                        {
                            "status": "error",
                            "message": result["message"],
                            "progress": 0,
                            "step": "error",
                            "error": result["message"],
                        }
                    )
                    logger.error(f"復旧失敗: {result['message']}")

            except Exception as e:
                restore_progress.update(
                    {
                        "status": "error",
                        "message": f"復旧中にエラーが発生しました: {str(e)}",
                        "progress": 0,
                        "step": "error",
                        "error": str(e),
                    }
                )
                logger.error(f"復旧実行エラー: {str(e)}")

        # 復旧を別スレッドで実行
        import threading

        restore_thread = threading.Thread(target=run_restore)
        restore_thread.daemon = True
        restore_thread.start()

        # 復旧開始レスポンス
        return jsonify(
            {
                "status": "success",
                "message": "復旧実行を開始しました",
                "data": {
                    "backup_name": backup_name,
                    "restore_id": f"restore_{get_app_now().strftime('%Y%m%d_%H%M%S')}",
                    "estimated_time": 120,  # 見積もり時間（秒）
                },
            }
        )

    except Exception as e:
        logger.error(f"復旧API呼び出しエラー: {str(e)}")
        return jsonify({"status": "error", "message": f"復旧実行エラー: {str(e)}"}), 500


@app.route("/admin/backup/restore-status")
def restore_status():
    """
    復旧進行状況取得（Server-Sent Events対応）
    """
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check

    if not session.get("authenticated"):
        return jsonify({"status": "error", "message": "認証が必要です"}), 401

    def generate():
        global restore_progress

        # 初期状態
        if "restore_progress" not in globals():
            restore_progress = {
                "status": "idle",
                "message": "復旧は実行されていません",
                "progress": 0,
            }

        # 進行状況をSSEで送信
        while True:
            try:
                # 進行状況をJSON形式で送信
                progress_data = {
                    "status": restore_progress.get("status", "idle"),
                    "message": restore_progress.get("message", ""),
                    "progress": restore_progress.get("progress", 0),
                    "backup_name": restore_progress.get("backup_name", ""),
                    "step": restore_progress.get("step", ""),
                    "timestamp": get_app_now().isoformat(),
                }

                # 復旧完了・エラー時は結果も含める
                if restore_progress.get("status") in ["completed", "error"]:
                    if "result" in restore_progress:
                        progress_data["result"] = restore_progress["result"]
                    if "error" in restore_progress:
                        progress_data["error"] = restore_progress["error"]

                yield f"data: {json.dumps(progress_data, ensure_ascii=False)}\n\n"

                # 完了またはエラー時は終了
                if restore_progress.get("status") in ["completed", "error"]:
                    break

                time.sleep(1)  # 1秒間隔で更新

            except Exception as e:
                logger.error(f"復旧ステータスSSEエラー: {str(e)}")
                error_data = {
                    "status": "error",
                    "message": f"ステータス取得エラー: {str(e)}",
                    "progress": 0,
                }
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                break

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


# 管理者権限システム API エンドポイント


@app.route("/admin/users", methods=["GET"])
@require_admin_permission
def get_admin_users_api():
    """管理者一覧取得API"""
    try:
        from database.models import get_admin_users

        admins = get_admin_users()

        # フロントエンド表示用にフォーマット
        for admin in admins:
            if admin.get("added_at"):
                # 文字列の日時をdatetimeに変換してからフォーマット
                try:
                    from datetime import datetime

                    dt = datetime.fromisoformat(
                        admin["added_at"].replace("Z", "+00:00")
                    )
                    admin["added_at_display"] = format_for_display(dt)
                except (ValueError, AttributeError):
                    admin["added_at_display"] = admin["added_at"]  # 変換できない場合は元の値を使用

        return jsonify({"users": admins, "total": len(admins), "max_admins": 6})

    except Exception as e:
        logger.error(f"管理者一覧取得エラー: {str(e)}")
        return jsonify({"error": "管理者一覧の取得に失敗しました"}), 500


@app.route("/admin/users", methods=["POST"])
@require_admin_permission
def add_admin_user_api():
    """管理者追加API"""
    try:
        data = request.get_json()
        email = data.get("email", "").strip()

        if not email:
            return jsonify({"error": "メールアドレスが必要です"}), 400

        # メールアドレスの簡単なバリデーション
        import re

        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, email):
            return jsonify({"error": "有効なメールアドレスを入力してください"}), 400

        from database.models import add_admin_user

        # 操作者のメールアドレスを取得
        operator_email = session.get("email")

        success = add_admin_user(email, operator_email)

        if success:
            return jsonify({"message": "管理者を追加しました", "email": email})
        else:
            return jsonify({"error": "管理者の追加に失敗しました（重複または上限に達している可能性があります）"}), 400

    except Exception as e:
        logger.error(f"管理者追加エラー: {str(e)}")
        return jsonify({"error": "管理者の追加に失敗しました"}), 500


@app.route("/admin/users/<int:admin_id>", methods=["PUT"])
@require_admin_permission
def update_admin_user_api(admin_id):
    """管理者更新API"""
    try:
        data = request.get_json()
        is_active = data.get("is_active")

        if is_active is None:
            return jsonify({"error": "is_activeパラメータが必要です"}), 400

        from database.models import update_admin_status

        success = update_admin_status(admin_id, is_active)

        if success:
            status_text = "有効化" if is_active else "無効化"
            return jsonify({"message": f"管理者を{status_text}しました"})
        else:
            return jsonify({"error": "管理者の更新に失敗しました（最後の管理者は無効化できません）"}), 400

    except Exception as e:
        logger.error(f"管理者更新エラー: {str(e)}")
        return jsonify({"error": "管理者の更新に失敗しました"}), 500


@app.route("/admin/users/<int:admin_id>", methods=["DELETE"])
@require_admin_permission
def delete_admin_user_api(admin_id):
    """管理者削除API"""
    try:
        permanent = request.args.get("permanent", "false").lower() == "true"

        from database.models import delete_admin_user

        success = delete_admin_user(admin_id, permanent)

        if success:
            delete_type = "完全削除" if permanent else "削除"
            return jsonify({"message": f"管理者を{delete_type}しました"})
        else:
            return jsonify({"error": "管理者の削除に失敗しました（最後の管理者は削除できません）"}), 400

    except Exception as e:
        logger.error(f"管理者削除エラー: {str(e)}")
        return jsonify({"error": "管理者の削除に失敗しました"}), 500


if __name__ == "__main__":
    # 起動時に期限切れ設定をクリーンアップ
    cleanup_expired_schedules()

    # PDF セキュリティ設定の初期化
    print("PDF セキュリティ設定を初期化中...")
    initialize_pdf_security_settings()

    # バックアップマネージャーの初期化
    print("バックアップマネージャーを初期化中...")
    backup_manager = BackupManager()

    app.run(debug=True, host="0.0.0.0", port=5000)
