#!/usr/bin/env python3
"""
BackupManagerクラスの単体テスト
"""
import unittest
import tempfile
import os
import sqlite3
import tarfile
import json
import shutil
from datetime import datetime
import sys

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.backup import BackupManager  # noqa: E402


class TestBackupManager(unittest.TestCase):
    def setUp(self):
        """テスト用の環境セットアップ"""
        # テスト用ディレクトリ作成
        self.test_dir = tempfile.mkdtemp()
        self.backup_dir = os.path.join(self.test_dir, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)

        # テスト用データベース作成
        self.db_path = os.path.join(self.test_dir, "test_database.db")
        self._create_test_database()

        # テスト用設定ファイル作成
        self.env_path = os.path.join(self.test_dir, ".env")
        self._create_test_env_file()

        # テスト用PDFディレクトリ作成
        self.pdf_dir = os.path.join(self.test_dir, "static", "pdfs")
        os.makedirs(self.pdf_dir, exist_ok=True)
        self._create_test_pdf_files()

        # テスト用ログディレクトリ作成
        self.logs_dir = os.path.join(self.test_dir, "logs")
        self.instance_dir = os.path.join(self.test_dir, "instance")
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.instance_dir, exist_ok=True)
        self._create_test_log_files()

        # BackupManagerインスタンス作成
        self.backup_manager = BackupManager(
            db_path=self.db_path,
            backup_dir=self.backup_dir,
            env_path=self.env_path,
            pdf_dir=self.pdf_dir,
            logs_dir=self.logs_dir,
            instance_dir=self.instance_dir,
        )

    def tearDown(self):
        """テスト後のクリーンアップ"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_test_database(self):
        """テスト用SQLiteデータベース作成"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # テストテーブル作成
        cursor.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """
        )

        # テストデータ挿入
        cursor.execute(
            """
            INSERT INTO users (username, email, created_at)
            VALUES ('test_user', 'test@example.com', '2025-01-01 12:00:00')
        """
        )

        conn.commit()
        conn.close()

    def _create_test_env_file(self):
        """テスト用.envファイル作成"""
        env_content = """# Test environment file
