import hmac
import hashlib
import base64
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode
import os
from database.models import get_setting


class PDFURLSecurity:
    """PDF配信用の署名付きURL生成・検証クラス"""
    
    def __init__(self, secret_key=None):
        """
        Args:
            secret_key (str): HMAC署名用の秘密鍵。指定しない場合は環境変数またはFlaskの設定から取得
        """
        self.secret_key = secret_key or os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-this')
    
    def generate_signed_url(self, filename, session_id, expiry_hours=72, one_time=False, conn=None):
        """
        署名付きPDF配信URLを生成する
        
        Args:
            filename (str): PDFファイル名
            session_id (str): セッションID
            expiry_hours (int): 有効期限（時間）。デフォルト72時間
            one_time (bool): ワンタイムアクセス制御。デフォルトFalse
            conn: データベース接続（設定取得用、オプション）
            
        Returns:
            dict: {
                'signed_url': str,  # 署名付きURL
                'token': str,       # URLトークン部分
                'expires_at': str,  # 有効期限（ISO形式）
                'signature': str    # 署名
            }
        """
        try:
            # 設定値からexpiry_hoursを取得（指定がある場合）
            if conn:
                try:
                    configured_expiry = get_setting(conn, 'pdf_url_expiry_hours', expiry_hours)
                    expiry_hours = int(configured_expiry)
                except:
                    pass  # エラー時はデフォルト値を使用
            
            # 有効期限を計算（UTC）
            expires_at = datetime.utcnow() + timedelta(hours=expiry_hours)
            expiry_timestamp = int(expires_at.timestamp())
            
            # 署名対象文字列を作成
            # フォーマット: "filename:expiry:session_id:one_time"
            sign_string = f"{filename}:{expiry_timestamp}:{session_id}:{str(one_time).lower()}"
            
            # HMAC-SHA256で署名生成
            signature = hmac.new(
                self.secret_key.encode('utf-8'),
                sign_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # URLトークンを生成（Base64エンコード）
            token_data = {
                'f': filename,
                'exp': expiry_timestamp,
                'sid': session_id,
                'sig': signature
            }
            
            if one_time:
                token_data['ot'] = '1'
            
            # URLクエリ文字列として組み立て
            query_string = urlencode(token_data)
            
            # Base64エンコードしてURLセーフな形式に
            token = base64.urlsafe_b64encode(query_string.encode('utf-8')).decode('utf-8').rstrip('=')
            
            # 署名付きURL構築
            signed_url = f"/secure/pdf/{token}"
            
            return {
                'signed_url': signed_url,
                'token': token,
                'expires_at': expires_at.isoformat(),
                'signature': signature,
                'expiry_timestamp': expiry_timestamp
            }
            
        except Exception as e:
            raise ValueError(f"署名付きURL生成に失敗しました: {str(e)}")
    
    def verify_signed_url(self, token):
        """
        署名付きURLトークンを検証する
        
        Args:
            token (str): URLトークン
            
        Returns:
            dict: {
                'valid': bool,
                'filename': str,
                'session_id': str,
                'expires_at': datetime,
                'one_time': bool,
                'error': str  # エラー時のみ
            }
        """
        try:
            # Base64パディングを復元
            padding = '=' * (4 - len(token) % 4) if len(token) % 4 != 0 else ''
            padded_token = token + padding
            
            # Base64デコード
            try:
                query_string = base64.urlsafe_b64decode(padded_token).decode('utf-8')
            except Exception:
                return {'valid': False, 'error': 'トークンのデコードに失敗しました'}
            
            # クエリパラメータをパース
            params = {}
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
            
            # 必須パラメータの確認
            required_params = ['f', 'exp', 'sid', 'sig']
            for param in required_params:
                if param not in params:
                    return {'valid': False, 'error': f'必須パラメータ {param} が不足しています'}
            
            filename = params['f']
            expiry_timestamp = int(params['exp'])
            session_id = params['sid']
            provided_signature = params['sig']
            one_time = params.get('ot') == '1'
            
            # 有効期限チェック
            expires_at = datetime.utcfromtimestamp(expiry_timestamp)
            if datetime.utcnow() > expires_at:
                return {'valid': False, 'error': 'URLの有効期限が切れています'}
            
            # 署名を再計算して検証
            sign_string = f"{filename}:{expiry_timestamp}:{session_id}:{str(one_time).lower()}"
            expected_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                sign_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # 署名の比較（タイミング攻撃対策）
            if not hmac.compare_digest(expected_signature, provided_signature):
                return {'valid': False, 'error': 'URL署名が無効です'}
            
            return {
                'valid': True,
                'filename': filename,
                'session_id': session_id,
                'expires_at': expires_at,
                'one_time': one_time,
                'expiry_timestamp': expiry_timestamp
            }
            
        except ValueError as e:
            return {'valid': False, 'error': f'パラメータエラー: {str(e)}'}
        except Exception as e:
            return {'valid': False, 'error': f'検証エラー: {str(e)}'}
    
    def create_pdf_access_url(self, pdf_file_info, session_id, conn=None):
        """
        PDFファイル情報から署名付きアクセスURLを生成する便利メソッド
        
        Args:
            pdf_file_info (dict): PDFファイル情報（stored_name必須）
            session_id (str): セッションID
            conn: データベース接続（オプション）
            
        Returns:
            str: 署名付きURL
        """
        if not pdf_file_info or 'stored_name' not in pdf_file_info:
            raise ValueError("PDFファイル情報にstored_nameが必要です")
        
        result = self.generate_signed_url(
            filename=pdf_file_info['stored_name'],
            session_id=session_id,
            conn=conn
        )
        
        return result['signed_url']
    
    def log_pdf_access(self, filename, session_id, ip_address, success=True, error_message=None, referer=None, user_agent=None):
        """
        PDFアクセスログを記録する
        
        Args:
            filename (str): ファイル名
            session_id (str): セッションID  
            ip_address (str): IPアドレス
            success (bool): 成功/失敗
            error_message (str): エラーメッセージ（失敗時）
            referer (str): Referrerヘッダー（オプション）
            user_agent (str): User-Agentヘッダー（オプション）
        """
        try:
            import sqlite3
            conn = sqlite3.connect('instance/database.db')
            cursor = conn.cursor()
            
            # PDFアクセスログテーブルの作成（存在しない場合）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pdf_access_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    ip_address TEXT,
                    success BOOLEAN NOT NULL,
                    error_message TEXT,
                    referer TEXT,
                    user_agent TEXT,
                    access_time TEXT
                )
            ''')
            
            # 既存テーブルに新しいカラムを追加（存在しない場合）
            try:
                cursor.execute('ALTER TABLE pdf_access_logs ADD COLUMN referer TEXT')
            except:
                pass  # カラムが既に存在する場合
            
            try:
                cursor.execute('ALTER TABLE pdf_access_logs ADD COLUMN user_agent TEXT')
            except:
                pass  # カラムが既に存在する場合
            
            # ログ記録
            cursor.execute('''
                INSERT INTO pdf_access_logs 
                (filename, session_id, ip_address, success, error_message, referer, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (filename, session_id, ip_address, success, error_message, referer, user_agent))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"PDFアクセスログの記録に失敗: {e}")