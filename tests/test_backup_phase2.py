"""
TASK-018 Phase 2: 定期バックアップ・世代管理機能のテスト

Phase 2で実装する機能:
1. 定期バックアップ設定（日次/週次）
2. 保持世代数管理（デフォルト30日）
3. 自動バックアップ有効/無効設定
4. バックアップ保存先パス設定
5. 古いファイル自動削除（世代管理）
"""
import os
import json
import unittest
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import patch
import time

# テスト対象のインポート
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.backup import BackupManager  # noqa: E402


class TestBackupManagerPhase2(unittest.TestCase):
    """BackupManager Phase 2 機能のテスト"""

    def setUp(self):
        """テスト前の準備"""
        # 一時ディレクトリ作成
        self.temp_dir = tempfile.mkdtemp()
        self.backup_dir = os.path.join(self.temp_dir, "backups")
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.env_path = os.path.join(self.temp_dir, ".env")
        self.pdf_dir = os.path.join(self.temp_dir, "pdfs")
        self.logs_dir = os.path.join(self.temp_dir, "logs")
        self.instance_dir = os.path.join(self.temp_dir, "instance")

        # テスト用ファイル作成
        self._create_test_files()

        # BackupManager初期化
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
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_files(self):
        """テスト用ファイル作成"""
        # ディレクトリ作成
        os.makedirs(self.pdf_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.instance_dir, exist_ok=True)

        # .envファイル作成
        with open(self.env_path, "w") as f:
            f.write("SECRET_KEY=test_secret\n")
            f.write("DEBUG=True\n")

        # テスト用PDFファイル作成
        with open(os.path.join(self.pdf_dir, "test.pdf"), "w") as f:
            f.write("test pdf content")

        # ログファイル作成
        with open(os.path.join(self.logs_dir, "app.log"), "w") as f:
            f.write("test log content")

    def test_backup_settings_initialization(self):
        """バックアップ設定の初期化テスト"""
        # 設定ファイルが存在しない場合のデフォルト設定確認
        settings = self.backup_manager.get_backup_settings()

        expected_defaults = {
            "auto_backup_enabled": False,
            "backup_interval": "daily",  # 'daily' または 'weekly'
            "retention_days": 30,
            "backup_time": "02:00",  # 実行時刻
            "max_backup_size": 1024,  # MB
        }

        for key, expected_value in expected_defaults.items():
            self.assertEqual(settings[key], expected_value, f"デフォルト設定値が正しくありません: {key}")

    def test_update_backup_settings(self):
        """バックアップ設定の更新テスト"""
        new_settings = {
            "auto_backup_enabled": True,
            "backup_interval": "weekly",
            "retention_days": 14,
            "backup_time": "03:30",
            "max_backup_size": 2048,
        }

        # 設定更新
        result = self.backup_manager.update_backup_settings(new_settings)
        self.assertTrue(result, "設定更新が失敗しました")

        # 設定読み込み確認
        updated_settings = self.backup_manager.get_backup_settings()
        for key, expected_value in new_settings.items():
            self.assertEqual(
                updated_settings[key], expected_value, f"設定が正しく更新されていません: {key}"
            )

    def test_backup_settings_validation(self):
        """バックアップ設定の妥当性チェックテスト"""
        # 不正な設定値のテスト
        invalid_settings = [
            {"backup_interval": "invalid"},  # 不正な間隔
            {"retention_days": -1},  # 負の保持日数
            {"backup_time": "25:00"},  # 不正な時刻
            {"max_backup_size": -100},  # 負のサイズ
        ]

        for invalid_setting in invalid_settings:
            with self.assertRaises(
                ValueError, msg=f"不正な設定値が受け入れられました: {invalid_setting}"
            ):
                self.backup_manager.update_backup_settings(invalid_setting)

    def test_cleanup_old_backups_by_retention_days(self):
        """保持日数による古いバックアップの削除テスト"""
        # 古いバックアップファイルを作成
        old_backup_names = []
        recent_backup_names = []

        # 35日前のバックアップ（削除対象）
        old_date = datetime.now() - timedelta(days=35)
        old_backup_name = f"backup_{old_date.strftime('%Y%m%d_%H%M%S')}"
        self._create_fake_backup(old_backup_name, "manual", old_date)
        old_backup_names.append(old_backup_name)

        # 20日前のバックアップ（保持対象）
        recent_date = datetime.now() - timedelta(days=20)
        recent_backup_name = f"backup_{recent_date.strftime('%Y%m%d_%H%M%S')}"
        self._create_fake_backup(recent_backup_name, "manual", recent_date)
        recent_backup_names.append(recent_backup_name)

        # 設定更新（30日保持）
        settings = {"retention_days": 30}
        self.backup_manager.update_backup_settings(settings)

        # クリーンアップ実行
        deleted_count = self.backup_manager.cleanup_old_backups()

        # 結果確認
        self.assertEqual(deleted_count, 1, "古いバックアップが1つ削除されるべきです")

        # ファイル存在確認
        backups_after = self.backup_manager.list_backups()
        backup_names_after = [b["backup_name"] for b in backups_after]

        for old_name in old_backup_names:
            self.assertNotIn(
                old_name, backup_names_after, f"古いバックアップが削除されていません: {old_name}"
            )

        for recent_name in recent_backup_names:
            self.assertIn(
                recent_name, backup_names_after, f"最近のバックアップが誤って削除されました: {recent_name}"
            )

    def test_cleanup_old_backups_by_count(self):
        """バックアップ数制限による削除テスト"""
        # 5つのバックアップを作成
        backup_names = []
        for i in range(5):
            backup_date = datetime.now() - timedelta(days=i)
            backup_name = f"backup_{backup_date.strftime('%Y%m%d_%H%M%S')}"
            self._create_fake_backup(backup_name, "manual", backup_date)
            backup_names.append(backup_name)
            time.sleep(0.1)  # タイムスタンプの重複を避ける

        # 最大3つまで保持する設定
        deleted_count = self.backup_manager.cleanup_old_backups(max_backups=3)

        # 結果確認（2つ削除されるべき）
        self.assertEqual(deleted_count, 2, "2つの古いバックアップが削除されるべきです")

        # 残りのバックアップ確認
        backups_after = self.backup_manager.list_backups()
        self.assertEqual(len(backups_after), 3, "3つのバックアップが残るべきです")

    def test_auto_backup_scheduling(self):
        """自動バックアップスケジューリングテスト"""
        # 自動バックアップ有効化
        settings = {
            "auto_backup_enabled": True,
            "backup_interval": "daily",
            "backup_time": "02:00",
        }
        self.backup_manager.update_backup_settings(settings)

        # 次回実行時間の計算をテスト
        next_run = self.backup_manager.get_next_backup_time()
        self.assertIsInstance(next_run, datetime, "次回実行時間がdatetimeオブジェクトではありません")

        # 実行時間が設定時刻になっているか確認
        self.assertEqual(next_run.hour, 2, "実行時刻が設定値と異なります")
        self.assertEqual(next_run.minute, 0, "実行分が設定値と異なります")

    def test_should_run_backup_timing(self):
        """バックアップ実行タイミングの判定テスト"""
        # 自動バックアップ有効化
        settings = {
            "auto_backup_enabled": True,
            "backup_interval": "daily",
            "backup_time": "02:00",
        }
        self.backup_manager.update_backup_settings(settings)

        # 現在時刻が2:00の場合の実行判定をテスト
        with patch("database.backup.get_app_now") as mock_get_app_now:
            # 2:00:00の時刻を設定
            mock_now = datetime(2025, 1, 1, 2, 0, 0)
            mock_get_app_now.return_value = mock_now

            should_run = self.backup_manager.should_run_backup()
            self.assertTrue(should_run, "設定時刻にバックアップが実行されるべきです")

    def test_should_run_backup_interval_check(self):
        """バックアップ間隔チェックテスト"""
        # 昨日バックアップが実行されている場合
        yesterday = datetime.now() - timedelta(days=1)
        yesterday_backup_name = f"backup_{yesterday.strftime('%Y%m%d_%H%M%S')}"
        self._create_fake_backup(yesterday_backup_name, "auto", yesterday)

        settings = {
            "auto_backup_enabled": True,
            "backup_interval": "daily",
            "backup_time": "02:00",
        }
        self.backup_manager.update_backup_settings(settings)

        # 日次設定で昨日実行済みの場合は実行しない
        with patch("database.backup.get_app_now") as mock_get_app_now:
            mock_now = datetime.now().replace(hour=2, minute=0, second=0)
            mock_get_app_now.return_value = mock_now

            should_run = self.backup_manager.should_run_backup()
            self.assertFalse(should_run, "昨日実行済みの場合は実行されるべきではありません")

    def test_get_backup_statistics(self):
        """バックアップ統計情報取得テスト"""
        # 複数のバックアップを作成
        for i in range(3):
            backup_date = datetime.now() - timedelta(days=i)
            backup_name = f"backup_{backup_date.strftime('%Y%m%d_%H%M%S')}"
            backup_type = "auto" if i % 2 == 0 else "manual"
            self._create_fake_backup(backup_name, backup_type, backup_date)

        # 統計情報取得
        stats = self.backup_manager.get_backup_statistics()

        # 確認項目
        expected_keys = [
            "total_backups",
            "manual_backups",
            "auto_backups",
            "total_size",
            "latest_backup",
            "oldest_backup",
        ]

        for key in expected_keys:
            self.assertIn(key, stats, f"統計情報に{key}が含まれていません")

        self.assertEqual(stats["total_backups"], 3, "総バックアップ数が正しくありません")

    def _create_fake_backup(
        self, backup_name: str, backup_type: str, created_at: datetime
    ):
        """テスト用の偽バックアップファイル作成"""
        # メタデータ作成
        metadata = {
            "backup_name": backup_name,
            "type": backup_type,
            "timestamp": created_at.strftime("%Y%m%d_%H%M%S"),
            "created_at": created_at.isoformat(),
            "files_count": 5,
            "size": 1024,
            "checksum": "sha256:testchecksum",
            "version": "1.0",
            "application": "secure-pdf-viewer",
        }

        # メタデータファイル保存
        metadata_dir = os.path.join(self.backup_dir, "metadata")
        os.makedirs(metadata_dir, exist_ok=True)

        metadata_file = os.path.join(metadata_dir, f"{backup_name}.json")
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        # 実際のバックアップファイル作成
        backup_dir = os.path.join(self.backup_dir, backup_type)
        os.makedirs(backup_dir, exist_ok=True)

        backup_file = os.path.join(backup_dir, f"{backup_name}.tar.gz")
        with open(backup_file, "wb") as f:
            f.write(b"fake backup content")


if __name__ == "__main__":
    unittest.main()
