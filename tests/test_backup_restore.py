#!/usr/bin/env python3
"""
BackupManager復旧機能（Phase 3）の単体テスト
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


class TestBackupRestore(unittest.TestCase):
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
        """テスト用環境のクリーンアップ"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_test_database(self):
        """テスト用SQLiteデータベース作成"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # テスト用テーブル作成
        cursor.execute("""
            CREATE TABLE test_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # テストデータ挿入
        cursor.execute(
            "INSERT INTO test_users (username, email) VALUES (?, ?)",
            ("testuser", "test@example.com"),
        )

        conn.commit()
        conn.close()

    def _create_test_env_file(self):
        """テスト用.envファイル作成"""
        with open(self.env_path, "w") as f:
            f.write("SECRET_KEY=test_secret_key\n")
            f.write("DATABASE_URL=sqlite:///test.db\n")
            f.write("DEBUG=True\n")

    def _create_test_pdf_files(self):
        """テスト用PDFファイル作成"""
        test_pdf_content = b"%PDF-1.4 test content"
        with open(os.path.join(self.pdf_dir, "test.pdf"), "wb") as f:
            f.write(test_pdf_content)

    def _create_test_log_files(self):
        """テスト用ログファイル作成"""
        with open(os.path.join(self.logs_dir, "app.log"), "w") as f:
            f.write("2025-01-31 12:00:00 INFO Test log entry\n")

        with open(os.path.join(self.instance_dir, "emergency_log.txt"), "w") as f:
            f.write("Emergency log test content\n")

    def _create_test_backup(self) -> str:
        """テスト用バックアップを作成"""
        backup_name = self.backup_manager.create_backup()
        return backup_name

    def _modify_current_data(self):
        """現在のデータを変更して復旧テスト用の状態を作成"""
        # データベースの変更
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO test_users (username, email) VALUES (?, ?)",
            ("modified_user", "modified@example.com"),
        )
        conn.commit()
        conn.close()

        # .envファイルの変更
        with open(self.env_path, "a") as f:
            f.write("MODIFIED=True\n")

        # PDFファイルの追加
        with open(os.path.join(self.pdf_dir, "modified.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 modified content")

        # ログファイルの変更
        with open(os.path.join(self.logs_dir, "app.log"), "a") as f:
            f.write("2025-01-31 13:00:00 INFO Modified log entry\n")

    def test_restore_from_backup_success(self):
        """正常な復旧処理のテスト"""
        # 1. 初期バックアップ作成
        backup_name = self._create_test_backup()

        # 2. 現在のデータを変更
        self._modify_current_data()

        # 3. データが変更されていることを確認
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM test_users")
        count_before = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count_before, 2)  # 元のデータ + 追加データ

        # 4. 復旧実行
        result = self.backup_manager.restore_from_backup(backup_name)
        self.assertTrue(result["success"])
        self.assertIn("pre_restore_backup", result)

        # 5. データが復旧されていることを確認
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM test_users")
        count_after = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count_after, 1)  # 元のデータのみ

        # 6. .envファイルが復旧されていることを確認
        with open(self.env_path, "r") as f:
            env_content = f.read()
        self.assertNotIn("MODIFIED=True", env_content)

        # 7. PDFファイルが復旧されていることを確認
        self.assertTrue(os.path.exists(os.path.join(self.pdf_dir, "test.pdf")))
        self.assertFalse(os.path.exists(os.path.join(self.pdf_dir, "modified.pdf")))

    def test_restore_nonexistent_backup(self):
        """存在しないバックアップの復旧テスト"""
        result = self.backup_manager.restore_from_backup("nonexistent_backup")
        self.assertFalse(result["success"])
        self.assertIn("不正なバックアップ名", result["message"])

    def test_restore_creates_pre_restore_backup(self):
        """復旧前自動バックアップが作成されることのテスト"""
        # 1. 初期バックアップ作成
        backup_name = self._create_test_backup()

        # 2. 現在のデータを変更
        self._modify_current_data()

        # 3. 復旧実行
        result = self.backup_manager.restore_from_backup(backup_name)
        self.assertTrue(result["success"])

        # 4. 復旧前バックアップが作成されていることを確認
        pre_restore_backup = result["pre_restore_backup"]
        self.assertIsNotNone(pre_restore_backup)
        self.assertTrue(pre_restore_backup.startswith("pre_restore_"))

        # 5. 復旧前バックアップが実際に存在することを確認
        backups = self.backup_manager.list_backups()
        backup_names = [b["backup_name"] for b in backups]
        self.assertIn(pre_restore_backup, backup_names)

    def test_restore_integrity_check(self):
        """復旧後の整合性チェックテスト"""
        # 1. 初期バックアップ作成
        backup_name = self._create_test_backup()

        # 2. 現在のデータを変更
        self._modify_current_data()

        # 3. 復旧実行
        result = self.backup_manager.restore_from_backup(backup_name)
        self.assertTrue(result["success"])

        # 4. 整合性チェック結果が含まれていることを確認
        self.assertIn("integrity_check", result)
        self.assertTrue(result["integrity_check"]["passed"])

    def test_restore_with_corrupted_backup(self):
        """破損したバックアップからの復旧テスト"""
        # 1. 初期バックアップ作成
        backup_name = self._create_test_backup()

        # 2. バックアップファイルを破損させる
        backup_path = self.backup_manager.get_backup_path(backup_name)
        with open(backup_path, "w") as f:
            f.write("corrupted data")

        # 3. 復旧実行
        result = self.backup_manager.restore_from_backup(backup_name)
        # 破損ファイルの場合、整合性チェックで失敗するか、
        # tar展開エラーで失敗する可能性がある
        if result["success"]:
            # 成功した場合は、整合性チェックで問題が検出されるはず
            self.assertIn("integrity_check", result)
        else:
            # 失敗した場合は、適切なエラーメッセージが表示される
            self.assertTrue("破損" in result["message"] or 
                          "エラー" in result["message"])

    def test_restore_logs_operation(self):
        """復旧操作のログ記録テスト"""
        # 1. 初期バックアップ作成
        backup_name = self._create_test_backup()

        # 2. 現在のデータを変更
        self._modify_current_data()

        # 3. 復旧実行
        result = self.backup_manager.restore_from_backup(backup_name)
        self.assertTrue(result["success"])

        # 4. ログが記録されていることを確認
        self.assertIn("log_file", result)
        log_file = result["log_file"]
        self.assertTrue(os.path.exists(log_file))

        # 5. ログ内容を確認
        with open(log_file, "r") as f:
            log_content = f.read()
        self.assertIn("復旧開始", log_content)
        self.assertIn("復旧完了", log_content)
        self.assertIn(backup_name, log_content)

    def test_restore_permissions(self):
        """復旧後のファイル権限テスト"""
        # 1. 初期バックアップ作成
        backup_name = self._create_test_backup()

        # 2. 現在のデータを変更
        self._modify_current_data()

        # 3. 復旧実行
        result = self.backup_manager.restore_from_backup(backup_name)
        self.assertTrue(result["success"])

        # 4. 復旧されたファイルの権限を確認
        # データベースファイル
        db_stat = os.stat(self.db_path)
        self.assertEqual(oct(db_stat.st_mode)[-3:], "600")

        # .envファイル
        env_stat = os.stat(self.env_path)
        self.assertEqual(oct(env_stat.st_mode)[-3:], "600")

    def test_restore_with_missing_directories(self):
        """ディレクトリが存在しない場合の復旧テスト"""
        # 1. 初期バックアップ作成
        backup_name = self._create_test_backup()

        # 2. 対象ディレクトリを削除
        shutil.rmtree(self.pdf_dir)

        # 3. 復旧実行
        result = self.backup_manager.restore_from_backup(backup_name)
        self.assertTrue(result["success"])

        # 4. ディレクトリが再作成されていることを確認
        self.assertTrue(os.path.exists(self.pdf_dir))
        self.assertTrue(os.path.exists(os.path.join(self.pdf_dir, "test.pdf")))


if __name__ == "__main__":
    unittest.main()