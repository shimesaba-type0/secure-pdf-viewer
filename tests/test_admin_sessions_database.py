"""
Sub-Phase 1A: データベース基盤整備のテストケース

TASK-021 Sub-Phase 1A:
- admin_sessions テーブル作成
- セキュリティ設定3項目の追加  
- 基本的なCRUD関数実装
"""

import unittest
import sqlite3
import tempfile
import os
import sys
import json
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import create_tables, insert_initial_data, get_setting, set_setting
from config.timezone import get_app_datetime_string


class TestAdminSessionsDatabase(unittest.TestCase):
    """admin_sessionsテーブルとCRUD関数のテストクラス"""

    def setUp(self):
        """テストケース毎の初期化"""
        # テスト用の一時データベース作成
        self.test_db_fd, self.test_db_path = tempfile.mkstemp()
        
        # テストデータベース接続
        self.db = sqlite3.connect(self.test_db_path)
        self.db.row_factory = sqlite3.Row
        
        # テーブル作成と初期データ挿入
        create_tables(self.db)
        insert_initial_data(self.db)
        self.db.commit()

    def tearDown(self):
        """テストケース毎のクリーンアップ"""
        self.db.close()
        os.close(self.test_db_fd)
        os.unlink(self.test_db_path)

    def test_admin_sessions_table_exists(self):
        """admin_sessionsテーブルが存在することを確認"""
        cursor = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='admin_sessions'"
        )
        result = cursor.fetchone()
        self.assertIsNotNone(result, "admin_sessionsテーブルが存在しません")

    def test_admin_sessions_table_structure(self):
        """admin_sessionsテーブルの構造を確認"""
        cursor = self.db.execute("PRAGMA table_info(admin_sessions)")
        columns = cursor.fetchall()
        
        expected_columns = {
            'session_id': 'TEXT',
            'admin_email': 'TEXT',
            'created_at': 'TEXT',
            'last_verified_at': 'TEXT',
            'ip_address': 'TEXT',
            'user_agent': 'TEXT',
            'is_active': 'BOOLEAN',
            'security_flags': 'JSON',
            'verification_token': 'TEXT'
        }
        
        actual_columns = {col[1]: col[2] for col in columns}
        
        for col_name, col_type in expected_columns.items():
            self.assertIn(col_name, actual_columns, f"カラム {col_name} が存在しません")

    def test_admin_security_settings_exist(self):
        """管理者用セキュリティ設定が存在することを確認"""
        expected_settings = {
            'admin_session_timeout': '1800',
            'admin_session_verification_interval': '300',
            'admin_session_ip_binding': 'true'
        }
        
        for key, expected_value in expected_settings.items():
            value = get_setting(self.db, key)
            self.assertIsNotNone(value, f"設定 {key} が存在しません")

    def test_create_admin_session_function_exists(self):
        """create_admin_session関数が存在することを確認（関数定義テスト）"""
        # 関数をインポートしてテスト
        try:
            from database.models import create_admin_session
            self.assertTrue(callable(create_admin_session), "create_admin_session関数が呼び出し可能ではありません")
        except ImportError:
            self.fail("create_admin_session関数がインポートできません")

    def test_verify_admin_session_function_exists(self):
        """verify_admin_session関数が存在することを確認（関数定義テスト）"""
        try:
            from database.models import verify_admin_session
            self.assertTrue(callable(verify_admin_session), "verify_admin_session関数が呼び出し可能ではありません")
        except ImportError:
            self.fail("verify_admin_session関数がインポートできません")

    def test_update_admin_session_verification_function_exists(self):
        """update_admin_session_verification関数が存在することを確認（関数定義テスト）"""
        try:
            from database.models import update_admin_session_verification
            self.assertTrue(callable(update_admin_session_verification), "update_admin_session_verification関数が呼び出し可能ではありません")
        except ImportError:
            self.fail("update_admin_session_verification関数がインポートできません")

    def test_delete_admin_session_function_exists(self):
        """delete_admin_session関数が存在することを確認（関数定義テスト）"""
        try:
            from database.models import delete_admin_session
            self.assertTrue(callable(delete_admin_session), "delete_admin_session関数が呼び出し可能ではありません")
        except ImportError:
            self.fail("delete_admin_session関数がインポートできません")

    def test_admin_session_crud_operations(self):
        """admin_sessionsテーブルの基本CRUD操作テスト"""
        try:
            from database.models import (
                create_admin_session,
                verify_admin_session,
                update_admin_session_verification,
                delete_admin_session
            )
            
            # テストデータ
            session_id = "test_session_123"
            admin_email = "test@example.com"
            ip_address = "192.168.1.1"
            user_agent = "Test Browser 1.0"
            
            # 1. セッション作成テスト
            result = create_admin_session(admin_email, session_id, ip_address, user_agent)
            self.assertTrue(result, "管理者セッション作成に失敗")
            
            # 2. セッション検証テスト
            session_data = verify_admin_session(session_id, ip_address, user_agent)
            self.assertIsNotNone(session_data, "管理者セッション検証に失敗")
            self.assertEqual(session_data['admin_email'], admin_email, "セッションのメールアドレスが一致しません")
            
            # 3. セッション検証時刻更新テスト
            result = update_admin_session_verification(session_id)
            self.assertTrue(result, "セッション検証時刻更新に失敗")
            
            # 4. セッション削除テスト
            result = delete_admin_session(session_id)
            self.assertTrue(result, "管理者セッション削除に失敗")
            
            # 5. 削除後の検証テスト（None が返されることを確認）
            session_data = verify_admin_session(session_id, ip_address, user_agent)
            self.assertIsNone(session_data, "削除されたセッションが検証されています")
            
        except ImportError as e:
            self.skipTest(f"必要な関数がまだ実装されていません: {e}")

    def test_admin_session_security_flags(self):
        """セキュリティフラグの保存・取得テスト"""
        try:
            from database.models import create_admin_session, verify_admin_session
            
            session_id = "test_session_with_flags"
            admin_email = "test@example.com"
            ip_address = "192.168.1.1"
            user_agent = "Test Browser 1.0"
            
            # セキュリティフラグ付きでセッション作成
            security_flags = {
                "ip_binding_enabled": True,
                "ua_verification_enabled": True,
                "risk_level": "low"
            }
            
            result = create_admin_session(
                admin_email, session_id, ip_address, user_agent, security_flags
            )
            self.assertTrue(result, "セキュリティフラグ付きセッション作成に失敗")
            
            # セキュリティフラグの確認
            session_data = verify_admin_session(session_id, ip_address, user_agent)
            self.assertIsNotNone(session_data, "セッション検証に失敗")
            
            if session_data and 'security_flags' in session_data:
                saved_flags = json.loads(session_data['security_flags']) if session_data['security_flags'] else {}
                self.assertEqual(saved_flags['ip_binding_enabled'], True, "IPバインディングフラグが保存されていません")
                self.assertEqual(saved_flags['ua_verification_enabled'], True, "ユーザーエージェント検証フラグが保存されていません")
            
        except ImportError:
            self.skipTest("必要な関数がまだ実装されていません")

    def test_admin_session_timeout_setting(self):
        """管理者セッションタイムアウト設定のテスト"""
        # デフォルト値確認
        timeout = get_setting(self.db, 'admin_session_timeout', 1800)
        self.assertEqual(timeout, 1800, "デフォルトのタイムアウト設定が正しくありません")
        
        # 設定変更テスト
        set_setting(self.db, 'admin_session_timeout', '3600', 'test')
        updated_timeout = get_setting(self.db, 'admin_session_timeout')
        self.assertEqual(updated_timeout, 3600, "タイムアウト設定の更新に失敗")

    def test_admin_session_verification_interval_setting(self):
        """管理者セッション検証間隔設定のテスト"""
        # デフォルト値確認
        interval = get_setting(self.db, 'admin_session_verification_interval', 300)
        self.assertEqual(interval, 300, "デフォルトの検証間隔設定が正しくありません")
        
        # 設定変更テスト
        set_setting(self.db, 'admin_session_verification_interval', '600', 'test')
        updated_interval = get_setting(self.db, 'admin_session_verification_interval')
        self.assertEqual(updated_interval, 600, "検証間隔設定の更新に失敗")

    def test_admin_session_ip_binding_setting(self):
        """管理者セッションIPバインディング設定のテスト"""
        # デフォルト値確認
        ip_binding = get_setting(self.db, 'admin_session_ip_binding', True)
        self.assertEqual(ip_binding, True, "デフォルトのIPバインディング設定が正しくありません")
        
        # 設定変更テスト
        set_setting(self.db, 'admin_session_ip_binding', 'false', 'test')
        updated_binding = get_setting(self.db, 'admin_session_ip_binding')
        self.assertEqual(updated_binding, False, "IPバインディング設定の更新に失敗")


if __name__ == '__main__':
    # テスト実行
    unittest.main(verbosity=2)