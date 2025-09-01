"""
TASK-021 Sub-Phase 2A/2B: API セキュリティ強化のテスト

テスト対象:
1. Sub-Phase 2A: 管理者API保護強化
   - 未保護管理者APIへの @require_admin_session デコレータ追加
   - CSRF保護機能実装
   - POST系管理者APIにCSRF検証統合

2. Sub-Phase 2B: エラーレスポンス・ヘッダー統一
   - 統一エラーハンドラー実装
   - セキュリティヘッダー自動付与
   - レート制限基盤実装
"""

import pytest
import sqlite3
import json
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from database.timezone_utils import get_current_app_timestamp


class TestAPISecurityPhase2:
    """Phase 2: API セキュリティ強化のテストクラス"""

    @pytest.fixture
    def setup_database(self):
        """テスト用データベースのセットアップ"""
        # テンポラリファイルを使用してテスト用データベースを作成
        db_fd, db_path = tempfile.mkstemp()

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # users テーブル作成
            cursor.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    is_admin BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TEXT NOT NULL
                )
            """
            )

            # admin_sessions テーブル作成
            cursor.execute(
                """
                CREATE TABLE admin_sessions (
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

            # settings テーブル作成
            cursor.execute(
                """
                CREATE TABLE settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    value_type TEXT NOT NULL DEFAULT 'string',
                    description TEXT,
                    category TEXT DEFAULT 'general'
                )
            """
            )

            # csrf_tokens テーブル作成（CSRF保護用）
            cursor.execute(
                """
                CREATE TABLE csrf_tokens (
                    token TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    is_used BOOLEAN DEFAULT FALSE
                )
            """
            )

            # テストデータ挿入
            current_timestamp = get_current_app_timestamp()

            # 管理者ユーザー
            cursor.execute(
                """
                INSERT INTO users (email, password_hash, is_admin, created_at)
                VALUES (?, ?, ?, ?)
            """,
                ("admin@test.com", "hashed_password", True, current_timestamp),
            )

            # 一般ユーザー
            cursor.execute(
                """
                INSERT INTO users (email, password_hash, is_admin, created_at)
                VALUES (?, ?, ?, ?)
            """,
                ("user@test.com", "hashed_password", False, current_timestamp),
            )

            # 管理者セッション
            cursor.execute(
                """
                INSERT INTO admin_sessions (
                    session_id, admin_email, created_at, last_verified_at,
                    ip_address, user_agent, security_flags
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    "admin_session_123",
                    "admin@test.com",
                    current_timestamp,
                    current_timestamp,
                    "127.0.0.1",
                    "Test-Agent",
                    '{"multi_device_count": 1, "last_anomaly_check": "'
                    + current_timestamp
                    + '"}',
                ),
            )

            conn.commit()
            conn.close()

            yield db_path

        finally:
            os.close(db_fd)
            os.unlink(db_path)

    def test_csrf_token_generation(self, setup_database):
        """CSRFトークンの生成機能テスト"""
        from security.api_security import generate_csrf_token

        session_id = "test_session_123"
        token = generate_csrf_token(session_id)

        # トークン形式の検証
        assert isinstance(token, str)
        assert len(token) >= 32  # 十分な長さ
        assert token.isalnum() or "-" in token or "_" in token  # 英数字または安全な文字

        # 異なるセッションIDで異なるトークンが生成されることを確認
        token2 = generate_csrf_token("different_session")
        assert token != token2

    def test_csrf_token_validation_valid(self, setup_database):
        """有効なCSRFトークンの検証テスト"""
        from security.api_security import generate_csrf_token, validate_csrf_token

        with patch("app.get_db_path", return_value=setup_database):
            session_id = "test_session_123"
            token = generate_csrf_token(session_id)

            # 有効なトークンの検証
            is_valid = validate_csrf_token(token, session_id)
            assert is_valid is True

    def test_csrf_token_validation_invalid(self, setup_database):
        """無効なCSRFトークンの検証テスト"""
        from security.api_security import validate_csrf_token

        with patch("app.get_db_path", return_value=setup_database):
            # 存在しないトークン
            is_valid = validate_csrf_token("invalid_token", "test_session")
            assert is_valid is False

            # 空のトークン
            is_valid = validate_csrf_token("", "test_session")
            assert is_valid is False

            # Noneトークン
            is_valid = validate_csrf_token(None, "test_session")
            assert is_valid is False

    def test_csrf_token_expiration(self, setup_database):
        """CSRFトークンの有効期限テスト"""
        from security.api_security import validate_csrf_token

        with patch("app.get_db_path", return_value=setup_database):
            session_id = "test_session_123"

            # 期限切れトークンをデータベースに直接挿入
            conn = sqlite3.connect(setup_database)
            cursor = conn.cursor()

            expired_time = get_current_app_timestamp()
            # 過去の時刻に設定（1時間前）
            past_time = (
                datetime.fromisoformat(expired_time.replace("Z", "+00:00"))
                - timedelta(hours=1)
            ).isoformat() + "Z"

            cursor.execute(
                """
                INSERT INTO csrf_tokens (token, session_id, created_at, expires_at, is_used)
                VALUES (?, ?, ?, ?, ?)
            """,
                ("expired_token", session_id, past_time, past_time, False),
            )

            conn.commit()
            conn.close()

            # 期限切れトークンの検証
            is_valid = validate_csrf_token("expired_token", session_id)
            assert is_valid is False

    def test_create_error_response_unauthorized(self):
        """401 Unauthorizedエラーレスポンス生成テスト"""
        from security.api_security import create_error_response

        response, status_code = create_error_response("unauthorized")

        assert status_code == 401
        assert response["error"] == "Unauthorized"
        assert response["message"] == "Authentication required"
        assert "timestamp" in response
        assert isinstance(response["timestamp"], str)

    def test_create_error_response_forbidden(self):
        """403 Forbiddenエラーレスポンス生成テスト"""
        from security.api_security import create_error_response

        response, status_code = create_error_response("forbidden")

        assert status_code == 403
        assert response["error"] == "Forbidden"
        assert response["message"] == "Access denied"
        assert "timestamp" in response

    def test_create_error_response_custom_message(self):
        """カスタムメッセージ付きエラーレスポンス生成テスト"""
        from security.api_security import create_error_response

        custom_message = "Custom error message"
        response, status_code = create_error_response("forbidden", custom_message)

        assert status_code == 403
        assert response["error"] == "Forbidden"
        assert response["message"] == custom_message
        assert "timestamp" in response

    def test_add_security_headers(self):
        """セキュリティヘッダー追加テスト"""
        from security.api_security import add_security_headers

        # モックレスポンスオブジェクト
        mock_response = Mock()
        mock_response.headers = {}

        result = add_security_headers(mock_response)

        # 期待されるセキュリティヘッダーが追加されていることを確認
        expected_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000",
        }

        for header, value in expected_headers.items():
            assert mock_response.headers[header] == value

        assert result == mock_response

    def test_apply_rate_limit_within_limit(self, setup_database):
        """レート制限範囲内のリクエストテスト"""
        from security.api_security import apply_rate_limit

        with patch("app.get_db_path", return_value=setup_database):
            endpoint = "/admin/api/test"
            user_id = "admin@test.com"

            # 制限範囲内のリクエスト
            is_allowed = apply_rate_limit(endpoint, user_id)
            assert is_allowed is True

    def test_apply_rate_limit_exceeds_limit(self, setup_database):
        """レート制限超過のリクエストテスト"""
        from security.api_security import apply_rate_limit

        with patch("app.get_db_path", return_value=setup_database):
            endpoint = "/admin/api/test"
            user_id = "admin@test.com"

            # レート制限テーブルを作成
            conn = sqlite3.connect(setup_database)
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    endpoint TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    request_count INTEGER DEFAULT 1,
                    window_start TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """
            )

            # 制限値を超える大量のリクエスト記録を挿入
            current_time = get_current_app_timestamp()
            for i in range(15):  # 想定制限値（10）を超える
                cursor.execute(
                    """
                    INSERT INTO rate_limits
                    (endpoint, user_id, request_count, window_start, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (endpoint, user_id, 1, current_time, current_time),
                )

            conn.commit()
            conn.close()

            # レート制限超過の確認
            is_allowed = apply_rate_limit(endpoint, user_id)
            assert is_allowed is False

    def test_admin_api_protection_integration(self, setup_database):
        """管理者API保護の統合テスト（擬似テスト）"""
        # 実際のFlaskアプリケーションとの統合テストはE2Eテストで実施
        # ここでは保護機能の基本動作を確認

        # モック関数で管理者権限チェック
        def mock_require_admin_session(f):
            def wrapper(*args, **kwargs):
                # 管理者セッション検証の擬似実装
                session_data = kwargs.get("session", {})
                if not session_data.get("admin_verified"):
                    return {"error": "Forbidden"}, 403
                return f(*args, **kwargs)

            return wrapper

        # 保護された管理者API関数の擬似実装
        @mock_require_admin_session
        def protected_admin_api(session=None):
            return {"status": "success"}, 200

        # 管理者権限なしでのアクセス
        response, status = protected_admin_api(session={})
        assert status == 403
        assert response["error"] == "Forbidden"

        # 管理者権限ありでのアクセス
        response, status = protected_admin_api(session={"admin_verified": True})
        assert status == 200
        assert response["status"] == "success"

    def test_csrf_protection_integration(self, setup_database):
        """CSRF保護の統合テスト"""
        from security.api_security import validate_csrf_token, get_csrf_token_for_session

        with patch("app.get_db_path", return_value=setup_database):
            session_id = "integration_test_session"

            # 1. CSRFトークン生成
            csrf_token = get_csrf_token_for_session(session_id)
            assert csrf_token is not None

            # 2. POST系API呼び出しの擬似テスト
            def mock_post_api_with_csrf(token, session_id):
                if not validate_csrf_token(token, session_id):
                    return {"error": "CSRF token validation failed"}, 400
                return {"status": "success"}, 200

            # 有効なCSRFトークンでの呼び出し
            response, status = mock_post_api_with_csrf(csrf_token, session_id)
            assert status == 200
            assert response["status"] == "success"

            # 無効なCSRFトークンでの呼び出し
            response, status = mock_post_api_with_csrf("invalid_token", session_id)
            assert status == 400
            assert "CSRF token validation failed" in response["error"]

    def test_error_response_security_compliance(self):
        """エラーレスポンスのセキュリティ準拠テスト"""
        from security.api_security import create_error_response

        # 機密情報の非漏洩確認
        response, status = create_error_response("unauthorized")

        # エラーレスポンスに機密情報が含まれていないことを確認
        response_str = json.dumps(response)

        # 含まれてはいけない情報の例
        sensitive_info = [
            "password",
            "secret",
            "key",
            "token",
            "session_id",
            "admin_email",
            "database",
            "internal",
            "debug",
        ]

        for info in sensitive_info:
            assert info.lower() not in response_str.lower()

        # 必要な情報のみが含まれていることを確認
        assert "error" in response
        assert "message" in response
        assert "timestamp" in response
        assert len(response.keys()) == 3  # 余分な情報なし

    def test_security_headers_compliance(self):
        """セキュリティヘッダーの準拠性テスト"""
        from security.api_security import add_security_headers

        mock_response = Mock()
        mock_response.headers = {}

        add_security_headers(mock_response)

        # OWASP推奨のセキュリティヘッダーがすべて設定されていることを確認
        required_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Strict-Transport-Security",
        ]

        for header in required_headers:
            assert header in mock_response.headers

        # 各ヘッダーの値が適切であることを確認
        assert mock_response.headers["X-Content-Type-Options"] == "nosniff"
        assert mock_response.headers["X-Frame-Options"] == "DENY"
        assert "mode=block" in mock_response.headers["X-XSS-Protection"]
        assert "max-age" in mock_response.headers["Strict-Transport-Security"]
