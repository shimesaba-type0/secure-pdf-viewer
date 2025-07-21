"""
認証フロー統合テストコード
セキュリティ脆弱性（2段階認証バイパス）のテストを含む
"""
import unittest
import sqlite3
import tempfile
import os
import datetime
from unittest.mock import patch, MagicMock
import sys

# Flaskアプリをテスト用にインポート
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from database.models import create_tables, insert_initial_data


class TestAuthenticationFlow(unittest.TestCase):
    """認証フロー統合テスト"""
    
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
        """データベース接続をテスト用に置き換える"""
        # 保存した元のconnectを使用して循環参照を回避
        conn = self.original_sqlite_connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def test_complete_authentication_flow(self):
        """完全な認証フローのテスト"""
        
        # Step 1: パスフレーズ認証
        with self.client.session_transaction() as sess:
            sess.clear()
        
        # パスフレーズ認証画面の表示
        response = self.client.get('/auth/login')
        self.assertEqual(response.status_code, 200)
        
        # 画面表示内容の確認（日本語）
        self.assertIn('パスフレーズ'.encode('utf-8'), response.data)
        
        # 機能面の確認
        self.assertIn(b'name="password"', response.data)  # パスフレーズ入力欄
        self.assertIn(b'type="submit"', response.data)    # 送信ボタン
        
        # パスフレーズ認証の実行（正しいパスフレーズを取得）
        with self.mock_db_connection() as conn:
            passphrase_row = conn.execute('SELECT value FROM settings WHERE key = ?', 
                                        ('shared_passphrase',)).fetchone()
            correct_passphrase = passphrase_row['value']
        
        response = self.client.post('/auth/login', data={
            'password': correct_passphrase
        }, follow_redirects=True)
        
        self.assertEqual(response.status_code, 200)
        # メールアドレス入力画面にリダイレクトされることを確認
        self.assertIn('メールアドレス'.encode('utf-8'), response.data)
        self.assertIn(b'name="email"', response.data)  # メールアドレス入力欄
    
    @patch('mail.email_service.EmailService')
    def test_email_otp_flow(self, mock_email_service):
        """メールアドレス入力からOTP送信までのフロー"""
        
        # EmailServiceのモック設定
        mock_service_instance = MagicMock()
        mock_service_instance.send_otp_email.return_value = True
        mock_email_service.return_value = mock_service_instance
        
        # Step 1: セッションにパスフレーズ認証完了をセット
        with self.client.session_transaction() as sess:
            sess['passphrase_verified'] = True
            sess['login_time'] = datetime.datetime.now().isoformat()
        
        # Step 2: メールアドレス入力画面の表示
        response = self.client.get('/auth/email')
        self.assertEqual(response.status_code, 200)
        
        # 画面表示内容の確認（日本語）
        self.assertIn('ワンタイムパスワード認証'.encode('utf-8'), response.data)
        self.assertIn('メールアドレス'.encode('utf-8'), response.data)
        
        # 機能面の確認
        self.assertIn(b'name="email"', response.data)  # メールアドレス入力欄
        
        # Step 3: メールアドレス送信とOTP生成
        test_email = 'test@example.com'
        response = self.client.post('/auth/email', data={
            'email': test_email
        }, follow_redirects=True)
        
        self.assertEqual(response.status_code, 200)
        # OTP検証画面にリダイレクトされることを確認
        self.assertIn(test_email.encode(), response.data)
        
        # データベースにOTPが保存されていることを確認
        with self.mock_db_connection() as conn:
            otp_record = conn.execute('''
                SELECT otp_code, email, used FROM otp_tokens 
                WHERE email = ? ORDER BY created_at DESC LIMIT 1
            ''', (test_email,)).fetchone()
            
            self.assertIsNotNone(otp_record)
            self.assertEqual(otp_record['email'], test_email)
            self.assertFalse(otp_record['used'])
            self.assertEqual(len(otp_record['otp_code']), 6)
            self.assertTrue(otp_record['otp_code'].isdigit())
        
        # メール送信が呼ばれたことを確認
        mock_service_instance.send_otp_email.assert_called_once_with(test_email, otp_record['otp_code'])
    
    def test_otp_verification_flow(self):
        """OTP検証フローのテスト"""
        
        test_email = 'test@example.com'
        test_otp = '123456'
        
        # テスト用OTPをデータベースに挿入
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
        with self.mock_db_connection() as conn:
            conn.execute('''
                INSERT INTO otp_tokens (email, otp_code, expires_at, session_id, ip_address)
                VALUES (?, ?, ?, ?, ?)
            ''', (test_email, test_otp, expires_at.isoformat(), 'test_session', '127.0.0.1'))
            conn.commit()
        
        # セッション設定
        with self.client.session_transaction() as sess:
            sess['passphrase_verified'] = True
            sess['email'] = test_email
        
        # OTP検証画面の表示
        response = self.client.get('/auth/verify-otp')
        self.assertEqual(response.status_code, 200)
        self.assertIn(test_email.encode(), response.data)
        
        # 正しいOTPでの検証
        response = self.client.post('/auth/verify-otp', data={
            'otp_code': test_otp
        })
        
        # リダイレクトが発生することを確認
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/'))  # indexページへのリダイレクト
        
        # セッションが完全認証状態になっていることを確認
        with self.client.session_transaction() as sess:
            self.assertTrue(sess.get('authenticated'))
            self.assertEqual(sess.get('email'), test_email)
        
        # OTPが使用済みになっていることを確認
        with self.mock_db_connection() as conn:
            otp_record = conn.execute('''
                SELECT used FROM otp_tokens WHERE email = ? AND otp_code = ?
            ''', (test_email, test_otp)).fetchone()
            self.assertTrue(otp_record['used'])
    
    def test_invalid_otp_verification(self):
        """無効なOTP検証のテスト"""
        
        test_email = 'test@example.com'
        valid_otp = '123456'
        invalid_otp = '654321'
        
        # 有効なOTPをデータベースに挿入
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
        with self.mock_db_connection() as conn:
            conn.execute('''
                INSERT INTO otp_tokens (email, otp_code, expires_at)
                VALUES (?, ?, ?)
            ''', (test_email, valid_otp, expires_at.isoformat()))
            conn.commit()
        
        # セッション設定
        with self.client.session_transaction() as sess:
            sess['passphrase_verified'] = True
            sess['email'] = test_email
        
        # 無効なOTPでの検証試行
        response = self.client.post('/auth/verify-otp', data={
            'otp_code': invalid_otp
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'error', response.data.lower())
        
        # セッションが未認証のままであることを確認
        with self.client.session_transaction() as sess:
            self.assertFalse(sess.get('authenticated', False))
    
    def test_expired_otp_verification(self):
        """期限切れOTP検証のテスト"""
        
        test_email = 'test@example.com'
        expired_otp = '123456'
        
        # 期限切れOTPをデータベースに挿入
        expires_at = datetime.datetime.now() - datetime.timedelta(minutes=1)
        with self.mock_db_connection() as conn:
            conn.execute('''
                INSERT INTO otp_tokens (email, otp_code, expires_at)
                VALUES (?, ?, ?)
            ''', (test_email, expired_otp, expires_at.isoformat()))
            conn.commit()
        
        # セッション設定
        with self.client.session_transaction() as sess:
            sess['passphrase_verified'] = True
            sess['email'] = test_email
        
        # 期限切れOTPでの検証試行
        response = self.client.post('/auth/verify-otp', data={
            'otp_code': expired_otp
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'error', response.data.lower())
        self.assertIn(b'\xe6\x9c\x9f\xe9\x99\x90', response.data)  # 期限（UTF-8エンコード）
    
    def test_authentication_redirects(self):
        """認証が必要なページへのリダイレクトテスト"""
        
        # 未認証での管理画面アクセス
        response = self.client.get('/admin')
        self.assertEqual(response.status_code, 302)  # リダイレクト
        
        # 未認証でのメイン画面アクセス
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)  # リダイレクト
        
        # パスフレーズ認証のみでのOTP検証画面アクセス
        with self.client.session_transaction() as sess:
            sess['passphrase_verified'] = True
            # emailが設定されていない
        
        response = self.client.get('/auth/verify-otp')
        self.assertEqual(response.status_code, 302)  # ログイン画面にリダイレクト
    
    def test_session_management(self):
        """セッション管理のテスト"""
        
        test_email = 'test@example.com'
        
        # 完全認証状態のセッション作成
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['email'] = test_email
            sess['auth_completed_at'] = datetime.datetime.now().isoformat()
        
        # 認証が必要なページにアクセス可能であることを確認
        response = self.client.get('/admin')
        self.assertEqual(response.status_code, 200)
        
        # ログアウト
        response = self.client.get('/auth/logout', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # セッションがクリアされていることを確認
        with self.client.session_transaction() as sess:
            self.assertFalse(sess.get('authenticated', False))
            self.assertIsNone(sess.get('email'))
        
        # 再度認証が必要になることを確認
        response = self.client.get('/admin')
        self.assertEqual(response.status_code, 302)


class TestAuthenticationSecurity(unittest.TestCase):
    """認証セキュリティのテスト"""
    
    def setUp(self):
        """テスト前の準備"""
        self.db_fd, self.db_path = tempfile.mkstemp()
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        
        # 元のsqlite3.connectを保存
        self.original_sqlite_connect = sqlite3.connect
        
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
        """データベース接続をテスト用に置き換える"""
        # 保存した元のconnectを使用して循環参照を回避
        conn = self.original_sqlite_connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def test_otp_rate_limiting(self):
        """OTP送信レート制限のテスト（将来の機能）"""
        
        # セッション設定
        with self.client.session_transaction() as sess:
            sess['passphrase_verified'] = True
        
        test_email = 'test@example.com'
        
        # 短時間での複数回OTP送信
        for i in range(3):
            response = self.client.post('/auth/email', data={
                'email': test_email
            })
            # 現在は制限なしだが、将来実装予定
            self.assertIn(response.status_code, [200, 302])
    
    def test_session_isolation(self):
        """セッション分離のテスト"""
        
        # 2つの異なるクライアント
        client1 = app.test_client()
        client2 = app.test_client()
        
        # client1で認証
        with client1.session_transaction() as sess:
            sess['authenticated'] = True
            sess['email'] = 'user1@example.com'
        
        # client2は未認証
        response1 = client1.get('/admin')
        response2 = client2.get('/admin')
        
        self.assertEqual(response1.status_code, 200)  # 認証済み
        self.assertEqual(response2.status_code, 302)  # 未認証


class TestSessionExpiration(unittest.TestCase):
    """セッション有効期限のテスト"""
    
    def setUp(self):
        """テスト前の準備"""
        self.db_fd, self.db_path = tempfile.mkstemp()
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret-key'
        
        # 元のsqlite3.connectを保存
        self.original_sqlite_connect = sqlite3.connect
        
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
        """データベース接続をテスト用に置き換える"""
        conn = self.original_sqlite_connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def test_session_expiration_check(self):
        """セッション有効期限チェック機能のテスト"""
        import app
        
        # 各テストケース用にリクエストコンテキストとセッションを作成
        
        # テストケース1: 認証していないセッション
        with app.app.test_request_context():
            from flask import session
            session.clear()
            self.assertTrue(app.is_session_expired())
        
        # テストケース2: 認証済みだが期限切れのセッション
        old_time = datetime.datetime.now() - datetime.timedelta(hours=73)  # 73時間前
        with app.app.test_request_context():
            from flask import session
            session['authenticated'] = True
            session['auth_completed_at'] = old_time.isoformat()
            self.assertTrue(app.is_session_expired())
        
        # テストケース3: 有効なセッション
        valid_time = datetime.datetime.now() - datetime.timedelta(hours=1)  # 1時間前
        with app.app.test_request_context():
            from flask import session
            session['authenticated'] = True
            session['auth_completed_at'] = valid_time.isoformat()
            self.assertFalse(app.is_session_expired())
    
    def test_expired_session_redirect(self):
        """期限切れセッションでのリダイレクトテスト"""
        # 期限切れセッションを設定
        old_time = datetime.datetime.now() - datetime.timedelta(hours=73)
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['auth_completed_at'] = old_time.isoformat()
        
        # メインページにアクセス
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)  # リダイレクト
        self.assertIn('/auth/login', response.location)
    
    def test_expired_session_api_response(self):
        """期限切れセッションでのAPI応答テスト"""
        # 期限切れセッションを設定
        old_time = datetime.datetime.now() - datetime.timedelta(hours=73)
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['auth_completed_at'] = old_time.isoformat()
        
        # APIエンドポイントにアクセス
        response = self.client.get('/api/session-info')
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data['error'], 'Session expired')
    
    def test_valid_session_access(self):
        """有効セッションでの正常アクセステスト"""
        # 有効なセッションを設定
        valid_time = datetime.datetime.now() - datetime.timedelta(hours=1)
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['auth_completed_at'] = valid_time.isoformat()
            sess['email'] = 'test@example.com'
            sess['session_id'] = 'test-session-id'
        
        # APIエンドポイントにアクセス
        response = self.client.get('/api/session-info')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['email'], 'test@example.com')
    
    @patch('app.get_setting')
    def test_custom_session_timeout(self, mock_get_setting):
        """カスタムセッション有効期限設定のテスト"""
        # カスタム有効期限を設定（2時間 = 7200秒）
        mock_get_setting.return_value = 7200
        
        import app
        
        # 3時間前のセッション（カスタム設定では期限切れ）
        old_time = datetime.datetime.now() - datetime.timedelta(hours=3)
        with app.app.test_request_context():
            from flask import session
            session['authenticated'] = True
            session['auth_completed_at'] = old_time.isoformat()
            self.assertTrue(app.is_session_expired())
        
        # 1時間前のセッション（カスタム設定では有効）
        valid_time = datetime.datetime.now() - datetime.timedelta(hours=1)
        with app.app.test_request_context():
            from flask import session
            session['authenticated'] = True
            session['auth_completed_at'] = valid_time.isoformat()
            self.assertFalse(app.is_session_expired())
    
    @patch('mail.email_service.EmailService')
    def test_two_factor_auth_bypass_prevention(self, mock_email_service):
        """2段階認証バイパス脆弱性の防止テスト"""
        mock_email_service.return_value.send_otp_email.return_value = True
        
        # 1. 正常な2段階認証フローでセッションを確立
        # パスフレーズ認証
        response = self.client.post('/auth/login', data={'password': 'correct-passphrase'})
        self.assertEqual(response.status_code, 302)
        
        # メール認証
        response = self.client.post('/auth/email', data={'email': 'test@example.com'})
        self.assertEqual(response.status_code, 302)
        
        # OTP認証完了
        response = self.client.post('/auth/verify-otp', data={'otp_code': '123456'})
        self.assertEqual(response.status_code, 302)
        
        # セッションが確立されていることを確認
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        
        # 2. 全セッション無効化を実行
        import app
        with app.app.test_request_context():
            app.invalidate_all_sessions()
        
        # 3. セッション無効化後、パスフレーズ認証のみでコンテンツアクセスを試行
        response = self.client.post('/auth/login', data={'password': 'correct-passphrase'})
        self.assertEqual(response.status_code, 302)
        
        # パスフレーズ認証後、メイン画面に直接アクセスを試行（これは失敗すべき）
        response = self.client.get('/')
        # セッション整合性チェックによりログイン画面にリダイレクトされるべき
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login', response.location)
    
    def test_session_integrity_check_missing_database_record(self):
        """データベース記録がない場合のセッション整合性チェック"""
        import app
        
        # Flaskセッションに認証情報を設定するが、データベースには記録しない
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['passphrase_verified'] = True
            sess['email'] = 'test@example.com'
            sess['session_id'] = 'nonexistent-session-id'
            sess['auth_completed_at'] = datetime.datetime.now().isoformat()
        
        # セッション整合性チェックは失敗すべき
        with app.app.test_request_context():
            from flask import session
            session.update({
                'authenticated': True,
                'passphrase_verified': True,
                'email': 'test@example.com',
                'session_id': 'nonexistent-session-id',
                'auth_completed_at': datetime.datetime.now().isoformat()
            })
            self.assertFalse(app.check_session_integrity())
    
    def test_session_integrity_check_time_mismatch(self):
        """認証時刻不整合の場合のセッション整合性チェック"""
        import app
        
        # データベースに正常なセッション記録を作成
        with self.original_sqlite_connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO session_stats (session_id, email_hash, start_time, ip_address, device_type)
                VALUES (?, ?, ?, ?, ?)
            ''', ('test-session-id', '973dfe463ec85785',  # get_consistent_hash('test@example.com')の結果 
                  int(datetime.datetime.now().timestamp()), '127.0.0.1', 'web'))
            conn.commit()
        
        # Flaskセッションには大幅に異なる認証時刻を設定
        with app.app.test_request_context():
            from flask import session
            wrong_time = datetime.datetime.now() - datetime.timedelta(hours=1)
            session.update({
                'authenticated': True,
                'passphrase_verified': True,
                'email': 'test@example.com',
                'session_id': 'test-session-id',
                'auth_completed_at': wrong_time.isoformat()
            })
            
            # 時刻不整合によりセッション整合性チェックは失敗すべき
            self.assertFalse(app.check_session_integrity())
    
    def test_auth_flow_with_integrity_check(self):
        """認証フロー中の整合性チェック機能テスト"""
        # 不正なセッション状態でメール認証画面にアクセス
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['passphrase_verified'] = True
            sess['email'] = 'test@example.com'
            sess['session_id'] = 'fake-session-id'
            sess['auth_completed_at'] = datetime.datetime.now().isoformat()
        
        # 整合性チェックにより /auth/email はログイン画面にリダイレクトすべき
        response = self.client.get('/auth/email')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login', response.location)


if __name__ == '__main__':
    # テストスイートの実行
    unittest.main(verbosity=2)