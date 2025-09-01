import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging
from dotenv import load_dotenv

class EmailService:
    def __init__(self):
        # .envファイルを読み込み
        load_dotenv()
        
        self.smtp_server = os.getenv('MAIL_SERVER')
        self.smtp_port = int(os.getenv('MAIL_PORT', 587))
        self.username = os.getenv('MAIL_USERNAME')
        self.password = os.getenv('MAIL_PASSWORD')
        self.from_email = os.getenv('MAIL_USERNAME')
        
        # ログ設定
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def send_otp_email(self, to_email, otp_code, expires_in_minutes=10):
        """
        OTP認証メールを送信
        
        Args:
            to_email (str): 送信先メールアドレス
            otp_code (str): OTPコード（6桁）
            expires_in_minutes (int): 有効期限（分）
        
        Returns:
            bool: 送信成功の場合True、失敗の場合False
        """
        try:
            # メール本文作成
            subject = "【セキュアPDFビューア】認証コードのお知らせ"
            
            # HTMLメール本文
            html_body = f"""
            <html>
            <body>
                <h2>認証コードのお知らせ</h2>
                <p>セキュアPDFビューアへのログインのため、以下の認証コードを入力してください。</p>
                
                <div style="background-color: #f5f5f5; padding: 20px; margin: 20px 0; text-align: center;">
                    <h1 style="color: #333; font-size: 36px; letter-spacing: 5px; margin: 0;">
                        {otp_code}
                    </h1>
                </div>
                
                <p><strong>有効期限:</strong> {expires_in_minutes}分</p>
                <p><strong>送信日時:</strong> {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}</p>
                
                <hr>
                <p style="color: #666; font-size: 12px;">
                    ※このメールに心当たりがない場合は、無視してください。<br>
                    ※このメールは自動送信されています。返信はできません。
                </p>
            </body>
            </html>
            """
            
            # テキストメール本文（HTMLが表示できない場合のバックアップ）
            text_body = f"""
認証コードのお知らせ

セキュアPDFビューアへのログインのため、以下の認証コードを入力してください。

認証コード: {otp_code}

有効期限: {expires_in_minutes}分
送信日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}

※このメールに心当たりがない場合は、無視してください。
※このメールは自動送信されています。返信はできません。
            """
            
            return self._send_email(to_email, subject, text_body, html_body)
            
        except Exception as e:
            self.logger.error(f"OTPメール送信エラー: {str(e)}")
            return False
    
    def send_test_email(self, to_email):
        """
        テスト用メール送信
        
        Args:
            to_email (str): 送信先メールアドレス
        
        Returns:
            bool: 送信成功の場合True、失敗の場合False
        """
        try:
            subject = "【セキュアPDFビューア】メール送信テスト"
            
            html_body = f"""
            <html>
            <body>
                <h2>メール送信テスト</h2>
                <p>セキュアPDFビューアからのメール送信テストです。</p>
                <p><strong>送信日時:</strong> {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}</p>
                <p>メール送信機能が正常に動作しています。</p>
            </body>
            </html>
            """
            
            text_body = f"""
メール送信テスト

セキュアPDFビューアからのメール送信テストです。

送信日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}

メール送信機能が正常に動作しています。
            """
            
            return self._send_email(to_email, subject, text_body, html_body)
            
        except Exception as e:
            self.logger.error(f"テストメール送信エラー: {str(e)}")
            return False
    
    def _send_email(self, to_email, subject, text_body, html_body=None):
        """
        メール送信の共通処理
        
        Args:
            to_email (str): 送信先メールアドレス
            subject (str): 件名
            text_body (str): テキスト本文
            html_body (str): HTML本文（オプション）
        
        Returns:
            bool: 送信成功の場合True、失敗の場合False
        """
        server = None
        try:
            # SMTP設定確認
            self.logger.info(f"SMTP設定: {self.smtp_server}:{self.smtp_port}")
            self.logger.info(f"ユーザー名: {self.username}")
            
            # メール作成
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            # テキスト部分を追加
            part1 = MIMEText(text_body, 'plain', 'utf-8')
            msg.attach(part1)
            
            # HTML部分を追加（指定されている場合）
            if html_body:
                part2 = MIMEText(html_body, 'html', 'utf-8')
                msg.attach(part2)
            
            # SMTP接続してメール送信
            self.logger.info(f"SMTP接続開始: {self.smtp_server}:{self.smtp_port}")
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            
            self.logger.info("TLS暗号化を開始")
            server.starttls()  # TLS暗号化を開始
            
            self.logger.info("SMTP認証を開始")
            server.login(self.username, self.password)
            
            self.logger.info("メール送信を開始")
            text = msg.as_string()
            server.sendmail(self.from_email, to_email, text)
            
            self.logger.info(f"メール送信成功: {to_email}")
            return True
            
        except Exception as e:
            self.logger.error(f"メール送信失敗: {to_email}, エラー: {str(e)}")
            self.logger.error(f"エラー詳細: {type(e).__name__}: {str(e)}")
            return False
        finally:
            # サーバー接続を確実に閉じる
            if server:
                try:
                    server.quit()
                except:
                    pass
    
    def validate_email(self, email):
        """
        メールアドレスの簡単な検証
        
        Args:
            email (str): 検証するメールアドレス
        
        Returns:
            bool: 有効な場合True、無効な場合False
        """
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

# シングルトンインスタンス
email_service = EmailService()