#!/usr/bin/env python3
"""
セキュリティイベントログ機能のテスト
"""
import unittest
import sqlite3
import tempfile
import os
import json
from datetime import datetime, timedelta
import sys

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.models import log_security_event, get_security_events, get_security_event_stats


class TestSecurityEventLogging(unittest.TestCase):
    def setUp(self):
        """テスト用データベースを作成"""
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.test_db.close()
        self.db_path = self.test_db.name
        
        # テスト用データベース接続
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
        # テスト用テーブルを直接作成
        self.create_test_tables()
        self.conn.commit()
    
    def create_test_tables(self):
        """テスト用テーブルを作成"""
        # security_events テーブル
        self.conn.execute('''
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
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        self.conn.close()
        os.unlink(self.db_path)
    
    def test_log_security_event_basic(self):
        """基本的なセキュリティイベント記録のテスト"""
        # テストデータ
        user_email = 'test@example.com'
        event_type = 'download_attempt'
        event_details = {
            'method': 'right_click',
            'prevented': True,
            'timestamp': 1627890123456
        }
        risk_level = 'high'
        ip_address = '192.168.1.100'
        user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        pdf_file_path = '/path/to/test.pdf'
        session_id = 'test_session_123'
        
        # イベントを記録
        log_security_event(
            db=self.conn,
            user_email=user_email,
            event_type=event_type,
            event_details=event_details,
            risk_level=risk_level,
            ip_address=ip_address,
            user_agent=user_agent,
            pdf_file_path=pdf_file_path,
            session_id=session_id
        )
        self.conn.commit()
        
        # データベースから確認
        events = self.conn.execute('''
            SELECT * FROM security_events ORDER BY id DESC LIMIT 1
        ''').fetchone()
        
        self.assertIsNotNone(events)
        self.assertEqual(events['user_email'], user_email)
        self.assertEqual(events['event_type'], event_type)
        self.assertEqual(events['risk_level'], risk_level)
        self.assertEqual(events['ip_address'], ip_address)
        self.assertEqual(events['user_agent'], user_agent)
        self.assertEqual(events['pdf_file_path'], pdf_file_path)
        self.assertEqual(events['session_id'], session_id)
        
        # event_detailsはJSONとして保存されているはず
        stored_details = json.loads(events['event_details'])
        self.assertEqual(stored_details['method'], 'right_click')
        self.assertEqual(stored_details['prevented'], True)
    
    def test_invalid_event_type(self):
        """無効なイベントタイプのテスト"""
        log_security_event(
            db=self.conn,
            user_email='test@example.com',
            event_type='invalid_event_type',
            event_details={'test': 'data'},
            risk_level='low'
        )
        self.conn.commit()
        
        # 無効なイベントタイプは 'unauthorized_action' に変換され、リスクレベルは 'high' になるはず
        events = self.conn.execute('''
            SELECT * FROM security_events ORDER BY id DESC LIMIT 1
        ''').fetchone()
        
        self.assertEqual(events['event_type'], 'unauthorized_action')
        self.assertEqual(events['risk_level'], 'high')
    
    def test_invalid_risk_level(self):
        """無効なリスクレベルのテスト"""
        log_security_event(
            db=self.conn,
            user_email='test@example.com',
            event_type='pdf_view',
            event_details={'test': 'data'},
            risk_level='invalid_risk'
        )
        self.conn.commit()
        
        # 無効なリスクレベルは 'low' にフォールバックするはず
        events = self.conn.execute('''
            SELECT * FROM security_events ORDER BY id DESC LIMIT 1
        ''').fetchone()
        
        self.assertEqual(events['risk_level'], 'low')
    
    def test_get_security_events_basic(self):
        """セキュリティイベント取得の基本テスト"""
        # テストデータを複数挿入
        test_events = [
            ('user1@example.com', 'download_attempt', 'high'),
            ('user2@example.com', 'print_attempt', 'high'),
            ('user1@example.com', 'pdf_view', 'low'),
            ('user3@example.com', 'devtools_open', 'high'),
        ]
        
        for user_email, event_type, risk_level in test_events:
            log_security_event(
                db=self.conn,
                user_email=user_email,
                event_type=event_type,
                event_details={'test': 'data'},
                risk_level=risk_level
            )
        self.conn.commit()
        
        # 全イベントを取得
        result = get_security_events(self.conn)
        self.assertEqual(len(result['events']), 4)
        self.assertEqual(result['total'], 4)
        self.assertFalse(result['has_more'])
    
    def test_get_security_events_with_filters(self):
        """フィルタ付きセキュリティイベント取得のテスト"""
        # テストデータを挿入
        test_events = [
            ('user1@example.com', 'download_attempt', 'high'),
            ('user2@example.com', 'print_attempt', 'high'),
            ('user1@example.com', 'pdf_view', 'low'),
            ('user3@example.com', 'devtools_open', 'high'),
        ]
        
        for user_email, event_type, risk_level in test_events:
            log_security_event(
                db=self.conn,
                user_email=user_email,
                event_type=event_type,
                event_details={'test': 'data'},
                risk_level=risk_level
            )
        self.conn.commit()
        
        # user1@example.com のイベントのみ取得
        result = get_security_events(self.conn, user_email='user1@example.com')
        self.assertEqual(len(result['events']), 2)
        self.assertEqual(result['total'], 2)
        
        # high リスクのイベントのみ取得
        result = get_security_events(self.conn, risk_level='high')
        self.assertEqual(len(result['events']), 3)
        self.assertEqual(result['total'], 3)
        
        # download_attempt イベントのみ取得
        result = get_security_events(self.conn, event_type='download_attempt')
        self.assertEqual(len(result['events']), 1)
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['events'][0]['user_email'], 'user1@example.com')
    
    def test_get_security_events_pagination(self):
        """ページネーションのテスト"""
        # 10個のテストイベントを挿入
        for i in range(10):
            log_security_event(
                db=self.conn,
                user_email=f'user{i}@example.com',
                event_type='pdf_view',
                event_details={'index': i},
                risk_level='low'
            )
        self.conn.commit()
        
        # 最初の5件を取得
        result = get_security_events(self.conn, limit=5, offset=0)
        self.assertEqual(len(result['events']), 5)
        self.assertEqual(result['total'], 10)
        self.assertTrue(result['has_more'])
        
        # 次の5件を取得
        result = get_security_events(self.conn, limit=5, offset=5)
        self.assertEqual(len(result['events']), 5)
        self.assertEqual(result['total'], 10)
        self.assertFalse(result['has_more'])
    
    def test_get_security_event_stats(self):
        """統計情報取得のテスト"""
        # テストデータを挿入
        test_events = [
            ('high', 'download_attempt'),
            ('high', 'print_attempt'),
            ('high', 'devtools_open'),
            ('medium', 'direct_access'),
            ('medium', 'copy_attempt'),
            ('low', 'pdf_view'),
            ('low', 'pdf_view'),
            ('low', 'page_leave'),
        ]
        
        for risk_level, event_type in test_events:
            log_security_event(
                db=self.conn,
                user_email='test@example.com',
                event_type=event_type,
                event_details={'test': 'data'},
                risk_level=risk_level
            )
        self.conn.commit()
        
        # 統計情報を取得
        stats = get_security_event_stats(self.conn)
        
        self.assertEqual(stats['total'], 8)
        self.assertEqual(stats['risk_levels']['high'], 3)
        self.assertEqual(stats['risk_levels']['medium'], 2)
        self.assertEqual(stats['risk_levels']['low'], 3)
        
        # イベントタイプ別統計（件数順）
        self.assertEqual(stats['event_types']['pdf_view'], 2)
        self.assertEqual(stats['event_types']['download_attempt'], 1)
        self.assertEqual(stats['event_types']['print_attempt'], 1)
    
    def test_event_details_json_handling(self):
        """イベント詳細のJSON処理テスト"""
        # 複雑なイベント詳細をテスト
        complex_details = {
            'method': 'ctrl_s',
            'prevented': True,
            'timestamp': 1627890123456,
            'browser_info': {
                'name': 'Chrome',
                'version': '91.0.4472.124'
            },
            'coordinates': {
                'x': 100,
                'y': 200
            },
            'nested_array': [1, 2, 3, 'test']
        }
        
        log_security_event(
            db=self.conn,
            user_email='test@example.com',
            event_type='download_attempt',
            event_details=complex_details,
            risk_level='high'
        )
        self.conn.commit()
        
        # 取得して確認
        result = get_security_events(self.conn, limit=1)
        stored_details = json.loads(result['events'][0]['event_details'])
        
        self.assertEqual(stored_details['method'], 'ctrl_s')
        self.assertEqual(stored_details['browser_info']['name'], 'Chrome')
        self.assertEqual(stored_details['coordinates']['x'], 100)
        self.assertEqual(stored_details['nested_array'], [1, 2, 3, 'test'])
    
    def test_empty_event_details(self):
        """空のイベント詳細のテスト"""
        log_security_event(
            db=self.conn,
            user_email='test@example.com',
            event_type='pdf_view',
            event_details=None,
            risk_level='low'
        )
        self.conn.commit()
        
        result = get_security_events(self.conn, limit=1)
        self.assertIsNone(result['events'][0]['event_details'])
    
    def test_date_filtering(self):
        """日付フィルタリングのテスト"""
        # 現在時刻を基準に過去と未来のイベントを作成
        base_time = datetime.now()
        
        # 過去のイベント（2日前）
        past_event_time = (base_time - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
        self.conn.execute('''
            INSERT INTO security_events (user_email, event_type, risk_level, occurred_at)
            VALUES (?, ?, ?, ?)
        ''', ('past@example.com', 'pdf_view', 'low', past_event_time))
        
        # 現在のイベント
        log_security_event(
            db=self.conn,
            user_email='current@example.com',
            event_type='download_attempt',
            event_details={'test': 'data'},
            risk_level='high'
        )
        self.conn.commit()
        
        # 昨日以降のイベントのみ取得
        yesterday = (base_time - timedelta(days=1)).strftime('%Y-%m-%d')
        result = get_security_events(self.conn, start_date=yesterday)
        
        # current@example.com のイベントのみが取得されるはず
        self.assertEqual(len(result['events']), 1)
        self.assertEqual(result['events'][0]['user_email'], 'current@example.com')


if __name__ == '__main__':
    unittest.main()