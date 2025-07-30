import unittest
import sqlite3
import tempfile  
import os
from database.models import get_access_logs, get_access_logs_stats


class TestAccessLogsSimple(unittest.TestCase):
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
            ('sess1', 'hash1', 'user1@example.com', '192.168.1.1', 'Mozilla/5.0', '/viewer', 'GET', 200, 120, None),
            ('sess2', 'hash2', 'user2@example.com', '192.168.1.2', 'Chrome/100.0', '/api/test', 'POST', 404, 5, None),
            ('sess3', 'hash3', 'user3@example.com', '192.168.1.3', 'Firefox/90.0', '/admin', 'GET', 500, 30, None)
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
    
    def test_access_logs_functions_work(self):
        """アクセスログ関数が動作することを確認"""
        # get_access_logs関数のテスト
        result = get_access_logs(self.conn)
        self.assertEqual(len(result['logs']), 3)
        self.assertEqual(result['pagination']['total'], 3)
        
        # get_access_logs_stats関数のテスト
        stats = get_access_logs_stats(self.conn)
        self.assertEqual(stats['total'], 3)
        self.assertIn('200', stats['status_codes'])
        self.assertIn('404', stats['status_codes'])
        self.assertIn('500', stats['status_codes'])
        
        print("✅ アクセスログ機能が正常に動作しています")


if __name__ == '__main__':
    unittest.main()