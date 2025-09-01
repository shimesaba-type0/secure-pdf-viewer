"""
セッション無効化機能テストコード
TASK-003-7の実装をテスト
"""
import unittest
import sqlite3
import tempfile
import os
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import sys

# Flaskアプリをテスト用にインポート
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app, invalidate_all_sessions, setup_session_invalidation_scheduler
from database.models import create_tables, insert_initial_data, get_setting, set_setting


class TestSessionInvalidation(unittest.TestCase):
    """セッション無効化機能テスト"""
    
    def setUp(self):
        """テスト前の準備"""
        # テスト用データベース
        self.db_fd, self.db_path = tempfile.mkstemp()
        
        # Flaskアプリのテスト設定
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret-key'
        
        # データベースパスを置き換え
        self.original_db_path = 'instance/database.db'
        
        # テスト用データベースでテーブル作成
        with sqlite3.connect(self.db_path) as conn:
            create_tables(conn)
            
            # 初期設定をテスト用に簡単に設定
            conn.execute('''
                INSERT INTO settings (key, value, created_at, updated_at, updated_by)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            ''', ('shared_passphrase', 'test-passphrase-hash', 'system'))
            
            conn.execute('''
                INSERT INTO settings (key, value, created_at, updated_at, updated_by)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            ''', ('author_name', 'Test Author', 'system'))
            
            # テスト用セッションデータを挿入
            conn.execute('''
                INSERT INTO session_stats (session_id, start_time, email_hash)
                VALUES (?, ?, ?)
            ''', ('test-session-1', int(datetime.now().timestamp()), 'test1@example.com'))
            
            conn.execute('''
                INSERT INTO session_stats (session_id, start_time, email_hash)
                VALUES (?, ?, ?)
            ''', ('test-session-2', int(datetime.now().timestamp()), 'test2@example.com'))
            
            # テスト用OTPトークンを挿入
            now = datetime.now()
            expires = now + timedelta(minutes=5)
            conn.execute('''
                INSERT INTO otp_tokens (email, otp_code, created_at, expires_at)
                VALUES (?, ?, ?, ?)
            ''', ('test1@example.com', '123456', now.isoformat(), expires.isoformat()))
            
            conn.execute('''
                INSERT INTO otp_tokens (email, otp_code, created_at, expires_at)
                VALUES (?, ?, ?, ?)
            ''', ('test2@example.com', '789012', now.isoformat(), expires.isoformat()))
            
            conn.commit()
        
        self.client = app.test_client()
        
    def tearDown(self):
        """テスト後のクリーンアップ"""
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    @patch('app.sqlite3.connect')
    def test_invalidate_all_sessions_success(self, mock_connect):
        """全セッション無効化機能の成功テスト"""
        # モックデータベース接続の設定
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # セッション数とOTP数をモック
        mock_cursor.fetchone.side_effect = [
            (2,),  # session_stats count
            (3,)   # otp_tokens count
        ]
        mock_cursor.rowcount = 2  # 最初の削除で2行削除
        
        # 2回目の呼び出し用に再設定
        def side_effect_rowcount(*args):
            if mock_cursor.execute.call_count <= 2:
                return 2  # セッション削除
            else:
                return 3  # OTP削除
        
        mock_cursor.rowcount = 2
        
        # 関数実行
        result = invalidate_all_sessions()
        
        # 結果検証
        self.assertTrue(result['success'])
        self.assertEqual(result['deleted_sessions'], 2)
        self.assertIn('timestamp', result)
        self.assertIn('message', result)
        
        # データベース操作の検証
        self.assertEqual(mock_cursor.execute.call_count, 4)  # 2つのCOUNT + 2つのDELETE
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('app.sqlite3.connect')
    def test_invalidate_all_sessions_error(self, mock_connect):
        """全セッション無効化機能のエラーテスト"""
        # データベースエラーをシミュレート
        mock_connect.side_effect = sqlite3.Error("Database error")
        
        # 関数実行
        result = invalidate_all_sessions()
        
        # エラー結果検証
        self.assertFalse(result['success'])
        self.assertIn('error', result)
        self.assertIn('timestamp', result)
        self.assertIn('message', result)
    
    def test_manual_invalidate_api_unauthorized(self):
        """手動無効化API認証エラーテスト"""
        response = self.client.post('/admin/invalidate-all-sessions')
        self.assertEqual(response.status_code, 401)
        
        data = json.loads(response.data)
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'Unauthorized')
    
    def test_manual_invalidate_api_authenticated(self):
        """手動無効化API認証済みテスト"""
        # セッションを設定して認証状態をシミュレート
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
        
        with patch('app.invalidate_all_sessions') as mock_invalidate:
            mock_invalidate.return_value = {
                'success': True,
                'deleted_sessions': 5,
                'deleted_otps': 3,
                'timestamp': datetime.now().isoformat(),
                'message': 'Test completion'
            }
            
            response = self.client.post('/admin/invalidate-all-sessions')
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertTrue(data['success'])
            self.assertEqual(data['deleted_sessions'], 5)
            self.assertEqual(data['deleted_otps'], 3)
    
    def test_schedule_session_invalidation_unauthorized(self):
        """スケジュール設定API認証エラーテスト"""
        future_datetime = (datetime.now() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
        response = self.client.post('/admin/schedule-session-invalidation', 
                                  data={'invalidation_datetime': future_datetime})
        # 認証エラーではloginページにリダイレクト
        self.assertEqual(response.status_code, 302)
    
    def test_schedule_session_invalidation_authenticated(self):
        """スケジュール設定API認証済みテスト"""
        # セッションを設定して認証状態をシミュレート
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
        
        with patch('app.setup_session_invalidation_scheduler') as mock_setup, \
             patch('app.sqlite3.connect') as mock_connect, \
             patch('app.set_setting') as mock_set_setting:
            
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            
            # 未来の日時を設定
            future_datetime = (datetime.now() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
            
            response = self.client.post('/admin/schedule-session-invalidation', 
                                      data={'invalidation_datetime': future_datetime})
            
            # リダイレクトを確認
            self.assertEqual(response.status_code, 302)
            
            # スケジューラー設定が呼ばれたことを確認
            mock_setup.assert_called_once_with(future_datetime)
            mock_set_setting.assert_called_once()
    
    def test_schedule_session_invalidation_invalid_time(self):
        """スケジュール設定API不正時刻テスト"""
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
        
        response = self.client.post('/admin/schedule-session-invalidation', 
                                  data={'invalidation_datetime': 'invalid-datetime'})
        
        # リダイレクトを確認
        self.assertEqual(response.status_code, 302)
    
    def test_clear_session_invalidation_schedule_unauthorized(self):
        """スケジュール解除API認証エラーテスト"""
        response = self.client.post('/admin/clear-session-invalidation-schedule')
        self.assertEqual(response.status_code, 401)
        
        data = json.loads(response.data)
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'Unauthorized')
    
    def test_clear_session_invalidation_schedule_authenticated(self):
        """スケジュール解除API認証済みテスト"""
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
        
        with patch('app.sqlite3.connect') as mock_connect, \
             patch('app.set_setting') as mock_set_setting, \
             patch('app.scheduler') as mock_scheduler:
            
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            
            response = self.client.post('/admin/clear-session-invalidation-schedule')
            
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data['success'])
            
            # データベース設定削除が呼ばれたことを確認
            mock_set_setting.assert_called_once()
            # スケジューラーからジョブ削除が試行されたことを確認
            mock_scheduler.remove_job.assert_called_once_with('session_invalidation')
    
    @patch('app.scheduler')
    def test_setup_session_invalidation_scheduler(self, mock_scheduler):
        """スケジューラー設定機能テスト（日時形式）"""
        # 既存ジョブ削除のエラーは無視されることを確認
        mock_scheduler.remove_job.side_effect = Exception("Job not found")
        
        # 未来の日時でテスト
        future_datetime = (datetime.now() + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')
        
        # 関数実行
        setup_session_invalidation_scheduler(future_datetime)
        
        # スケジューラー操作が正しく呼ばれたことを確認
        mock_scheduler.remove_job.assert_called_once_with('session_invalidation')
        mock_scheduler.add_job.assert_called_once()
        
        # add_jobの引数を検証（dateトリガーに変更されている）
        call_args = mock_scheduler.add_job.call_args
        self.assertEqual(call_args[1]['trigger'], 'date')
        self.assertEqual(call_args[1]['id'], 'session_invalidation')
        self.assertTrue(call_args[1]['replace_existing'])
    
    @patch('app.broadcast_sse_event')
    @patch('app.sqlite3.connect')
    def test_invalidate_all_sessions_with_sse_notification(self, mock_connect, mock_sse):
        """SSE通知付きセッション無効化テスト"""
        # モックデータベース接続の設定
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # セッション数とOTP数をモック
        mock_cursor.fetchone.side_effect = [
            (3,),  # session_stats count
            (2,)   # otp_tokens count
        ]
        mock_cursor.rowcount = 3  # 削除された行数
        
        # 関数実行
        result = invalidate_all_sessions()
        
        # 結果検証
        self.assertTrue(result['success'])
        self.assertEqual(result['deleted_sessions'], 3)
        
        # SSE通知が送信されたことを確認
        mock_sse.assert_called_once()
        call_args = mock_sse.call_args
        self.assertEqual(call_args[0][0], 'session_invalidated')  # イベントタイプ
        
        # メッセージ内容を確認（新しいメッセージ）
        sse_data = call_args[0][1]
        self.assertEqual(sse_data['message'], '予定された時刻になったため、システムからログアウトされました。再度ログインしてください。')
        self.assertEqual(sse_data['redirect_url'], '/login')
        self.assertEqual(sse_data['deleted_sessions'], 3)
    
    def test_setup_session_invalidation_scheduler_past_time(self):
        """過去日時でのスケジューラー設定エラーテスト"""
        # 過去の日時でテスト
        past_datetime = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')
        
        # ValueErrorが発生することを確認
        with self.assertRaises(ValueError) as context:
            setup_session_invalidation_scheduler(past_datetime)
        
        self.assertIn('過去の日時は設定できません', str(context.exception))


if __name__ == '__main__':
    # テスト実行
    unittest.main(verbosity=2)