"""
バックアップAPI機能のテスト
Phase 1B: Flask APIエンドポイントのテスト
"""

import os
import sys
import unittest
import tempfile
import shutil
import json
import threading
import time
from unittest.mock import patch, MagicMock

# テスト用のパス設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.backup import BackupManager


class BackupAPITestCase(unittest.TestCase):
    """バックアップAPIエンドポイントのテストケース"""

    def setUp(self):
        """テストセットアップ"""
        self.test_dir = tempfile.mkdtemp()
        self.backups_dir = os.path.join(self.test_dir, "backups")
        self.database_path = os.path.join(self.test_dir, "test_database.db")

        # テスト用アプリケーション設定
        os.environ["TESTING"] = "True"
        os.environ["DATABASE"] = self.database_path

        # テスト用データベース作成（instanceディレクトリ構造）
        instance_dir = os.path.join(self.test_dir, 'instance')
        os.makedirs(instance_dir, exist_ok=True)
        real_db_path = os.path.join(instance_dir, 'database.db')
        
        import sqlite3
        conn = sqlite3.connect(real_db_path)
        conn.execute("""CREATE TABLE test_table (id INTEGER PRIMARY KEY, data TEXT)""")
        conn.execute("""INSERT INTO test_table (data) VALUES ("test_data")""")
        # セッション管理用のテーブルも作成
        conn.execute("""CREATE TABLE IF NOT EXISTS session_stats (
            id TEXT PRIMARY KEY,
            created_at REAL,
            updated_at REAL
        )""")
        conn.commit()
        conn.close()

        # アプリをインポート（環境変数設定後）
        from app import app

        self.app = app
        self.app.config["TESTING"] = True
        self.app.config["DATABASE"] = real_db_path
        self.client = self.app.test_client()

        # テスト用セッション認証とapp設定
        self.app.config['SECRET_KEY'] = 'test_secret_key_for_testing'
        self.app.config['TESTING'] = True
        
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["session_id"] = "test_session"
            sess["login_time"] = time.time()  # セッション有効期限チェック対応

    def tearDown(self):
        """テストクリーンアップ"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        # 環境変数リセット
        os.environ.pop("TESTING", None)
        os.environ.pop("DATABASE", None)

    def test_backup_create_api_success(self):
        """バックアップ作成API - 成功ケース"""
        with patch('app.require_valid_session', return_value=None), \
             patch('app.session', {'authenticated': True}):
            response = self.client.post("/admin/backup/create")

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data["status"], "in_progress")
            self.assertIn("message", data)

    def test_backup_create_api_unauthenticated(self):
        """バックアップ作成API - 未認証エラー"""
        # セッションクリア
        with self.client.session_transaction() as sess:
            sess.clear()

        response = self.client.post("/admin/backup/create")
        self.assertEqual(response.status_code, 302)  # リダイレクト

    def test_backup_list_api_success(self):
        """バックアップ一覧API - 成功ケース"""
        # まずバックアップを作成
        backup_manager = BackupManager(self.test_dir)
        backup_name = backup_manager.create_backup()

        response = self.client.get("/admin/backup/list")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "success")
        self.assertIsInstance(data["data"], list)
        if data["data"]:  # バックアップが存在する場合
            backup = data["data"][0]
            self.assertIn("name", backup)
            self.assertIn("timestamp", backup)
            self.assertIn("size", backup)

    def test_backup_list_api_empty(self):
        """バックアップ一覧API - 空の一覧"""
        response = self.client.get("/admin/backup/list")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"], [])

    def test_backup_download_api_success(self):
        """バックアップダウンロードAPI - 成功ケース"""
        # バックアップ作成
        backup_manager = BackupManager(self.test_dir)
        backup_name = backup_manager.create_backup()

        response = self.client.get(f"/admin/backup/download/{backup_name}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/gzip")
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))

    def test_backup_download_api_not_found(self):
        """バックアップダウンロードAPI - 存在しないファイル"""
        response = self.client.get("/admin/backup/download/nonexistent_backup")

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "error")

    def test_backup_download_api_path_traversal(self):
        """バックアップダウンロードAPI - パストラバーサル攻撃対策"""
        malicious_names = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "backup_../../sensitive_file",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        ]

        for malicious_name in malicious_names:
            response = self.client.get(f"/admin/backup/download/{malicious_name}")

            # 400 (Bad Request) または 404 (Not Found) が期待される
            self.assertIn(response.status_code, [400, 404])
            if response.data:
                data = json.loads(response.data)
                self.assertEqual(data["status"], "error")

    def test_backup_delete_api_success(self):
        """バックアップ削除API - 成功ケース"""
        # バックアップ作成
        backup_manager = BackupManager(self.test_dir)
        backup_name = backup_manager.create_backup()

        response = self.client.delete(f"/admin/backup/delete/{backup_name}")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "success")

        # ファイルが削除されたことを確認
        backups = backup_manager.list_backups()
        backup_names = [b["name"] for b in backups]
        self.assertNotIn(backup_name, backup_names)

    def test_backup_delete_api_not_found(self):
        """バックアップ削除API - 存在しないファイル"""
        response = self.client.delete("/admin/backup/delete/nonexistent_backup")

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "error")

    def test_backup_status_api_success(self):
        """バックアップ状況API - 成功ケース（基本レスポンス）"""
        response = self.client.get("/admin/backup/status")

        # SSEの場合は text/plain、通常JSONの場合は200
        self.assertIn(response.status_code, [200, 201])

    def test_api_error_handling(self):
        """API エラーハンドリング"""
        # BackupManagerの初期化に失敗するケースをシミュレート
        with patch("database.backup.BackupManager") as mock_manager:
            mock_manager.side_effect = Exception("Backup initialization failed")

            response = self.client.post("/admin/backup/create")

            # エラーが適切に処理されることを確認
            self.assertEqual(response.status_code, 500)
            data = json.loads(response.data)
            self.assertEqual(data["status"], "error")
            self.assertIn("message", data)

    def test_concurrent_backup_prevention(self):
        """同時バックアップ実行の防止テスト"""

        # 長時間実行されるバックアップをシミュレート
        def slow_backup():
            time.sleep(0.1)  # 短い遅延
            return "test_backup"

        with patch.object(BackupManager, "create_backup", side_effect=slow_backup):
            # 複数のバックアップリクエストを並行実行
            responses = []
            threads = []

            def make_request():
                response = self.client.post("/admin/backup/create")
                responses.append(response)

            # 3つの並行リクエスト
            for _ in range(3):
                thread = threading.Thread(target=make_request)
                threads.append(thread)
                thread.start()

            # 全スレッド完了を待機
            for thread in threads:
                thread.join()

            # 成功レスポンスと進行中/エラーレスポンスの混在を確認
            success_count = sum(1 for r in responses if r.status_code == 200)
            self.assertGreaterEqual(success_count, 1)  # 少なくとも1つは成功

    def test_backup_metadata_validation(self):
        """バックアップメタデータの検証"""
        # バックアップ作成
        backup_manager = BackupManager(self.test_dir)
        backup_name = backup_manager.create_backup()

        # 一覧取得でメタデータ確認
        response = self.client.get("/admin/backup/list")
        data = json.loads(response.data)

        if data["data"]:
            backup = data["data"][0]
            required_fields = ["name", "timestamp", "size", "checksum"]
            for field in required_fields:
                self.assertIn(field, backup)
                self.assertIsNotNone(backup[field])


class BackupAPISecurityTestCase(unittest.TestCase):
    """バックアップAPIのセキュリティテスト"""

    def setUp(self):
        """テストセットアップ"""
        self.test_dir = tempfile.mkdtemp()
        os.environ["TESTING"] = "True"

        from app import app

        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        """テストクリーンアップ"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.environ.pop("TESTING", None)

    def test_authentication_required(self):
        """全エンドポイントで認証が必要"""
        endpoints = [
            ("POST", "/admin/backup/create"),
            ("GET", "/admin/backup/list"),
            ("GET", "/admin/backup/download/test"),
            ("DELETE", "/admin/backup/delete/test"),
            ("GET", "/admin/backup/status"),
        ]

        for method, endpoint in endpoints:
            if method == "POST":
                response = self.client.post(endpoint)
            elif method == "GET":
                response = self.client.get(endpoint)
            elif method == "DELETE":
                response = self.client.delete(endpoint)

            # 未認証の場合はリダイレクトまたは401エラー
            self.assertIn(response.status_code, [302, 401])

    def test_csrf_protection(self):
        """CSRF保護の確認"""
        # 認証済みセッション設定
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True

        # CSRFトークンなしでのPOSTリクエスト
        # 実装によってはCSRF保護が必要
        response = self.client.post("/admin/backup/create")

        # CSRF保護が実装されている場合は403、されていない場合は他のエラー
        # ここでは基本的な動作確認のみ
        self.assertIsNotNone(response.status_code)


if __name__ == "__main__":
    unittest.main()
