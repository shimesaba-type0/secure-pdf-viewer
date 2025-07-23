#!/usr/bin/env python3
"""
TASK-003-5: セッション制限機能の簡単な動作確認

現在のデータベース状態でセッション制限機能をテストします。
"""

import sys
import os
import sqlite3

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app
from database.models import get_setting, set_setting


def test_session_limit_function():
    """セッション制限チェック機能のテスト"""
    print("=== セッション制限機能テスト開始 ===")
    
    # 現在の設定を確認
    conn = sqlite3.connect('instance/database.db')
    conn.row_factory = sqlite3.Row
    
    current_max = get_setting(conn, 'max_concurrent_sessions', 100)
    current_enabled = get_setting(conn, 'session_limit_enabled', True)
    
    print(f"現在の設定: 最大セッション数={current_max}, 有効={current_enabled}")
    
    # 現在のセッション数を確認
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM session_stats')
    current_sessions = cursor.fetchone()['count']
    print(f"現在のアクティブセッション数: {current_sessions}")
    
    # セッション制限チェック関数をテスト
    print("\n--- セッション制限チェック結果 ---")
    result = app.check_session_limit()
    print(f"許可: {result['allowed']}")
    print(f"現在のセッション数: {result['current_count']}")
    print(f"制限値: {result['max_limit']}")
    print(f"警告メッセージ: {result['warning']}")
    
    # テスト用に制限値を低く設定してテスト
    print(f"\n--- テスト用制限値設定 (3セッション) ---")
    set_setting(conn, 'max_concurrent_sessions', '3', 'test')
    
    result_test = app.check_session_limit()
    print(f"テスト結果 - 許可: {result_test['allowed']}")
    print(f"テスト結果 - 現在のセッション数: {result_test['current_count']}")
    print(f"テスト結果 - 制限値: {result_test['max_limit']}")
    print(f"テスト結果 - 警告メッセージ: {result_test['warning']}")
    
    # 元の設定に戻す
    set_setting(conn, 'max_concurrent_sessions', str(current_max), 'test')
    
    conn.close()
    print("\n=== テスト完了 ===")


def test_admin_api():
    """管理画面APIのテスト"""
    print("\n=== 管理画面APIテスト開始 ===")
    
    with app.app.test_client() as client:
        # 認証状態をシミュレート
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['email'] = 'test@example.com'
        
        # セッション制限状況APIをテスト
        response = client.get('/admin/api/session-limit-status')
        print(f"APIレスポンス ステータス: {response.status_code}")
        
        if response.status_code == 200:
            data = response.get_json()
            print(f"API結果 - 成功: {data.get('success')}")
            print(f"API結果 - 現在のセッション数: {data.get('current_sessions')}")
            print(f"API結果 - 最大セッション数: {data.get('max_sessions')}")
            print(f"API結果 - 使用率: {data.get('usage_percentage')}%")
            print(f"API結果 - 警告レベル: {data.get('is_warning')}")
            print(f"API結果 - クリティカルレベル: {data.get('is_critical')}")
        else:
            print(f"APIエラー: {response.data}")
    
    print("=== 管理画面APIテスト完了 ===")


if __name__ == '__main__':
    test_session_limit_function()
    test_admin_api()