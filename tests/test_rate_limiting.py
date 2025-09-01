"""
レート制限システムのテストケース
TASK-004: 詳細レート制限システム実装のテスト
"""

import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import sys
import time

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.models import create_tables, insert_initial_data
from database.utils import (
    is_ip_blocked, block_ip, unblock_ip, 
    check_auth_failures, log_auth_failure
)


class TestRateLimitingBasic:
    """基本的なレート制限機能のテスト"""
    
    @pytest.fixture
    def temp_db(self):
        """テスト用の一時データベース"""
        fd, path = tempfile.mkstemp()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        
        # テーブル作成
        create_tables(conn)
        conn.commit()
        
        yield conn
        
        conn.close()
        os.close(fd)
        os.unlink(path)
    
    def test_ip_blocking_basic(self, temp_db):
        """基本的なIP制限機能のテスト"""
        test_ip = "192.168.1.100"
        
        # 初期状態では制限されていない
        assert not is_ip_blocked(temp_db, test_ip)
        
        # IP制限を実行
        block_ip(temp_db, test_ip, 1800, "Test block")
        temp_db.commit()
        
        # 制限されている状態
        assert is_ip_blocked(temp_db, test_ip)
        
        # 制限解除
        unblock_ip(temp_db, test_ip)
        temp_db.commit()
        
        # 制限が解除されている
        assert not is_ip_blocked(temp_db, test_ip)
    
    def test_auth_failure_counting(self, temp_db):
        """認証失敗回数カウントのテスト"""
        test_ip = "192.168.1.101"
        
        # 初期状態では失敗回数0
        assert check_auth_failures(temp_db, test_ip, 10) == 0
        
        # 3回失敗を記録
        for i in range(3):
            log_auth_failure(temp_db, test_ip, "password_failure", f"test{i}@example.com")
        temp_db.commit()
        
        # 失敗回数が3回
        assert check_auth_failures(temp_db, test_ip, 10) == 3
        
        # 時間窓を短くすると0回（過去の失敗は対象外）
        assert check_auth_failures(temp_db, test_ip, 0) == 0
    
    def test_expired_block_not_active(self, temp_db):
        """期限切れのIP制限が無効になることのテスト"""
        test_ip = "192.168.1.102"
        
        # 過去の時刻で制限を設定（すでに期限切れ）
        past_time = datetime.utcnow() - timedelta(hours=1)
        temp_db.execute('''
            INSERT INTO ip_blocks (ip_address, blocked_until, reason)
            VALUES (?, ?, ?)
        ''', (test_ip, past_time, "Expired test block"))
        temp_db.commit()
        
        # 期限切れなので制限されていない
        assert not is_ip_blocked(temp_db, test_ip)


class TestRateLimitingIntegration:
    """統合テストケース（10分5回制限）"""
    
    @pytest.fixture
    def temp_db(self):
        """テスト用の一時データベース"""
        fd, path = tempfile.mkstemp()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        
        create_tables(conn)
        conn.commit()
        
        yield conn
        
        conn.close()
        os.close(fd)
        os.unlink(path)
    
    def test_five_failures_trigger_block(self, temp_db):
        """5回失敗でIP制限が発動することのテスト"""
        test_ip = "192.168.1.200"
        
        # 4回失敗では制限されない
        for i in range(4):
            log_auth_failure(temp_db, test_ip, "password_failure", f"user{i}@example.com")
        temp_db.commit()
        
        assert check_auth_failures(temp_db, test_ip, 10) == 4
        assert not is_ip_blocked(temp_db, test_ip)
        
        # 5回目で制限される想定（実装時にテスト更新）
        log_auth_failure(temp_db, test_ip, "password_failure", "user5@example.com")
        temp_db.commit()
        
        assert check_auth_failures(temp_db, test_ip, 10) == 5
        # 注意: 実際のブロック処理は RateLimitManager 実装時に統合
    
    def test_different_ips_independent(self, temp_db):
        """異なるIPアドレスは独立して制限されることのテスト"""
        ip1 = "192.168.1.201"
        ip2 = "192.168.1.202"
        
        # IP1で5回失敗
        for i in range(5):
            log_auth_failure(temp_db, ip1, "password_failure", f"user{i}@example.com")
        temp_db.commit()
        
        # IP2で2回失敗
        for i in range(2):
            log_auth_failure(temp_db, ip2, "password_failure", f"user{i}@example.com")
        temp_db.commit()
        
        # 失敗回数が独立して記録されている
        assert check_auth_failures(temp_db, ip1, 10) == 5
        assert check_auth_failures(temp_db, ip2, 10) == 2
    
    def test_time_window_sliding(self, temp_db):
        """時間窓のスライディング動作テスト"""
        test_ip = "192.168.1.203"
        
        # 過去の失敗（11分前）は対象外
        past_time = datetime.utcnow() - timedelta(minutes=11)
        temp_db.execute('''
            INSERT INTO auth_failures (ip_address, attempt_time, failure_type, email_attempted)
            VALUES (?, ?, ?, ?)
        ''', (test_ip, past_time, "password_failure", "old@example.com"))
        
        # 最近の失敗（5分前）
        recent_time = datetime.utcnow() - timedelta(minutes=5)
        temp_db.execute('''
            INSERT INTO auth_failures (ip_address, attempt_time, failure_type, email_attempted)
            VALUES (?, ?, ?, ?)
        ''', (test_ip, recent_time, "password_failure", "recent@example.com"))
        
        temp_db.commit()
        
        # 10分窓では最近の1回のみカウント
        assert check_auth_failures(temp_db, test_ip, 10) == 1
        
        # 20分窓では両方カウント
        assert check_auth_failures(temp_db, test_ip, 20) == 2


