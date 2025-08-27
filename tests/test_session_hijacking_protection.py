"""
Sub-Phase 1D: セッションハイジャック対策機能のテストコード
TASK-021 セキュリティ強化プロジェクト
"""

import pytest
import sqlite3
import tempfile
import os
import json
from datetime import datetime, timedelta
from database.models import (
    create_tables,
    insert_initial_data,
    create_admin_session,
    regenerate_admin_session_id,
    verify_session_environment,
    detect_session_anomalies,
    get_admin_session_info
)


@pytest.fixture
def temp_db(monkeypatch):
    """テスト用の一時データベースを作成"""
    temp_fd, temp_path = tempfile.mkstemp(suffix='.db')
    os.close(temp_fd)
    
    # データベース初期化
    conn = sqlite3.connect(temp_path)
    conn.row_factory = sqlite3.Row  # 辞書形式でアクセス可能にする
    try:
        create_tables(conn)
        insert_initial_data(conn)
        conn.commit()
    finally:
        conn.close()
    
    # データベースモジュールのDATABASE_PATHをパッチ
    import database
    monkeypatch.setattr(database, 'DATABASE_PATH', temp_path)
    
    yield temp_path
    
    # クリーンアップ
    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestSessionHijackingProtection:
    """セッションハイジャック対策機能のテスト"""
    
    def test_regenerate_admin_session_id_success(self, temp_db):
        """セッションID再生成の成功テスト"""
        admin_email = "admin@test.com"
        old_session_id = "old_session_123"
        new_session_id = "new_session_456"
        ip_address = "192.168.1.100"
        user_agent = "Mozilla/5.0 Test Browser"
        
        # 元のセッション作成
        assert create_admin_session(admin_email, old_session_id, ip_address, user_agent, 
                                   security_flags={"ip_binding_enabled": True})
        
        # セッションID再生成
        result = regenerate_admin_session_id(old_session_id, new_session_id)
        assert result is True
        
        # 新しいセッションIDでセッション情報取得
        session_info = get_admin_session_info(new_session_id)
        assert session_info is not None
        assert session_info["admin_email"] == admin_email
        assert session_info["ip_address"] == ip_address
        
        # セキュリティフラグに再生成履歴があることを確認
        security_flags = json.loads(session_info["security_flags"])
        assert security_flags["session_regenerated"] is True
        assert "regenerated_at" in security_flags
        assert security_flags["old_session_id"] == "old_sess..."
        
        # 古いセッションIDではアクセスできないことを確認
        old_session_info = get_admin_session_info(old_session_id)
        assert old_session_info is None
    
    def test_regenerate_admin_session_id_invalid_input(self, temp_db):
        """セッションID再生成の無効入力テスト"""
        # 無効な入力でのテスト
        assert regenerate_admin_session_id(None, "new_session") is False
        assert regenerate_admin_session_id("old_session", None) is False
        assert regenerate_admin_session_id("", "new_session") is False
        
        # 存在しないセッションIDでのテスト
        result = regenerate_admin_session_id("nonexistent_session", "new_session")
        assert result is False
    
    def test_verify_session_environment_valid_session(self, temp_db):
        """セッション環境検証の正常ケーステスト"""
        admin_email = "admin@test.com"
        session_id = "test_session_123"
        ip_address = "192.168.1.100"
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        # セッション作成
        assert create_admin_session(admin_email, session_id, ip_address, user_agent,
                                   security_flags={"ip_binding_enabled": True})
        
        # 正常な環境での検証
        result = verify_session_environment(session_id, ip_address, user_agent)
        
        assert result["valid"] is True
        # 新しいセッション（1分以内）なのでmediumが正常
        assert result["risk_level"] in ["low", "medium"]
        # 新しいセッションの警告はあり得る
        if result["risk_level"] == "medium":
            assert any("Very new session" in warning for warning in result["warnings"])
        assert result["ip_match"] is True
        assert result["has_verification_token"] is True
    
    def test_verify_session_environment_ip_change(self, temp_db):
        """IPアドレス変更検出テスト"""
        admin_email = "admin@test.com"
        session_id = "test_session_124"
        original_ip = "192.168.1.100"
        new_ip = "10.0.0.50"
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        # IPバインディング有効でセッション作成
        assert create_admin_session(admin_email, session_id, original_ip, user_agent,
                                   security_flags={"ip_binding_enabled": True})
        
        # 異なるIPからのアクセス
        result = verify_session_environment(session_id, new_ip, user_agent)
        
        assert result["valid"] is False  # IPバインディング有効時は無効
        assert result["risk_level"] == "high"
        assert any("IP address changed" in warning for warning in result["warnings"])
        assert result["ip_match"] is False
    
    def test_verify_session_environment_user_agent_change(self, temp_db):
        """ユーザーエージェント変更検出テスト"""
        admin_email = "admin@test.com"
        session_id = "test_session_125"
        ip_address = "192.168.1.100"
        original_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        new_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
        
        # セッション作成
        assert create_admin_session(admin_email, session_id, ip_address, original_ua)
        
        # 異なるユーザーエージェントからのアクセス
        result = verify_session_environment(session_id, ip_address, new_ua)
        
        assert result["valid"] is True  # UAの変更は警告のみ
        assert result["risk_level"] == "medium"
        assert any("User agent changed" in warning for warning in result["warnings"])
    
    def test_verify_session_environment_invalid_session(self, temp_db):
        """無効なセッションの検証テスト"""
        # 存在しないセッション
        result = verify_session_environment("nonexistent_session", "192.168.1.100", "Mozilla/5.0")
        
        assert result["valid"] is False
        assert result["risk_level"] == "high"
        assert any("Session not found" in warning for warning in result["warnings"])
    
    def test_detect_session_anomalies_normal_session(self, temp_db):
        """正常セッションの異常検出テスト"""
        admin_email = "admin@test.com"
        session_id = "normal_session_123"
        ip_address = "192.168.1.100"
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        # 正常なセッション作成
        assert create_admin_session(admin_email, session_id, ip_address, user_agent)
        
        # 異常検出
        result = detect_session_anomalies(admin_email, session_id, ip_address, user_agent)
        
        assert result["anomalies_detected"] is False
        assert result["action_required"] == "allow"
        assert len(result["anomaly_types"]) == 0
        assert result["active_sessions_count"] == 1
    
    def test_detect_session_anomalies_multiple_sessions(self, temp_db):
        """複数セッション異常検出テスト"""
        admin_email = "admin@test.com"
        ip_address = "192.168.1.100"
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        # 複数のセッションを作成
        session1 = "multi_session_1"
        session2 = "multi_session_2"
        
        assert create_admin_session(admin_email, session1, ip_address, user_agent)
        assert create_admin_session(admin_email, session2, ip_address, user_agent)
        
        # 異常検出（session1から実行）
        result = detect_session_anomalies(admin_email, session1, ip_address, user_agent)
        
        assert result["anomalies_detected"] is True
        assert "multiple_active_sessions" in result["anomaly_types"]
        assert result["action_required"] == "warn"
        assert result["active_sessions_count"] == 2
    
    def test_detect_session_anomalies_multiple_ip_sessions(self, temp_db):
        """異なるIPでの複数セッション異常検出テスト"""
        admin_email = "admin@test.com"
        ip1 = "192.168.1.100"
        ip2 = "10.0.0.50"
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        # 異なるIPで複数セッション作成
        session1 = "multi_ip_session_1"
        session2 = "multi_ip_session_2"
        
        assert create_admin_session(admin_email, session1, ip1, user_agent)
        assert create_admin_session(admin_email, session2, ip2, user_agent)
        
        # 異常検出（session1から実行）
        result = detect_session_anomalies(admin_email, session1, ip1, user_agent)
        
        assert result["anomalies_detected"] is True
        assert "multiple_active_sessions" in result["anomaly_types"]
        assert "multiple_ip_sessions" in result["anomaly_types"]
        assert result["action_required"] == "block"
    
    def test_detect_session_anomalies_rapid_session_creation(self, temp_db):
        """短時間での複数セッション作成異常検出テスト"""
        admin_email = "admin@test.com"
        ip_address = "192.168.1.100"
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        # 短時間で3つのセッション作成
        sessions = ["rapid_session_1", "rapid_session_2", "rapid_session_3"]
        for session_id in sessions:
            assert create_admin_session(admin_email, session_id, ip_address, user_agent)
        
        # 異常検出
        result = detect_session_anomalies(admin_email, sessions[0], ip_address, user_agent)
        
        assert result["anomalies_detected"] is True
        assert "rapid_session_creation" in result["anomaly_types"]
        assert result["action_required"] == "block"
    
    def test_detect_session_anomalies_browser_change(self, temp_db):
        """ブラウザ変更検出テスト"""
        admin_email = "admin@test.com"
        session_id = "browser_change_session"
        ip_address = "192.168.1.100"
        original_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        new_ua = "Chrome/91.0.4472.124 Safari/537.36"
        
        # セッション作成
        assert create_admin_session(admin_email, session_id, ip_address, original_ua)
        
        # ブラウザ変更での異常検出
        result = detect_session_anomalies(admin_email, session_id, ip_address, new_ua)
        
        assert result["anomalies_detected"] is True
        assert "browser_change" in result["anomaly_types"]
        assert result["action_required"] == "warn"
    
    def test_detect_session_anomalies_invalid_input(self, temp_db):
        """異常検出の無効入力テスト"""
        # 無効な入力での異常検出
        result = detect_session_anomalies(None, "session_id", "192.168.1.100", "Mozilla/5.0")
        assert result["anomalies_detected"] is True
        assert "invalid_input" in result["anomaly_types"]
        assert result["action_required"] == "block"
        
        result = detect_session_anomalies("admin@test.com", None, "192.168.1.100", "Mozilla/5.0")
        assert result["anomalies_detected"] is True
        assert "invalid_input" in result["anomaly_types"]
        assert result["action_required"] == "block"
        
        # 存在しないセッション
        result = detect_session_anomalies("admin@test.com", "nonexistent", "192.168.1.100", "Mozilla/5.0")
        assert result["anomalies_detected"] is True
        assert "session_not_found" in result["anomaly_types"]
        assert result["action_required"] == "block"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])