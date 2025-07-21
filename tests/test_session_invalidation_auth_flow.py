"""
セッション無効化後の認証フロー統合テスト
TASK-003-8で発生した問題をキャッチするためのテスト
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
from app import app, invalidate_all_sessions
from database.models import create_tables, insert_initial_data


class TestSessionInvalidationAuthFlow(unittest.TestCase):
    """セッション無効化後の認証フロー統合テスト"""
    
    def setUp(self):
        """テスト前の準備"""
        # テスト用データベース
        self.db_fd, self.db_path = tempfile.mkstemp()
        
        # Flaskアプリのテスト設定
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret-key'
        
        # 元のsqlite3.connectを保存
        self.original_sqlite_connect = sqlite3.connect
        
        # テスト用データベース作成
        with self.original_sqlite_connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_tables(conn)
            insert_initial_data(conn)
        
        # アプリケーションのデータベースパスをテスト用に変更
        self.patcher = patch('app.sqlite3.connect')
        self.mock_connect = self.patcher.start()
        self.mock_connect.side_effect = lambda *args: self.mock_db_connection()
        
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        self.patcher.stop()
        self.app_context.pop()
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def mock_db_connection(self):
        """テスト用データベース接続を返す"""
        conn = self.original_sqlite_connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    @patch('mail.email_service.EmailService')
    def complete_authentication_flow(self, mock_email_service):
        """完全な認証フローを実行してセッションを確立"""
        mock_email_service.return_value.send_otp_email.return_value = True
        
        # 1. パスフレーズ認証
        response = self.client.post('/auth/login', data={'password': 'correct-passphrase'})
        self.assertEqual(response.status_code, 302)
        
        # 2. メール認証
        response = self.client.post('/auth/email', data={'email': 'test@example.com'})
        self.assertEqual(response.status_code, 302)
        
        # 3. OTP認証完了
        response = self.client.post('/auth/verify-otp', data={'otp_code': '123456'})
        self.assertEqual(response.status_code, 302)
        
        # 認証完了を確認
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        
        return True
    
    @patch('app.broadcast_sse_event')  # SSE通知をモック
    @patch('mail.email_service.EmailService')
    def test_session_invalidation_complete_auth_flow(self, mock_email_service, mock_sse):
        """セッション無効化→完全認証フローテスト"""
        mock_email_service.return_value.send_otp_email.return_value = True
        
        # 1. 最初に正常な認証セッションを確立
        self.complete_authentication_flow()
        
        # 2. 全セッション無効化を実行
        with app.test_request_context():
            result = invalidate_all_sessions()
        self.assertTrue(result['success'])
        
        # 3. セッション無効化後、メイン画面アクセスでリダイレクトを確認
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login', response.location)
        
        # 4. パスフレーズ認証（この段階で問題が発生していた）
        response = self.client.post('/auth/login', data={'password': 'correct-passphrase'})
        self.assertEqual(response.status_code, 302)
        
        # 5. メール認証画面への遷移（整合性エラーが出ていた箇所）
        response = self.client.get('/auth/email')
        self.assertEqual(response.status_code, 200)  # エラーが出ずに正常表示
        
        # 6. 残りの認証フローも完了できることを確認
        response = self.client.post('/auth/email', data={'email': 'test@example.com'})
        self.assertEqual(response.status_code, 302)
        
        response = self.client.post('/auth/verify-otp', data={'otp_code': '123456'})
        self.assertEqual(response.status_code, 302)
        
        # 7. 最終的にメイン画面にアクセス可能
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
    
    @patch('app.broadcast_sse_event')
    def test_session_invalidation_clears_flask_session_residue(self, mock_sse):
        """セッション無効化がFlaskセッションの残留情報をクリアするかテスト"""
        # 1. セッションに古い認証情報を手動で設定（セッション無効化後の残留データをシミュレート）
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['session_id'] = 'old-invalid-session-id'
            sess['auth_completed_at'] = datetime.now().isoformat()
            sess['email'] = 'old@example.com'
            sess['passphrase_verified'] = True
        
        # 2. パスフレーズ認証でセッションがリセットされることを確認
        response = self.client.post('/auth/login', data={'password': 'correct-passphrase'})
        # パスフレーズが正しくない場合でも、ログイン画面のレンダリングは成功する
        self.assertIn(response.status_code, [200, 302])
        
        # 3. セッション情報が正しくリセットされているか確認
        with self.client.session_transaction() as sess:
            # パスフレーズ認証後は、古い認証情報がクリアされているはず
            self.assertIsNone(sess.get('authenticated'))
            self.assertIsNone(sess.get('session_id'))
            self.assertIsNone(sess.get('auth_completed_at'))
            self.assertIsNone(sess.get('email'))
            # パスフレーズ認証情報のみ残っているはず
            self.assertTrue(sess.get('passphrase_verified'))
    
    def test_session_integrity_check_triggers_correctly(self):
        """セッション整合性チェックが適切なタイミングで実行されるかテスト"""
        # 1. 不完全な認証状態を手動で設定
        with self.client.session_transaction() as sess:
            sess['passphrase_verified'] = True
            # authenticatedやsession_idは設定しない
        
        # 2. /auth/emailにアクセス（整合性チェックはスキップされるはず）
        response = self.client.get('/auth/email')
        self.assertEqual(response.status_code, 200)
        
        # 3. 完全認証状態を手動で設定
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['session_id'] = 'nonexistent-session-id'  # DBに存在しないID
            sess['auth_completed_at'] = datetime.now().isoformat()
            sess['email'] = 'test@example.com'
            sess['passphrase_verified'] = True
        
        # 4. /auth/emailにアクセス（今度は整合性チェックが実行され、失敗するはず）
        response = self.client.get('/auth/email')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login', response.location)
    
    @patch('mail.email_service.EmailService')
    def test_session_integrity_check_with_valid_session(self, mock_email_service):
        """有効なセッションでの整合性チェック成功テスト"""
        mock_email_service.return_value.send_otp_email.return_value = True
        
        # 1. 正常な認証フローで有効なセッションを作成
        self.complete_authentication_flow()
        
        # 2. /auth/emailにアクセス（整合性チェックで正常と判定され、メイン画面にリダイレクト）
        response = self.client.get('/auth/email')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/', response.location)  # メイン画面へリダイレクト
    
    def test_consistent_hash_function(self):
        """一貫したハッシュ関数の動作テスト"""
        from app import get_consistent_hash
        
        # 同じ入力に対して常に同じハッシュ値を返すことを確認
        email = "test@example.com"
        hash1 = get_consistent_hash(email)
        hash2 = get_consistent_hash(email)
        
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 16)  # SHA256の最初の16文字
        self.assertEqual(hash1, "973dfe463ec85785")  # 期待値
    
    @patch('app.broadcast_sse_event')
    @patch('mail.email_service.EmailService')
    def test_multiple_tab_session_invalidation_scenario(self, mock_email_service, mock_sse):
        """複数タブでのセッション無効化シナリオテスト"""
        mock_email_service.return_value.send_otp_email.return_value = True
        
        # 1. 最初のタブで認証完了
        with self.client as client1:
            with client1.session_transaction() as sess:
                sess['authenticated'] = True
                sess['passphrase_verified'] = True
                sess['session_id'] = 'valid-session-id'
                sess['auth_completed_at'] = datetime.now().isoformat()
                sess['email'] = 'test@example.com'
            
            # データベースにセッション記録を作成
            conn = self.original_sqlite_connect(self.db_path)
            conn.execute('''
                INSERT INTO session_stats (session_id, email_hash, start_time, ip_address, device_type)
                VALUES (?, ?, ?, ?, ?)
            ''', ('valid-session-id', '973dfe463ec85785', 
                  int(datetime.now().timestamp()), '127.0.0.1', 'web'))
            conn.commit()
            conn.close()
            
            # 2. 2番目のタブ（同じセッション）で認証状態を確認
            response = client1.get('/')
            self.assertEqual(response.status_code, 200)
        
        # 3. セッション無効化実行
        with app.test_request_context():
            invalidate_all_sessions()
        
        # 4. 1番目のタブでパスフレーズ認証を試行
        response = self.client.post('/auth/login', data={'password': 'correct-passphrase'})
        self.assertEqual(response.status_code, 302)
        
        # 5. メール認証画面への遷移が正常に動作することを確認
        response = self.client.get('/auth/email')
        self.assertEqual(response.status_code, 200)
    
    def test_debug_logging_functionality(self):
        """デバッグログ機能のテスト"""
        with app.test_request_context():
            from app import check_session_integrity
            from flask import session
            
            # 1. 認証されていない状態
            result = check_session_integrity()
            self.assertFalse(result)
            
            # 2. 不完全な認証状態
            session['authenticated'] = True
            # passphrase_verifiedやemailを設定しない
            result = check_session_integrity()
            self.assertFalse(result)
            
            # 3. session_idがない状態
            session['passphrase_verified'] = True
            session['email'] = 'test@example.com'
            result = check_session_integrity()
            self.assertFalse(result)
            
            # 4. データベースに記録がない状態
            session['session_id'] = 'nonexistent-session-id'
            result = check_session_integrity()
            self.assertFalse(result)


if __name__ == '__main__':
    # テストスイートの実行
    unittest.main(verbosity=2)