SECRET_KEY=test_secret_key_123
DATABASE_URL=sqlite:///test.db
API_KEY=sensitive_api_key_456
NORMAL_CONFIG=normal_value
PASSWORD=sensitive_password_789
"""
        with open(self.env_path, "w") as f:
            f.write(env_content)

    def _create_test_pdf_files(self):
        """テスト用PDFファイル作成"""
        # ダミーPDFファイル作成（実際のPDFではないが、テスト目的）
        pdf_files = ["test1.pdf", "test2.pdf", "subfolder/test3.pdf"]

        for pdf_file in pdf_files:
            full_path = os.path.join(self.pdf_dir, pdf_file)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "wb") as f:
                f.write(b"%PDF-1.4\nFake PDF content for testing\n%%EOF")

    def _create_test_log_files(self):
        """テスト用ログファイル作成"""
        # app.log作成
        app_log_path = os.path.join(self.logs_dir, "app.log")
        with open(app_log_path, "w") as f:
            f.write("2025-01-01 12:00:00 INFO Test log entry\n")
            f.write("2025-01-01 12:01:00 WARNING Test warning\n")

        # emergency_log.txt作成
        emergency_log_path = os.path.join(self.instance_dir, "emergency_log.txt")
        with open(emergency_log_path, "w") as f:
            f.write("2025-01-01 12:00:00 EMERGENCY Test emergency log\n")

    def test_create_backup_success(self):
        """バックアップ作成の正常系テスト"""
        backup_name = self.backup_manager.create_backup()

        # バックアップファイルが作成されていることを確認
        self.assertIsNotNone(backup_name)
        backup_file = os.path.join(self.backup_dir, "manual", f"{backup_name}.tar.gz")
        self.assertTrue(os.path.exists(backup_file))

        # メタデータファイルが作成されていることを確認
        metadata_file = os.path.join(self.backup_dir, "metadata", f"{backup_name}.json")
        self.assertTrue(os.path.exists(metadata_file))

        # メタデータの内容確認
        with open(metadata_file, "r") as f:
            metadata = json.load(f)

        self.assertEqual(metadata["backup_name"], backup_name)
        self.assertEqual(metadata["type"], "manual")
        self.assertIn("timestamp", metadata)
        self.assertIn("size", metadata)
        self.assertIn("files_count", metadata)
        self.assertIn("checksum", metadata)

    def test_backup_database_safe(self):
        """SQLite安全バックアップのテスト"""
        temp_backup_dir = tempfile.mkdtemp()
        try:
            backup_files = self.backup_manager._backup_database(temp_backup_dir)

            # バックアップファイルが作成されていることを確認
            self.assertTrue(len(backup_files) >= 1)
            
            # データベースファイルを探す
            backup_db_path = None
            for file_path in backup_files:
                if file_path.endswith('database.db'):
                    backup_db_path = file_path
                    break
            
            self.assertIsNotNone(backup_db_path)
            self.assertTrue(os.path.exists(backup_db_path))

            # バックアップされたデータベースが読み取り可能であることを確認
            conn = sqlite3.connect(backup_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][1], "test_user")
            conn.close()

        finally:
            shutil.rmtree(temp_backup_dir, ignore_errors=True)

    def test_backup_config_files_masking(self):
        """設定ファイルバックアップ（機密情報マスク）のテスト"""
        temp_backup_dir = tempfile.mkdtemp()
        try:
            config_files = self.backup_manager._backup_config_files(temp_backup_dir)

            # 設定ファイルがバックアップされていることを確認
            self.assertTrue(len(config_files) > 0)

            # マスク処理されたファイルの内容確認
            backup_env_path = os.path.join(temp_backup_dir, "config", ".env")
            self.assertTrue(os.path.exists(backup_env_path))

            with open(backup_env_path, "r") as f:
                content = f.read()

            # 機密情報がマスクされていることを確認
            self.assertIn("SECRET_KEY=***MASKED***", content)
            self.assertIn("API_KEY=***MASKED***", content)
            self.assertIn("PASSWORD=***MASKED***", content)

            # 通常の設定はマスクされていないことを確認
            self.assertIn("NORMAL_CONFIG=normal_value", content)

        finally:
            shutil.rmtree(temp_backup_dir, ignore_errors=True)

    def test_backup_pdf_files(self):
        """PDFファイルバックアップのテスト"""
        temp_backup_dir = tempfile.mkdtemp()
        try:
            pdf_files = self.backup_manager._backup_pdf_files(temp_backup_dir)

            # PDFファイルがバックアップされていることを確認
            self.assertTrue(
                len(pdf_files) >= 3
            )  # test1.pdf, test2.pdf, subfolder/test3.pdf

            # バックアップされたファイルが存在することを確認
            backup_pdf_dir = os.path.join(temp_backup_dir, "files", "pdfs")
            self.assertTrue(os.path.exists(os.path.join(backup_pdf_dir, "test1.pdf")))
            self.assertTrue(os.path.exists(os.path.join(backup_pdf_dir, "test2.pdf")))
            self.assertTrue(
                os.path.exists(os.path.join(backup_pdf_dir, "subfolder", "test3.pdf"))
            )

        finally:
            shutil.rmtree(temp_backup_dir, ignore_errors=True)

    def test_backup_log_files(self):
        """ログファイルバックアップのテスト"""
        temp_backup_dir = tempfile.mkdtemp()
        try:
            log_files = self.backup_manager._backup_log_files(temp_backup_dir)

            # ログファイルがバックアップされていることを確認
            self.assertTrue(len(log_files) >= 2)  # app.log, emergency_log.txt

            # バックアップされたファイルが存在することを確認
            backup_logs_dir = os.path.join(temp_backup_dir, "logs")
            self.assertTrue(os.path.exists(os.path.join(backup_logs_dir, "app.log")))
            self.assertTrue(
                os.path.exists(os.path.join(backup_logs_dir, "emergency_log.txt"))
            )

        finally:
            shutil.rmtree(temp_backup_dir, ignore_errors=True)

    def test_create_archive(self):
        """アーカイブ作成のテスト"""
        # テスト用データディレクトリ作成
        temp_data_dir = tempfile.mkdtemp()
        test_file = os.path.join(temp_data_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("test content")

        try:
            archive_path = self.backup_manager._create_archive(
                temp_data_dir, "test_backup"
            )

            # アーカイブファイルが作成されていることを確認
            self.assertTrue(os.path.exists(archive_path))
            self.assertTrue(archive_path.endswith(".tar.gz"))

            # アーカイブの中身確認
            with tarfile.open(archive_path, "r:gz") as tar:
                members = tar.getnames()
                self.assertTrue(any("test.txt" in member for member in members))

        finally:
            shutil.rmtree(temp_data_dir, ignore_errors=True)
            if os.path.exists(archive_path):
                os.remove(archive_path)

    def test_list_backups(self):
        """バックアップ一覧取得のテスト"""
        # テスト用バックアップファイルとメタデータ作成
        backup_name = f"test_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # ダミーバックアップファイル作成
        manual_dir = os.path.join(self.backup_dir, "manual")
        os.makedirs(manual_dir, exist_ok=True)
        backup_file = os.path.join(manual_dir, f"{backup_name}.tar.gz")
        with open(backup_file, "wb") as f:
            f.write(b"dummy backup content")

        # メタデータファイル作成
        metadata_dir = os.path.join(self.backup_dir, "metadata")
        os.makedirs(metadata_dir, exist_ok=True)
        metadata_file = os.path.join(metadata_dir, f"{backup_name}.json")
        metadata = {
            "backup_name": backup_name,
            "type": "manual",
            "timestamp": "20250730_143025",
            "size": 100,
            "files_count": 5,
            "checksum": "test_checksum",
        }
        with open(metadata_file, "w") as f:
            json.dump(metadata, f)

        # バックアップ一覧取得
        backups = self.backup_manager.list_backups()

        # バックアップが一覧に含まれていることを確認
        self.assertTrue(len(backups) >= 1)

        # 作成したバックアップが含まれていることを確認
        backup_found = False
        for backup in backups:
            if backup["backup_name"] == backup_name:
                backup_found = True
                self.assertEqual(backup["type"], "manual")
                self.assertEqual(backup["size"], 100)
                self.assertEqual(backup["files_count"], 5)
                break

        self.assertTrue(backup_found, f"作成したバックアップ {backup_name} が一覧に見つかりません")

    def test_delete_backup(self):
        """バックアップ削除のテスト"""
        # テスト用バックアップ作成
        backup_name = self.backup_manager.create_backup()

        # バックアップが存在することを確認
        backup_file = os.path.join(self.backup_dir, "manual", f"{backup_name}.tar.gz")
        metadata_file = os.path.join(self.backup_dir, "metadata", f"{backup_name}.json")
        self.assertTrue(os.path.exists(backup_file))
        self.assertTrue(os.path.exists(metadata_file))

        # バックアップ削除
        result = self.backup_manager.delete_backup(backup_name)
        self.assertTrue(result)

        # ファイルが削除されていることを確認
        self.assertFalse(os.path.exists(backup_file))
        self.assertFalse(os.path.exists(metadata_file))

    def test_get_backup_path(self):
        """バックアップパス取得のテスト"""
        # テスト用バックアップ作成
        backup_name = self.backup_manager.create_backup()

        # パス取得
        backup_path = self.backup_manager.get_backup_path(backup_name)

        # パスが正しいことを確認
        expected_path = os.path.join(self.backup_dir, "manual", f"{backup_name}.tar.gz")
        self.assertEqual(backup_path, expected_path)

        # ファイルが存在することを確認
        self.assertTrue(os.path.exists(backup_path))

    def test_path_traversal_protection(self):
        """Path Traversal攻撃対策のテスト"""
        # 危険なバックアップ名でのテスト
        dangerous_names = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "backup/../../../secret.txt",
            "backup\\..\\..\\..\\secret.txt",
        ]

        for dangerous_name in dangerous_names:
            with self.assertRaises((ValueError, OSError)):
                self.backup_manager.get_backup_path(dangerous_name)

    def test_backup_integrity_checksum(self):
        """バックアップファイルの整合性チェック（チェックサム）のテスト"""
        backup_name = self.backup_manager.create_backup()

        # メタデータからチェックサムを取得
        metadata_file = os.path.join(self.backup_dir, "metadata", f"{backup_name}.json")
        with open(metadata_file, "r") as f:
            metadata = json.load(f)

        stored_checksum = metadata["checksum"]

        # 実際のファイルのチェックサムを計算
        backup_file = os.path.join(self.backup_dir, "manual", f"{backup_name}.tar.gz")
        actual_checksum = self.backup_manager._calculate_checksum(backup_file)

        # チェックサムが一致することを確認
        self.assertEqual(stored_checksum, actual_checksum)


if __name__ == "__main__":
    unittest.main()
