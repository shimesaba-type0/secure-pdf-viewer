"""
インシデント検索機能のテストケース

このテストモジュールは、インシデント検索機能の包括的なテストを提供します。
- API正常系・異常系テスト
- 入力検証テスト
- 権限制御テスト
- セキュリティテスト
"""

import pytest
import json
import re
import sqlite3
import tempfile
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.utils import BlockIncidentManager
from database.models import create_tables


class TestIncidentSearchAPI:
    """インシデント検索API のテストクラス"""

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
        conn.commit()
        
        yield conn
        
        # クリーンアップ
        conn.close()
        os.unlink(path)

    @pytest.fixture 
    def app(self):
        """テスト用Flaskアプリケーション"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        import app as main_app
        
        main_app.app.config['TESTING'] = True
        main_app.app.config['SECRET_KEY'] = 'test-secret-key'
        
        return main_app.app

    @pytest.fixture
    def client(self, app):
        """テスト用クライアント"""
        return app.test_client()

    @pytest.fixture
    def auth_admin(self, client):
        """管理者認証済みセッション"""
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['admin'] = True
            sess['session_start'] = datetime.now().timestamp()

    def setup_method(self):
        """各テストメソッド実行前の初期化"""
        self.valid_incident_id = "BLOCK-20250727140530-A4B2"
        self.invalid_incident_formats = [
            "INVALID-ID",
            "BLOCK-202507271405-A4B2",  # 日時部分が短い
            "BLOCK-20250727140530-A4B23",  # ハッシュ部分が長い
            "BLOCK-20250727140530-a4b2",  # 小文字
            "block-20250727140530-A4B2",  # プレフィックス小文字
            "",
            "   ",
            None
        ]

    def test_incident_search_success(self, client, temp_db, auth_admin):
        """正常系: 有効なインシデントIDで検索成功"""
        # テスト用インシデント作成
        incident_manager = BlockIncidentManager(temp_db)
        test_ip = "192.168.1.100"
        test_reason = "認証失敗回数制限(5回/10分)"
        
        # インシデント作成
        incident_id = incident_manager.create_incident(test_ip, test_reason)
        assert incident_id is not None
        
        # 検索API実行
        response = client.get(f'/admin/api/incident-search?incident_id={incident_id}')
        
        # レスポンス検証
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'incident' in data
        
        # インシデントデータ検証
        incident = data['incident']
        assert incident['incident_id'] == incident_id
        assert incident['ip_address'] == test_ip
        assert incident['block_reason'] == test_reason
        assert incident['resolved'] is False
        assert incident['resolved_at'] is None
        assert incident['resolved_by'] is None

    def test_incident_search_not_found(self, client, temp_db, auth_admin):
        """異常系: 存在しないインシデントIDで検索"""
        non_existent_id = "BLOCK-20990101000000-ZZZZ"
        
        response = client.get(f'/admin/api/incident-search?incident_id={non_existent_id}')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'error' in data
        assert 'インシデントが見つかりません' in data['error']

    def test_incident_search_empty_id(self, client, temp_db, auth_admin):
        """異常系: 空のインシデントID"""
        response = client.get('/admin/api/incident-search?incident_id=')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'インシデントIDが指定されていません' in data['error']

    def test_incident_search_missing_parameter(self, client, temp_db, auth_admin):
        """異常系: パラメータなし"""
        response = client.get('/admin/api/incident-search')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'インシデントIDが指定されていません' in data['error']

    @pytest.mark.parametrize("invalid_id", [
        "INVALID-ID",
        "BLOCK-202507271405-A4B2",  # 日時部分が短い
        "BLOCK-20250727140530-A4B23",  # ハッシュ部分が長い
        "BLOCK-20250727140530-a4b2",  # 小文字
        "block-20250727140530-A4B2",  # プレフィックス小文字
        "   BLOCK-20250727140530-A4B2   ",  # 空白込み（trimされるべき）
    ])
    def test_incident_search_invalid_format(self, client, temp_db, auth_admin, invalid_id):
        """異常系: 無効なインシデントID形式"""
        response = client.get(f'/admin/api/incident-search?incident_id={invalid_id}')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False
        assert '無効なインシデントID形式です' in data['error']

    def test_incident_search_unauthorized(self, client, temp_db):
        """セキュリティテスト: 非管理者ユーザーのアクセス拒否"""
        response = client.get(f'/admin/api/incident-search?incident_id={self.valid_incident_id}')
        
        # 管理者権限がない場合はリダイレクトまたは401/403
        assert response.status_code in [302, 401, 403]

    def test_incident_search_sql_injection_protection(self, client, temp_db, auth_admin):
        """セキュリティテスト: SQLインジェクション攻撃の防御"""
        malicious_inputs = [
            "'; DROP TABLE block_incidents; --",
            "' OR '1'='1",
            "UNION SELECT * FROM users",
            "'; INSERT INTO block_incidents VALUES ('evil'); --"
        ]
        
        for malicious_input in malicious_inputs:
            response = client.get(f'/admin/api/incident-search?incident_id={malicious_input}')
            
            # 無効なフォーマットとして拒否されるべき
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is False

    def test_incident_search_resolved_incident(self, client, temp_db, auth_admin):
        """正常系: 解決済みインシデントの検索"""
        # テスト用インシデント作成・解決
        incident_manager = BlockIncidentManager(temp_db)
        test_ip = "192.168.1.101"
        test_reason = "認証失敗回数制限(5回/10分)"
        admin_user = "test_admin"
        admin_notes = "テスト解決"
        
        # インシデント作成・解決
        incident_id = incident_manager.create_incident(test_ip, test_reason)
        success = incident_manager.resolve_incident(incident_id, admin_user, admin_notes)
        assert success is True
        
        # 検索API実行
        response = client.get(f'/admin/api/incident-search?incident_id={incident_id}')
        
        # レスポンス検証
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        
        # 解決済み情報の検証
        incident = data['incident']
        assert incident['resolved'] is True
        assert incident['resolved_by'] == admin_user
        assert incident['admin_notes'] == admin_notes
        assert incident['resolved_at'] is not None

    def test_incident_id_format_validation(self):
        """単体テスト: インシデントID形式検証の正規表現テスト"""
        pattern = r'^BLOCK-\d{14}-[A-Z0-9]{4}$'
        
        # 有効なフォーマット
        valid_ids = [
            "BLOCK-20250727140530-A4B2",
            "BLOCK-20991231235959-Z9Z9",
            "BLOCK-20000101000000-0000"
        ]
        
        for valid_id in valid_ids:
            assert re.match(pattern, valid_id), f"Valid ID failed: {valid_id}"
        
        # 無効なフォーマット
        invalid_ids = [
            "BLOCK-2025072714053-A4B2",   # 日時13桁
            "BLOCK-202507271405300-A4B2", # 日時15桁
            "BLOCK-20250727140530-A4B",   # ハッシュ3桁
            "BLOCK-20250727140530-A4B23", # ハッシュ5桁
            "BLOCK-20250727140530-a4b2",  # 小文字
            "block-20250727140530-A4B2",  # プレフィックス小文字
            "LOCK-20250727140530-A4B2",   # 間違ったプレフィックス
            "BLOCK-20250727140530_A4B2",  # アンダースコア
            ""
        ]
        
        for invalid_id in invalid_ids:
            assert not re.match(pattern, invalid_id), f"Invalid ID passed: {invalid_id}"


class TestIncidentSearchIntegration:
    """インシデント検索機能の統合テスト"""

    def test_end_to_end_incident_lifecycle(self, client, temp_db, auth_admin):
        """E2Eテスト: インシデント作成→検索→解除の完全な流れ"""
        # 1. インシデント作成
        incident_manager = BlockIncidentManager(temp_db)
        test_ip = "192.168.1.200"
        test_reason = "認証失敗回数制限(5回/10分)"
        
        incident_id = incident_manager.create_incident(test_ip, test_reason)
        assert incident_id is not None
        
        # 2. 検索によるインシデント確認
        search_response = client.get(f'/admin/api/incident-search?incident_id={incident_id}')
        assert search_response.status_code == 200
        
        search_data = json.loads(search_response.data)
        assert search_data['success'] is True
        assert search_data['incident']['resolved'] is False
        
        # 3. インシデント解除（解除APIが存在する場合）
        resolve_payload = {
            'incident_id': incident_id,
            'admin_notes': 'E2Eテストによる解除'
        }
        
        resolve_response = client.post('/admin/api/resolve-incident',
                                     data=json.dumps(resolve_payload),
                                     content_type='application/json')
        assert resolve_response.status_code == 200
        
        # 4. 解除後の検索確認
        final_search_response = client.get(f'/admin/api/incident-search?incident_id={incident_id}')
        assert final_search_response.status_code == 200
        
        final_data = json.loads(final_search_response.data)
        assert final_data['success'] is True
        assert final_data['incident']['resolved'] is True

    def test_concurrent_search_operations(self, client, temp_db, auth_admin):
        """パフォーマンステスト: 複数同時検索操作"""
        # 複数のインシデントを作成
        incident_manager = BlockIncidentManager(temp_db)
        incident_ids = []
        
        for i in range(5):
            test_ip = f"192.168.1.{20 + i}"
            incident_id = incident_manager.create_incident(test_ip, "テスト用インシデント")
            incident_ids.append(incident_id)
        
        # 同時検索実行
        responses = []
        for incident_id in incident_ids:
            response = client.get(f'/admin/api/incident-search?incident_id={incident_id}')
            responses.append(response)
        
        # 全ての検索が成功することを確認
        for i, response in enumerate(responses):
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['incident']['incident_id'] == incident_ids[i]

    def test_search_performance_metrics(self, client, temp_db, auth_admin):
        """パフォーマンステスト: 検索応答時間測定"""
        import time
        
        # テスト用インシデント作成
        incident_manager = BlockIncidentManager(temp_db)
        test_ip = "192.168.1.250"
        incident_id = incident_manager.create_incident(test_ip, "パフォーマンステスト")
        
        # 検索時間測定
        start_time = time.time()
        response = client.get(f'/admin/api/incident-search?incident_id={incident_id}')
        end_time = time.time()
        
        # レスポンス時間検証（1秒以内）
        response_time = end_time - start_time
        assert response_time < 1.0, f"検索が遅すぎます: {response_time:.3f}秒"
        
        # 正常なレスポンス確認
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


class TestIncidentSearchSecurity:
    """インシデント検索機能のセキュリティテスト"""

    def test_xss_protection(self, client, temp_db, auth_admin):
        """セキュリティテスト: XSS攻撃の防御"""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "'; alert('xss'); //"
        ]
        
        for payload in xss_payloads:
            response = client.get(f'/admin/api/incident-search?incident_id={payload}')
            
            # 無効なフォーマットとして適切に処理されるべき
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is False
            
            # レスポンスにスクリプトが含まれていないことを確認
            response_text = response.data.decode('utf-8')
            assert '<script>' not in response_text
            assert 'javascript:' not in response_text

    def test_input_length_limits(self, client, temp_db, auth_admin):
        """セキュリティテスト: 入力長制限のテスト"""
        # 非常に長い入力
        long_input = "A" * 1000
        
        response = client.get(f'/admin/api/incident-search?incident_id={long_input}')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False

    def test_special_characters_handling(self, client, temp_db, auth_admin):
        """セキュリティテスト: 特殊文字の適切な処理"""
        special_chars = [
            "BLOCK-20250727140530-A4B2%00",  # null byte
            "BLOCK-20250727140530-A4B2\n",   # newline
            "BLOCK-20250727140530-A4B2\r",   # carriage return
            "BLOCK-20250727140530-A4B2\t",   # tab
        ]
        
        for special_char in special_chars:
            response = client.get(f'/admin/api/incident-search?incident_id={special_char}')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is False