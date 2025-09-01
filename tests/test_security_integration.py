"""
TASK-021 Sub-Phase 3D: セキュリティ統合テスト

ログ完全性保証と異常検出機能の統合テストコード
"""

import unittest
import tempfile
import os
import json
import time
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


class TestSecurityIntegration(unittest.TestCase):
    """セキュリティ統合機能のテストクラス"""
    
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
            self._setup_security_thresholds()
            
        # テスト用管理者データ
        self.test_admin = "security_admin@test.com"
        self.normal_admin = "normal_admin@test.com"
        self.base_action = {
            "ip_address": "192.168.1.100",
            "user_agent": "Mozilla/5.0 Test Browser",
            "session_id": "test_session_123",
            "admin_session_id": "admin_session_456",
            "success": True,
            "error_message": None
        }
    
    def tearDown(self):
        """各テスト実行後のクリーンアップ"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def _setup_security_thresholds(self):
        """セキュリティ閾値テーブルのセットアップ"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # security_thresholdsテーブル作成
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_thresholds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                threshold_type TEXT NOT NULL,
                threshold_value INTEGER NOT NULL,
                timeframe_minutes INTEGER NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # デフォルト閾値設定
        thresholds = [
            ('bulk_operations', 10, 5, True),
            ('night_access', 1, 60, True),
            ('ip_changes', 3, 60, True),
            ('critical_operations', 3, 10, True)
        ]
        
        for threshold_type, value, timeframe, is_active in thresholds:
            cursor.execute("""
                INSERT INTO security_thresholds 
                (threshold_type, threshold_value, timeframe_minutes, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (threshold_type, value, timeframe, is_active, 
                  get_app_datetime_string(), get_app_datetime_string()))
        
        conn.commit()
        conn.close()
    
    def _create_admin_actions_with_checksum(self, actions_data, admin_email=None):
        """チェックサム付きの管理者操作ログを作成"""
        try:
            from security.integrity import generate_log_checksum
        except ImportError:
            self.skipTest("security.integrity module not implemented yet")
            
        admin = admin_email or self.test_admin
        log_ids = []
        
        with patch('database.models.DATABASE_PATH', self.db_path):
            for action_data in actions_data:
                action = self.base_action.copy()
                action["admin_email"] = admin
                action.update(action_data)
                
                log_id = log_admin_action(**action)
                checksum = generate_log_checksum(action)
                
                # チェックサムを保存
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE admin_actions 
                    SET checksum = ?, integrity_status = 'verified'
                    WHERE id = ?
                """, (checksum, log_id))
                conn.commit()
                conn.close()
                
                log_ids.append(log_id)
        
        return log_ids
    
    def test_end_to_end_security_monitoring(self):
        """エンドツーエンドセキュリティ監視テスト"""
        try:
            from security.anomaly_detector import detect_admin_anomalies
            from security.integrity import verify_all_logs_integrity
        except ImportError:
            self.skipTest("Security modules not implemented yet")
            
        # 正常な操作シナリオ
        normal_actions = []
        now = get_app_now()
        for i in range(3):
            normal_actions.append({
                "action_type": "view_dashboard",
                "resource_type": "admin_dashboard",
                "risk_level": "low",
                "action_details": {"view": f"section_{i}"},
                "created_at": (now - timedelta(minutes=10-i*3)).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        log_ids = self._create_admin_actions_with_checksum(normal_actions, self.normal_admin)
        
        # セキュリティ監視実行
        anomaly_result = detect_admin_anomalies(self.normal_admin, timeframe=1800)
        integrity_result = verify_all_logs_integrity()
        
        # 正常操作では異常検出されないことを確認
        self.assertFalse(anomaly_result["anomalies_detected"])
        self.assertLessEqual(anomaly_result["risk_score"], 20)
        
        # ログ完全性が保持されていることを確認
        self.assertEqual(integrity_result["valid_logs"], len(log_ids))
        self.assertEqual(integrity_result["invalid_logs"], 0)
    
    def test_security_incident_simulation(self):
        """セキュリティインシデントシミュレーション"""
        try:
            from security.anomaly_detector import detect_admin_anomalies, trigger_security_alert
            from security.integrity import verify_log_integrity
        except ImportError:
            self.skipTest("Security modules not implemented yet")
            
        # 攻撃者による悪意ある操作シナリオ
        malicious_actions = []
        now = get_app_now()
        night_time = now.replace(hour=3, minute=0)  # 深夜3時
        
        # 深夜の大量高リスク操作 + 頻繁なIP変更
        ips = ["203.0.113.10", "198.51.100.5", "192.0.2.15", "172.16.1.200"]
        for i in range(20):
            malicious_actions.append({
                "action_type": "security_bypass",
                "resource_type": "security_settings",
                "resource_id": f"critical_setting_{i}",
                "risk_level": "critical",
                "ip_address": ips[i % len(ips)],
                "action_details": {"malicious_change": True, "bypass_attempt": i},
                "created_at": (night_time + timedelta(minutes=i*2)).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        log_ids = self._create_admin_actions_with_checksum(malicious_actions, self.test_admin)
        
        # 異常検出実行
        anomaly_result = detect_admin_anomalies(self.test_admin, timeframe=3600)
        
        # 複数の異常が検出されることを確認
        self.assertTrue(anomaly_result["anomalies_detected"])
        expected_anomalies = ["bulk_operations", "night_access", "ip_changes", "critical_operations"]
        for anomaly_type in expected_anomalies:
            self.assertIn(anomaly_type, anomaly_result["anomaly_types"])
        
        # 極めて高いリスクスコア
        self.assertGreaterEqual(anomaly_result["risk_score"], 90)
        
        # セキュリティアラートがトリガーされることを確認
        alert_triggered = trigger_security_alert(anomaly_result)
        self.assertTrue(alert_triggered["alert_sent"])
        self.assertEqual(alert_triggered["severity"], "critical")
        
        # ログ完全性の確認
        for log_id in log_ids[:5]:  # 最初の5件をサンプル検証
            integrity_result = verify_log_integrity(log_id)
            self.assertTrue(integrity_result["valid"])
    
    def test_performance_load_simulation(self):
        """パフォーマンス負荷シミュレーション"""
        try:
            from security.anomaly_detector import detect_admin_anomalies
            from security.integrity import verify_all_logs_integrity
        except ImportError:
            self.skipTest("Security modules not implemented yet")
            
        # 大量データ処理シナリオ（1000件のログエントリ）
        bulk_actions = []
        now = get_app_now()
        
        # 複数管理者による大量操作
        admins = [f"admin_{i}@test.com" for i in range(5)]
        
        for i in range(1000):
            admin = admins[i % len(admins)]
            bulk_actions.append({
                "admin_email": admin,
                "action_type": f"bulk_process_{i % 10}",
                "resource_type": "mass_data",
                "resource_id": f"batch_{i}",
                "risk_level": "low" if i % 5 != 0 else "medium",
                "action_details": {"batch_id": i, "processed": True},
                "created_at": (now - timedelta(minutes=60-i*0.06)).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # パフォーマンス測定開始
        start_time = time.time()
        
        # 大量ログ作成（チェックサムなしで高速化）
        with patch('database.models.DATABASE_PATH', self.db_path):
            for action_data in bulk_actions:
                log_admin_action(**action_data)
        
        creation_time = time.time() - start_time
        
        # 異常検出パフォーマンス測定
        detection_start = time.time()
        for admin in admins:
            detect_admin_anomalies(admin, timeframe=3600)
        detection_time = time.time() - detection_start
        
        # 完全性検証パフォーマンス測定
        integrity_start = time.time()
        integrity_result = verify_all_logs_integrity(batch_size=100)
        integrity_time = time.time() - integrity_start
        
        # パフォーマンス要件の確認
        self.assertLess(creation_time, 30.0, "ログ作成時間が30秒を超過")
        self.assertLess(detection_time, 10.0, "異常検出時間が10秒を超過")
        self.assertLess(integrity_time, 15.0, "完全性検証時間が15秒を超過")
        
        # データ整合性の確認
        self.assertEqual(integrity_result["total_logs"], 1000)
    
    def test_data_corruption_detection(self):
        """データ破損検出テスト"""
        try:
            from security.integrity import verify_log_integrity, generate_log_checksum
        except ImportError:
            self.skipTest("security.integrity module not implemented yet")
            
        # 正常ログの作成
        test_action = {
            "admin_email": self.test_admin,
            "action_type": "critical_operation",
            "resource_type": "system_config",
            "risk_level": "critical",
            "action_details": {"original": "data"},
            **self.base_action
        }
        
        log_ids = self._create_admin_actions_with_checksum([test_action])
        log_id = log_ids[0]
        
        # 初期状態の完全性確認
        initial_check = verify_log_integrity(log_id)
        self.assertTrue(initial_check["valid"])
        
        # データベース直接操作による破損シミュレーション
        with patch('database.models.DATABASE_PATH', self.db_path):
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 複数種類のデータ破損をシミュレーション
            corruption_scenarios = [
                ("action_details", '{"corrupted": "malicious_data"}', "JSON改ざん"),
                ("ip_address", "999.999.999.999", "IPアドレス改ざん"),
                ("risk_level", "fake_level", "リスクレベル改ざん"),
                ("admin_email", "attacker@malicious.com", "管理者情報改ざん")
            ]
            
            for field, corrupted_value, description in corruption_scenarios:
                # データ破損実行
                cursor.execute(f"""
                    UPDATE admin_actions 
                    SET {field} = ?
                    WHERE id = ?
                """, (corrupted_value, log_id))
                conn.commit()
                
                # 破損検出確認
                corruption_check = verify_log_integrity(log_id)
                self.assertFalse(corruption_check["valid"], f"{description}が検出されませんでした")
                self.assertNotEqual(corruption_check["expected"], corruption_check["actual"])
            
            conn.close()
    
    def test_automated_security_workflow(self):
        """自動化セキュリティワークフローテスト"""
        try:
            from security.anomaly_detector import detect_admin_anomalies, calculate_risk_score
            from security.integrity import verify_all_logs_integrity, add_checksum_to_existing_logs
        except ImportError:
            self.skipTest("Security modules not implemented yet")
            
        # 混合シナリオ（正常 + 疑わしい + 異常操作）
        workflow_actions = []
        now = get_app_now()
        
        # フェーズ1: 正常操作（朝の業務開始）
        morning_time = now.replace(hour=9, minute=0)
        for i in range(5):
            workflow_actions.append({
                "admin_email": self.normal_admin,
                "action_type": "daily_review",
                "resource_type": "audit_logs",
                "risk_level": "low",
                "action_details": {"routine_check": i},
                "created_at": (morning_time + timedelta(minutes=i*10)).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # フェーズ2: 疑わしい操作（昼食時の設定変更）
        lunch_time = now.replace(hour=12, minute=30)
        for i in range(3):
            workflow_actions.append({
                "admin_email": self.test_admin,
                "action_type": "settings_modification",
                "resource_type": "security_config",
                "risk_level": "medium",
                "action_details": {"unusual_timing": True, "change_id": i},
                "created_at": (lunch_time + timedelta(minutes=i*5)).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # フェーズ3: 異常操作（深夜の緊急対応？）
        night_time = now.replace(hour=2, minute=0)  # 深夜2時
        for i in range(8):
            workflow_actions.append({
                "admin_email": self.test_admin,
                "action_type": "emergency_override",
                "resource_type": "critical_system",
                "risk_level": "critical",
                "ip_address": f"203.0.113.{10+i}",  # 異なるIP
                "action_details": {"emergency_flag": True, "override_id": i},
                "created_at": (night_time + timedelta(minutes=i*3)).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # ログ作成とチェックサム追加
        with patch('database.models.DATABASE_PATH', self.db_path):
            for action in workflow_actions:
                log_admin_action(**action)
        
        # 既存ログにチェックサム追加
        checksum_result = add_checksum_to_existing_logs()
        self.assertEqual(checksum_result["updated_logs"], len(workflow_actions))
        
        # 管理者別異常検出
        normal_anomalies = detect_admin_anomalies(self.normal_admin, timeframe=43200)  # 12時間
        suspicious_anomalies = detect_admin_anomalies(self.test_admin, timeframe=43200)
        
        # 正常管理者は異常検出されない
        self.assertFalse(normal_anomalies["anomalies_detected"])
        self.assertLessEqual(normal_anomalies["risk_score"], 30)
        
        # 疑わしい管理者は異常検出される
        self.assertTrue(suspicious_anomalies["anomalies_detected"])
        self.assertGreaterEqual(suspicious_anomalies["risk_score"], 70)
        
        # 全ログの完全性確認
        integrity_result = verify_all_logs_integrity()
        self.assertEqual(integrity_result["total_logs"], len(workflow_actions))
        self.assertEqual(integrity_result["valid_logs"], len(workflow_actions))
        self.assertEqual(integrity_result["invalid_logs"], 0)


if __name__ == '__main__':
    unittest.main()