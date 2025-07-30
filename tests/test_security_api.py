#!/usr/bin/env python3
"""
セキュリティイベントログAPIのテスト
"""
import unittest
import sqlite3
import tempfile
import os
import json
import sys
from unittest.mock import patch, MagicMock

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import app as flask_app
from database.models import log_security_event


class TestSecurityAPI(unittest.TestCase):
    def setUp(self):
        """テスト用Flaskアプリとデータベースを作成"""
        # テスト用データベース
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.test_db.close()
        self.db_path = self.test_db.name
        
        # Flaskテストクライアント
        flask_app.app.config['TESTING'] = True
        flask_app.app.config['DATABASE'] = self.db_path
        self.client = flask_app.app.test_client()
        
        # テスト用データベース設定
        self.create_test_tables()
        
        # テスト用セッション設定
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['email'] = 'test@example.com'
            sess['session_id'] = 'test_session_123'
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        os.unlink(self.db_path)
    
    def create_test_tables(self):
        """テスト用テーブルを作成"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK (event_type IN (
                    'pdf_view', 'download_attempt', 'print_attempt', 
                    'direct_access', 'devtools_open', 'unauthorized_action', 
                    'page_leave', 'screenshot_attempt', 'copy_attempt'
                )),
                event_details JSON,
                risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')) DEFAULT 'low',
                ip_address TEXT,
                user_agent TEXT,
                occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                pdf_file_path TEXT,
                session_id TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                added_by TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        # テスト用管理者を追加
        conn.execute('''
            INSERT INTO admin_users (email, added_by, is_active)
            VALUES (?, ?, ?)
        ''', ('test@example.com', 'system', True))
        conn.commit()
        conn.close()
    
    def test_record_security_event_success(self):
        """セキュリティイベント記録APIの成功テスト"""
        event_data = {
            'event_type': 'download_attempt',
            'event_details': {
                'method': 'right_click',
                'prevented': True,
                'timestamp': 1627890123456
            },
            'risk_level': 'high',
            'pdf_file_path': '/path/to/test.pdf'
        }
        
        with patch('app.get_db_path', return_value=self.db_path), \
             patch('app.is_session_expired', return_value=False):
            response = self.client.post('/api/security-event',
                                       data=json.dumps(event_data),
                                       content_type='application/json')
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['message'], 'Security event recorded')
        
        # データベースで確認
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        event = conn.execute('SELECT * FROM security_events ORDER BY id DESC LIMIT 1').fetchone()
        self.assertIsNotNone(event)
        self.assertEqual(event['user_email'], 'test@example.com')
        self.assertEqual(event['event_type'], 'download_attempt')
        self.assertEqual(event['risk_level'], 'high')
        conn.close()
    
    def test_record_security_event_unauthorized(self):
        """認証なしでのセキュリティイベント記録APIテスト"""
        event_data = {
            'event_type': 'download_attempt',
            'event_details': {'test': 'data'}
        }
        
        # セッションをクリア
        with self.client.session_transaction() as sess:
            sess.clear()
        
        response = self.client.post('/api/security-event',
                                   data=json.dumps(event_data),
                                   content_type='application/json')
        
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Unauthorized')
    
    def test_record_security_event_invalid_data(self):
        """無効なデータでのセキュリティイベント記録APIテスト"""
        # event_typeが欠如
        event_data = {
            'event_details': {'test': 'data'}
        }
        
        with patch('app.get_db_path', return_value=self.db_path), \
             patch('app.is_session_expired', return_value=False):
            response = self.client.post('/api/security-event',
                                       data=json.dumps(event_data),
                                       content_type='application/json')
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'event_type is required')
    
    def test_get_security_events_success(self):
        """セキュリティイベント取得APIの成功テスト"""
        # テストデータを挿入
        conn = sqlite3.connect(self.db_path)
        log_security_event(
            db=conn,
            user_email='test@example.com',
            event_type='download_attempt',
            event_details={'method': 'right_click'},
            risk_level='high'
        )
        conn.commit()
        conn.close()
        
        with patch('app.get_db_path', return_value=self.db_path):
            response = self.client.get('/api/logs/security-events')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['data']['events']), 1)
        self.assertEqual(data['data']['events'][0]['event_type'], 'download_attempt')
    
    def test_get_security_events_unauthorized(self):
        """管理者以外でのセキュリティイベント取得APIテスト"""
        # 管理者ユーザーを削除
        conn = sqlite3.connect(self.db_path)
        conn.execute('DELETE FROM admin_users')
        conn.commit()
        conn.close()
        
        with patch('app.get_db_path', return_value=self.db_path):
            response = self.client.get('/api/logs/security-events')
        
        self.assertEqual(response.status_code, 403)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Admin access required')
    
    def test_get_security_events_with_filters(self):
        """フィルタ付きセキュリティイベント取得APIテスト"""
        # 複数のテストデータを挿入
        conn = sqlite3.connect(self.db_path)
        test_events = [
            ('user1@example.com', 'download_attempt', 'high'),
            ('user2@example.com', 'print_attempt', 'high'),
            ('user1@example.com', 'pdf_view', 'low'),
        ]
        for user_email, event_type, risk_level in test_events:
            log_security_event(
                db=conn,
                user_email=user_email,
                event_type=event_type,
                event_details={'test': 'data'},
                risk_level=risk_level
            )
        conn.commit()
        conn.close()
        
        # user1@example.com のイベントのみ取得
        with patch('app.get_db_path', return_value=self.db_path):
            response = self.client.get('/api/logs/security-events?user_email=user1@example.com')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['data']['events']), 2)
        
        # high リスクのイベントのみ取得
        with patch('app.get_db_path', return_value=self.db_path):
            response = self.client.get('/api/logs/security-events?risk_level=high')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['data']['events']), 2)
    
    def test_get_security_events_stats(self):
        """セキュリティイベント統計取得APIテスト"""
        # テストデータを挿入
        conn = sqlite3.connect(self.db_path)
        test_events = [
            ('high', 'download_attempt'),
            ('high', 'print_attempt'),
            ('medium', 'direct_access'),
            ('low', 'pdf_view'),
            ('low', 'page_leave'),
        ]
        for risk_level, event_type in test_events:
            log_security_event(
                db=conn,
                user_email='test@example.com',
                event_type=event_type,
                event_details={'test': 'data'},
                risk_level=risk_level
            )
        conn.commit()
        conn.close()
        
        with patch('app.get_db_path', return_value=self.db_path):
            response = self.client.get('/api/logs/security-events/stats')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        
        stats = data['data']
        self.assertEqual(stats['total'], 5)
        self.assertEqual(stats['risk_levels']['high'], 2)
        self.assertEqual(stats['risk_levels']['medium'], 1)
        self.assertEqual(stats['risk_levels']['low'], 2)


if __name__ == '__main__':
    unittest.main()