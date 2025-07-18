#!/usr/bin/env python3
"""
メール送信サービスのテストコード
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

# プロジェクトルートをpathに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mail.email_service import EmailService


class TestEmailService(unittest.TestCase):
    """EmailServiceのテストクラス"""
    
    def setUp(self):
        """テストセットアップ"""
        self.email_service = EmailService()
    
    def test_email_validation_valid_emails(self):
        """有効なメールアドレスの検証テスト"""
        valid_emails = [
            "test@example.com",
            "user.name@domain.co.jp",
            "admin+test@site.org",
            "123@456.com",
            "test-user@example-site.com"
        ]
        
        for email in valid_emails:
            with self.subTest(email=email):
                self.assertTrue(self.email_service.validate_email(email))
    
    def test_email_validation_invalid_emails(self):
        """無効なメールアドレスの検証テスト"""
        invalid_emails = [
            "plainaddress",
            "@domain.com",
            "test@",
            "test..test@example.com",
            "test@domain",
            "",
            "test@domain..com",
            "test space@example.com"
        ]
        
        for email in invalid_emails:
            with self.subTest(email=email):
                self.assertFalse(self.email_service.validate_email(email))
    
    @patch('mail.email_service.smtplib.SMTP')
    def test_send_otp_email_success(self, mock_smtp):
        """OTPメール送信成功テスト"""
        # SMTPサーバーのモック設定
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # テスト実行
        result = self.email_service.send_otp_email("test@example.com", "123456")
        
        # 結果確認
        self.assertTrue(result)
        mock_smtp.assert_called_once_with(
            self.email_service.smtp_server, 
            self.email_service.smtp_port
        )
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with(
            self.email_service.username, 
            self.email_service.password
        )
        mock_server.sendmail.assert_called_once()
        mock_server.quit.assert_called_once()
    
    @patch('mail.email_service.smtplib.SMTP')
    def test_send_otp_email_smtp_error(self, mock_smtp):
        """OTPメール送信SMTP エラーテスト"""
        # SMTPエラーのモック設定
        mock_smtp.side_effect = Exception("SMTP接続エラー")
        
        # テスト実行
        result = self.email_service.send_otp_email("test@example.com", "123456")
        
        # 結果確認
        self.assertFalse(result)
    
    @patch('mail.email_service.smtplib.SMTP')
    def test_send_test_email_success(self, mock_smtp):
        """テストメール送信成功テスト"""
        # SMTPサーバーのモック設定
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # テスト実行
        result = self.email_service.send_test_email("test@example.com")
        
        # 結果確認
        self.assertTrue(result)
        mock_server.sendmail.assert_called_once()
    
    @patch('mail.email_service.smtplib.SMTP')
    def test_send_test_email_login_error(self, mock_smtp):
        """テストメール送信ログインエラーテスト"""
        # SMTPサーバーのモック設定
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        mock_server.login.side_effect = Exception("認証エラー")
        
        # テスト実行
        result = self.email_service.send_test_email("test@example.com")
        
        # 結果確認
        self.assertFalse(result)
    
    def test_otp_email_content_structure(self):
        """OTPメールの内容構造テスト"""
        with patch('mail.email_service.smtplib.SMTP') as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value = mock_server
            
            # テスト実行
            self.email_service.send_otp_email("test@example.com", "123456", 10)
            
            # sendmailの呼び出し引数を取得
            args, kwargs = mock_server.sendmail.call_args
            from_email, to_email, message = args
            
            # メール内容の確認
            self.assertEqual(from_email, self.email_service.from_email)
            self.assertEqual(to_email, "test@example.com")
            self.assertIn("123456", message)
            self.assertIn("10分", message)
            self.assertIn("セキュアPDFビューア", message)
    
    def test_test_email_content_structure(self):
        """テストメールの内容構造テスト"""
        with patch('mail.email_service.smtplib.SMTP') as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value = mock_server
            
            # テスト実行
            self.email_service.send_test_email("test@example.com")
            
            # sendmailの呼び出し引数を取得
            args, kwargs = mock_server.sendmail.call_args
            from_email, to_email, message = args
            
            # メール内容の確認
            self.assertEqual(from_email, self.email_service.from_email)
            self.assertEqual(to_email, "test@example.com")
            self.assertIn("メール送信テスト", message)
            self.assertIn("正常に動作", message)


def get_test_email_address(provided_email=None):
    """テスト用メールアドレスを取得"""
    if provided_email:
        return provided_email
    
    # 環境変数から取得を試行
    admin_email = os.getenv('ADMIN_EMAIL')
    if admin_email:
        use_admin = input(f"管理者メールアドレス ({admin_email}) を使用しますか? (y/n): ").strip().lower()
        if use_admin in ['y', 'yes', '']:
            return admin_email
    
    # ユーザーに入力を促す
    while True:
        email = input("テスト用メールアドレスを入力してください: ").strip()
        if email:
            # 簡単な検証
            email_service = EmailService()
            if email_service.validate_email(email):
                return email
            else:
                print("無効なメールアドレスです。再入力してください。")
        else:
            print("メールアドレスを入力してください。")


def run_manual_tests(test_email):
    """手動テストの実行"""
    print("=== 手動メール送信テスト ===")
    print(f"送信先: {test_email}")
    print("実際のメール送信を行います。")
    
    email_service = EmailService()
    
    # 1. テストメール送信
    print(f"\n1. テストメール送信...")
    result1 = email_service.send_test_email(test_email)
    print(f"結果: {'成功' if result1 else '失敗'}")
    
    # 2. OTPメール送信
    print(f"\n2. OTPメール送信...")
    result2 = email_service.send_otp_email(test_email, "123456")
    print(f"結果: {'成功' if result2 else '失敗'}")
    
    # 3. メールアドレス検証テスト
    print(f"\n3. メールアドレス検証テスト")
    test_emails = [
        "valid@example.com",
        "invalid-email",
        test_email
    ]
    
    for email in test_emails:
        is_valid = email_service.validate_email(email)
        print(f"  {email}: {'有効' if is_valid else '無効'}")
    
    print("\n=== テスト完了 ===")
    if result1 and result2:
        print("✅ 全てのテストが成功しました")
    else:
        print("❌ 一部のテストが失敗しました")
    
    return result1 and result2


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='メール送信サービスのテスト')
    parser.add_argument('--manual', action='store_true', help='手動テスト（実際のメール送信）を実行')
    parser.add_argument('--unit', action='store_true', help='ユニットテスト（モック使用）を実行')
    parser.add_argument('--email', type=str, help='テスト用メールアドレスを指定')
    
    args = parser.parse_args()
    
    if args.manual:
        # 手動テストの実行
        test_email = get_test_email_address(args.email)
        success = run_manual_tests(test_email)
        sys.exit(0 if success else 1)
    elif args.unit:
        # ユニットテストの実行
        unittest.main(argv=[''])
    else:
        # デフォルトはユニットテスト
        print("=== メール送信サービス ユニットテスト ===")
        unittest.main(argv=[''], verbosity=2)