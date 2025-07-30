import unittest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from database.models import get_access_logs, get_access_logs_stats, log_access


class TestAccessLogs(unittest.TestCase):
    def setUp(self):
        """テスト用データベースを作成"""
        self.test_db_fd, self.test_db_path = tempfile.mkstemp()
        self.conn = sqlite3.connect(self.test_db_path)
        self.conn.row_factory = sqlite3.Row
        
        # テスト用テーブルを作成
        self.conn.execute('''
            CREATE TABLE access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                email_hash TEXT,
                user_email TEXT,
                ip_address TEXT,
                user_agent TEXT,
                endpoint TEXT,
                method TEXT,
                status_code INTEGER,
                access_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                duration_seconds INTEGER,
                pdf_file_path TEXT
            )
        ''')
        
        # テストデータを挿入
        test_logs = [
            ('sess1', 'hash1', 'user1@example.com', '192.168.1.1', 'Mozilla/5.0', '/viewer', 'GET', 200, 120, '/path/to/file1.pdf'),
            ('sess2', 'hash2', 'user2@example.com', '192.168.1.2', 'Chrome/100.0', '/api/test', 'POST', 404, 5, None),
            ('sess3', 'hash3', 'user3@example.com', '192.168.1.3', 'Firefox/90.0', '/admin', 'GET', 500, 30, None),
            ('sess4', 'hash4', 'user1@example.com', '192.168.1.1', 'Mozilla/5.0', '/logout', 'POST', 302, 2, None)
        ]
        
        for log in test_logs:
            self.conn.execute('''
                INSERT INTO access_logs (session_id, email_hash, user_email, ip_address, user_agent, endpoint, method, status_code, duration_seconds, pdf_file_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', log)
        
        self.conn.commit()
    
    def tearDown(self):
        """テスト用データベースを削除"""
        self.conn.close()
        os.close(self.test_db_fd)
        os.unlink(self.test_db_path)
    
    def test_get_access_logs_no_filters(self):
        """フィルターなしでアクセスログを取得"""
        result = get_access_logs(self.conn)
        
        self.assertEqual(len(result['logs']), 4)
        self.assertEqual(result['pagination']['total'], 4)
        self.assertEqual(result['pagination']['page'], 1)
        self.assertEqual(result['pagination']['limit'], 20)
        self.assertFalse(result['pagination']['has_more'])
    
    def test_get_access_logs_with_user_filter(self):
        """ユーザーフィルターでアクセスログを取得"""
        filters = {'user_email': 'user1@example.com'}
        result = get_access_logs(self.conn, filters)
        
        self.assertEqual(len(result['logs']), 2)
        self.assertEqual(result['pagination']['total'], 2)
        
        # すべてのログがuser1のもの
        for log in result['logs']:
            self.assertEqual(log['user_email'], 'user1@example.com')
    
    def test_get_access_logs_with_ip_filter(self):
        """IPアドレスフィルターでアクセスログを取得"""
        filters = {'ip_address': '192.168.1.2'}
        result = get_access_logs(self.conn, filters)
        
        self.assertEqual(len(result['logs']), 1)
        self.assertEqual(result['logs'][0]['ip_address'], '192.168.1.2')
        self.assertEqual(result['logs'][0]['user_email'], 'user2@example.com')
    
    def test_get_access_logs_with_endpoint_filter(self):
        """エンドポイントフィルターでアクセスログを取得"""
        filters = {'endpoint': '/viewer'}
        result = get_access_logs(self.conn, filters)
        
        self.assertEqual(len(result['logs']), 1)
        self.assertEqual(result['logs'][0]['endpoint'], '/viewer')
    
    def test_get_access_logs_pagination(self):
        """ページネーション機能をテスト"""
        result = get_access_logs(self.conn, page=1, limit=2)
        
        self.assertEqual(len(result['logs']), 2)
        self.assertEqual(result['pagination']['total'], 4)
        self.assertEqual(result['pagination']['page'], 1)
        self.assertEqual(result['pagination']['limit'], 2)
        self.assertTrue(result['pagination']['has_more'])
        
        # 2ページ目
        result_page2 = get_access_logs(self.conn, page=2, limit=2)
        self.assertEqual(len(result_page2['logs']), 2)
        self.assertEqual(result_page2['pagination']['page'], 2)
        self.assertFalse(result_page2['pagination']['has_more'])  # 2ページ目が最後のページ
    
    def test_get_access_logs_stats(self):
        """アクセスログ統計を取得"""
        stats = get_access_logs_stats(self.conn)
        
        self.assertEqual(stats['total'], 4)
        
        # ステータスコード別統計
        expected_status_codes = {'200': 1, '404': 1, '500': 1, '302': 1}
        self.assertEqual(stats['status_codes'], expected_status_codes)
        
        # メソッド別統計
        expected_methods = {'GET': 2, 'POST': 2}
        self.assertEqual(stats['methods'], expected_methods)
        
        # エンドポイント別統計（上位10件）
        self.assertIn('/viewer', stats['endpoints'])
        self.assertIn('/api/test', stats['endpoints'])
        self.assertIn('/admin', stats['endpoints'])
        self.assertIn('/logout', stats['endpoints'])
    
    def test_get_access_logs_stats_with_date_filter(self):
        """日付フィルター付きで統計を取得"""
        # 未来の日付でフィルター（結果は0件）
        future_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        filters = {'start_date': future_date}
        stats = get_access_logs_stats(self.conn, filters)
        
        self.assertEqual(stats['total'], 0)
        self.assertEqual(stats['status_codes'], {})
        self.assertEqual(stats['methods'], {})
        self.assertEqual(stats['endpoints'], {})
    
    def test_get_access_logs_empty_result(self):
        """該当データがない場合のテスト"""
        filters = {'user_email': 'nonexistent@example.com'}
        result = get_access_logs(self.conn, filters)
        
        self.assertEqual(len(result['logs']), 0)
        self.assertEqual(result['pagination']['total'], 0)
        self.assertFalse(result['pagination']['has_more'])
    
    def test_get_access_logs_multiple_filters(self):
        """複数フィルターの組み合わせテスト"""
        filters = {
            'user_email': 'user1@example.com',
            'ip_address': '192.168.1.1'
        }
        result = get_access_logs(self.conn, filters)
        
        self.assertEqual(len(result['logs']), 2)
        for log in result['logs']:
            self.assertEqual(log['user_email'], 'user1@example.com')
            self.assertEqual(log['ip_address'], '192.168.1.1')


if __name__ == '__main__':
    unittest.main()