class TestRateLimitingManager:
    """RateLimitManager クラスのテスト（実装後に有効化）"""
    
    @pytest.fixture
    def temp_db(self):
        """テスト用の一時データベース"""
        fd, path = tempfile.mkstemp()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        
        create_tables(conn)
        conn.commit()
        
        yield conn
        
        conn.close()
        os.close(fd)
        os.unlink(path)
    
    def test_rate_limit_manager_full_flow(self, temp_db):
        """RateLimitManager の完全フローテスト"""
        from database.utils import RateLimitManager
        
        test_ip = "192.168.1.300"
        rate_limiter = RateLimitManager(temp_db)
        
        # 初期状態では制限されていない
        assert not is_ip_blocked(temp_db, test_ip)
        
        # 4回失敗では制限されない
        for i in range(4):
            blocked = rate_limiter.record_auth_failure(test_ip, "test_failure", f"test{i}@example.com")
            assert not blocked
        
        # 5回目で制限される
        blocked = rate_limiter.record_auth_failure(test_ip, "test_failure", "test5@example.com")
        assert blocked
        
        # 制限状態を確認
        temp_db.commit()
        assert is_ip_blocked(temp_db, test_ip)
        
        # 統計情報を確認
        stats = rate_limiter.get_rate_limit_stats()
        assert stats['active_blocks_count'] >= 1
    
    def test_auto_unblock_functionality(self, temp_db):
        """自動制限解除機能のテスト"""
        from database.utils import RateLimitManager
        
        test_ip = "192.168.1.301"
        rate_limiter = RateLimitManager(temp_db)
        
        # 過去の時刻で制限を作成（期限切れ）
        past_time = datetime.utcnow() - timedelta(hours=1)
        temp_db.execute('''
            INSERT INTO ip_blocks (ip_address, blocked_until, reason)
            VALUES (?, ?, ?)
        ''', (test_ip, past_time, "Test expired block"))
        temp_db.commit()
        
        # 自動クリーンアップを実行
        cleanup_count = rate_limiter.cleanup_expired_blocks()
        temp_db.commit()
        
        # 期限切れブロックが削除されている
        assert cleanup_count >= 1
        assert not is_ip_blocked(temp_db, test_ip)
    
    def test_admin_manual_unblock(self, temp_db):
        """管理者手動解除機能のテスト"""
        from database.utils import RateLimitManager
        
        test_ip = "192.168.1.302"
        rate_limiter = RateLimitManager(temp_db)
        
        # IP制限を設定
        rate_limiter.apply_ip_block(test_ip, "Test manual block", 30)
        temp_db.commit()
        
        # 制限されていることを確認
        assert is_ip_blocked(temp_db, test_ip)
        
        # 管理者による手動解除
        success = rate_limiter.unblock_ip_manual(test_ip, "test_admin")
        temp_db.commit()
        
        # 解除されていることを確認
        assert success
        assert not is_ip_blocked(temp_db, test_ip)
        
        # 存在しないIPの解除は失敗
        success = rate_limiter.unblock_ip_manual("192.168.1.999", "test_admin")
        assert not success


class TestRateLimitingEdgeCases:
    """エッジケースとセキュリティテスト"""
    
    @pytest.fixture
    def temp_db(self):
        """テスト用の一時データベース"""
        fd, path = tempfile.mkstemp()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        
        create_tables(conn)
        conn.commit()
        
        yield conn
        
        conn.close()
        os.close(fd)
        os.unlink(path)
    
    def test_invalid_ip_address(self, temp_db):
        """不正なIPアドレスの処理テスト"""
        invalid_ips = ["", None, "999.999.999.999", "not_an_ip", "' OR 1=1--"]
        
        for invalid_ip in invalid_ips:
            # 例外が発生せず、適切に処理される
            result = is_ip_blocked(temp_db, invalid_ip)
            assert isinstance(result, bool)
    
    def test_sql_injection_prevention(self, temp_db):
        """SQLインジェクション防止テスト"""
        malicious_ip = "192.168.1.1'; DROP TABLE auth_failures; --"
        
        # SQLインジェクションが実行されない
        log_auth_failure(temp_db, malicious_ip, "test", "test@example.com")
        temp_db.commit()
        
        # テーブルが存在することを確認
        result = temp_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auth_failures'").fetchone()
        assert result is not None
    
    def test_concurrent_access_simulation(self, temp_db):
        """同時アクセスのシミュレーションテスト"""
        test_ip = "192.168.1.250"
        
        # 複数の失敗を短時間で記録（同時アクセス模擬）
        for i in range(10):
            log_auth_failure(temp_db, test_ip, "concurrent_test", f"user{i}@example.com")
        temp_db.commit()
        
        # 全ての記録が正常に保存される
        assert check_auth_failures(temp_db, test_ip, 10) == 10
    
    def test_database_performance_basic(self, temp_db):
        """基本的なパフォーマンステスト"""
        # 大量のデータを挿入
        test_ips = [f"192.168.1.{i}" for i in range(100, 200)]
        
        start_time = time.time()
        for ip in test_ips:
            for j in range(3):
                log_auth_failure(temp_db, ip, "perf_test", f"user{j}@example.com")
        temp_db.commit()
        
        insert_time = time.time() - start_time
        
        # 検索パフォーマンステスト
        start_time = time.time()
        for ip in test_ips[:10]:  # 一部のIPで検索テスト
            check_auth_failures(temp_db, ip, 10)
        
        search_time = time.time() - start_time
        
        # 基本的なパフォーマンス要件（調整可能）
        assert insert_time < 5.0  # 300件挿入が5秒以内
        assert search_time < 1.0  # 10件検索が1秒以内


if __name__ == "__main__":
    # テスト実行例
    pytest.main([__file__, "-v"])