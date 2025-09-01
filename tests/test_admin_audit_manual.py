#!/usr/bin/env python3
"""
Phase 3A 管理者監査ログ機能の手動動作確認スクリプト
"""

import sys
import os

# プロジェクトルートをPythonパスに追加（tests/ディレクトリの親ディレクトリ）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import (
    log_admin_action,
    get_admin_actions,
    get_admin_action_stats,
    get_risk_level_for_action,
    delete_admin_actions_before_date
)
from database import get_db
from config.timezone import get_app_now, add_app_timedelta

def test_admin_audit_logging():
    """管理者監査ログ機能の動作確認"""
    print("=== Phase 3A: 管理者監査ログ機能 動作確認 ===\n")
    
    # 1. admin_actionsテーブル作成確認
    print("1. admin_actionsテーブル作成確認...")
    try:
        with get_db() as db:
            cursor = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='admin_actions'"
            )
            table_exists = cursor.fetchone()
            if table_exists:
                print("✅ admin_actionsテーブルが存在します")
            else:
                print("❌ admin_actionsテーブルが存在しません")
                return False
    except Exception as e:
        print(f"❌ テーブル確認エラー: {e}")
        return False
    
    # 2. ログ記録テスト
    print("\n2. 管理者操作ログ記録テスト...")
    test_actions = [
        {
            "admin_email": "admin@test.com",
            "action_type": "admin_login",
            "ip_address": "192.168.1.100",
            "user_agent": "Mozilla/5.0 (Test Browser)"
        },
        {
            "admin_email": "admin@test.com", 
            "action_type": "user_view",
            "resource_type": "user",
            "resource_id": "test_user_001",
            "action_details": {"viewed_user": "testuser@example.com"},
            "ip_address": "192.168.1.100",
        },
        {
            "admin_email": "admin@test.com",
            "action_type": "setting_update",
            "resource_type": "setting",
            "resource_id": "security_config", 
            "action_details": {"setting": "session_timeout", "old_value": 3600, "new_value": 1800},
            "before_state": {"session_timeout": 3600},
            "after_state": {"session_timeout": 1800},
            "ip_address": "192.168.1.100",
        },
        {
            "admin_email": "admin@test.com",
            "action_type": "user_delete",
            "resource_type": "user",
            "resource_id": "test_user_002",
            "action_details": {"deleted_user": "deleteduser@example.com"},
            "ip_address": "192.168.1.100",
        },
        {
            "admin_email": "admin2@test.com",
            "action_type": "system_maintenance",
            "action_details": {"maintenance_type": "database_cleanup"},
            "ip_address": "192.168.1.101",
        }
    ]
    
    logged_count = 0
    for action in test_actions:
        result = log_admin_action(**action)
        if result:
            logged_count += 1
            print(f"  ✅ ログ記録成功: {action['action_type']} ({get_risk_level_for_action(action['action_type'])})")
        else:
            print(f"  ❌ ログ記録失敗: {action['action_type']}")
    
    print(f"ログ記録結果: {logged_count}/{len(test_actions)}")
    
    # 3. ログ取得テスト
    print("\n3. ログ取得テスト...")
    
    # 3.1 全ログ取得
    result = get_admin_actions()
    print(f"  全ログ件数: {result['total']}件")
    print(f"  1ページ目表示件数: {len(result['actions'])}件")
    
    # 3.2 管理者フィルタ
    result = get_admin_actions(admin_email="admin@test.com")
    print(f"  admin@test.com の操作: {result['total']}件")
    
    # 3.3 リスクレベルフィルタ
    result = get_admin_actions(risk_level="high")
    print(f"  高リスク操作: {result['total']}件")
    
    result = get_admin_actions(risk_level="critical")
    print(f"  重要リスク操作: {result['total']}件")
    
    # 3.4 アクション種別フィルタ
    result = get_admin_actions(action_type="user_delete")
    print(f"  ユーザー削除操作: {result['total']}件")
    
    # 4. 統計情報テスト
    print("\n4. 統計情報取得テスト...")
    
    # 4.1 操作種別別統計
    stats = get_admin_action_stats(period="7d", group_by="action_type")
    print(f"  操作種別別統計（過去7日）: {len(stats['stats'])}種類")
    for stat in stats['stats']:
        print(f"    {stat['action_type']}: {stat['count']}回 (成功: {stat['success_count']}, エラー: {stat['error_count']})")
    
    # 4.2 リスクレベル別統計
    stats = get_admin_action_stats(period="7d", group_by="risk_level")
    print(f"  リスクレベル別統計: {len(stats['stats'])}レベル")
    for stat in stats['stats']:
        print(f"    {stat['risk_level']}: {stat['count']}回")
    
    # 4.3 管理者別統計
    stats = get_admin_action_stats(period="7d", group_by="admin_email")
    print(f"  管理者別統計: {len(stats['stats'])}人")
    for stat in stats['stats']:
        print(f"    {stat['admin_email']}: {stat['count']}回")
    
    # 5. リスクレベル分類テスト
    print("\n5. リスクレベル分類テスト...")
    test_risk_actions = [
        ("admin_login", "low"),
        ("user_view", "low"),
        ("setting_update", "medium"),
        ("user_delete", "high"),
        ("system_maintenance", "critical"),
        ("unknown_action", "medium")  # デフォルト値
    ]
    
    for action_type, expected_risk in test_risk_actions:
        actual_risk = get_risk_level_for_action(action_type)
        status = "✅" if actual_risk == expected_risk else "❌"
        print(f"  {status} {action_type}: {actual_risk} (期待値: {expected_risk})")
    
    # 6. データベース詳細確認
    print("\n6. データベース詳細確認...")
    try:
        with get_db() as db:
            db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
            
            # 最新ログを1件取得して詳細表示
            cursor = db.execute(
                "SELECT * FROM admin_actions ORDER BY created_at DESC LIMIT 1"
            )
            latest_action = cursor.fetchone()
            
            if latest_action:
                print("  最新ログエントリの詳細:")
                for key, value in latest_action.items():
                    if key in ['action_details', 'before_state', 'after_state'] and value:
                        print(f"    {key}: {value}")
                    else:
                        print(f"    {key}: {value}")
            else:
                print("  ログエントリが見つかりません")
                
    except Exception as e:
        print(f"  ❌ データベース詳細確認エラー: {e}")
    
    print("\n=== 動作確認完了 ===")
    return True

if __name__ == "__main__":
    test_admin_audit_logging()