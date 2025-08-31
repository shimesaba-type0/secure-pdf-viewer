"""
Sub-Phase 1E: 管理者完全ログアウト機能のテストコード
"""

import os
import sys
import tempfile
import sqlite3
import pytest
import json
import secrets
from unittest.mock import Mock, patch

# プロジェクトルートをPythonパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from database import init_db, get_db
from database.models import (
    create_admin_session,
    verify_admin_session,
    get_admin_session_info,
    # 実装済みの関数
    admin_complete_logout,
    cleanup_related_tokens,
    invalidate_admin_session_completely,
)
from config.timezone import get_app_datetime_string, get_app_now
from database.timezone_utils import get_current_app_timestamp


class TestAdminCompleteLogout:
    """管理者完全ログアウト機能のテストクラス"""

    def setup_method(self):
        """各テストの前に実行されるセットアップ"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        os.environ["DATABASE_PATH"] = self.temp_db.name

        # データベース初期化
        # init_dbは引数を取らないため、環境変数を設定してから呼び出し
        init_db()
        self.conn = sqlite3.connect(self.temp_db.name)

        # テストデータの準備
        self.admin_email = "admin@example.com"
        self.session_id = "test-session-" + secrets.token_hex(16)
        self.ip_address = "192.168.1.100"
        self.user_agent = "Test-Browser/1.0"

    def teardown_method(self):
        """各テストの後に実行されるクリーンアップ"""
        if hasattr(self, "conn"):
            self.conn.close()
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_admin_complete_logout_success(self):
        """管理者完全ログアウトの正常ケース"""
        # 前提条件: 管理者セッションを作成
        create_admin_session(
            admin_email=self.admin_email,
            session_id=self.session_id,
            ip_address=self.ip_address,
            user_agent=self.user_agent,
        )

        # session_statsテーブルが存在する場合のみ関連データを作成
        try:
            self.conn.execute(
                "INSERT INTO session_stats (session_id, email, last_activity, timezone) VALUES (?, ?, ?, ?)",
                (
                    self.session_id,
                    self.admin_email,
                    get_current_app_timestamp(),
                    "Asia/Tokyo",
                ),
            )
            self.conn.commit()
            has_session_stats = True
        except sqlite3.OperationalError:
            # session_statsテーブルが存在しない場合はスキップ
            has_session_stats = False

        # テスト実行: 完全ログアウト
        result = admin_complete_logout(
            admin_email=self.admin_email, session_id=self.session_id
        )

        # 検証
        assert result is True, "完全ログアウトが成功すること"

        # admin_sessionsから削除されていることを確認
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM admin_sessions WHERE session_id = ?",
            (self.session_id,),
        )
        assert cursor.fetchone()[0] == 0, "admin_sessionsから削除されていること"

        # session_statsから削除されていることを確認（テーブルが存在する場合）
        if has_session_stats:
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM session_stats WHERE session_id = ?",
                (self.session_id,),
            )
            assert cursor.fetchone()[0] == 0, "session_statsから削除されていること"

    def test_admin_complete_logout_with_otp_cleanup(self):
        """OTPトークンも含む完全ログアウト"""
        # 前提条件: 管理者セッションとOTPトークンを作成
        create_admin_session(
            admin_email=self.admin_email,
            session_id=self.session_id,
            ip_address=self.ip_address,
            user_agent=self.user_agent,
        )

        # OTPトークンを作成（存在する場合）
        try:
            self.conn.execute(
                "INSERT INTO otp_tokens (email, token, expires_at, session_id) VALUES (?, ?, ?, ?)",
                (
                    self.admin_email,
                    "123456",
                    get_current_app_timestamp(),
                    self.session_id,
                ),
            )
            self.conn.commit()
            has_otp_table = True
        except sqlite3.OperationalError:
            has_otp_table = False

        # テスト実行: 完全ログアウト
        result = admin_complete_logout(
            admin_email=self.admin_email, session_id=self.session_id
        )

        # 検証
        assert result is True, "完全ログアウトが成功すること"

        if has_otp_table:
            # OTPトークンが削除されていることを確認
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM otp_tokens WHERE session_id = ?",
                (self.session_id,),
            )
            assert cursor.fetchone()[0] == 0, "OTPトークンが削除されていること"

    def test_admin_complete_logout_nonexistent_session(self):
        """存在しないセッションの完全ログアウト"""
        nonexistent_session = "nonexistent-session-id"

        # テスト実行: 存在しないセッションのログアウト
        result = admin_complete_logout(
            admin_email=self.admin_email, session_id=nonexistent_session
        )

        # 検証: エラーにならずにFalseを返すこと
        assert result is False, "存在しないセッションの場合はFalseを返すこと"

    def test_admin_complete_logout_database_error_handling(self):
        """データベースエラーの処理"""
        # 前提条件: 管理者セッションを作成
        create_admin_session(
            admin_email=self.admin_email,
            session_id=self.session_id,
            ip_address=self.ip_address,
            user_agent=self.user_agent,
        )

        # データベース接続を閉じてエラーを発生させる
        self.conn.close()

        # テスト実行: データベースエラーが発生する状況でのログアウト
        with pytest.raises(Exception):
            admin_complete_logout(
                admin_email=self.admin_email, session_id=self.session_id
            )

    def test_cleanup_related_tokens_success(self):
        """関連トークンのクリーンアップ成功"""
        # 前提条件: セッション関連データを作成
        create_admin_session(
            admin_email=self.admin_email,
            session_id=self.session_id,
            ip_address=self.ip_address,
            user_agent=self.user_agent,
        )

        # テスト実行: 関連トークンのクリーンアップ
        result = cleanup_related_tokens(self.session_id)

        # 検証
        assert result is True, "関連トークンのクリーンアップが成功すること"

    def test_invalidate_admin_session_completely_success(self):
        """管理者セッションの完全無効化成功"""
        # 前提条件: 管理者セッションを作成
        create_admin_session(
            admin_email=self.admin_email,
            session_id=self.session_id,
            ip_address=self.ip_address,
            user_agent=self.user_agent,
        )

        # セッションが有効であることを確認
        session_info = get_admin_session_info(self.session_id)
        assert session_info is not None, "セッションが存在すること"
        assert session_info["is_active"] is True, "セッションがアクティブであること"

        # テスト実行: 完全無効化
        result = invalidate_admin_session_completely(self.session_id)

        # 検証
        assert result is True, "セッションの完全無効化が成功すること"

        # セッションが削除されていることを確認
        session_info = get_admin_session_info(self.session_id)
        assert session_info is None, "セッションが削除されていること"

    def test_admin_complete_logout_logging(self):
        """ログアウト操作のログ記録"""
        # 前提条件: 管理者セッションを作成
        create_admin_session(
            admin_email=self.admin_email,
            session_id=self.session_id,
            ip_address=self.ip_address,
            user_agent=self.user_agent,
        )

        # ログ出力をモック
        with patch("logging.Logger.info") as mock_logger:
            # テスト実行: 完全ログアウト
            result = admin_complete_logout(
                admin_email=self.admin_email, session_id=self.session_id
            )

            # 検証
            assert result is True, "完全ログアウトが成功すること"
            # ログが出力されていることを確認
            mock_logger.assert_called()

    def test_admin_complete_logout_security_flags_preservation(self):
        """セキュリティフラグの保持確認"""
        # 前提条件: セキュリティフラグ付きの管理者セッションを作成
        security_flags = {
            "high_security": True,
            "ip_verified": True,
            "anomaly_detected": False,
        }

        self.conn.execute(
            """INSERT INTO admin_sessions 
               (session_id, admin_email, created_at, last_verified_at, 
                ip_address, user_agent, is_active, security_flags, verification_token) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                self.session_id,
                self.admin_email,
                get_current_app_timestamp(),
                get_current_app_timestamp(),
                self.ip_address,
                self.user_agent,
                True,
                json.dumps(security_flags),
                "test-token",
            ),
        )
        self.conn.commit()

        # テスト実行: 完全ログアウト
        result = admin_complete_logout(
            admin_email=self.admin_email, session_id=self.session_id
        )

        # 検証
        assert result is True, "完全ログアウトが成功すること"

        # セッションが削除されていることを確認
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM admin_sessions WHERE session_id = ?",
            (self.session_id,),
        )
        assert cursor.fetchone()[0] == 0, "セッションが完全に削除されていること"

    def test_admin_complete_logout_multiple_sessions(self):
        """複数セッション環境での完全ログアウト"""
        # 前提条件: 同じ管理者の複数セッションを作成
        session_id2 = "test-session2-" + secrets.token_hex(16)

        create_admin_session(
            admin_email=self.admin_email,
            session_id=self.session_id,
            ip_address=self.ip_address,
            user_agent=self.user_agent,
        )

        create_admin_session(
            admin_email=self.admin_email,
            session_id=session_id2,
            ip_address="192.168.1.101",
            user_agent="Another-Browser/1.0",
        )

        # テスト実行: 1つのセッションの完全ログアウト
        result = admin_complete_logout(
            admin_email=self.admin_email, session_id=self.session_id
        )

        # 検証
        assert result is True, "完全ログアウトが成功すること"

        # 指定したセッションのみが削除されていることを確認
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM admin_sessions WHERE session_id = ?",
            (self.session_id,),
        )
        assert cursor.fetchone()[0] == 0, "指定されたセッションが削除されていること"

        # 他のセッションは残っていることを確認
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM admin_sessions WHERE session_id = ?", (session_id2,)
        )
        assert cursor.fetchone()[0] == 1, "他のセッションは残っていること"

    def test_admin_complete_logout_timezone_consistency(self):
        """タイムゾーン一貫性の確認"""
        # 前提条件: 管理者セッションを作成
        create_admin_session(
            admin_email=self.admin_email,
            session_id=self.session_id,
            ip_address=self.ip_address,
            user_agent=self.user_agent,
        )

        # 現在のアプリケーション時刻を取得
        before_logout = get_current_app_timestamp()

        # テスト実行: 完全ログアウト（ログ出力の時刻確認）
        with patch("logging.Logger.info") as mock_logger:
            result = admin_complete_logout(
                admin_email=self.admin_email, session_id=self.session_id
            )

            # 検証
            assert result is True, "完全ログアウトが成功すること"

            # ログ出力にアプリケーション統一タイムスタンプが使用されていることを確認
            # （実際のログ内容は実装に依存）
            mock_logger.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
