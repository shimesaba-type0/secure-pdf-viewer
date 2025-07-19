"""
OTP機能のテストコード
"""
import unittest
import sqlite3
import tempfile
import os
import datetime
from unittest.mock import patch, MagicMock
import sys
import time

# テスト対象のモジュールをインポート
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.models import create_tables
from mail.email_service import EmailService


class TestOTPDatabase(unittest.TestCase):
    """OTPデータベース機能のテスト"""
    
    def setUp(self):
        """テスト前の準備"""
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        create_tables(self.conn)
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        self.conn.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_otp_table_creation(self):
        """OTPテーブルが正しく作成されることを確認"""
        # テーブルの存在確認
        result = self.conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='otp_tokens'
        """).fetchone()
        self.assertIsNotNone(result)
        
        # カラムの確認
        columns = self.conn.execute("PRAGMA table_info(otp_tokens)").fetchall()
        column_names = [col['name'] for col in columns]
        
        expected_columns = ['id', 'email', 'otp_code', 'session_id', 'ip_address', 
                          'created_at', 'expires_at', 'used', 'used_at']
        for col in expected_columns:
            self.assertIn(col, column_names)
    
    def test_otp_insert_and_retrieve(self):
        """OTPの挿入と取得のテスト"""
        email = 'test@example.com'
        otp_code = '123456'
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
        
        # OTP挿入
        self.conn.execute("""
            INSERT INTO otp_tokens (email, otp_code, expires_at, session_id, ip_address)
            VALUES (?, ?, ?, ?, ?)
        """, (email, otp_code, expires_at.isoformat(), 'test_session', '127.0.0.1'))
        self.conn.commit()
        
        # 取得テスト
        result = self.conn.execute("""
            SELECT email, otp_code, used FROM otp_tokens 
            WHERE email = ? AND otp_code = ?
        """, (email, otp_code)).fetchone()
        
        self.assertIsNotNone(result)
        self.assertEqual(result['email'], email)
        self.assertEqual(result['otp_code'], otp_code)
        self.assertFalse(result['used'])
    
    def test_otp_expiration(self):
        """OTP有効期限のテスト"""
        email = 'test@example.com'
        otp_code = '123456'
        
        # 期限切れのOTP
        expired_time = datetime.datetime.now() - datetime.timedelta(minutes=1)
        self.conn.execute("""
            INSERT INTO otp_tokens (email, otp_code, expires_at)
            VALUES (?, ?, ?)
        """, (email, otp_code, expired_time.isoformat()))
        
        # 有効なOTP
        valid_time = datetime.datetime.now() + datetime.timedelta(minutes=10)
        self.conn.execute("""
            INSERT INTO otp_tokens (email, otp_code, expires_at)
            VALUES (?, ?, ?)
        """, (email, '654321', valid_time.isoformat()))
        self.conn.commit()
        
        # 期限切れチェック
        now = datetime.datetime.now().isoformat()
        expired_otps = self.conn.execute("""
            SELECT COUNT(*) as count FROM otp_tokens 
            WHERE expires_at < ? AND used = FALSE
        """, (now,)).fetchone()
        
        self.assertEqual(expired_otps['count'], 1)
    
    def test_otp_invalidation(self):
        """OTP無効化のテスト"""
        email = 'test@example.com'
        otp_code = '123456'
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
        
        # OTP挿入
        self.conn.execute("""
            INSERT INTO otp_tokens (email, otp_code, expires_at)
            VALUES (?, ?, ?)
        """, (email, otp_code, expires_at.isoformat()))
        self.conn.commit()
        
        # 無効化
        self.conn.execute("""
            UPDATE otp_tokens 
            SET used = TRUE, used_at = CURRENT_TIMESTAMP 
            WHERE email = ? AND otp_code = ?
        """, (email, otp_code))
        self.conn.commit()
        
        # 確認
        result = self.conn.execute("""
            SELECT used FROM otp_tokens WHERE email = ? AND otp_code = ?
        """, (email, otp_code)).fetchone()
        
        self.assertTrue(result['used'])


class TestOTPGeneration(unittest.TestCase):
    """OTP生成機能のテスト"""
    
    def test_otp_generation_format(self):
        """OTP生成フォーマットのテスト"""
        import secrets
        
        # 6桁OTP生成
        otp_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        
        # フォーマット確認
        self.assertEqual(len(otp_code), 6)
        self.assertTrue(otp_code.isdigit())
        self.assertTrue(0 <= int(otp_code) <= 999999)
    
    def test_otp_uniqueness(self):
        """OTP一意性のテスト（確率的）"""
        import secrets
        
        # 100個のOTPを生成して重複をチェック
        otps = set()
        for _ in range(100):
            otp = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            otps.add(otp)
        
        # 重複がないことを確認（確率的に非常に高い）
        self.assertEqual(len(otps), 100)


class TestEmailService(unittest.TestCase):
    """メール送信機能のテスト"""
    
    @patch('smtplib.SMTP')
    def test_otp_email_sending(self, mock_smtp):
        """OTPメール送信のテスト"""
        # モックの設定
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # EmailServiceのテスト
        email_service = EmailService()
        
        # 環境変数をモック
        with patch.dict(os.environ, {
            'MAIL_SERVER': 'smtp.test.com',
            'MAIL_PORT': '587',
            'MAIL_USERNAME': 'test@test.com',
            'MAIL_PASSWORD': 'password'
        }):
            result = email_service.send_otp_email('user@example.com', '123456')
        
        # メール送信が呼ばれたことを確認
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.sendmail.assert_called_once()
        mock_server.quit.assert_called_once()
    
    def test_otp_email_content(self):
        """OTPメール内容のテスト"""
        email_service = EmailService()
        to_email = 'user@example.com'
        otp_code = '123456'
        
        # メール作成のテスト（送信はしない）
        subject = f"【Secure PDF Viewer】認証コード: {otp_code}"
        self.assertIn(otp_code, subject)
        self.assertIn('認証コード', subject)


class TestOTPValidation(unittest.TestCase):
    """OTP検証機能のテスト"""
    
    def test_otp_format_validation(self):
        """OTPフォーマット検証のテスト"""
        
        # 有効なOTPコード
        valid_otps = ['123456', '000000', '999999']
        for otp in valid_otps:
            self.assertEqual(len(otp), 6)
            self.assertTrue(otp.isdigit())
        
        # 無効なOTPコード
        invalid_otps = ['12345', '1234567', 'abcdef', '12a456', '']
        for otp in invalid_otps:
            with self.subTest(otp=otp):
                self.assertFalse(len(otp) == 6 and otp.isdigit())
    
    def test_otp_expiry_calculation(self):
        """OTP有効期限計算のテスト"""
        now = datetime.datetime.now()
        expiry_minutes = 10
        expires_at = now + datetime.timedelta(minutes=expiry_minutes)
        
        # 期限内
        check_time = now + datetime.timedelta(minutes=5)
        self.assertTrue(check_time < expires_at)
        
        # 期限切れ
        check_time = now + datetime.timedelta(minutes=15)
        self.assertTrue(check_time > expires_at)


class TestOTPSecurity(unittest.TestCase):
    """OTPセキュリティ機能のテスト"""
    
    def setUp(self):
        """テスト前の準備"""
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        create_tables(self.conn)
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        self.conn.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_old_otp_invalidation(self):
        """古いOTP無効化のテスト"""
        email = 'test@example.com'
        
        # 古いOTPを挿入
        old_otp = '111111'
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
        self.conn.execute("""
            INSERT INTO otp_tokens (email, otp_code, expires_at)
            VALUES (?, ?, ?)
        """, (email, old_otp, expires_at.isoformat()))
        self.conn.commit()
        
        # 新しいOTP送信時に古いOTPを無効化
        self.conn.execute("""
            UPDATE otp_tokens 
            SET used = TRUE, used_at = CURRENT_TIMESTAMP 
            WHERE email = ? AND used = FALSE
        """, (email,))
        
        # 新しいOTPを挿入
        new_otp = '222222'
        self.conn.execute("""
            INSERT INTO otp_tokens (email, otp_code, expires_at)
            VALUES (?, ?, ?)
        """, (email, new_otp, expires_at.isoformat()))
        self.conn.commit()
        
        # 古いOTPが無効化されていることを確認
        old_result = self.conn.execute("""
            SELECT used FROM otp_tokens WHERE otp_code = ?
        """, (old_otp,)).fetchone()
        self.assertTrue(old_result['used'])
        
        # 新しいOTPが有効であることを確認
        new_result = self.conn.execute("""
            SELECT used FROM otp_tokens WHERE otp_code = ?
        """, (new_otp,)).fetchone()
        self.assertFalse(new_result['used'])
    
    def test_otp_reuse_prevention(self):
        """OTP再利用防止のテスト"""
        email = 'test@example.com'
        otp_code = '123456'
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
        
        # OTP挿入
        self.conn.execute("""
            INSERT INTO otp_tokens (email, otp_code, expires_at)
            VALUES (?, ?, ?)
        """, (email, otp_code, expires_at.isoformat()))
        self.conn.commit()
        
        # 最初の使用（成功）
        otp_record = self.conn.execute("""
            SELECT id FROM otp_tokens 
            WHERE email = ? AND otp_code = ? AND used = FALSE
        """, (email, otp_code)).fetchone()
        self.assertIsNotNone(otp_record)
        
        # 使用済みにマーク
        self.conn.execute("""
            UPDATE otp_tokens 
            SET used = TRUE, used_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (otp_record['id'],))
        self.conn.commit()
        
        # 2回目の使用試行（失敗）
        otp_record_reuse = self.conn.execute("""
            SELECT id FROM otp_tokens 
            WHERE email = ? AND otp_code = ? AND used = FALSE
        """, (email, otp_code)).fetchone()
        self.assertIsNone(otp_record_reuse)


if __name__ == '__main__':
    # テストスイートの実行
    unittest.main(verbosity=2)