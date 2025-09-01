"""
バックアップAPI機能のシンプルテスト
Phase 1B: Flask APIエンドポイントの統合テスト
"""

import os
import sys
import json
import tempfile
import shutil
import subprocess
import requests
import time

# テスト用のパス設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_backup_api_endpoints():
    """実際に動作中のアプリケーションでAPIエンドポイントをテスト"""
    
    # アプリケーションが動作中かチェック
    try:
        response = requests.get('http://localhost:5000/', timeout=5)
        print(f"アプリケーション接続確認: {response.status_code}")
    except requests.RequestException as e:
        print(f"アプリケーションに接続できません: {e}")
        print("別ターミナルでアプリケーションを起動してからテストを実行してください")
        return False
    
    # セッション作成（ログイン）
    session = requests.Session()
    
    # まずログインページにアクセス
    login_response = session.get('http://localhost:5000/login')
    print(f"ログインページアクセス: {login_response.status_code}")
    
    # 実際のログイン処理は手動で行われることを想定
    print("\n=== バックアップAPI未認証テスト ===")
    
    # 1. 認証なしでのアクセステスト
    unauthenticated_session = requests.Session()
    
    test_endpoints = [
        ('POST', '/admin/backup/create'),
        ('GET', '/admin/backup/list'),
        ('GET', '/admin/backup/download/test'),
        ('DELETE', '/admin/backup/delete/test'),
        ('GET', '/admin/backup/status')
    ]
    
    for method, endpoint in test_endpoints:
        try:
            if method == 'POST':
                response = unauthenticated_session.post(f'http://localhost:5000{endpoint}')
            elif method == 'GET':
                response = unauthenticated_session.get(f'http://localhost:5000{endpoint}')
            elif method == 'DELETE':
                response = unauthenticated_session.delete(f'http://localhost:5000{endpoint}')
            
            print(f"{method} {endpoint}: {response.status_code}")
            
            # 未認証の場合はリダイレクト(302)が期待される
            if response.status_code == 302:
                print(f"  ✓ 認証リダイレクト正常")
            else:
                print(f"  ⚠ 予期しないレスポンス: {response.status_code}")
                
        except requests.RequestException as e:
            print(f"  ✗ リクエストエラー: {e}")
    
    print("\n=== APIエンドポイント実装確認 ===")
    
    # 2. APIエンドポイントの実装確認（認証を通さずにエンドポイントの存在を確認）
    for method, endpoint in test_endpoints:
        try:
            if method == 'POST':
                response = session.post(f'http://localhost:5000{endpoint}')
            elif method == 'GET':
                response = session.get(f'http://localhost:5000{endpoint}')
            elif method == 'DELETE':
                response = session.delete(f'http://localhost:5000{endpoint}')
            
            print(f"{method} {endpoint}: {response.status_code}")
            
            # 404でなければエンドポイントは実装されている
            if response.status_code != 404:
                print(f"  ✓ エンドポイント実装済み")
            else:
                print(f"  ✗ エンドポイント未実装")
                
        except requests.RequestException as e:
            print(f"  ✗ リクエストエラー: {e}")
    
    print("\n=== パストラバーサル対策テスト ===")
    
    # 3. パストラバーサル攻撃の対策確認
    malicious_paths = [
        '../../../etc/passwd',
        '..\\..\\..\\windows\\system32\\hosts',
        '%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd'
    ]
    
    for malicious_path in malicious_paths:
        try:
            response = session.get(f'http://localhost:5000/admin/backup/download/{malicious_path}')
            print(f"パストラバーサル {malicious_path}: {response.status_code}")
            
            if response.status_code in [400, 404]:
                print(f"  ✓ 適切にブロック")
            elif response.status_code == 302:
                print(f"  ✓ 認証でブロック")
            else:
                print(f"  ⚠ 予期しないレスポンス: {response.status_code}")
                
        except requests.RequestException as e:
            print(f"  ✗ リクエストエラー: {e}")
    
    print("\n=== APIレスポンス形式確認 ===")
    
    # 4. JSONレスポンス形式の確認
    try:
        response = session.get('http://localhost:5000/admin/backup/list')
        print(f"バックアップ一覧API: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"  ✓ 有効なJSON形式")
                if 'status' in data:
                    print(f"  ✓ status フィールド存在: {data['status']}")
                else:
                    print(f"  ⚠ status フィールドなし")
            except json.JSONDecodeError:
                print(f"  ✗ 無効なJSON形式")
        elif response.status_code == 302:
            print(f"  ✓ 認証リダイレクト")
        else:
            print(f"  ⚠ 予期しないレスポンス")
            
    except requests.RequestException as e:
        print(f"  ✗ リクエストエラー: {e}")
    
    print("\n=== テスト完了 ===")
    print("認証後の詳細テストは管理画面から手動で確認してください")
    
    return True


if __name__ == '__main__':
    test_backup_api_endpoints()