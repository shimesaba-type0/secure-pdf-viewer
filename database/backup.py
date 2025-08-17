"""
アプリケーション内バックアップ・復旧システム
BackupManagerクラス - コア機能実装
"""
import os
import sqlite3
import tarfile
import json
import hashlib
import shutil
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import tempfile
import logging
from config.timezone import get_app_now, to_app_timezone, create_app_datetime

logger = logging.getLogger(__name__)


class BackupManager:
    """
    システム全体のバックアップ・復旧を管理するクラス
    """

    def __init__(
        self,
        db_path: str = None,
        backup_dir: str = None,
        env_path: str = None,
        pdf_dir: str = None,
        logs_dir: str = None,
        instance_dir: str = None,
    ):
        """
        BackupManagerの初期化

        Args:
            db_path: SQLiteデータベースのパス
            backup_dir: バックアップ保存ディレクトリ
            env_path: .envファイルのパス
            pdf_dir: PDFファイルディレクトリ
            logs_dir: ログディレクトリ
            instance_dir: instanceディレクトリ
        """
        # デフォルトパス設定
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.db_path = db_path or os.path.join(current_dir, "instance", "database.db")
        self.backup_dir = backup_dir or os.path.join(current_dir, "backups")
        self.env_path = env_path or os.path.join(current_dir, ".env")
        self.pdf_dir = pdf_dir or os.path.join(current_dir, "static", "pdfs")
        self.logs_dir = logs_dir or os.path.join(current_dir, "logs")
        self.instance_dir = instance_dir or os.path.join(current_dir, "instance")

        # バックアップディレクトリ構造作成
        self._ensure_backup_directories()

        # 機密情報キーワード
        self.sensitive_keys = [
            "SECRET_KEY",
            "PASSWORD",
            "API_KEY",
            "TOKEN",
            "PRIVATE",
            "ACCESS_KEY",
            "SECRET",
            "CREDENTIAL",
            "AUTH",
            "KEY",
        ]

        # Phase 2: バックアップ設定ファイルパス (config/ ディレクトリに統合)
        self.settings_file = os.path.join(current_dir, "config", "backup_settings.json")

    def _ensure_backup_directories(self):
        """バックアップディレクトリ構造を作成"""
        directories = [
            self.backup_dir,
            os.path.join(self.backup_dir, "manual"),
            os.path.join(self.backup_dir, "auto"),
            os.path.join(self.backup_dir, "metadata"),
        ]

        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            # セキュアな権限設定（所有者のみアクセス可能）
            os.chmod(directory, 0o700)

    def create_backup(self, backup_type: str = "manual") -> str:
        """
        システム全体のバックアップを作成

        Args:
            backup_type: バックアップタイプ ('manual' または 'auto')

        Returns:
            str: 作成されたバックアップ名
        """
        try:
            # バックアップ名生成
            timestamp = get_app_now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}"

            logger.info(f"バックアップ開始: {backup_name}")

            # 一時作業ディレクトリ作成
            with tempfile.TemporaryDirectory() as temp_dir:
                backup_data_dir = os.path.join(temp_dir, backup_name)
                os.makedirs(backup_data_dir)

                # 各コンポーネントのバックアップ実行
                database_files = self._backup_database(backup_data_dir)
                config_files = self._backup_config_files(backup_data_dir)
                pdf_files = self._backup_pdf_files(backup_data_dir)
                log_files = self._backup_log_files(backup_data_dir)

                # メタデータ作成
                metadata = self._create_metadata(
                    backup_name,
                    backup_type,
                    timestamp,
                    database_files + config_files + pdf_files + log_files,
                )

                # メタデータファイル保存
                metadata_content = os.path.join(backup_data_dir, "metadata.json")
                with open(metadata_content, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)

                # アーカイブ作成
                archive_path = self._create_archive(
                    backup_data_dir, backup_name, backup_type
                )

                # チェックサム計算
                checksum = self._calculate_checksum(archive_path)
                metadata["checksum"] = checksum
                metadata["size"] = os.path.getsize(archive_path)

                # メタデータファイル保存（最終版）
                metadata_file = os.path.join(
                    self.backup_dir, "metadata", f"{backup_name}.json"
                )
                with open(metadata_file, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)

                logger.info(f"バックアップ完了: {backup_name}, サイズ: {metadata['size']} bytes")
                return backup_name

        except Exception as e:
            logger.error(f"バックアップ作成中にエラーが発生: {str(e)}")
            raise

    def _backup_database(self, backup_dir: str) -> List[str]:
        """
        SQLiteデータベースの安全バックアップ

        Args:
            backup_dir: バックアップ先ディレクトリ

        Returns:
            List[str]: バックアップされたファイルのリスト
        """
        database_dir = os.path.join(backup_dir, "database")
        os.makedirs(database_dir, exist_ok=True)

        files = []

        if os.path.exists(self.db_path):
            # SQLite安全バックアップ実行
            backup_db_path = os.path.join(database_dir, "database.db")

            # SQLite .backup コマンドを使用した安全なバックアップ
            source_conn = sqlite3.connect(self.db_path, timeout=30.0)
            source_conn.execute("PRAGMA journal_mode=WAL")  # WALモード有効化
            backup_conn = sqlite3.connect(backup_db_path, timeout=30.0)

            try:
                source_conn.backup(backup_conn)
                files.append(backup_db_path)
                logger.info(f"データベースバックアップ完了: {backup_db_path}")

                # スキーマ情報もエクスポート
                schema_path = os.path.join(database_dir, "database_schema.sql")
                with open(schema_path, "w") as f:
                    for line in source_conn.iterdump():
                        if line.startswith("CREATE"):
                            f.write(f"{line}\n")
                files.append(schema_path)

            except Exception as e:
                logger.error(f"データベースバックアップエラー: {str(e)}")
                raise
            finally:
                source_conn.close()
                backup_conn.close()

        return files

    def _backup_config_files(self, backup_dir: str) -> List[str]:
        """
        設定ファイルのバックアップ（機密情報マスク処理）

        Args:
            backup_dir: バックアップ先ディレクトリ

        Returns:
            List[str]: バックアップされたファイルのリスト
        """
        config_dir = os.path.join(backup_dir, "config")
        os.makedirs(config_dir, exist_ok=True)

        files = []

        if os.path.exists(self.env_path):
            backup_env_path = os.path.join(config_dir, ".env")

            # .envファイルの機密情報マスク処理
            with open(self.env_path, "r", encoding="utf-8") as source:
                with open(backup_env_path, "w", encoding="utf-8") as backup:
                    for line in source:
                        masked_line = self._mask_sensitive_info(line)
                        backup.write(masked_line)

            files.append(backup_env_path)
            logger.info(f"設定ファイルバックアップ完了（マスク処理済み): {backup_env_path}")

        return files

    def _mask_sensitive_info(self, line: str) -> str:
        """
        設定ファイル行の機密情報をマスク

        Args:
            line: 設定ファイルの行

        Returns:
            str: マスク処理された行
        """
        # コメント行や空行はそのまま
        if line.strip().startswith("#") or "=" not in line:
            return line

        # キー=値の形式を解析
        key, value = line.split("=", 1)
        key = key.strip()

        # 機密情報のキーワードチェック
        for sensitive_key in self.sensitive_keys:
            if sensitive_key.upper() in key.upper():
                return f"{key}=***MASKED***\n"

        return line

    def _backup_pdf_files(self, backup_dir: str) -> List[str]:
        """
        PDFファイルのバックアップ

        Args:
            backup_dir: バックアップ先ディレクトリ

        Returns:
            List[str]: バックアップされたファイルのリスト
        """
        files_dir = os.path.join(backup_dir, "files")
        os.makedirs(files_dir, exist_ok=True)

        files = []

        if os.path.exists(self.pdf_dir):
            backup_pdf_dir = os.path.join(files_dir, "pdfs")

            # PDFディレクトリ全体をコピー
            shutil.copytree(self.pdf_dir, backup_pdf_dir)

            # バックアップされたファイルのリストを作成
            for root, dirs, file_list in os.walk(backup_pdf_dir):
                for file in file_list:
                    file_path = os.path.join(root, file)
                    files.append(file_path)

            logger.info(f"PDFファイルバックアップ完了: {len(files)} ファイル")

        return files

    def _backup_log_files(self, backup_dir: str) -> List[str]:
        """
        重要ログファイルのバックアップ

        Args:
            backup_dir: バックアップ先ディレクトリ

        Returns:
            List[str]: バックアップされたファイルのリスト
        """
        logs_backup_dir = os.path.join(backup_dir, "logs")
        os.makedirs(logs_backup_dir, exist_ok=True)

        files = []

        # app.logのバックアップ
        app_log_path = os.path.join(self.logs_dir, "app.log")
        if os.path.exists(app_log_path):
            backup_app_log = os.path.join(logs_backup_dir, "app.log")
            shutil.copy2(app_log_path, backup_app_log)
            files.append(backup_app_log)

        # emergency_log.txtのバックアップ
        emergency_log_path = os.path.join(self.instance_dir, "emergency_log.txt")
        if os.path.exists(emergency_log_path):
            backup_emergency_log = os.path.join(logs_backup_dir, "emergency_log.txt")
            shutil.copy2(emergency_log_path, backup_emergency_log)
            files.append(backup_emergency_log)

        logger.info(f"ログファイルバックアップ完了: {len(files)} ファイル")
        return files

    def _create_metadata(
        self, backup_name: str, backup_type: str, timestamp: str, files: List[str]
    ) -> Dict:
        """
        バックアップメタデータの作成

        Args:
            backup_name: バックアップ名
            backup_type: バックアップタイプ
            timestamp: タイムスタンプ
            files: バックアップされたファイルのリスト

        Returns:
            Dict: メタデータ辞書
        """
        return {
            "backup_name": backup_name,
            "type": backup_type,
            "timestamp": timestamp,
            "created_at": get_app_now().isoformat(),
            "files_count": len(files),
            "files": files,
            "version": "1.0",
            "application": "secure-pdf-viewer",
        }

    def _create_archive(
        self, source_dir: str, backup_name: str, backup_type: str = "manual"
    ) -> str:
        """
        tar.gz アーカイブの作成

        Args:
            source_dir: アーカイブ対象ディレクトリ
            backup_name: バックアップ名
            backup_type: バックアップタイプ

        Returns:
            str: 作成されたアーカイブファイルのパス
        """
        archive_dir = os.path.join(self.backup_dir, backup_type)
        os.makedirs(archive_dir, exist_ok=True)

        archive_path = os.path.join(archive_dir, f"{backup_name}.tar.gz")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(source_dir, arcname=backup_name)

        # セキュアな権限設定
        os.chmod(archive_path, 0o600)

        logger.info(f"アーカイブ作成完了: {archive_path}")
        return archive_path

    def _calculate_checksum(self, file_path: str) -> str:
        """
        ファイルのSHA256チェックサムを計算

        Args:
            file_path: チェックサム計算対象ファイル

        Returns:
            str: SHA256チェックサム
        """
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)

        return f"sha256:{sha256_hash.hexdigest()}"

    def list_backups(self) -> List[Dict]:
        """
        バックアップファイル一覧の取得

        Returns:
            List[Dict]: バックアップ情報のリスト
        """
        backups = []
        metadata_dir = os.path.join(self.backup_dir, "metadata")

        if not os.path.exists(metadata_dir):
            return backups

        for filename in os.listdir(metadata_dir):
            if filename.endswith(".json"):
                metadata_path = os.path.join(metadata_dir, filename)
                try:
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)

                    # バックアップファイルの存在確認
                    backup_name = metadata["backup_name"]
                    backup_file = os.path.join(
                        self.backup_dir, metadata["type"], f"{backup_name}.tar.gz"
                    )

                    if os.path.exists(backup_file):
                        backups.append(metadata)

                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"メタデータファイル読み込みエラー {filename}: {str(e)}")
                    continue

        # 作成日時でソート（新しい順）
        backups.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return backups

    def delete_backup(self, backup_name: str) -> bool:
        """
        バックアップファイルの削除

        Args:
            backup_name: 削除するバックアップ名

        Returns:
            bool: 削除成功の可否
        """
        try:
            # Path Traversal対策
            if not self._is_safe_backup_name(backup_name):
                raise ValueError(f"不正なバックアップ名: {backup_name}")

            # メタデータ読み込み
            metadata_file = os.path.join(
                self.backup_dir, "metadata", f"{backup_name}.json"
            )
            if not os.path.exists(metadata_file):
                logger.warning(f"メタデータファイルが見つかりません: {backup_name}")
                return False

            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            backup_type = metadata.get("type", "manual")

            # バックアップファイル削除
            backup_file = os.path.join(
                self.backup_dir, backup_type, f"{backup_name}.tar.gz"
            )
            if os.path.exists(backup_file):
                os.remove(backup_file)
                logger.info(f"バックアップファイル削除: {backup_file}")

            # メタデータファイル削除
            os.remove(metadata_file)
            logger.info(f"メタデータファイル削除: {metadata_file}")

            return True

        except Exception as e:
            logger.error(f"バックアップ削除エラー {backup_name}: {str(e)}")
            return False

    def get_backup_path(self, backup_name: str) -> Optional[str]:
        """
        バックアップファイルのパスを取得（ダウンロード用）

        Args:
            backup_name: バックアップ名

        Returns:
            Optional[str]: バックアップファイルのパス（存在しない場合はNone）
        """
        # Path Traversal対策
        if not self._is_safe_backup_name(backup_name):
            raise ValueError(f"不正なバックアップ名: {backup_name}")

        # メタデータからバックアップタイプを取得
        metadata_file = os.path.join(self.backup_dir, "metadata", f"{backup_name}.json")
        if not os.path.exists(metadata_file):
            return None

        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            backup_type = metadata.get("type", "manual")
            backup_file = os.path.join(
                self.backup_dir, backup_type, f"{backup_name}.tar.gz"
            )

            if os.path.exists(backup_file):
                return backup_file

        except (json.JSONDecodeError, KeyError):
            logger.warning(f"メタデータファイル読み込みエラー: {backup_name}")

        return None

    def _is_safe_backup_name(self, backup_name: str) -> bool:
        """
        バックアップ名の安全性チェック（Path Traversal対策）

        Args:
            backup_name: チェック対象のバックアップ名

        Returns:
            bool: 安全性の可否
        """
        # 危険な文字列パターンをチェック
        dangerous_patterns = ["..", "/", "\\", ":", "*", "?", '"', "<", ">", "|"]

        for pattern in dangerous_patterns:
            if pattern in backup_name:
                return False

        # 正規表現での形式チェック（backup_YYYYMMDD_HHMMSS形式）
        if not re.match(r"^backup_\d{8}_\d{6}$", backup_name):
            return False

        return True

    # ===== Phase 2: 定期バックアップ・世代管理機能 =====

    def get_backup_settings(self) -> Dict:
        """
        バックアップ設定を取得

        Returns:
            Dict: バックアップ設定
        """
        default_settings = {
            "auto_backup_enabled": False,
            "backup_interval": "daily",  # 'daily' または 'weekly'
            "retention_days": 30,
            "backup_time": "02:00",  # HH:MM形式
            "max_backup_size": 1024,  # MB
        }

        if not os.path.exists(self.settings_file):
            return default_settings

        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
                # デフォルト値で不足分を補完
                for key, default_value in default_settings.items():
                    if key not in settings:
                        settings[key] = default_value
                return settings
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"設定ファイル読み込みエラー: {str(e)}")
            return default_settings

    def update_backup_settings(self, new_settings: Dict) -> bool:
        """
        バックアップ設定を更新

        Args:
            new_settings: 更新する設定項目

        Returns:
            bool: 更新成功の可否
        """
        try:
            # 現在の設定取得
            current_settings = self.get_backup_settings()

            # 設定値の妥当性チェック
            for key, value in new_settings.items():
                if key == "backup_interval" and value not in ["daily", "weekly"]:
                    raise ValueError(f"不正なバックアップ間隔: {value}")
                elif key == "retention_days" and (
                    not isinstance(value, int) or value < 1
                ):
                    raise ValueError(f"不正な保持日数: {value}")
                elif key == "backup_time":
                    # HH:MM形式チェック
                    try:
                        hour, minute = value.split(":")
                        if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                            raise ValueError
                    except (ValueError, IndexError):
                        raise ValueError(f"不正な実行時刻形式: {value}")
                elif key == "max_backup_size" and (
                    not isinstance(value, int) or value < 1
                ):
                    raise ValueError(f"不正な最大バックアップサイズ: {value}")

            # 設定更新
            current_settings.update(new_settings)

            # ファイル保存
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(current_settings, f, indent=2, ensure_ascii=False)

            logger.info(f"バックアップ設定更新完了: {new_settings}")
            return True

        except Exception as e:
            logger.error(f"設定更新エラー: {str(e)}")
            raise

    def cleanup_old_backups(self, max_backups: Optional[int] = None) -> int:
        """
        古いバックアップファイルの削除（世代管理）

        Args:
            max_backups: 最大保持バックアップ数（Noneの場合は保持日数で判定）

        Returns:
            int: 削除されたバックアップ数
        """
        try:
            settings = self.get_backup_settings()
            backups = self.list_backups()

            if not backups:
                return 0

            deleted_count = 0

            if max_backups is not None:
                # バックアップ数制限による削除
                if len(backups) > max_backups:
                    # 古い順にソート（created_atで昇順）
                    backups_sorted = sorted(
                        backups, key=lambda x: x.get("created_at", "")
                    )
                    backups_to_delete = backups_sorted[:-max_backups]

                    for backup in backups_to_delete:
                        if self.delete_backup(backup["backup_name"]):
                            deleted_count += 1
            else:
                # 保持日数による削除
                retention_days = settings["retention_days"]
                cutoff_date = get_app_now() - timedelta(days=retention_days)

                for backup in backups:
                    try:
                        created_at = datetime.fromisoformat(backup["created_at"])
                        created_at = to_app_timezone(created_at)
                        if created_at < cutoff_date:
                            if self.delete_backup(backup["backup_name"]):
                                deleted_count += 1
                    except (ValueError, KeyError):
                        logger.warning(
                            f"バックアップ日時解析エラー: {backup.get('backup_name', 'unknown')}"
                        )
                        continue

            if deleted_count > 0:
                logger.info(f"古いバックアップ削除完了: {deleted_count}個")

            return deleted_count

        except Exception as e:
            logger.error(f"バックアップクリーンアップエラー: {str(e)}")
            return 0

    def get_next_backup_time(self) -> Optional[datetime]:
        """
        次回自動バックアップ実行時刻を計算

        Returns:
            Optional[datetime]: 次回実行時刻（自動バックアップ無効の場合はNone）
        """
        settings = self.get_backup_settings()

        if not settings["auto_backup_enabled"]:
            return None

        try:
            # 設定時刻を解析
            backup_time = settings["backup_time"]
            hour, minute = map(int, backup_time.split(":"))

            # 今日の実行時刻を計算
            now = get_app_now()
            today_run_time = now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )

            # 今日の実行時刻を過ぎている場合は明日を設定
            if now >= today_run_time:
                if settings["backup_interval"] == "daily":
                    next_run = today_run_time + timedelta(days=1)
                elif settings["backup_interval"] == "weekly":
                    next_run = today_run_time + timedelta(days=7)
                else:
                    next_run = today_run_time + timedelta(days=1)
            else:
                next_run = today_run_time

            return next_run

        except (ValueError, KeyError) as e:
            logger.error(f"次回実行時刻計算エラー: {str(e)}")
            return None

    def should_run_backup(self) -> bool:
        """
        自動バックアップを実行すべきかどうかを判定

        Returns:
            bool: 実行すべきかどうか
        """
        settings = self.get_backup_settings()

        # 自動バックアップが無効の場合
        if not settings["auto_backup_enabled"]:
            return False

        try:
            now = get_app_now()

            # 設定時刻を解析
            backup_time = settings["backup_time"]
            hour, minute = map(int, backup_time.split(":"))

            # 今日の実行時刻を計算
            today_run_time = now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )

            # 実行時刻の近似チェック（5分以内）
            time_diff = abs((now - today_run_time).total_seconds())
            if time_diff > 300:  # 5分 = 300秒
                return False

            # 最後の自動バックアップとの間隔チェック
            backups = self.list_backups()
            auto_backups = [b for b in backups if b.get("type") == "auto"]

            if auto_backups:
                latest_auto_backup = max(
                    auto_backups, key=lambda x: x.get("created_at", "")
                )
                latest_time = datetime.fromisoformat(latest_auto_backup["created_at"])
                latest_time = to_app_timezone(latest_time)

                if settings["backup_interval"] == "daily":
                    min_interval = timedelta(days=1)
                elif settings["backup_interval"] == "weekly":
                    min_interval = timedelta(days=7)
                else:
                    min_interval = timedelta(days=1)

                # 最小間隔をチェック（23時間45分で日次バックアップを許可）
                actual_interval = now - latest_time
                if actual_interval < (min_interval - timedelta(minutes=15)):
                    return False

            return True

        except Exception as e:
            logger.error(f"バックアップ実行判定エラー: {str(e)}")
            return False

    def get_backup_statistics(self) -> Dict:
        """
        バックアップ統計情報を取得

        Returns:
            Dict: 統計情報
        """
        try:
            backups = self.list_backups()

            if not backups:
                return {
                    "total_backups": 0,
                    "manual_backups": 0,
                    "auto_backups": 0,
                    "total_size": 0,
                    "latest_backup": None,
                    "oldest_backup": None,
                }

            manual_backups = [b for b in backups if b.get("type") == "manual"]
            auto_backups = [b for b in backups if b.get("type") == "auto"]
            total_size = sum(b.get("size", 0) for b in backups)

            # 最新・最古のバックアップ
            latest_backup = max(backups, key=lambda x: x.get("created_at", ""))
            oldest_backup = min(backups, key=lambda x: x.get("created_at", ""))

            return {
                "total_backups": len(backups),
                "manual_backups": len(manual_backups),
                "auto_backups": len(auto_backups),
                "total_size": total_size,
                "latest_backup": latest_backup,
                "oldest_backup": oldest_backup,
            }

        except Exception as e:
            logger.error(f"統計情報取得エラー: {str(e)}")
            return {
                "total_backups": 0,
                "manual_backups": 0,
                "auto_backups": 0,
                "total_size": 0,
                "latest_backup": None,
                "oldest_backup": None,
            }
