"""
TASK-021 Phase 3B: 管理者操作デコレータのテストコード

Sub-Phase 3B実装項目:
1. @log_admin_operation デコレータの単体テスト
2. 状態キャプチャ機能のテスト  
3. エラーハンドリングのテスト
4. 既存エンドポイントとの統合テスト
"""
import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import sqlite3
import sys

# テスト用のアプリケーションコンテキスト設定
sys.path.insert(0, "/home/ope/secure-pdf-viewer")

from database import init_db
from database.models import (
    create_admin_session,
    log_admin_action,
    get_admin_actions,
)


class TestAdminOperationDecorator:
    """管理者操作デコレータのテストクラス"""

    @pytest.fixture
    def temp_db(self):
        """テスト用の一時データベース"""
        db_fd, db_path = tempfile.mkstemp()
        os.environ["DATABASE_PATH"] = db_path

        # データベースを初期化
        init_db()

        yield db_path

        # クリーンアップ
        os.close(db_fd)
        os.unlink(db_path)

    @pytest.fixture
    def mock_flask_app(self):
        """Flask アプリケーションのモック"""
        app_mock = Mock()
        request_mock = Mock()
        session_mock = {}

        # Flask のグローバルオブジェクトをモック
        with patch("app.request", request_mock), patch("app.session", session_mock):
            # リクエスト情報設定
            request_mock.remote_addr = "192.168.1.100"
            request_mock.headers = {"User-Agent": "TestBrowser/1.0"}
            request_mock.method = "POST"
            request_mock.endpoint = "/admin/api/test"

            # セッション情報設定
            session_mock["email"] = "admin@example.com"
            session_mock["session_id"] = "test-session-id"
            session_mock["admin_session_id"] = "admin-session-123"
            session_mock["is_admin"] = True

            yield {"app": app_mock, "request": request_mock, "session": session_mock}

    def test_decorator_basic_functionality(self, temp_db, mock_flask_app):
        """基本的なデコレータ機能のテスト"""
        from app import log_admin_operation

        @log_admin_operation("test_action", "test_resource", risk_level="low")
        def test_function():
            return "success"

        # デコレータ付き関数を実行
        result = test_function()

        # 戻り値の確認
        assert result == "success"

        # ログが記録されているかチェック
        logs = get_admin_actions(admin_email="admin@example.com", limit=1)
        assert len(logs["actions"]) == 1

        log_entry = logs["actions"][0]
        assert log_entry["admin_email"] == "admin@example.com"
        assert log_entry["action_type"] == "test_action"
        assert log_entry["resource_type"] == "test_resource"
        assert log_entry["risk_level"] == "low"
        assert log_entry["success"] == True
        assert log_entry["ip_address"] == "192.168.1.100"

    def test_decorator_with_arguments(self, temp_db, mock_flask_app):
        """引数付きデコレータのテスト"""
        from app import log_admin_operation

        @log_admin_operation("user_update", "user", risk_level="medium")
        def update_user(user_id, name=None, email=None):
            return f"Updated user {user_id}: {name}, {email}"

        # 引数付きで実行
        result = update_user("123", name="Test User", email="test@example.com")

        # 戻り値の確認
        assert result == "Updated user 123: Test User, test@example.com"

        # ログの詳細確認
        logs = get_admin_actions(action_type="user_update", limit=1)
        assert len(logs["actions"]) == 1

        log_entry = logs["actions"][0]
        assert log_entry["action_type"] == "user_update"
        assert log_entry["resource_type"] == "user"
        assert log_entry["risk_level"] == "medium"

        # action_details の確認
        details = json.loads(log_entry["action_details"])
        assert details["args"] == ["123"]
        assert details["kwargs"] == {"name": "Test User", "email": "test@example.com"}

    def test_decorator_error_handling(self, temp_db, mock_flask_app):
        """エラーハンドリングのテスト"""
        from app import log_admin_operation

        @log_admin_operation("error_action", "test_resource", risk_level="high")
        def error_function():
            raise ValueError("Test error message")

        # エラーが発生する関数の実行
        with pytest.raises(ValueError, match="Test error message"):
            error_function()

        # エラーログが記録されているかチェック
        logs = get_admin_actions(success=False, limit=1)
        assert len(logs["actions"]) == 1

        error_log = logs["actions"][0]
        assert error_log["action_type"] == "error_action"
        assert error_log["success"] == False
        assert error_log["error_message"] == "Test error message"
        assert error_log["risk_level"] == "high"

    def test_state_capture_functionality(self, temp_db, mock_flask_app):
        """状態キャプチャ機能のテスト"""
        from app import log_admin_operation, capture_current_state

        # 状態キャプチャ関数をモック
        with patch("app.capture_current_state") as mock_capture:
            mock_capture.side_effect = [
                {"name": "Before State", "value": "old_value"},  # before_state
                {"name": "After State", "value": "new_value"},  # after_state
            ]

            @log_admin_operation(
                "setting_update", "setting", capture_state=True, risk_level="medium"
            )
            def update_setting(setting_key, value):
                return f"Updated {setting_key} = {value}"

            # 状態キャプチャ付きで実行
            result = update_setting("test_key", "test_value")

            # 戻り値の確認
            assert result == "Updated test_key = test_value"

            # モック関数が2回呼ばれているかチェック（before/after）
            assert mock_capture.call_count == 2

            # ログの状態情報確認
            logs = get_admin_actions(action_type="setting_update", limit=1)
            assert len(logs["actions"]) == 1

            log_entry = logs["actions"][0]
            before_state = json.loads(log_entry["before_state"])
            after_state = json.loads(log_entry["after_state"])

            assert before_state["name"] == "Before State"
            assert before_state["value"] == "old_value"
            assert after_state["name"] == "After State"
            assert after_state["value"] == "new_value"

    def test_state_capture_with_error(self, temp_db, mock_flask_app):
        """状態キャプチャ中のエラーテスト"""
        from app import log_admin_operation, capture_current_state

        # 状態キャプチャ関数をモック（エラー発生）
        with patch("app.capture_current_state") as mock_capture:
            mock_capture.return_value = {"name": "Before State"}

            @log_admin_operation(
                "failing_action", "test_resource", capture_state=True, risk_level="high"
            )
            def failing_function():
                raise RuntimeError("Function failed")

            # エラーが発生する関数の実行
            with pytest.raises(RuntimeError, match="Function failed"):
                failing_function()

            # before_state だけ記録されているかチェック
            logs = get_admin_actions(success=False, limit=1)
            assert len(logs["actions"]) == 1

            error_log = logs["actions"][0]
            assert error_log["success"] == False
            assert error_log["error_message"] == "Function failed"

            # before_state は記録されているが after_state は null
            assert json.loads(error_log["before_state"])["name"] == "Before State"
            assert error_log["after_state"] is None

    def test_decorator_without_admin_session(self, temp_db, mock_flask_app):
        """管理者セッションなしでのデコレータテスト"""
        from app import log_admin_operation

        # セッション情報をクリア
        mock_flask_app["session"].clear()

        @log_admin_operation("unauthorized_action", "test_resource")
        def unauthorized_function():
            return "unauthorized result"

        # セッション情報なしで実行
        result = unauthorized_function()

        # 戻り値は正常
        assert result == "unauthorized result"

        # ログは記録されているが admin_email は None
        logs = get_admin_actions(limit=1)
        assert len(logs["actions"]) == 1

        log_entry = logs["actions"][0]
        assert log_entry["admin_email"] is None
        assert log_entry["action_type"] == "unauthorized_action"
        assert log_entry["session_id"] is None
        assert log_entry["admin_session_id"] is None

    def test_multiple_decorators_integration(self, temp_db, mock_flask_app):
        """複数デコレータとの統合テスト"""
        from app import log_admin_operation

        def dummy_decorator(func):
            def wrapper(*args, **kwargs):
                result = func(*args, **kwargs)
                return f"decorated: {result}"

            return wrapper

        @dummy_decorator
        @log_admin_operation(
            "multi_decorator_action", "test_resource", risk_level="low"
        )
        def multi_decorated_function():
            return "original result"

        # 複数デコレータ付き関数の実行
        result = multi_decorated_function()

        # デコレータが適用された戻り値
        assert result == "decorated: original result"

        # ログが正常に記録されているかチェック
        logs = get_admin_actions(action_type="multi_decorator_action", limit=1)
        assert len(logs["actions"]) == 1

        log_entry = logs["actions"][0]
        assert log_entry["action_type"] == "multi_decorator_action"
        assert log_entry["success"] == True

    def test_performance_overhead(self, temp_db, mock_flask_app):
        """パフォーマンスオーバーヘッドテスト"""
        from app import log_admin_operation
        import time

        @log_admin_operation("performance_test", "test_resource")
        def performance_function():
            time.sleep(0.01)  # 10ms の処理時間をシミュレート
            return "performance test"

        # 実行時間測定
        start_time = time.time()
        result = performance_function()
        end_time = time.time()

        execution_time = (end_time - start_time) * 1000  # ms変換

        # 戻り値の確認
        assert result == "performance test"

        # オーバーヘッドが50ms未満であることを確認（設計要件）
        assert execution_time < 60  # 10ms処理時間 + 50msオーバーヘッド上限

        # ログが記録されているかチェック
        logs = get_admin_actions(action_type="performance_test", limit=1)
        assert len(logs["actions"]) == 1


