import unittest
import sqlite3
import tempfile  
import os
import json
import sys
sys.path.append('/home/ope/secure-pdf-viewer')
from database.models import log_access


class TestAccessLogsAPI(unittest.TestCase):
    def setUp(self):
        """テスト用アプリケーションとデータベースを設定"""
        # app.pyから直接importしないで、DATABASE_PATHをグローバル変数として設定
        self.test_db_fd, self.test_db_path = tempfile.mkstemp()
        
        # DATABASE_PATHをモンキーパッチ
        import app
        self.original_database_path = getattr(app, 'DATABASE_PATH', None)
        app.DATABASE_PATH = self.test_db_path
        
        app.app.config['TESTING'] = True
        self.client = app.app.test_client()
        
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        
        # テスト用テーブルを作成
        conn.execute('''
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
            ('sess3', 'hash3', 'user3@example.com', '192.168.1.3', 'Firefox/90.0', '/admin', 'GET', 500, 30, None)
        ]
        
        for log in test_logs:
            conn.execute('''
                INSERT INTO access_logs (session_id, email_hash, user_email, ip_address, user_agent, endpoint, method, status_code, duration_seconds, pdf_file_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', log)
        
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """テスト用データベースを削除"""
        import app
        if self.original_database_path:
            app.DATABASE_PATH = self.original_database_path
        os.close(self.test_db_fd)
        os.unlink(self.test_db_path)
    
    def test_get_access_logs_api_success(self):
        """アクセスログAPI取得の成功テスト"""
        response = self.client.get('/api/logs/access-logs')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('data', data)
        self.assertIn('logs', data['data'])
        self.assertIn('pagination', data['data'])
        
        # 3件のテストデータが返される
        self.assertEqual(len(data['data']['logs']), 3)
        self.assertEqual(data['data']['pagination']['total'], 3)
    
    def test_get_access_logs_api_with_filters(self):
        """フィルター付きアクセスログAPI取得テスト"""
        response = self.client.get('/api/logs/access-logs?user_email=user1@example.com')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['data']['logs']), 1)
        self.assertEqual(data['data']['logs'][0]['user_email'], 'user1@example.com')
    
    def test_get_access_logs_api_with_pagination(self):
        """ページネーション付きアクセスログAPI取得テスト"""
        response = self.client.get('/api/logs/access-logs?page=1&limit=2')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['data']['logs']), 2)
        self.assertEqual(data['data']['pagination']['page'], 1)
        self.assertEqual(data['data']['pagination']['limit'], 2)
        self.assertTrue(data['data']['pagination']['has_more'])
    
    def test_get_access_logs_api_with_ip_filter(self):
        """IPアドレスフィルター付きアクセスログAPI取得テスト"""
        response = self.client.get('/api/logs/access-logs?ip_address=192.168.1.2')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['data']['logs']), 1)
        self.assertEqual(data['data']['logs'][0]['ip_address'], '192.168.1.2')
    
    def test_get_access_logs_api_with_endpoint_filter(self):
        """エンドポイントフィルター付きアクセスログAPI取得テスト"""
        response = self.client.get('/api/logs/access-logs?endpoint=/viewer')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['data']['logs']), 1)
        self.assertEqual(data['data']['logs'][0]['endpoint'], '/viewer')
    
    def test_get_access_logs_stats_api_success(self):
        """アクセスログ統計API取得の成功テスト"""
        response = self.client.get('/api/logs/access-logs/stats')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('data', data)
        
        stats = data['data']
        self.assertEqual(stats['total'], 3)
        self.assertIn('status_codes', stats)
        self.assertIn('methods', stats)
        self.assertIn('endpoints', stats)
        
        # ステータスコード別統計の確認
        self.assertIn('200', stats['status_codes'])
        self.assertIn('404', stats['status_codes'])
        self.assertIn('500', stats['status_codes'])
        
        # メソッド別統計の確認
        self.assertIn('GET', stats['methods'])
        self.assertIn('POST', stats['methods'])
    
    def test_get_access_logs_stats_api_with_date_filter(self):
        """日付フィルター付きアクセスログ統計API取得テスト"""
        from datetime import datetime, timedelta
        future_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        response = self.client.get(f'/api/logs/access-logs/stats?start_date={future_date}')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        
        # 未来の日付でフィルターしているので結果は0
        stats = data['data']
        self.assertEqual(stats['total'], 0)
        self.assertEqual(stats['status_codes'], {})
    
    def test_get_access_logs_api_empty_result(self):
        """該当データがない場合のアクセスログAPIテスト"""
        response = self.client.get('/api/logs/access-logs?user_email=nonexistent@example.com')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['data']['logs']), 0)
        self.assertEqual(data['data']['pagination']['total'], 0)
    
    def test_get_access_logs_api_multiple_filters(self):
        """複数フィルター組み合わせのアクセスログAPIテスト"""
        response = self.client.get('/api/logs/access-logs?user_email=user1@example.com&ip_address=192.168.1.1')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['data']['logs']), 1)
        
        log = data['data']['logs'][0]
        self.assertEqual(log['user_email'], 'user1@example.com')
        self.assertEqual(log['ip_address'], '192.168.1.1')


if __name__ == '__main__':
    unittest.main()