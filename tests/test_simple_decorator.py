#!/usr/bin/env python3
"""
Sub-Phase 3Bデコレータの簡単なテスト
"""
import sys
sys.path.insert(0, '/home/ope/secure-pdf-viewer')

import tempfile
import os
from database import init_db
from database.models import log_admin_action, get_admin_actions

def test_simple_logging():
    """簡単なログ記録テスト"""
    # 一時データベース作成
    db_fd, db_path = tempfile.mkstemp()
    os.environ['DATABASE_PATH'] = db_path
    
    try:
        # データベース初期化
        init_db()
        
        # ログ記録テスト
        result = log_admin_action(
            admin_email="test@example.com",
            action_type="test_action",
            resource_type="test_resource",
            action_details='{"test": "data"}',
            ip_address="127.0.0.1",
            user_agent="TestAgent/1.0",
            session_id="test-session-123",
            admin_session_id=None,
            risk_level="low",
            success=True
        )
        
        print(f"Log action result: {result}")
        
        # ログ取得テスト
        logs = get_admin_actions(admin_email="test@example.com", limit=1)
        print(f"Retrieved logs: {logs}")
        
        if logs and logs.get('actions'):
            log_entry = logs['actions'][0]
            assert log_entry['admin_email'] == "test@example.com"
            assert log_entry['action_type'] == "test_action"
            print("✅ Simple logging test passed!")
        else:
            print("❌ No logs found")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # クリーンアップ
        os.close(db_fd)
        os.unlink(db_path)

if __name__ == "__main__":
    test_simple_logging()