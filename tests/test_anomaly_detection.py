"""
TASK-021 Sub-Phase 3D: 異常検出機能テスト

管理者操作の異常パターン検出機能のテストコード
"""

import unittest
import tempfile
import os
import json
from unittest.mock import patch, MagicMock
import sys
from datetime import datetime, timedelta

# プロジェクトルートをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import (
    create_tables, get_db_connection,
    log_admin_action, get_admin_actions
)
from config.timezone import get_app_datetime_string, get_app_now


class TestAnomalyDetection(unittest.TestCase):
    """異常検出機能のテストクラス"""
    
    def setUp(self):
        """各テスト実行前の準備"""
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.test_db.close()
        self.db_path = self.test_db.name
        
        # テスト用データベース初期化
        with patch('database.models.DATABASE_PATH', self.db_path):
            conn = get_db_connection()
            create_tables(conn)
            conn.close()
            
        # テスト用管理者データ
        self.test_admin = "admin@test.com"
        self.test_ip = "192.168.1.100"
        self.test_user_agent = "Mozilla/5.0 Test Browser"
        
        # 基本操作データ
        self.base_action = {
            "admin_email": self.test_admin,
            "ip_address": self.test_ip,
            "user_agent": self.test_user_agent,
            "session_id": "test_session_123",
            "admin_session_id": "admin_session_456",
            "success": True,
            "error_message": None
        }
    
    def tearDown(self):
        """各テスト実行後のクリーンアップ"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def _create_test_actions(self, actions_data):
        """テスト用の操作ログを作成"""
        with patch('database.models.DATABASE_PATH', self.db_path):
            for action_data in actions_data:
                action = self.base_action.copy()
                action.update(action_data)
                log_admin_action(**action)
    
    def test_detect_bulk_operations_normal(self):
        """通常操作（大量操作なし）の検出テスト"""
        try:
            from security.anomaly_detector import detect_admin_anomalies
        except ImportError:
            self.skipTest("security.anomaly_detector module not implemented yet")
            
        # 通常の操作数（5分間に3操作）
        actions = []
        now = get_app_now()
        for i in range(3):
            actions.append({
                "action_type": "view_logs",
                "resource_type": "audit_logs",
                "risk_level": "low",
                "action_details": {"page": i + 1},
                # 5分間に分散
                "created_at": (now - timedelta(minutes=4-i)).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        self._create_test_actions(actions)
        
        # 異常検出実行
        result = detect_admin_anomalies(self.test_admin, timeframe=300)  # 5分
        
        # 大量操作異常が検出されないことを確認
        self.assertFalse(result["anomalies_detected"])
        self.assertNotIn("bulk_operations", result["anomaly_types"])
        self.assertLessEqual(result["risk_score"], 30)  # 低リスク
    
    def test_detect_bulk_operations_anomaly(self):
        """大量操作異常の検出テスト"""
        try:
            from security.anomaly_detector import detect_admin_anomalies
        except ImportError:
            self.skipTest("security.anomaly_detector module not implemented yet")
            
        # 異常な操作数（5分間に15操作）
        actions = []
        now = get_app_now()
        for i in range(15):
            actions.append({
                "action_type": "settings_update",
                "resource_type": "security_settings",
                "risk_level": "high",
                "action_details": {"setting_" + str(i): "value"},
                # 5分間に集中
                "created_at": (now - timedelta(minutes=4, seconds=i*20)).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        self._create_test_actions(actions)
        
        # 異常検出実行
        result = detect_admin_anomalies(self.test_admin, timeframe=300)  # 5分
        
        # 大量操作異常が検出されることを確認
        self.assertTrue(result["anomalies_detected"])
        self.assertIn("bulk_operations", result["anomaly_types"])
        self.assertGreaterEqual(result["risk_score"], 60)  # 高リスク
        self.assertIn("大量操作", "\n".join(result["recommendations"]))
    
    def test_detect_night_access_normal(self):
        """通常時間帯アクセスの検出テスト"""
        try:
            from security.anomaly_detector import detect_admin_anomalies
        except ImportError:
            self.skipTest("security.anomaly_detector module not implemented yet")
            
        # 通常時間帯（午前10時）の操作
        normal_time = datetime.now().replace(hour=10, minute=0, second=0)
        actions = [{
            "action_type": "view_dashboard",
            "resource_type": "admin_dashboard",
            "risk_level": "low",
            "action_details": {"view": "main"},
            "created_at": normal_time.strftime('%Y-%m-%d %H:%M:%S')
        }]
        
        self._create_test_actions(actions)
        
        # 異常検出実行
        result = detect_admin_anomalies(self.test_admin, timeframe=3600)  # 1時間
        
        # 深夜アクセス異常が検出されないことを確認
        self.assertFalse(result["anomalies_detected"])
        self.assertNotIn("night_access", result["anomaly_types"])
    
    def test_detect_night_access_anomaly(self):
        """深夜アクセス異常の検出テスト"""
        try:
            from security.anomaly_detector import detect_admin_anomalies
        except ImportError:
            self.skipTest("security.anomaly_detector module not implemented yet")
            
        # 深夜時間帯（午前3時）の操作
        night_time = datetime.now().replace(hour=3, minute=30, second=0)
        actions = [{
            "action_type": "settings_update",
            "resource_type": "security_settings", 
            "risk_level": "high",
            "action_details": {"critical_setting": "changed"},
            "created_at": night_time.strftime('%Y-%m-%d %H:%M:%S')
        }]
        
        self._create_test_actions(actions)
        
        # 異常検出実行
        result = detect_admin_anomalies(self.test_admin, timeframe=3600)  # 1時間
        
        # 深夜アクセス異常が検出されることを確認
        self.assertTrue(result["anomalies_detected"])
        self.assertIn("night_access", result["anomaly_types"])
        self.assertGreaterEqual(result["risk_score"], 40)
        self.assertIn("深夜", "\n".join(result["recommendations"]))
    
    def test_detect_ip_changes_normal(self):
        """通常IP使用の検出テスト"""
        try:
            from security.anomaly_detector import detect_admin_anomalies
        except ImportError:
            self.skipTest("security.anomaly_detector module not implemented yet")
            
        # 同一IPからの複数操作
        actions = []
        for i in range(5):
            actions.append({
                "action_type": "view_logs",
                "resource_type": "audit_logs",
                "risk_level": "low",
                "action_details": {"page": i + 1}
            })
        
        self._create_test_actions(actions)
        
        # 異常検出実行
        result = detect_admin_anomalies(self.test_admin, timeframe=3600)  # 1時間
        
        # IP変更異常が検出されないことを確認
        self.assertFalse(result["anomalies_detected"])
        self.assertNotIn("ip_changes", result["anomaly_types"])
    
    def test_detect_ip_changes_anomaly(self):
        """IP変更異常の検出テスト"""
        try:
            from security.anomaly_detector import detect_admin_anomalies
        except ImportError:
            self.skipTest("security.anomaly_detector module not implemented yet")
            
        # 異なるIPからの操作（1時間に5回IP変更）
        ips = ["192.168.1.100", "10.0.1.50", "172.16.1.200", "203.0.113.10", "198.51.100.5"]
        actions = []
        now = get_app_now()
        
        for i, ip in enumerate(ips):
            action = self.base_action.copy()
            action.update({
                "action_type": "settings_update",
                "resource_type": "security_settings",
                "risk_level": "medium",
                "ip_address": ip,
                "action_details": {"from_ip": ip},
                "created_at": (now - timedelta(minutes=50-i*10)).strftime('%Y-%m-%d %H:%M:%S')
            })
            actions.append(action)
        
        self._create_test_actions(actions)
        
        # 異常検出実行
        result = detect_admin_anomalies(self.test_admin, timeframe=3600)  # 1時間
        
        # IP変更異常が検出されることを確認
        self.assertTrue(result["anomalies_detected"])
        self.assertIn("ip_changes", result["anomaly_types"])
        self.assertGreaterEqual(result["risk_score"], 50)
        self.assertIn("IP", "\n".join(result["recommendations"]))
    
    def test_detect_high_risk_operations_anomaly(self):
        """高リスク操作連続実行の検出テスト"""
        try:
            from security.anomaly_detector import detect_admin_anomalies
        except ImportError:
            self.skipTest("security.anomaly_detector module not implemented yet")
            
        # 高リスク操作を短時間に連続実行
        actions = []
        now = get_app_now()
        risk_operations = [
            {"action_type": "user_permission_change", "resource_type": "user_management"},
            {"action_type": "security_settings_update", "resource_type": "security_config"},
            {"action_type": "incident_resolve", "resource_type": "security_incidents"},
            {"action_type": "system_restart", "resource_type": "system_control"}
        ]
        
        for i, op in enumerate(risk_operations):
            actions.append({
                **op,
                "risk_level": "critical",
                "action_details": {"critical_action": i + 1},
                "created_at": (now - timedelta(minutes=10-i*2)).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        self._create_test_actions(actions)
        
        # 異常検出実行
        result = detect_admin_anomalies(self.test_admin, timeframe=600)  # 10分
        
        # 高リスク操作異常が検出されることを確認
        self.assertTrue(result["anomalies_detected"])
        self.assertIn("critical_operations", result["anomaly_types"])
        self.assertGreaterEqual(result["risk_score"], 80)
        self.assertIn("重要操作", "\n".join(result["recommendations"]))
    
    def test_calculate_risk_score_low(self):
        """低リスクスコア算出テスト"""
        try:
            from security.anomaly_detector import calculate_risk_score
        except ImportError:
            self.skipTest("security.anomaly_detector module not implemented yet")
            
        # 低リスク操作のみ
        actions = []
        for i in range(3):
            actions.append({
                "action_type": "view_logs",
                "resource_type": "audit_logs", 
                "risk_level": "low",
                "success": True,
                "ip_address": self.test_ip,
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        
        risk_score = calculate_risk_score(actions)
        
        # 低リスクスコアであることを確認
        self.assertLessEqual(risk_score, 20)
    
    def test_calculate_risk_score_high(self):
        """高リスクスコア算出テスト"""
        try:
            from security.anomaly_detector import calculate_risk_score
        except ImportError:
            self.skipTest("security.anomaly_detector module not implemented yet")
            
        # 高リスク要素を含む操作群
        actions = []
        now = datetime.now()
        
        # 深夜の重要操作、複数IP、高失敗率
        for i in range(12):  # 大量操作
            actions.append({
                "action_type": "security_settings_update",
                "resource_type": "security_config",
                "risk_level": "critical" if i % 3 == 0 else "high",
                "success": i % 4 != 0,  # 25%失敗率
                "ip_address": f"192.168.1.{100 + i % 4}",  # IP変更
                "created_at": now.replace(hour=3).strftime('%Y-%m-%d %H:%M:%S')  # 深夜
            })
        
        risk_score = calculate_risk_score(actions)
        
        # 高リスクスコアであることを確認
        self.assertGreaterEqual(risk_score, 80)
    
    def test_multiple_anomaly_types(self):
        """複数の異常タイプが同時検出されるテスト"""
        try:
            from security.anomaly_detector import detect_admin_anomalies
        except ImportError:
            self.skipTest("security.anomaly_detector module not implemented yet")
            
        # 複数の異常要素を含む操作群
        actions = []
        now = get_app_now()
        night_time = now.replace(hour=2, minute=30)  # 深夜2:30
        
        # 深夜 + 大量操作 + IP変更 + 高リスク操作
        for i in range(15):
            actions.append({
                "action_type": "critical_system_change",
                "resource_type": "system_config",
                "risk_level": "critical",
                "ip_address": f"10.0.{i%5}.{100+i}",  # 頻繁なIP変更
                "action_details": {"critical_change": i},
                "created_at": (night_time + timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        self._create_test_actions(actions)
        
        # 異常検出実行
        result = detect_admin_anomalies(self.test_admin, timeframe=1800)  # 30分
        
        # 複数の異常タイプが検出されることを確認
        self.assertTrue(result["anomalies_detected"])
        expected_anomalies = ["bulk_operations", "night_access", "ip_changes", "critical_operations"]
        for anomaly_type in expected_anomalies:
            self.assertIn(anomaly_type, result["anomaly_types"])
        
        # 非常に高いリスクスコア
        self.assertGreaterEqual(result["risk_score"], 95)
        self.assertGreater(len(result["recommendations"]), 3)
    
    def test_anomaly_detection_time_filtering(self):
        """時間範囲フィルタリングの検出テスト"""
        try:
            from security.anomaly_detector import detect_admin_anomalies
        except ImportError:
            self.skipTest("security.anomaly_detector module not implemented yet")
            
        # 時間範囲外の大量操作
        old_actions = []
        now = get_app_now()
        old_time = now - timedelta(hours=2)  # 2時間前
        
        for i in range(15):
            old_actions.append({
                "action_type": "bulk_operation",
                "resource_type": "mass_update", 
                "risk_level": "high",
                "action_details": {"batch": i},
                "created_at": (old_time + timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        self._create_test_actions(old_actions)
        
        # 1時間の時間範囲で異常検出実行
        result = detect_admin_anomalies(self.test_admin, timeframe=3600)  # 1時間
        
        # 時間範囲外の操作は検出されないことを確認
        self.assertFalse(result["anomalies_detected"])
        self.assertEqual(result["risk_score"], 0)


if __name__ == '__main__':
    unittest.main()