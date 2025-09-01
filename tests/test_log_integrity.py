"""
TASK-021 Sub-Phase 3D: ログ完全性保証機能テスト

ログの改ざん検出・防止機能のテストコード
"""

import unittest
import tempfile
import os
import json
import hashlib
from unittest.mock import patch, MagicMock
import sys
import sqlite3

# プロジェクトルートをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import create_tables, log_admin_action, get_admin_actions
from config.timezone import get_app_datetime_string


def get_test_db_connection(db_path):
    """テスト用データベース接続"""
    return sqlite3.connect(db_path)


class TestLogIntegrity(unittest.TestCase):
    """ログ完全性保証機能のテストクラス"""
    
    def setUp(self):
        """各テスト実行前の準備"""
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.test_db.close()
        self.db_path = self.test_db.name
        
        # テスト用データベース初期化
        conn = get_test_db_connection(self.db_path)
        create_tables(conn)
        conn.close()
            
        # テスト用管理者操作データ
        self.test_admin_action = {
            "admin_email": "admin@test.com",
            "action_type": "settings_update",
            "resource_type": "security_settings", 
            "resource_id": "pdf_security",
            "action_details": {"setting": "value"},
            "before_state": {"old_setting": "old_value"},
            "after_state": {"setting": "value"},
            "ip_address": "192.168.1.100",
            "user_agent": "Mozilla/5.0 Test Browser",
            "session_id": "test_session_123",
            "admin_session_id": "admin_session_456",
            "success": True,
            "error_message": None,
            "risk_level": "medium"
        }
    
    def tearDown(self):
        """各テスト実行後のクリーンアップ"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def test_generate_log_checksum_basic(self):
        """基本的なチェックサム生成テスト"""
        # チェックサム生成関数のインポート（実装後）
        try:
            from security.integrity import generate_log_checksum
        except ImportError:
            self.skipTest("security.integrity module not implemented yet")
            
        # テストデータでチェックサム生成
        checksum = generate_log_checksum(self.test_admin_action)
        
        # チェックサムが生成されることを確認
        self.assertIsInstance(checksum, str)
        self.assertEqual(len(checksum), 64)  # SHA-256は64文字
        self.assertTrue(all(c in '0123456789abcdef' for c in checksum))
    
    def test_generate_log_checksum_consistency(self):
        """チェックサム生成の一貫性テスト"""
        try:
            from security.integrity import generate_log_checksum
        except ImportError:
            self.skipTest("security.integrity module not implemented yet")
            
        # 同じデータで複数回チェックサム生成
        checksum1 = generate_log_checksum(self.test_admin_action)
        checksum2 = generate_log_checksum(self.test_admin_action)
        
        # 同じデータからは同じチェックサムが生成されることを確認
        self.assertEqual(checksum1, checksum2)
        
        # データを変更すると異なるチェックサムが生成されることを確認
        modified_action = self.test_admin_action.copy()
        modified_action["action_details"] = {"modified": "data"}
        checksum3 = generate_log_checksum(modified_action)
        
        self.assertNotEqual(checksum1, checksum3)
    
    def test_verify_log_integrity_valid(self):
        """有効なログの完全性検証テスト"""
        try:
            from security.integrity import verify_log_integrity, generate_log_checksum
        except ImportError:
            self.skipTest("security.integrity module not implemented yet")
            
        with patch('database.models.DATABASE_PATH', self.db_path):
            # ログを記録してチェックサムを生成
            log_id = log_admin_action(**self.test_admin_action)
            expected_checksum = generate_log_checksum(self.test_admin_action)
            
            # データベースにチェックサムを保存
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE admin_actions 
                SET checksum = ?, integrity_status = 'verified'
                WHERE id = ?
            """, (expected_checksum, log_id))
            conn.commit()
            conn.close()
            
            # 完全性検証実行
            result = verify_log_integrity(log_id)
            
            # 検証結果を確認
            self.assertTrue(result["valid"])
            self.assertEqual(result["expected"], expected_checksum)
            self.assertEqual(result["actual"], expected_checksum)
            self.assertIsInstance(result["timestamp"], str)
    
    def test_verify_log_integrity_tampered(self):
        """改ざんされたログの検証テスト"""
        try:
            from security.integrity import verify_log_integrity, generate_log_checksum
        except ImportError:
            self.skipTest("security.integrity module not implemented yet")
            
        with patch('database.models.DATABASE_PATH', self.db_path):
            # ログを記録
            log_id = log_admin_action(**self.test_admin_action)
            original_checksum = generate_log_checksum(self.test_admin_action)
            
            # データベースにチェックサムを保存
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE admin_actions 
                SET checksum = ?, integrity_status = 'verified'
                WHERE id = ?
            """, (original_checksum, log_id))
            
            # ログデータを改ざん
            cursor.execute("""
                UPDATE admin_actions 
                SET action_details = '{"tampered": "data"}'
                WHERE id = ?
            """, (log_id,))
            conn.commit()
            conn.close()
            
            # 完全性検証実行
            result = verify_log_integrity(log_id)
            
            # 改ざんが検出されることを確認
            self.assertFalse(result["valid"])
            self.assertEqual(result["expected"], original_checksum)
            self.assertNotEqual(result["actual"], original_checksum)
    
    def test_verify_log_integrity_missing_checksum(self):
        """チェックサム未設定ログの検証テスト"""
        try:
            from security.integrity import verify_log_integrity
        except ImportError:
            self.skipTest("security.integrity module not implemented yet")
            
        with patch('database.models.DATABASE_PATH', self.db_path):
            # チェックサム未設定でログを記録
            log_id = log_admin_action(**self.test_admin_action)
            
            # 完全性検証実行
            result = verify_log_integrity(log_id)
            
            # チェックサム未設定の場合の処理を確認
            self.assertFalse(result["valid"])
            self.assertIsNone(result["expected"])
            self.assertIsNotNone(result["actual"])
    
    def test_verify_all_logs_integrity_batch(self):
        """全ログの一括完全性検証テスト"""
        try:
            from security.integrity import verify_all_logs_integrity, generate_log_checksum
        except ImportError:
            self.skipTest("security.integrity module not implemented yet")
            
        with patch('database.models.DATABASE_PATH', self.db_path):
            # 複数のログを記録
            log_ids = []
            for i in range(5):
                action = self.test_admin_action.copy()
                action["action_details"] = {"test_index": i}
                log_id = log_admin_action(**action)
                log_ids.append(log_id)
                
                # チェックサムを設定
                checksum = generate_log_checksum(action)
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE admin_actions 
                    SET checksum = ?, integrity_status = 'verified'
                    WHERE id = ?
                """, (checksum, log_id))
                conn.commit()
                conn.close()
            
            # 1つのログを改ざん
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE admin_actions 
                SET action_details = '{"tampered": true}'
                WHERE id = ?
            """, (log_ids[2],))
            conn.commit()
            conn.close()
            
            # 全ログの完全性検証実行
            result = verify_all_logs_integrity(batch_size=3)
            
            # 検証結果を確認
            self.assertEqual(result["total_logs"], 5)
            self.assertEqual(result["valid_logs"], 4)
            self.assertEqual(result["invalid_logs"], 1)
            self.assertEqual(len(result["tampered_log_ids"]), 1)
            self.assertIn(log_ids[2], result["tampered_log_ids"])
    
    def test_add_checksum_to_existing_logs(self):
        """既存ログへのチェックサム追加テスト"""
        try:
            from security.integrity import add_checksum_to_existing_logs
        except ImportError:
            self.skipTest("security.integrity module not implemented yet")
            
        with patch('database.models.DATABASE_PATH', self.db_path):
            # チェックサム未設定のログを記録
            log_ids = []
            for i in range(3):
                action = self.test_admin_action.copy()
                action["action_details"] = {"batch_index": i}
                log_id = log_admin_action(**action)
                log_ids.append(log_id)
            
            # 既存ログにチェックサム追加
            result = add_checksum_to_existing_logs()
            
            # チェックサムが追加されたことを確認
            self.assertEqual(result["processed_logs"], 3)
            self.assertEqual(result["updated_logs"], 3)
            
            # データベースでチェックサム設定を確認
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM admin_actions 
                WHERE checksum IS NOT NULL AND checksum != ''
            """)
            count = cursor.fetchone()[0]
            conn.close()
            
            self.assertEqual(count, 3)


if __name__ == '__main__':
    unittest.main()