"""
TASK-021 Sub-Phase 3C: 監査ログ分析機能のテストコード

監査ログ分析画面（/admin/audit-logs）の機能をテストします：
1. 監査ログ検索・フィルタリング機能
2. 統計情報生成機能
3. エクスポート機能
4. Chart.js用データ生成機能
"""

import json
import os
import sys
from datetime import datetime
from unittest.mock import patch

import pytest

# アプリケーションインポート
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from config.timezone import (
    get_app_now,
    get_app_datetime_string,
    add_app_timedelta,
)


class TestAuditLogAnalysis:
    """監査ログ分析機能のテストクラス"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """テストセットアップ"""
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        # テスト用の管理者セッション設定
        with self.client.session_transaction() as sess:
            sess["email"] = "admin@example.com"
            sess["is_admin"] = True
            sess["session_id"] = "test_session_123"
            sess["admin_session_id"] = "admin_session_123"
            sess["csrf_token"] = "test_csrf_token"

    def test_audit_logs_page_access(self):
        """監査ログ画面へのアクセステスト"""
        with patch("database.models.is_admin", return_value=True), \
             patch("database.models.verify_admin_session", return_value=True), \
             patch("database.models.get_admin_action_stats", return_value={}), \
             patch("app.require_admin_session", lambda f: f):
            
            response = self.client.get("/admin/audit-logs")

            assert response.status_code == 200

    def test_audit_logs_api_search_basic(self):
        """監査ログAPI基本検索機能テスト"""
        test_actions = [{
            "admin_email": "admin@example.com",
            "action_type": "user_update",
            "resource_type": "user",
            "risk_level": "medium",
            "created_at": get_app_datetime_string(),
            "success": True,
        }]

        with patch("database.models.is_admin", return_value=True), \
             patch("database.models.verify_admin_session", return_value=True), \
             patch("database.models.get_admin_actions", return_value=test_actions), \
             patch("app.require_admin_api_access", lambda f: f), \
             patch("app.log_admin_operation", lambda *args, **kwargs: lambda f: f):

            response = self.client.get("/admin/api/audit-logs")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert "actions" in data
            assert "pagination" in data
            assert "filters" in data

    def test_audit_logs_api_stats_basic(self):
        """監査ログ統計API基本機能テスト"""
        test_stats = {
            "total_actions": 150,
            "action_type_counts": {"user_update": 45, "setting_update": 30},
            "risk_level_counts": {"low": 75, "medium": 45, "high": 25, "critical": 5},
        }

        with patch("database.models.is_admin", return_value=True), \
             patch("database.models.verify_admin_session", return_value=True), \
             patch("database.models.get_admin_action_stats", return_value=test_stats), \
             patch("app.require_admin_api_access", lambda f: f), \
             patch("app.log_admin_operation", lambda *args, **kwargs: lambda f: f):

            response = self.client.get("/admin/api/audit-logs/stats")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert data["total_actions"] == 150
            assert "action_type_counts" in data
            assert "risk_level_counts" in data

    def test_audit_logs_api_export_csv(self):
        """監査ログCSVエクスポート機能テスト"""
        test_actions = [{
            "id": 1,
            "admin_email": "admin@example.com",
            "action_type": "user_update",
            "resource_type": "user",
            "resource_id": "user123",
            "created_at": "2025-09-01 10:00:00",
            "risk_level": "medium",
            "success": True,
            "ip_address": "127.0.0.1",
        }]

        with patch("database.models.is_admin", return_value=True), \
             patch("database.models.verify_admin_session", return_value=True), \
             patch("database.models.get_admin_actions", return_value=test_actions), \
             patch("app.require_admin_api_access", lambda f: f), \
             patch("app.log_admin_operation", lambda *args, **kwargs: lambda f: f):

            response = self.client.get("/admin/api/audit-logs/export?format=csv")
            assert response.status_code == 200
            assert "text/csv" in response.headers.get("Content-Type", "")

    def test_audit_logs_api_export_json(self):
        """監査ログJSONエクスポート機能テスト"""
        test_actions = [{
            "id": 1,
            "admin_email": "admin@example.com",
            "action_type": "user_update"
        }]

        with patch("database.models.is_admin", return_value=True), \
             patch("database.models.verify_admin_session", return_value=True), \
             patch("database.models.get_admin_actions", return_value=test_actions), \
             patch("app.require_admin_api_access", lambda f: f), \
             patch("app.log_admin_operation", lambda *args, **kwargs: lambda f: f):

            response = self.client.get("/admin/api/audit-logs/export?format=json")
            assert response.status_code == 200
            assert "application/json" in response.headers.get("Content-Type", "")

    def test_audit_logs_api_chart_data(self):
        """監査ログChart.js用データ生成テスト"""
        test_chart_data = {
            "labels": ["admin@example.com", "admin2@example.com"],
            "datasets": [{
                "label": "管理者別操作数",
                "data": [75, 45],
                "backgroundColor": ["#007bff", "#28a745"],
            }],
        }

        with patch("database.models.is_admin", return_value=True), \
             patch("database.models.verify_admin_session", return_value=True), \
             patch("database.models.get_admin_action_stats", return_value=test_chart_data), \
             patch("app.require_admin_api_access", lambda f: f), \
             patch("app.log_admin_operation", lambda *args, **kwargs: lambda f: f):

            response = self.client.get("/admin/api/audit-logs/chart-data?type=admin_activity")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert "labels" in data
            assert "datasets" in data

    def test_audit_logs_unauthorized_access(self):
        """非管理者アクセス拒否テスト"""
        # 非管理者セッション
        with self.client.session_transaction() as sess:
            sess.clear()
            sess["email"] = "user@example.com"
            sess["is_admin"] = False

        with patch("database.models.is_admin", return_value=False):
            # 画面アクセス
            response = self.client.get("/admin/audit-logs")
            assert response.status_code in [302, 401, 403]

            # API アクセス
            response = self.client.get("/admin/api/audit-logs")
            assert response.status_code in [401, 403]

    def test_audit_logs_filtering_parameters(self):
        """監査ログフィルタリングパラメータテスト"""
        test_actions = []

        with patch("database.models.is_admin", return_value=True), \
             patch("database.models.verify_admin_session", return_value=True), \
             patch("database.models.get_admin_actions") as mock_get_actions, \
             patch("app.require_admin_api_access", lambda f: f), \
             patch("app.log_admin_operation", lambda *args, **kwargs: lambda f: f):

            mock_get_actions.return_value = test_actions

            # 複数フィルタ条件
            response = self.client.get(
                "/admin/api/audit-logs"
                "?admin_email=admin@example.com"
                "&action_type=user_update"
                "&risk_level=high"
                "&start_date=2025-09-01"
                "&end_date=2025-09-01"
                "&success=true"
                "&page=1"
                "&limit=25"
            )

            assert response.status_code == 200

            # get_admin_actions が適切なパラメータで呼ばれたことを確認
            mock_get_actions.assert_called_once()
            call_kwargs = mock_get_actions.call_args[1]
            assert call_kwargs["admin_email"] == "admin@example.com"
            assert call_kwargs["action_type"] == "user_update"
            assert call_kwargs["risk_level"] == "high"

    def test_audit_logs_action_details(self):
        """監査ログ詳細情報API機能テスト"""
        with patch("database.models.is_admin", return_value=True), \
             patch("database.models.verify_admin_session", return_value=True), \
             patch("database.models.get_database_connection") as mock_conn, \
             patch("app.require_admin_api_access", lambda f: f), \
             patch("app.log_admin_operation", lambda *args, **kwargs: lambda f: f):

            # モックデータベース接続
            mock_cursor = mock_conn.return_value.cursor.return_value
            mock_cursor.fetchone.return_value = (
                1, "admin@example.com", "user_update", "user", "user123",
                '{"test": "data"}', None, None, "2025-09-01 10:00:00",
                "medium", True, None, "127.0.0.1", "Test Agent",
                "session123", "admin_session123", "request123"
            )

            response = self.client.get("/admin/api/audit-logs/action-details/1")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert data["id"] == 1
            assert data["admin_email"] == "admin@example.com"
            assert data["action_type"] == "user_update"

    def test_audit_logs_timezone_consistency(self):
        """監査ログタイムゾーン一貫性テスト"""
        app_time = get_app_now()
        formatted_time = app_time.strftime("%Y-%m-%d %H:%M:%S")

        test_action = {
            "id": 1,
            "admin_email": "admin@example.com",
            "action_type": "user_view",
            "created_at": formatted_time,
            "success": True,
        }

        with patch("database.models.is_admin", return_value=True), \
             patch("database.models.verify_admin_session", return_value=True), \
             patch("database.models.get_admin_actions", return_value=[test_action]), \
             patch("app.require_admin_api_access", lambda f: f), \
             patch("app.log_admin_operation", lambda *args, **kwargs: lambda f: f):

            response = self.client.get("/admin/api/audit-logs")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert len(data["actions"]) == 1

            # 時刻形式が期待する形式であることを確認
            action = data["actions"][0]
            datetime.strptime(action["created_at"], "%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])