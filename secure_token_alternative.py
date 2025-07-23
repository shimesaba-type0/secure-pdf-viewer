#!/usr/bin/env python3
"""
より秘匿性の高いトークン設計の代替案
"""

import hmac
import hashlib
import secrets
import base64
import json
from datetime import datetime, timedelta

class EnhancedPDFURLSecurity:
    """より秘匿性の高い署名付きURL生成クラス（代替案）"""
    
    def __init__(self, secret_key):
        self.secret_key = secret_key
        self.token_store = {}  # 実際はRedisやDBに保存
    
    def generate_opaque_token(self, filename, session_id, expiry_hours=72):
        """不透明トークン生成（情報が見えない方式）"""
        
        # ランダムな不透明トークンを生成
        opaque_token = secrets.token_urlsafe(32)
        
        # 有効期限を計算
        expires_at = datetime.utcnow() + timedelta(hours=expiry_hours)
        
        # トークンに対応する情報をサーバー側で保存
        token_data = {
            'filename': filename,
            'session_id': session_id,
            'expires_at': expires_at.isoformat(),
            'created_at': datetime.utcnow().isoformat()
        }
        
        # 実際の実装ではデータベースやRedisに保存
        self.token_store[opaque_token] = token_data
        
        return {
            'signed_url': f'/secure/pdf/{opaque_token}',
            'token': opaque_token,
            'expires_at': expires_at.isoformat()
        }
    
    def verify_opaque_token(self, token):
        """不透明トークンの検証"""
        
        # トークンストアから情報を取得
        token_data = self.token_store.get(token)
        if not token_data:
            return {'valid': False, 'error': '無効なトークンです'}
        
        # 有効期限チェック
        expires_at = datetime.fromisoformat(token_data['expires_at'])
        if datetime.utcnow() > expires_at:
            # 期限切れトークンを削除
            del self.token_store[token]
            return {'valid': False, 'error': 'トークンの有効期限が切れています'}
        
        return {
            'valid': True,
            'filename': token_data['filename'],
            'session_id': token_data['session_id'],
            'expires_at': expires_at
        }

def compare_approaches():
    """現在の方式と代替案の比較"""
    
    print("🔍 トークン方式の比較")
    print("=" * 60)
    
    print("\n📊 現在の方式（Base64エンコード）:")
    print("✅ 利点:")
    print("  - サーバー側ストレージ不要（ステートレス）")
    print("  - デバッグ・監査が容易")
    print("  - 標準的な実装パターン")
    print("  - クライアント側で期限チェック可能")
    
    print("⚠️  懸念:")
    print("  - パラメータが可視（セッションID、有効期限等）")
    print("  - 情報漏洩時の心理的影響")
    
    print("\n🔒 代替案（不透明トークン）:")
    print("✅ 利点:")
    print("  - 完全に不透明（情報が見えない）")
    print("  - より高い秘匿性")
    print("  - 即座なトークン無効化が可能")
    
    print("⚠️  欠点:")
    print("  - サーバー側ストレージ必要（Redis/DB）")
    print("  - ステートフル（スケーラビリティに影響）")
    print("  - デバッグ・監査が複雑")
    print("  - インフラコストの増加")

if __name__ == "__main__":
    compare_approaches()
    
    # 代替案のデモ
    print("\n" + "=" * 60)
    print("🧪 代替案デモ")
    
    alt_security = EnhancedPDFURLSecurity("secret-key")
    
    # 不透明トークン生成
    result = alt_security.generate_opaque_token("test.pdf", "session-123")
    print(f"\n生成されたURL: {result['signed_url']}")
    print(f"トークン: {result['token']}")
    print("→ トークンから情報は一切読み取れません")
    
    # 検証
    verification = alt_security.verify_opaque_token(result['token'])
    print(f"\n検証結果: {verification}")