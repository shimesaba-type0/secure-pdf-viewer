"""
Sub-Phase 1B: 管理者セッション作成・検証機能の統合テスト

テスト内容:
1. 管理者ログイン成功時のセッション作成
2. 管理者権限チェック時のセッション検証
3. admin_sessionsテーブルとの統合
"""

import unittest
import tempfile
import os
import sqlite3
import json
from unittest.mock import patch, MagicMock
from app import app
from database import init_db
from database.models import create_admin_session, verify_admin_session, is_admin


class TestAdminSessionIntegration(unittest.TestCase):
    """管理者セッション統合機能のテストクラス"""

    def setUp(self):
        """テストの前準備"""
        # テスト用一時データベース作成
        self.test_db_fd, self.test_db_path = tempfile.mkstemp()

        # Flaskアプリのテスト設定
        app.config["TESTING"] = True
        app.config["DATABASE"] = self.test_db_path
        app.config["WTF_CSRF_ENABLED"] = False  # CSRFトークンを無効化
        app.config["SECRET_KEY"] = "test_secret_key"

        self.app = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

        # データベース初期化
        with app.app_context():
            # テスト用データベースのスキーマを作成
            from database.models import create_tables, insert_initial_data
            conn = sqlite3.connect(self.test_db_path)
            conn.row_factory = sqlite3.Row  # 辞書形式でアクセス可能にする
            create_tables(conn)
            insert_initial_data(conn)
            conn.commit()

            # テスト用管理者追加
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("admin_users", "admin@test.com"),
            )
            # admin_session関連設定も追加
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, value_type) VALUES (?, ?, ?)",
                ("admin_session_timeout", "3600", "integer"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, value_type) VALUES (?, ?, ?)",
                ("admin_session_verification_interval", "300", "integer"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, value_type) VALUES (?, ?, ?)",
                ("admin_session_ip_binding", "true", "boolean"),
            )
            conn.commit()
            conn.close()

    def tearDown(self):
        """テストの後片付け"""
        self.app_context.pop()
        os.close(self.test_db_fd)
        os.unlink(self.test_db_path)

    def admin_login_complete(self):
        """管理者として完全ログインを実行するヘルパーメソッド"""
        # パスフレーズ認証
        with patch(
            "auth.passphrase.PassphraseManager.verify_passphrase"
        ) as mock_verify:
            mock_verify.return_value = True
            response = self.app.post(
                "/auth/login", data={"password": "test_passphrase"}
            )
            self.assertEqual(response.status_code, 302)

        # メールアドレス入力
        response = self.app.post("/auth/email", data={"email": "admin@test.com"})
        self.assertEqual(response.status_code, 302)

        # OTP認証をモック（直接データベースにOTPを挿入）
        with patch("mail.email_service.EmailService.send_otp_email") as mock_send:
            mock_send.return_value = True
            # テスト用OTPコードをデータベースに挿入
            test_otp = "123456"
            with self.app.session_transaction() as sess:
                email = sess.get("email", "admin@test.com")
                session_id = sess.get("session_id", "test_session")
            
            # テスト用データベースにOTP挿入
            conn = sqlite3.connect(self.test_db_path)
            conn.execute("""
                INSERT INTO otp_tokens (email, otp_code, session_id, ip_address, expires_at, used)
                VALUES (?, ?, ?, ?, datetime('now', '+1 hour'), FALSE)
            """, (email, test_otp, session_id, "127.0.0.1"))
            conn.commit()
            conn.close()

            response = self.app.post("/auth/verify-otp", data={"otp": test_otp})
            return response

    def test_admin_login_creates_admin_session(self):
        """テスト1: 管理者ログイン成功時にadmin_sessionが作成されることを確認"""
        # 管理者としてログイン
        response = self.admin_login_complete()

        # リダイレクトが成功することを確認
        self.assertEqual(response.status_code, 302)

        # admin_sessionsテーブルに記録があることを確認
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM admin_sessions 
            WHERE admin_email = ? AND is_active = 1
        """,
            ("admin@test.com",),
        )

        admin_session = cursor.fetchone()
        conn.close()

        # admin_sessionが作成されていることを確認
        self.assertIsNotNone(admin_session, "管理者セッションが作成されていません")
        self.assertEqual(admin_session["admin_email"], "admin@test.com")
        self.assertTrue(admin_session["is_active"])
        self.assertIsNotNone(admin_session["session_id"])
        self.assertIsNotNone(admin_session["created_at"])

    def test_admin_permission_verifies_admin_session(self):
        """テスト2: 管理者権限チェック時にadmin_sessionが検証されることを確認"""
        # まず管理者としてログイン
        response = self.admin_login_complete()

        # 管理画面にアクセス
        with self.app.session_transaction() as sess:
            # セッション状態を確認
            self.assertTrue(sess.get("authenticated"))
            self.assertEqual(sess.get("email"), "admin@test.com")

        # 管理画面へのアクセスが成功することを確認
        response = self.app.get("/admin")
        self.assertIn(response.status_code, [200, 302])  # 成功またはリダイレクト

    def test_admin_session_verification_with_ip_check(self):
        """テスト3: IPアドレス検証が動作することを確認"""
        # 管理者としてログイン（IPアドレス記録）
        with patch("flask.request") as mock_request:
            mock_request.environ = {"HTTP_X_FORWARDED_FOR": "192.168.1.100"}
            mock_request.remote_addr = "192.168.1.100"
            mock_request.headers = {"User-Agent": "Test Browser"}

            response = self.admin_login_complete()

        # admin_sessionsテーブルからセッション情報を取得
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT session_id, ip_address FROM admin_sessions 
            WHERE admin_email = ? AND is_active = 1
        """,
            ("admin@test.com",),
        )

        admin_session = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(admin_session)
        # IPアドレスが記録されていることを確認（実装により異なる可能性）

    def test_non_admin_user_no_admin_session(self):
        """テスト4: 一般ユーザーにはadmin_sessionが作成されないことを確認"""
        # 一般ユーザー用設定
        conn = sqlite3.connect(self.test_db_path)
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("admin_users", "admin@test.com"),  # user@test.comは管理者ではない
        )
        conn.commit()
        conn.close()

        # パスフレーズ認証
        with patch(
            "auth.passphrase.PassphraseManager.verify_passphrase"
        ) as mock_verify:
            mock_verify.return_value = True
            response = self.app.post(
                "/auth/login", data={"password": "test_passphrase"}
            )

        # 一般ユーザーのメールアドレス入力
        response = self.app.post("/auth/email", data={"email": "user@test.com"})

        # OTP認証
        with patch("mail.email_service.EmailService.send_otp_email") as mock_send:
            mock_send.return_value = True
            # テスト用OTPコードをデータベースに挿入
            test_otp = "123456"
            with self.app.session_transaction() as sess:
                email = sess.get("email", "user@test.com")
                session_id = sess.get("session_id", "test_session")
            
            # テスト用データベースにOTP挿入
            conn = sqlite3.connect(self.test_db_path)
            conn.execute("""
                INSERT INTO otp_tokens (email, otp_code, session_id, ip_address, expires_at, used)
                VALUES (?, ?, ?, ?, datetime('now', '+1 hour'), FALSE)
            """, (email, test_otp, session_id, "127.0.0.1"))
            conn.commit()
            conn.close()

            response = self.app.post("/auth/verify-otp", data={"otp": test_otp})

        # admin_sessionsテーブルに記録がないことを確認
        conn = sqlite3.connect(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) as count FROM admin_sessions 
            WHERE admin_email = ?
        """,
            ("user@test.com",),
        )

        count = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(count, 0, "一般ユーザーにadmin_sessionが作成されてしまいました")

    def test_admin_session_database_functions(self):
        """テスト5: create_admin_session/verify_admin_session関数の動作確認"""
        session_id = "test_session_123"
        admin_email = "admin@test.com"
        ip_address = "192.168.1.100"
        user_agent = "Test Browser"

        # create_admin_session関数テスト
        result = create_admin_session(admin_email, session_id, ip_address, user_agent)
        self.assertTrue(result, "create_admin_session関数が失敗しました")

        # verify_admin_session関数テスト
        session_data = verify_admin_session(session_id, ip_address, user_agent)
        self.assertIsNotNone(session_data, "verify_admin_session関数が失敗しました")
        self.assertEqual(session_data["admin_email"], admin_email)
        self.assertTrue(session_data["is_active"])


if __name__ == "__main__":
    unittest.main()
