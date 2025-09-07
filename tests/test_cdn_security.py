"""
Cloudflare CDN セキュリティ機能のテスト

GitHub Issue #6: Cloudflare CDN対応のためのセキュリティ機能強化

テスト対象:
1. Real IP Address取得機能
2. Cloudflare Referrer検証機能
3. CDNセキュリティヘッダー設定
4. CDNアクセスログ記録機能
"""

import json
import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest
from flask import Flask


class TestCDNSecurityFeatures:
    """CDN セキュリティ機能のテストクラス"""

    @pytest.fixture
    def app(self):
        """テスト用Flaskアプリケーション"""
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret-key"
        return app

    @pytest.fixture
    def setup_database(self):
        """テスト用データベースのセットアップ"""
        db_fd, db_path = tempfile.mkstemp()

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # cdn_access_logs テーブル作成
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cdn_access_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    endpoint TEXT NOT NULL,
                    action TEXT NOT NULL,
                    real_ip TEXT NOT NULL,
                    cf_connecting_ip TEXT,
                    x_forwarded_for TEXT,
                    user_agent TEXT,
                    referrer TEXT,
                    referrer_validation JSON,
                    cloudflare_domain TEXT,
                    session_id TEXT,
                    additional_info JSON,
                    created_at TEXT NOT NULL
                )
            """
            )

            conn.commit()
            conn.close()

            yield db_path

        finally:
            os.close(db_fd)
            os.unlink(db_path)

    def test_get_real_ip_cf_connecting_ip(self, app):
        """CF-Connecting-IP ヘッダーから実IPを取得するテスト"""
        with app.test_request_context(
            "/",
            headers={
                "CF-Connecting-IP": "203.0.113.1",
                "X-Forwarded-For": "192.168.1.1, 10.0.0.1",
            },
        ):
            # security.cdn_security をモックしてテスト
            with patch.dict(os.environ, {"TRUST_CF_CONNECTING_IP": "true"}):
                from security.cdn_security import get_real_ip

                result = get_real_ip()
                assert result == "203.0.113.1"

    def test_get_real_ip_x_forwarded_for(self, app):
        """X-Forwarded-For ヘッダーから実IPを取得するテスト"""
        with app.test_request_context(
            "/",
            headers={
                "X-Forwarded-For": "203.0.113.2, 192.168.1.1",
            },
        ):
            with patch.dict(os.environ, {"TRUST_CF_CONNECTING_IP": "false"}):
                from security.cdn_security import get_real_ip

                result = get_real_ip()
                assert result == "203.0.113.2"

    def test_get_real_ip_fallback_remote_addr(self, app):
        """request.remote_addr へのフォールバック テスト"""
        with app.test_request_context(
            "/", environ_base={"REMOTE_ADDR": "198.51.100.1"}
        ):
            from security.cdn_security import get_real_ip

            result = get_real_ip()
            assert result == "198.51.100.1"

    def test_is_valid_ip_valid_ipv4(self):
        """有効なIPv4アドレスの検証テスト"""
        from security.cdn_security import is_valid_ip

        assert is_valid_ip("192.168.1.1") is True
        assert is_valid_ip("203.0.113.255") is True
        assert is_valid_ip("127.0.0.1") is True

    def test_is_valid_ip_valid_ipv6(self):
        """有効なIPv6アドレスの検証テスト"""
        from security.cdn_security import is_valid_ip

        assert is_valid_ip("2001:db8::1") is True
        assert is_valid_ip("::1") is True
        assert is_valid_ip("fe80::1") is True

    def test_is_valid_ip_invalid(self):
        """無効なIPアドレスの検証テスト"""
        from security.cdn_security import is_valid_ip

        assert is_valid_ip("256.256.256.256") is False
        assert is_valid_ip("not.an.ip.address") is False
        assert is_valid_ip("") is False
        assert is_valid_ip(None) is False

    def test_strict_ip_validation_enabled(self, app):
        """厳密IP検証が有効な場合のテスト"""
        with app.test_request_context("/", headers={"CF-Connecting-IP": "invalid-ip"}):
            with patch.dict(
                os.environ,
                {"TRUST_CF_CONNECTING_IP": "true", "STRICT_IP_VALIDATION": "true"},
            ):
                from security.cdn_security import get_real_ip

                # 無効なIPの場合は次の方法にフォールバック
                result = get_real_ip()
                assert result != "invalid-ip"

    @patch.dict(os.environ, {"CLOUDFLARE_DOMAIN": "test-domain.com"})
    def test_is_cloudflare_referrer_valid_success(self):
        """Cloudflare リファラー検証成功のテスト"""
        from security.cdn_security import is_cloudflare_referrer_valid

        assert is_cloudflare_referrer_valid("https://test-domain.com/page") is True
        assert (
            is_cloudflare_referrer_valid("https://subdomain.test-domain.com/page")
            is True
        )

    @patch.dict(os.environ, {"CLOUDFLARE_DOMAIN": "test-domain.com"})
    def test_is_cloudflare_referrer_valid_failure(self):
        """Cloudflare リファラー検証失敗のテスト"""
        from security.cdn_security import is_cloudflare_referrer_valid

        assert is_cloudflare_referrer_valid("https://evil-domain.com/page") is False
        assert is_cloudflare_referrer_valid("") is False
        assert is_cloudflare_referrer_valid(None) is False

    @patch.dict(os.environ, {"CLOUDFLARE_DOMAIN": "test-domain.com"})
    def test_get_enhanced_referrer_validation_cloudflare(self):
        """強化リファラー検証の詳細情報取得テスト（Cloudflare）"""
        from security.cdn_security import get_enhanced_referrer_validation

        result = get_enhanced_referrer_validation("https://test-domain.com/page")

        assert result["is_valid"] is True
        assert result["validation_type"] == "cloudflare_cdn"
        assert result["cloudflare_domain"] == "test-domain.com"
        assert result["original_referrer"] == "https://test-domain.com/page"

    def test_get_enhanced_referrer_validation_fallback(self):
        """強化リファラー検証の既存システムへのフォールバックテスト"""
        with patch("config.pdf_security_settings.is_referrer_allowed", return_value=True):
            from security.cdn_security import get_enhanced_referrer_validation

            result = get_enhanced_referrer_validation("https://allowed-domain.com/page")

            assert result["is_valid"] is True
            assert result["validation_type"] == "traditional"

    def test_get_enhanced_referrer_validation_invalid(self):
        """強化リファラー検証の無効な場合のテスト"""
        with patch("config.pdf_security_settings.is_referrer_allowed", return_value=False):
            from security.cdn_security import get_enhanced_referrer_validation

            result = get_enhanced_referrer_validation("https://evil-domain.com/page")

            assert result["is_valid"] is False
            assert result["validation_type"] == "invalid"

    def test_cdn_access_log_creation(self, app, setup_database):
        """CDN アクセスログ作成のテスト"""
        db_path = setup_database

        with app.test_request_context(
            "/test-endpoint",
            headers={
                "CF-Connecting-IP": "203.0.113.1",
                "User-Agent": "Mozilla/5.0 Test Browser",
                "Referer": "https://test-domain.com/page",
            },
        ):
            with patch(
                "app.get_db_path", return_value=db_path
            ), patch.dict(os.environ, {"CLOUDFLARE_DOMAIN": "test-domain.com"}):
                from security.cdn_security import log_cdn_access

                # セッションIDを模擬
                with patch("flask.session.get", return_value="test-session-123"):
                    log_cdn_access(
                        endpoint="/test-endpoint",
                        action="test_action",
                        additional_info={"test_key": "test_value"},
                    )

                # データベースからログを確認
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT * FROM cdn_access_logs WHERE endpoint = ?",
                    ("/test-endpoint",),
                )
                result = cursor.fetchone()

                assert result is not None
                assert result["action"] == "test_action"
                assert result["real_ip"] == "203.0.113.1"
                assert result["cf_connecting_ip"] == "203.0.113.1"
                assert result["user_agent"] == "Mozilla/5.0 Test Browser"
                assert result["referrer"] == "https://test-domain.com/page"
                assert result["session_id"] == "test-session-123"

                # 追加情報の確認
                additional_info = json.loads(result["additional_info"])
                assert additional_info["test_key"] == "test_value"

                # リファラー検証結果の確認
                referrer_validation = json.loads(result["referrer_validation"])
                assert referrer_validation["is_valid"] is True
                assert referrer_validation["validation_type"] == "cloudflare_cdn"

                conn.close()

    @patch.dict(os.environ, {"CLOUDFLARE_DOMAIN": "test-domain.com"})
    def test_get_cdn_security_status(self, app):
        """CDN セキュリティ状態取得のテスト"""
        with app.test_request_context("/", headers={"CF-Connecting-IP": "203.0.113.1"}):
            from security.cdn_security import get_cdn_security_status

            status = get_cdn_security_status()

            assert status["cloudflare_domain"] == "test-domain.com"
            assert status["ip_detection_method"] == "CF-Connecting-IP"
            assert status["real_ip"] == "203.0.113.1"
            assert status["cdn_headers_present"] is True
            assert status["referrer_validation_active"] is True

    def test_get_cdn_security_status_no_cloudflare(self, app):
        """Cloudflare ヘッダーがない場合のセキュリティ状態テスト"""
        with app.test_request_context("/", headers={"X-Forwarded-For": "192.168.1.1"}):
            from security.cdn_security import get_cdn_security_status

            status = get_cdn_security_status()

            assert status["ip_detection_method"] == "X-Forwarded-For"
            assert status["cdn_headers_present"] is False

    def test_cdn_security_with_environment_disabled(self, app):
        """CDN セキュリティが無効な場合のテスト"""
        with patch.dict(os.environ, {"ENABLE_CDN_SECURITY": "false"}):
            with app.test_request_context(
                "/", headers={"CF-Connecting-IP": "203.0.113.1"}
            ):
                from security.cdn_security import get_real_ip

                # CDN機能が無効の場合の動作確認
                result = get_real_ip()
                # 環境変数による制御をテスト
                assert result is not None

    def test_error_handling_in_log_cdn_access(self, app):
        """log_cdn_access のエラーハンドリングテスト"""
        with app.test_request_context("/"):
            # 不正なDB pathでエラーを発生させる
            with patch(
                "app.get_db_path",
                return_value="/invalid/path/test.db",
            ):
                from security.cdn_security import log_cdn_access

                # エラーが発生してもクラッシュしないことを確認
                try:
                    log_cdn_access(endpoint="/test", action="test")
                    # エラーハンドリングが正しく動作している
                    assert True
                except Exception as e:
                    # 予期しないエラーの場合はテスト失敗
                    pytest.fail(f"Unexpected exception: {e}")

    @pytest.mark.parametrize(
        "cf_ip,x_forwarded,expected",
        [
            ("203.0.113.1", "192.168.1.1", "203.0.113.1"),  # CF-Connecting-IP優先
            (None, "203.0.113.2, 192.168.1.1", "203.0.113.2"),  # X-Forwarded-For
            (None, None, None),  # remote_addrに依存
        ],
    )
    def test_get_real_ip_priority_order(self, app, cf_ip, x_forwarded, expected):
        """Real IP取得の優先順位テスト"""
        headers = {}
        if cf_ip:
            headers["CF-Connecting-IP"] = cf_ip
        if x_forwarded:
            headers["X-Forwarded-For"] = x_forwarded

        with app.test_request_context(
            "/", headers=headers, environ_base={"REMOTE_ADDR": "198.51.100.1"}
        ):
            with patch.dict(os.environ, {"TRUST_CF_CONNECTING_IP": "true"}):
                from security.cdn_security import get_real_ip

                result = get_real_ip()

                if expected:
                    assert result == expected
                else:
                    assert result == "198.51.100.1"  # remote_addr fallback


class TestCDNSecurityIntegration:
    """CDN セキュリティ機能の統合テスト"""

    @pytest.fixture
    def setup_database(self):
        """テスト用データベースのセットアップ"""
        db_fd, db_path = tempfile.mkstemp()
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # cdn_access_logs テーブル作成
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cdn_access_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    endpoint TEXT NOT NULL,
                    action TEXT NOT NULL,
                    real_ip TEXT NOT NULL,
                    cf_connecting_ip TEXT,
                    x_forwarded_for TEXT,
                    user_agent TEXT,
                    referrer TEXT,
                    referrer_validation JSON,
                    cloudflare_domain TEXT,
                    session_id TEXT,
                    additional_info JSON,
                    created_at TEXT NOT NULL
                )
            """)
            
            conn.commit()
            conn.close()
            
            yield db_path
            
        finally:
            os.close(db_fd)
            os.unlink(db_path)

    @pytest.fixture
    def app_with_cdn(self):
        """CDN機能が有効なテスト用アプリケーション"""
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret-key"

        with patch.dict(
            os.environ,
            {
                "ENABLE_CDN_SECURITY": "true",
                "CLOUDFLARE_DOMAIN": "test-domain.com",
                "TRUST_CF_CONNECTING_IP": "true",
            },
        ):
            yield app

    def test_full_cdn_request_flow(self, app_with_cdn, setup_database):
        """CDN経由リクエストの完全なフローテスト"""
        db_path = setup_database

        with app_with_cdn.test_request_context(
            "/secure/pdf/test.pdf",
            headers={
                "CF-Connecting-IP": "203.0.113.1",
                "X-Forwarded-For": "203.0.113.1, 192.168.1.1",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://test-domain.com/admin",
            },
        ):
            with patch("app.get_db_path", return_value=db_path):
                from security.cdn_security import (
                    get_cdn_security_status,
                    get_enhanced_referrer_validation,
                    get_real_ip,
                    log_cdn_access,
                )

                # 1. Real IP 取得
                real_ip = get_real_ip()
                assert real_ip == "203.0.113.1"

                # 2. リファラー検証
                referrer_validation = get_enhanced_referrer_validation(
                    "https://test-domain.com/admin"
                )
                assert referrer_validation["is_valid"] is True
                assert referrer_validation["validation_type"] == "cloudflare_cdn"

                # 3. セキュリティ状態確認
                security_status = get_cdn_security_status()
                assert security_status["cdn_headers_present"] is True
                assert security_status["real_ip"] == "203.0.113.1"

                # 4. ログ記録
                with patch(
                    "flask.session.get", return_value="integration-test-session"
                ):
                    log_cdn_access(
                        endpoint="/secure/pdf/test.pdf",
                        action="pdf_access",
                        additional_info={"integration_test": True},
                    )

                # 5. ログ記録の確認
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT * FROM cdn_access_logs WHERE action = ?", ("pdf_access",)
                )
                log_entry = cursor.fetchone()

                assert log_entry is not None
                assert log_entry["real_ip"] == "203.0.113.1"
                assert log_entry["cf_connecting_ip"] == "203.0.113.1"

                referrer_data = json.loads(log_entry["referrer_validation"])
                assert referrer_data["validation_type"] == "cloudflare_cdn"

                conn.close()