class TestAdminActionTypes:
    """管理者操作種別のテスト"""

    def test_risk_level_classification(self):
        """リスクレベル分類のテスト"""
        from app import RISK_LEVELS, classify_risk_level

        # 各リスクレベルの操作をテスト
        assert classify_risk_level("admin_login") == "low"
        assert classify_risk_level("user_view") == "low"
        assert classify_risk_level("setting_view") == "low"

        assert classify_risk_level("user_update") == "medium"
        assert classify_risk_level("setting_update") == "medium"
        assert classify_risk_level("log_export") == "medium"

        assert classify_risk_level("user_delete") == "high"
        assert classify_risk_level("permission_change") == "high"
        assert classify_risk_level("emergency_stop") == "high"

        assert classify_risk_level("system_maintenance") == "critical"
        assert classify_risk_level("security_config") == "critical"
        assert classify_risk_level("bulk_operation") == "critical"

        # 未定義の操作はデフォルト（medium）
        assert classify_risk_level("unknown_action") == "medium"


class TestStateCapture:
    """状態キャプチャ機能のテスト"""

    @pytest.fixture
    def temp_db(self):
        """テスト用の一時データベース"""
        db_fd, db_path = tempfile.mkstemp()
        os.environ["DATABASE_PATH"] = db_path

        # データベースを初期化
        init_db()

        yield db_path

        # クリーンアップ
        os.close(db_fd)
        os.unlink(db_path)

    def test_capture_user_state(self):
        """ユーザー状態キャプチャのテスト"""
        from app import capture_current_state

        # ユーザー状態キャプチャのテスト
        kwargs = {"user_id": "123", "email": "test@example.com"}
        state = capture_current_state("user", kwargs)

        assert state is not None
        assert isinstance(state, dict)

        # 状態にユーザー情報が含まれているかチェック
        assert "user_id" in state
        assert "captured_at" in state

    def test_capture_setting_state(self):
        """設定状態キャプチャのテスト"""
        from app import capture_current_state

        # 設定状態キャプチャのテスト
        kwargs = {"setting_key": "pdf_max_size", "value": "10MB"}
        state = capture_current_state("setting", kwargs)

        assert state is not None
        assert isinstance(state, dict)

        # 状態に設定情報が含まれているかチェック
        assert "setting_key" in state
        assert "captured_at" in state

    def test_capture_unknown_resource_type(self):
        """未知のリソース種別の状態キャプチャテスト"""
        from app import capture_current_state

        # 未知のリソース種別
        kwargs = {"unknown_param": "value"}
        state = capture_current_state("unknown_resource", kwargs)

        # 未知のリソースでも基本的な状態情報は返される
        assert state is not None
        assert isinstance(state, dict)
        assert "captured_at" in state
        assert "resource_type" in state
        assert state["resource_type"] == "unknown_resource"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
