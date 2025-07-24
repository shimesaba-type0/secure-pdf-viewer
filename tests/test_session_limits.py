#!/usr/bin/env python3
"""
TASK-003-5: 同時接続数制限・監視機能のテストケース

このテストファイルは、セッション制限機能の動作を検証します。
- セッション制限チェック機能
- 管理画面設定機能
- 制限に達した場合の認証拒否
- 警告通知システム
"""

import unittest
import sqlite3
import tempfile
import os
import sys

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app
from database import init_db
from database.models import get_setting, set_setting


class TestSessionLimits(unittest.TestCase):
    """セッション制限機能のテストクラス"""
    
    def setUp(self):
        """テストケース毎の初期化"""
        # テスト用のデータベースファイルを作成
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        
        # アプリケーションをテストモードで初期化
        app.app.config['TESTING'] = True
        app.app.config['DATABASE'] = self.db_path
        self.client = app.app.test_client()
        
        # テスト用データベースを直接初期化
        from database.models import create_tables, insert_initial_data
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row  # 辞書形式でアクセス可能
            create_tables(conn)
            insert_initial_data(conn)
    
    def tearDown(self):
        """テストケース毎のクリーンアップ"""
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_check_session_limit_disabled(self):
        """セッション制限機能が無効な場合のテスト"""
        with sqlite3.connect(self.db_path) as conn:
            # 制限機能を無効化
            set_setting(conn, 'session_limit_enabled', 'false', 'test')
            
        result = app.check_session_limit()
        
        self.assertTrue(result['allowed'])
        self.assertEqual(result['current_count'], 0)
        self.assertEqual(result['max_limit'], 0)
        self.assertIsNone(result['warning'])
    
    def test_check_session_limit_normal(self):
        """通常時のセッション制限チェック"""
        with sqlite3.connect(self.db_path) as conn:
            # 制限設定（5セッション）
            set_setting(conn, 'max_concurrent_sessions', '5', 'test')
            set_setting(conn, 'session_limit_enabled', 'true', 'test')
            
            # 2つのセッションを作成
            conn.execute('''
                INSERT INTO session_stats (session_id, email_hash, start_time, ip_address, device_type)
                VALUES (?, ?, ?, ?, ?)
            ''', ('session1', 'hash1', 1234567890, '127.0.0.1', 'desktop'))
            conn.execute('''
                INSERT INTO session_stats (session_id, email_hash, start_time, ip_address, device_type)
                VALUES (?, ?, ?, ?, ?)
            ''', ('session2', 'hash2', 1234567891, '127.0.0.1', 'mobile'))
            conn.commit()
        
        result = app.check_session_limit()
        
        self.assertTrue(result['allowed'])
        self.assertEqual(result['current_count'], 2)
        self.assertEqual(result['max_limit'], 5)
        self.assertIsNone(result['warning'])  # 40%使用（80%未満なので警告なし）
    
    def test_check_session_limit_warning(self):
        """警告レベル（80%以上）のセッション制限チェック"""
        with sqlite3.connect(self.db_path) as conn:
            # 制限設定（5セッション）
            set_setting(conn, 'max_concurrent_sessions', '5', 'test')
            set_setting(conn, 'session_limit_enabled', 'true', 'test')
            
            # 4つのセッションを作成（80%）
            for i in range(4):
                conn.execute('''
                    INSERT INTO session_stats (session_id, email_hash, start_time, ip_address, device_type)
                    VALUES (?, ?, ?, ?, ?)
                ''', (f'session{i+1}', f'hash{i+1}', 1234567890 + i, '127.0.0.1', 'desktop'))
            conn.commit()
        
        result = app.check_session_limit()
        
        self.assertTrue(result['allowed'])
        self.assertEqual(result['current_count'], 4)
        self.assertEqual(result['max_limit'], 5)
        self.assertIsNotNone(result['warning'])
        self.assertIn('制限に近づいています', result['warning'])
    
    def test_check_session_limit_exceeded(self):
        """制限到達時のセッション制限チェック"""
        with sqlite3.connect(self.db_path) as conn:
            # 制限設定（3セッション）
            set_setting(conn, 'max_concurrent_sessions', '3', 'test')
            set_setting(conn, 'session_limit_enabled', 'true', 'test')
            
            # 3つのセッションを作成（100%）
            for i in range(3):
                conn.execute('''
                    INSERT INTO session_stats (session_id, email_hash, start_time, ip_address, device_type)
                    VALUES (?, ?, ?, ?, ?)
                ''', (f'session{i+1}', f'hash{i+1}', 1234567890 + i, '127.0.0.1', 'desktop'))
            conn.commit()
        
        result = app.check_session_limit()
        
        self.assertFalse(result['allowed'])
        self.assertEqual(result['current_count'], 3)
        self.assertEqual(result['max_limit'], 3)
        self.assertIsNotNone(result['warning'])
        self.assertIn('制限に達しています', result['warning'])
    
    def test_session_limit_status_api(self):
        """セッション制限状況取得APIのテスト"""
        with sqlite3.connect(self.db_path) as conn:
            # 制限設定
            set_setting(conn, 'max_concurrent_sessions', '10', 'test')
            set_setting(conn, 'session_limit_enabled', 'true', 'test')
            
            # 7つのセッションを作成
            for i in range(7):
                conn.execute('''
                    INSERT INTO session_stats (session_id, email_hash, start_time, ip_address, device_type)
                    VALUES (?, ?, ?, ?, ?)
                ''', (f'session{i+1}', f'hash{i+1}', 1234567890 + i, '127.0.0.1', 'desktop'))
            conn.commit()
        
        # 認証状態をシミュレート
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['email'] = 'test@example.com'
        
        response = self.client.get('/admin/api/session-limit-status')
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        
        self.assertTrue(data['success'])
        self.assertEqual(data['current_sessions'], 7)
        self.assertEqual(data['max_sessions'], 10)
        self.assertEqual(data['usage_percentage'], 70.0)
        self.assertFalse(data['is_warning'])  # 70% < 80%
        self.assertFalse(data['is_critical'])  # 70% < 100%
    
    def test_session_limit_status_api_warning(self):
        """警告レベルでのセッション制限状況取得APIテスト"""
        with sqlite3.connect(self.db_path) as conn:
            # 制限設定
            set_setting(conn, 'max_concurrent_sessions', '10', 'test')
            set_setting(conn, 'session_limit_enabled', 'true', 'test')
            
            # 9つのセッションを作成（90%）
            for i in range(9):
                conn.execute('''
                    INSERT INTO session_stats (session_id, email_hash, start_time, ip_address, device_type)
                    VALUES (?, ?, ?, ?, ?)
                ''', (f'session{i+1}', f'hash{i+1}', 1234567890 + i, '127.0.0.1', 'desktop'))
            conn.commit()
        
        # 認証状態をシミュレート
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['email'] = 'test@example.com'
        
        response = self.client.get('/admin/api/session-limit-status')
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        
        self.assertTrue(data['success'])
        self.assertEqual(data['current_sessions'], 9)
        self.assertEqual(data['max_sessions'], 10)
        self.assertEqual(data['usage_percentage'], 90.0)
        self.assertTrue(data['is_warning'])  # 90% >= 80%
        self.assertFalse(data['is_critical'])  # 90% < 100%
    
    def test_update_session_limits_valid(self):
        """有効な値でのセッション制限設定更新テスト"""
        # 認証状態をシミュレート
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['email'] = 'admin@example.com'
        
        response = self.client.post('/admin/update-session-limits', data={
            'max_concurrent_sessions': '50',
            'session_limit_enabled': 'on'
        })
        
        self.assertEqual(response.status_code, 302)  # リダイレクト
        
        # 設定が正しく保存されているか確認
        with sqlite3.connect(self.db_path) as conn:
            max_sessions = get_setting(conn, 'max_concurrent_sessions', 100)
            enabled = get_setting(conn, 'session_limit_enabled', True)
            
        self.assertEqual(int(max_sessions), 50)
        self.assertTrue(enabled)
    
    def test_update_session_limits_invalid(self):
        """無効な値でのセッション制限設定更新テスト"""
        # 認証状態をシミュレート
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['email'] = 'admin@example.com'
        
        # 範囲外の値（1001）を設定
        response = self.client.post('/admin/update-session-limits', data={
            'max_concurrent_sessions': '1001',
            'session_limit_enabled': 'on'
        })
        
        self.assertEqual(response.status_code, 302)  # リダイレクト（エラーメッセージ付き）
        
        # 設定が変更されていないことを確認
        with sqlite3.connect(self.db_path) as conn:
            max_sessions = get_setting(conn, 'max_concurrent_sessions', 100)
            
        self.assertEqual(int(max_sessions), 100)  # デフォルト値のまま
    
    def test_session_limit_enforcement_in_auth(self):
        """認証時のセッション制限実行テスト"""
        # 注意: この部分は実際のOTP認証フローをモックしたテストが必要
        # 現在の実装では複雑なテストケースになるため、基本的な動作確認のみ
        
        with sqlite3.connect(self.db_path) as conn:
            # 非常に低い制限を設定（1セッション）
            set_setting(conn, 'max_concurrent_sessions', '1', 'test')
            set_setting(conn, 'session_limit_enabled', 'true', 'test')
            
            # 既に1つのセッションを作成
            conn.execute('''
                INSERT INTO session_stats (session_id, email_hash, start_time, ip_address, device_type)
                VALUES (?, ?, ?, ?, ?)
            ''', ('existing_session', 'hash1', 1234567890, '127.0.0.1', 'desktop'))
            conn.commit()
        
        # check_session_limit関数で制限チェック
        result = app.check_session_limit()
        
        # 制限に達していることを確認
        self.assertFalse(result['allowed'])
        self.assertEqual(result['current_count'], 1)
        self.assertEqual(result['max_limit'], 1)
    
    def test_session_limit_settings_persistence(self):
        """セッション制限設定の永続化テスト"""
        # 設定を変更
        with sqlite3.connect(self.db_path) as conn:
            set_setting(conn, 'max_concurrent_sessions', '25', 'test')
            set_setting(conn, 'session_limit_enabled', 'false', 'test')
        
        # 新しい接続で設定を読み取り
        with sqlite3.connect(self.db_path) as conn:
            max_sessions = get_setting(conn, 'max_concurrent_sessions', 100)
            enabled = get_setting(conn, 'session_limit_enabled', True)
        
        self.assertEqual(int(max_sessions), 25)
        self.assertFalse(enabled)


if __name__ == '__main__':
    unittest.main()