"""
パスフレーズ認証機能
"""
import re
import hashlib
import secrets
import sqlite3
from typing import Tuple, Optional


class PassphraseValidator:
    """パスフレーズバリデーション機能"""
    
    # 許可する文字パターン (ASCII: 0-9, a-z, A-Z, _, -)
    ALLOWED_PATTERN = re.compile(r'^[0-9a-zA-Z_-]+$')
    
    # 文字数制限
    MIN_LENGTH = 32
    MAX_LENGTH = 128
    
    @classmethod
    def validate(cls, passphrase: str) -> Tuple[bool, str]:
        """
        パスフレーズの有効性を検証
        
        Args:
            passphrase: 検証するパスフレーズ
            
        Returns:
            Tuple[bool, str]: (有効性, エラーメッセージ)
        """
        if not isinstance(passphrase, str):
            return False, "パスフレーズは文字列である必要があります"
        
        if not passphrase:
            return False, "パスフレーズが空です"
        
        # 文字数チェック
        if len(passphrase) < cls.MIN_LENGTH:
            return False, f"パスフレーズは{cls.MIN_LENGTH}文字以上である必要があります"
        
        if len(passphrase) > cls.MAX_LENGTH:
            return False, f"パスフレーズは{cls.MAX_LENGTH}文字以下である必要があります"
        
        # 文字種チェック
        if not cls.ALLOWED_PATTERN.match(passphrase):
            return False, "パスフレーズは0-9, a-z, A-Z, _, - の文字のみ使用可能です"
        
        return True, "有効なパスフレーズです"


class PassphraseHasher:
    """パスフレーズハッシュ化機能"""
    
    @staticmethod
    def hash_passphrase(passphrase: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """
        パスフレーズをハッシュ化
        
        Args:
            passphrase: ハッシュ化するパスフレーズ
            salt: ソルト（指定しない場合は自動生成）
            
        Returns:
            Tuple[str, str]: (ハッシュ値, ソルト)
        """
        if salt is None:
            salt = secrets.token_hex(16)
        
        # PBKDF2でハッシュ化
        hash_value = hashlib.pbkdf2_hmac(
            'sha256',
            passphrase.encode('utf-8'),
            salt.encode('utf-8'),
            100000  # 反復回数
        )
        
        return hash_value.hex(), salt
    
    @staticmethod
    def verify_passphrase(passphrase: str, stored_hash: str, salt: str) -> bool:
        """
        パスフレーズを検証
        
        Args:
            passphrase: 検証するパスフレーズ
            stored_hash: 保存されたハッシュ値
            salt: ソルト
            
        Returns:
            bool: 検証結果
        """
        hash_value, _ = PassphraseHasher.hash_passphrase(passphrase, salt)
        return secrets.compare_digest(hash_value, stored_hash)


class PassphraseManager:
    """パスフレーズ管理機能"""
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    def set_passphrase(self, passphrase: str, updated_by: str = 'system') -> Tuple[bool, str]:
        """
        パスフレーズを設定
        
        Args:
            passphrase: 設定するパスフレーズ
            updated_by: 更新者
            
        Returns:
            Tuple[bool, str]: (成功/失敗, メッセージ)
        """
        # バリデーション
        is_valid, message = PassphraseValidator.validate(passphrase)
        if not is_valid:
            return False, message
        
        # ハッシュ化
        hash_value, salt = PassphraseHasher.hash_passphrase(passphrase)
        
        # データベースに保存
        combined_hash = f"{hash_value}:{salt}"
        
        try:
            # 現在の値を取得（履歴用）
            self.db.row_factory = sqlite3.Row
            current_row = self.db.execute(
                'SELECT value FROM settings WHERE key = ?', 
                ('shared_passphrase',)
            ).fetchone()
            old_value = current_row['value'] if current_row else None
            
            # 設定を更新
            self.db.execute('''
                INSERT OR REPLACE INTO settings (key, value, value_type, description, category, is_sensitive, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                'shared_passphrase',
                combined_hash,
                'string',
                '事前共有パスフレーズ（32-128文字、0-9a-zA-Z_-のみ）',
                'auth',
                True,
                updated_by
            ))
            
            # 履歴に記録
            self.db.execute('''
                INSERT INTO settings_history (setting_key, old_value, new_value, changed_by)
                VALUES (?, ?, ?, ?)
            ''', ('shared_passphrase', old_value, '[REDACTED]', updated_by))
            
            self.db.commit()
            return True, "パスフレーズが正常に設定されました"
            
        except Exception as e:
            self.db.rollback()
            return False, f"パスフレーズの設定中にエラーが発生しました: {str(e)}"
    
    def verify_passphrase(self, passphrase: str) -> Tuple[bool, str]:
        """
        パスフレーズを検証
        
        Args:
            passphrase: 検証するパスフレーズ
            
        Returns:
            Tuple[bool, str]: (検証結果, メッセージ)
        """
        try:
            # データベースから取得
            self.db.row_factory = sqlite3.Row
            row = self.db.execute(
                'SELECT value FROM settings WHERE key = ?', 
                ('shared_passphrase',)
            ).fetchone()
            
            if not row:
                return False, "パスフレーズが設定されていません"
            
            stored_value = row['value']
            
            # ハッシュ値とソルトを分離
            if ':' in stored_value:
                stored_hash, salt = stored_value.split(':', 1)
                # ハッシュ値で検証
                is_valid = PassphraseHasher.verify_passphrase(passphrase, stored_hash, salt)
                
                if is_valid:
                    return True, "認証成功"
                else:
                    return False, "認証失敗"
            else:
                # 古い形式（平文）の場合
                if stored_value == passphrase:
                    return True, "認証成功（古い形式）"
                else:
                    return False, "認証失敗"
                
        except Exception as e:
            return False, f"認証中にエラーが発生しました: {str(e)}"
    
    def get_passphrase_info(self) -> dict:
        """
        パスフレーズ設定情報を取得
        
        Returns:
            dict: パスフレーズ情報
        """
        try:
            self.db.row_factory = sqlite3.Row
            row = self.db.execute(
                'SELECT updated_at, updated_by FROM settings WHERE key = ?', 
                ('shared_passphrase',)
            ).fetchone()
            
            if row:
                return {
                    'is_set': True,
                    'updated_at': row['updated_at'],
                    'updated_by': row['updated_by']
                }
            else:
                return {
                    'is_set': False,
                    'updated_at': None,
                    'updated_by': None
                }
                
        except Exception as e:
            return {
                'is_set': False,
                'error': str(e)
            }