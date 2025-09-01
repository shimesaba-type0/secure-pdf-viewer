"""
TASK-021 Phase 3A: 管理者監査ログ機能のテスト

管理者操作の詳細監査ログシステムのテストケース：
1. admin_actionsテーブル作成・CRUD操作テスト
2. ログ記録機能テスト
3. フィルタリング・検索機能テスト
4. 統計情報取得テスト
"""

import unittest
import sqlite3
import json
from unittest.mock import patch, MagicMock

# テスト用のデータベースパス設定
TEST_DB = ":memory:"


class TestAdminAuditLogging(unittest.TestCase):
    """管理者監査ログ機能のテストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.db_path = TEST_DB

        # テスト用データベース接続
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row

        # データベース初期化
        self.create_test_tables()
        self.insert_test_data()

    def tearDown(self):
        """テスト後処理"""
        if self.db:
            self.db.close()

    def create_test_tables(self):
        """テスト用テーブル作成"""
        # admin_actionsテーブル作成
        self.db.execute(
            """
            CREATE TABLE admin_actions (
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

        # 必要なインデックス作成
        indexes = [
            "CREATE INDEX idx_admin_actions_admin_email ON admin_actions(admin_email)",
            "CREATE INDEX idx_admin_actions_action_type ON admin_actions(action_type)",
            "CREATE INDEX idx_admin_actions_created_at ON admin_actions(created_at)",
            "CREATE INDEX idx_admin_actions_risk_level ON admin_actions(risk_level)",
        ]

        for index_sql in indexes:
            self.db.execute(index_sql)

        self.db.commit()

    def insert_test_data(self):
        """テスト用データ挿入"""
        from config.timezone import get_app_datetime_string

        current_time = get_app_datetime_string()

        test_actions = [
            {
                "admin_email": "admin@example.com",
                "action_type": "user_view",
                "resource_type": "user",
                "resource_id": "user001",
                "action_details": json.dumps({"viewed_user": "test@example.com"}),
                "ip_address": "192.168.1.100",
                "user_agent": "Mozilla/5.0",
                "session_id": "sess001",
                "admin_session_id": "admin_sess001",
                "created_at": current_time,
                "risk_level": "low",
                "success": True,
            },
            {
                "admin_email": "admin@example.com",
                "action_type": "user_delete",
                "resource_type": "user",
                "resource_id": "user002",
                "action_details": json.dumps({"deleted_user": "test2@example.com"}),
                "before_state": json.dumps(
                    {"email": "test2@example.com", "active": True}
                ),
                "after_state": json.dumps({"deleted": True}),
                "ip_address": "192.168.1.100",
                "user_agent": "Mozilla/5.0",
                "session_id": "sess001",
                "admin_session_id": "admin_sess001",
                "created_at": current_time,
                "risk_level": "high",
                "success": True,
            },
            {
                "admin_email": "admin2@example.com",
                "action_type": "setting_update",
                "resource_type": "setting",
                "resource_id": "security_config",
                "action_details": json.dumps(
                    {"setting": "admin_session_timeout", "new_value": 1800}
                ),
                "before_state": json.dumps({"admin_session_timeout": 3600}),
                "after_state": json.dumps({"admin_session_timeout": 1800}),
                "ip_address": "192.168.1.101",
                "user_agent": "Chrome/91.0",
                "session_id": "sess002",
                "admin_session_id": "admin_sess002",
                "created_at": current_time,
                "risk_level": "medium",
                "success": False,
                "error_message": "Permission denied",
            },
        ]

        for action in test_actions:
            columns = ", ".join(action.keys())
            placeholders = ", ".join(["?" for _ in action])
            sql = f"INSERT INTO admin_actions ({columns}) VALUES ({placeholders})"
            self.db.execute(sql, list(action.values()))

        self.db.commit()

    def test_log_admin_action_success(self):
        """管理者操作ログ記録成功テスト"""
        # モック設定
        with patch("database.get_db") as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = self.db

            # テスト対象関数をインポート（後で実装）
            from database.models import log_admin_action

            result = log_admin_action(
                admin_email="admin@example.com",
                action_type="user_create",
                resource_type="user",
                resource_id="user003",
                action_details={"new_user": "test3@example.com"},
                ip_address="192.168.1.100",
                success=True,
            )

            self.assertTrue(result)

            # データベースに記録されたかチェック
            cursor = self.db.execute(
                "SELECT * FROM admin_actions WHERE action_type = 'user_create' "
                "AND resource_id = 'user003'"
            )
            action = cursor.fetchone()
            self.assertIsNotNone(action)
            self.assertEqual(action["admin_email"], "admin@example.com")
            self.assertEqual(action["action_type"], "user_create")
            self.assertTrue(action["success"])

    def test_log_admin_action_with_state_capture(self):
        """操作前後状態記録テスト"""
        with patch("database.get_db") as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = self.db

            from database.models import log_admin_action

            before_state = {"email": "old@example.com", "active": True}
            after_state = {"email": "new@example.com", "active": True}

            result = log_admin_action(
                admin_email="admin@example.com",
                action_type="user_update",
                resource_type="user",
                resource_id="user004",
                before_state=before_state,
                after_state=after_state,
                ip_address="192.168.1.100",
            )

            self.assertTrue(result)

            # 状態が正しく記録されたかチェック
            cursor = self.db.execute(
                "SELECT before_state, after_state FROM admin_actions "
                "WHERE resource_id = 'user004'"
            )
            action = cursor.fetchone()
            self.assertEqual(json.loads(action["before_state"]), before_state)
            self.assertEqual(json.loads(action["after_state"]), after_state)

    def test_get_admin_actions_basic(self):
        """管理者操作ログ取得基本テスト"""
        with patch("database.get_db") as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = self.db

            from database.models import get_admin_actions

            result = get_admin_actions()

            self.assertIsInstance(result, dict)
            self.assertIn("actions", result)
            self.assertIn("total", result)
            self.assertIn("page", result)
            self.assertGreaterEqual(result["total"], 3)  # テストデータ3件

    def test_get_admin_actions_with_filter(self):
        """フィルタリング付きログ取得テスト"""
        with patch("database.get_db") as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = self.db

            from database.models import get_admin_actions

            # 管理者メールでフィルタ
            result = get_admin_actions(admin_email="admin@example.com")
            self.assertGreaterEqual(result["total"], 2)

            # リスクレベルでフィルタ
            result = get_admin_actions(risk_level="high")
            self.assertGreaterEqual(result["total"], 1)

            # アクション種別でフィルタ
            result = get_admin_actions(action_type="user_delete")
            self.assertGreaterEqual(result["total"], 1)

    def test_get_admin_actions_with_date_filter(self):
        """日付範囲フィルタテスト"""
        with patch("database.get_db") as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = self.db

            from database.models import get_admin_actions
            from config.timezone import get_app_now, add_app_timedelta

            # 今日から1日前までの範囲
            start_date = add_app_timedelta(get_app_now(), days=-1).strftime("%Y-%m-%d")
            end_date = add_app_timedelta(get_app_now(), days=1).strftime("%Y-%m-%d")

            result = get_admin_actions(start_date=start_date, end_date=end_date)
            self.assertGreaterEqual(result["total"], 3)  # 全テストデータが範囲内

    def test_get_admin_actions_pagination(self):
        """ページネーションテスト"""
        with patch("database.get_db") as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = self.db

            from database.models import get_admin_actions

            # 1ページ目（1件表示）
            result = get_admin_actions(page=1, limit=1)
            self.assertEqual(len(result["actions"]), 1)
            self.assertEqual(result["page"], 1)
            self.assertEqual(result["limit"], 1)

            # 2ページ目
            result = get_admin_actions(page=2, limit=1)
            self.assertLessEqual(len(result["actions"]), 1)

    def test_get_admin_action_stats(self):
        """管理者操作統計テスト"""
        with patch("database.get_db") as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = self.db

            from database.models import get_admin_action_stats

            # アクション種別別統計
            result = get_admin_action_stats(group_by="action_type")
            self.assertIsInstance(result, dict)
            self.assertIn("stats", result)

            # リスクレベル別統計
            result = get_admin_action_stats(group_by="risk_level")
            self.assertIn("stats", result)

            # 管理者別統計
            result = get_admin_action_stats(group_by="admin_email")
            self.assertIn("stats", result)

    def test_delete_admin_actions(self):
        """管理者操作ログ削除テスト（クリーンアップ用）"""
        with patch("database.get_db") as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = self.db

            from database.models import delete_admin_actions_before_date
            from config.timezone import get_app_now, add_app_timedelta

            # 1日前より古いログを削除
            cutoff_date = add_app_timedelta(get_app_now(), days=-1)

            result = delete_admin_actions_before_date(
                cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
            )
            self.assertIsInstance(result, int)  # 削除件数が返される

    def test_risk_level_classification(self):
        """リスクレベル分類テスト"""
        with patch("database.get_db") as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = self.db

            from database.models import get_risk_level_for_action

            # 低リスク操作
            risk = get_risk_level_for_action("user_view")
            self.assertEqual(risk, "low")

            # 中リスク操作
            risk = get_risk_level_for_action("setting_update")
            self.assertEqual(risk, "medium")

            # 高リスク操作
            risk = get_risk_level_for_action("user_delete")
            self.assertEqual(risk, "high")

            # 重要リスク操作
            risk = get_risk_level_for_action("system_maintenance")
            self.assertEqual(risk, "critical")

    def test_log_admin_action_error_handling(self):
        """エラーハンドリングテスト"""
        with patch("database.get_db") as mock_get_db:
            # データベースエラーをシミュレート
            mock_db = MagicMock()
            mock_db.execute.side_effect = sqlite3.Error("Database error")
            mock_get_db.return_value.__enter__.return_value = mock_db

            from database.models import log_admin_action

            result = log_admin_action(
                admin_email="admin@example.com",
                action_type="user_view",
                ip_address="192.168.1.100",
            )

            # エラー時はFalseを返すことを確認
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
