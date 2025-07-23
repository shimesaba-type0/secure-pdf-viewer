#!/usr/bin/env python3
"""
署名付きURLトークンのデコード例
"""

import base64
from urllib.parse import parse_qs

def decode_pdf_token(token):
    """署名付きURLトークンをデコードして内容を表示"""
    try:
        # Base64パディングを復元
        padding = '=' * (4 - len(token) % 4) if len(token) % 4 != 0 else ''
        padded_token = token + padding
        
        # Base64デコード
        decoded_bytes = base64.urlsafe_b64decode(padded_token)
        query_string = decoded_bytes.decode('utf-8')
        
        print(f"🔓 デコード結果:")
        print(f"クエリ文字列: {query_string}")
        print()
        
        # パラメータを解析
        params = {}
        for param in query_string.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                params[key] = value
        
        print("📋 パラメータ詳細:")
        
        # ファイル名
        if 'f' in params:
            print(f"📄 ファイル名: {params['f']}")
        
        # 有効期限（Unix timestamp）
        if 'exp' in params:
            import datetime
            exp_timestamp = int(params['exp'])
            exp_datetime = datetime.datetime.fromtimestamp(exp_timestamp)
            print(f"⏰ 有効期限: {exp_datetime.strftime('%Y-%m-%d %H:%M:%S')} (Unix: {exp_timestamp})")
        
        # セッションID
        if 'sid' in params:
            print(f"🔑 セッションID: {params['sid']}")
        
        # 署名
        if 'sig' in params:
            print(f"✍️  署名: {params['sig'][:20]}...（先頭20文字）")
        
        # ワンタイムフラグ
        if 'ot' in params:
            print(f"🔐 ワンタイム: {'有効' if params['ot'] == '1' else '無効'}")
        
        return params
        
    except Exception as e:
        print(f"❌ デコードエラー: {e}")
        return None

if __name__ == "__main__":
    # 提供されたトークンの例
    example_token = "Zj03ZDA4YzVhOWQ0YjM0ODE3YmM4NGE3ZjVjNDFhNWJjMS5wZGYmZXhwPTE3NTM1MDYyMDUmc2lkPThlM2Q4YzUxLTdmNDAtNDhlNS1hOTQwLWU0MTA1YzRhMWUyMSZzaWc9NTA5OTgxM2FiOTFlMzQ4MDBhZjFhMmQxMGZjMTVlMGQ3ZGY5MmU3ZTkyZTJmZDc4ZWUxNTAyMjIxMmQ1MTlkNQ"
    
    print("🔍 署名付きURLトークン解析")
    print("=" * 50)
    print(f"トークン: {example_token[:50]}...")
    print()
    
    decode_pdf_token(example_token)