"""
ブロックインシデント管理システムのテストケース
IP制限時の緊急解除申請機能のテスト
"""

import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import sys
import hashlib

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.models import create_tables


class TestBlockIncidentManager:
    """ブロックインシデント管理のテスト"""
    
    @pytest.fixture
    def temp_db(self):
        """テスト用の一時データベース"""
        fd, path = tempfile.mkstemp()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        
        # テーブル作成
        create_tables(conn)
        
        # ブロックインシデントテーブル作成
        conn.execute('''
            CREATE TABLE IF NOT EXISTS block_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT UNIQUE NOT NULL,
                ip_address TEXT NOT NULL,
                block_reason TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved BOOLEAN DEFAULT FALSE,
                resolved_at TIMESTAMP NULL,
                resolved_by TEXT NULL,
                admin_notes TEXT NULL
            )
        ''')
        
        # インデックス作成
        conn.execute('CREATE INDEX IF NOT EXISTS idx_block_incidents_incident_id ON block_incidents(incident_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_block_incidents_ip ON block_incidents(ip_address)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_block_incidents_resolved ON block_incidents(resolved)')
        
        conn.commit()
        
        yield conn
        
        conn.close()
        os.close(fd)
        os.unlink(path)
    
    def test_generate_block_incident_id(self, temp_db):
        """ブロックインシデントID生成のテスト"""
        from database.utils import BlockIncidentManager
        
        manager = BlockIncidentManager(temp_db)
        test_ip = "192.168.1.100"
        
        # インシデントID生成
        incident_id = manager.generate_block_incident_id(test_ip)
        
        # フォーマット確認
        assert incident_id.startswith("BLOCK-")
        assert len(incident_id.split("-")) == 3  # BLOCK-YYYYMMDDHHMMSS-HASH
        
        # 一意性確認
        incident_id2 = manager.generate_block_incident_id(test_ip)
        assert incident_id != incident_id2
    
    def test_create_incident(self, temp_db):
        """インシデント作成のテスト"""
        from database.utils import BlockIncidentManager
        
        manager = BlockIncidentManager(temp_db)
        test_ip = "192.168.1.101"
        reason = "レート制限に達しました: 10分間で5回の認証失敗"
        
        # インシデント作成
        incident_id = manager.create_incident(test_ip, reason)
        
        # データベースに記録されていることを確認
        row = temp_db.execute('''
            SELECT * FROM block_incidents WHERE incident_id = ?
        ''', (incident_id,)).fetchone()
        
        assert row is not None
        assert row['incident_id'] == incident_id
        assert row['ip_address'] == test_ip
        assert row['block_reason'] == reason
        assert not row['resolved']
        assert row['resolved_at'] is None
        assert row['resolved_by'] is None
    
    def test_resolve_incident(self, temp_db):
        """インシデント解除のテスト"""
        from database.utils import BlockIncidentManager
        
        manager = BlockIncidentManager(temp_db)
        test_ip = "192.168.1.102"
        reason = "Test block reason"
        admin_user = "test_admin"
        admin_notes = "Resolved per user request"
        
        # インシデント作成
        incident_id = manager.create_incident(test_ip, reason)
        
        # インシデント解除
        success = manager.resolve_incident(incident_id, admin_user, admin_notes)
        
        assert success
        
        # 解除状態を確認
        row = temp_db.execute('''
            SELECT * FROM block_incidents WHERE incident_id = ?
        ''', (incident_id,)).fetchone()
        
        assert row['resolved'] == True
        assert row['resolved_by'] == admin_user
        assert row['admin_notes'] == admin_notes
        assert row['resolved_at'] is not None
    
    def test_resolve_nonexistent_incident(self, temp_db):
        """存在しないインシデントの解除テスト"""
        from database.utils import BlockIncidentManager
        
        manager = BlockIncidentManager(temp_db)
        
        # 存在しないインシデントIDで解除を試行
        success = manager.resolve_incident("BLOCK-99999999-999999-XXXX", "admin")
        
        assert not success
    
    def test_get_incident_by_id(self, temp_db):
        """インシデントID検索のテスト"""
        from database.utils import BlockIncidentManager
        
        manager = BlockIncidentManager(temp_db)
        test_ip = "192.168.1.103"
        reason = "Test incident for retrieval"
        
        # インシデント作成
        incident_id = manager.create_incident(test_ip, reason)
        
        # インシデント取得
        incident = manager.get_incident_by_id(incident_id)
        
        assert incident is not None
        assert incident['incident_id'] == incident_id
        assert incident['ip_address'] == test_ip
        assert incident['block_reason'] == reason
        assert not incident['resolved']
    
    def test_get_pending_incidents(self, temp_db):
        """未解決インシデント一覧取得のテスト"""
        from database.utils import BlockIncidentManager
        
        manager = BlockIncidentManager(temp_db)
        
        # 複数のインシデントを作成
        incident1 = manager.create_incident("192.168.1.104", "First incident")
        incident2 = manager.create_incident("192.168.1.105", "Second incident")
        incident3 = manager.create_incident("192.168.1.106", "Third incident")
        
        # 1つを解除
        manager.resolve_incident(incident2, "admin", "Resolved")
        
        # 未解決インシデント一覧を取得
        pending = manager.get_pending_incidents()
        
        # 2つが未解決で残っている
        assert len(pending) == 2
        
        pending_ids = [inc['incident_id'] for inc in pending]
        assert incident1 in pending_ids
        assert incident3 in pending_ids
        assert incident2 not in pending_ids
    
    def test_incident_id_hash_consistency(self, temp_db):
        """インシデントIDハッシュの一貫性テスト"""
        from database.utils import BlockIncidentManager
        
        manager = BlockIncidentManager(temp_db)
        test_ip = "192.168.1.107"
        
        # 実装の新しい形式に合わせて修正
        with patch('database.utils.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.strftime.return_value = '20250726140800'
            mock_datetime.utcnow.return_value.microsecond = 123456
            
            # 期待されるハッシュ計算
            expected_hash_input = "20250726140800123456192.168.1.107"
            expected_hash = hashlib.sha256(expected_hash_input.encode()).hexdigest()[:4].upper()
            
            incident_id = manager.generate_block_incident_id(test_ip)
            
            # フォーマット確認 (BLOCK-timestamp-hash の3部構成)
            parts = incident_id.split('-')
            assert len(parts) == 3
            assert parts[0] == "BLOCK"
            assert parts[1] == "20250726140800"
            assert parts[2] == expected_hash
    
    def test_incident_lifecycle_integration(self, temp_db):
        """インシデント全ライフサイクルの統合テスト"""
        from database.utils import BlockIncidentManager
        
        manager = BlockIncidentManager(temp_db)
        test_ip = "192.168.1.108"
        reason = "Integration test incident"
        admin_user = "integration_admin"
        
        # 1. インシデント作成
        incident_id = manager.create_incident(test_ip, reason)
        assert incident_id is not None
        
        # 2. 未解決一覧に含まれることを確認
        pending = manager.get_pending_incidents()
        assert len(pending) == 1
        assert pending[0]['incident_id'] == incident_id
        
        # 3. ID検索で取得できることを確認
        incident = manager.get_incident_by_id(incident_id)
        assert incident is not None
        assert not incident['resolved']
        
        # 4. インシデント解除
        success = manager.resolve_incident(incident_id, admin_user, "Test resolution")
        assert success
        
        # 5. 解除後の状態確認
        incident = manager.get_incident_by_id(incident_id)
        assert incident['resolved']
        assert incident['resolved_by'] == admin_user
        
        # 6. 未解決一覧から除外されることを確認
        pending = manager.get_pending_incidents()
        assert len(pending) == 0


class TestBlockIncidentSecurity:
    """ブロックインシデントのセキュリティテスト"""
    
    @pytest.fixture
    def temp_db(self):
        """テスト用の一時データベース"""
        fd, path = tempfile.mkstemp()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        
        create_tables(conn)
        
        # ブロックインシデントテーブル作成
        conn.execute('''
            CREATE TABLE IF NOT EXISTS block_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT UNIQUE NOT NULL,
                ip_address TEXT NOT NULL,
                block_reason TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved BOOLEAN DEFAULT FALSE,
                resolved_at TIMESTAMP NULL,
                resolved_by TEXT NULL,
                admin_notes TEXT NULL
            )
        ''')
        conn.commit()
        
        yield conn
        
        conn.close()
        os.close(fd)
        os.unlink(path)
    
    def test_sql_injection_prevention(self, temp_db):
        """SQLインジェクション防止テスト"""
        from database.utils import BlockIncidentManager
        
        manager = BlockIncidentManager(temp_db)
        
        # 悪意のあるIPアドレス文字列
        malicious_ip = "192.168.1.1'; DROP TABLE block_incidents; --"
        malicious_reason = "Test'; DELETE FROM block_incidents; --"
        
        # SQLインジェクションが実行されない
        incident_id = manager.create_incident(malicious_ip, malicious_reason)
        
        # テーブルが存在することを確認
        result = temp_db.execute('''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='block_incidents'
        ''').fetchone()
        assert result is not None
        
        # データが正常に保存されている
        incident = manager.get_incident_by_id(incident_id)
        assert incident is not None
    
    def test_incident_id_uniqueness(self, temp_db):
        """インシデントIDの一意性テスト"""
        from database.utils import BlockIncidentManager
        
        manager = BlockIncidentManager(temp_db)
        
        # 大量のインシデントを作成して重複チェック
        incident_ids = set()
        
        for i in range(100):
            incident_id = manager.create_incident(f"192.168.1.{i}", f"Test incident {i}")
            assert incident_id not in incident_ids, f"Duplicate incident ID: {incident_id}"
            incident_ids.add(incident_id)
        
        # データベースレベルでの一意性確認
        count = temp_db.execute('SELECT COUNT(DISTINCT incident_id) as count FROM block_incidents').fetchone()
        assert count['count'] == 100


class TestBlockIncidentIntegration:
    """ブロックインシデントとレート制限システムの統合テスト"""
    
    @pytest.fixture
    def temp_db(self):
        """テスト用の一時データベース"""
        fd, path = tempfile.mkstemp()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        
        create_tables(conn)
        
        # ブロックインシデントテーブル作成
        conn.execute('''
            CREATE TABLE IF NOT EXISTS block_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT UNIQUE NOT NULL,
                ip_address TEXT NOT NULL,
                block_reason TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved BOOLEAN DEFAULT FALSE,
                resolved_at TIMESTAMP NULL,
                resolved_by TEXT NULL,
                admin_notes TEXT NULL
            )
        ''')
        conn.commit()
        
        yield conn
        
        conn.close()
        os.close(fd)
        os.unlink(path)
    
    def test_rate_limit_with_incident_creation(self, temp_db):
        """レート制限発動時のインシデント自動作成テスト"""
        # 将来の統合実装時に有効化
        pytest.skip("RateLimitManager統合実装後に有効化")


if __name__ == "__main__":
    # テスト実行例
    pytest.main([__file__, "-v"])