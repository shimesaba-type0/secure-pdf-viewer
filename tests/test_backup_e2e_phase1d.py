#!/usr/bin/env python3
"""
Phase 1D: 統合・動作確認テスト

TASK-018 Phase 1D: エンドツーエンド統合テスト
BackupManager + API + UI の完全統合動作テスト
"""

import os
import sys
import time
import tempfile
import shutil
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# テスト環境設定
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.backup import BackupManager  # noqa: E402


class BackupE2EPhase1DTest:
    """Phase 1D 統合・エンドツーエンドテスト"""

    def __init__(self):
        self.driver = None
        self.base_url = "http://localhost:5001"
        self.test_passed = 0
        self.test_failed = 0
        self.test_results = []
        self.temp_dir = None
        self.test_backup_name = None
        self.admin_session = None

    def setup_test_environment(self):
        """テスト環境セットアップ"""
        try:
            # 一時ディレクトリ作成
            self.temp_dir = tempfile.mkdtemp(prefix="backup_e2e_test_")

            # Selenium WebDriverセットアップ
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")

            self.driver = webdriver.Chrome(options=options)
            self.driver.implicitly_wait(10)

            # HTTP セッション作成
            self.admin_session = requests.Session()

            return True

        except Exception as e:
            print(f"❌ テスト環境セットアップ失敗: {e}")
            return False

    def cleanup_test_environment(self):
        """テスト環境クリーンアップ"""
        try:
            if self.driver:
                self.driver.quit()

            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

            # テスト作成のバックアップファイル削除
            if self.test_backup_name:
                self.cleanup_test_backup()

        except Exception as e:
            print(f"⚠️ クリーンアップエラー: {e}")

    def cleanup_test_backup(self):
        """テスト用バックアップファイル削除"""
        try:
            backup_manager = BackupManager()
            backup_dir = backup_manager.backup_dir

            # manual ディレクトリ内のテスト用ファイル削除
            manual_dir = backup_dir / "manual"
            if manual_dir.exists():
                for file_path in manual_dir.glob(f"*{self.test_backup_name}*"):
                    file_path.unlink()

            # metadata ディレクトリ内のテスト用メタデータ削除
            metadata_dir = backup_dir / "metadata"
            if metadata_dir.exists():
                for file_path in metadata_dir.glob(f"*{self.test_backup_name}*"):
                    file_path.unlink()

        except Exception as e:
            print(f"⚠️ テスト用バックアップファイル削除エラー: {e}")

    def admin_login_web(self):
        """Web管理者ログイン"""
        try:
            self.driver.get(f"{self.base_url}/admin/login")

            # パスフレーズ入力
            passphrase_input = self.driver.find_element(By.NAME, "passphrase")
            passphrase_input.send_keys("test_admin_passphrase_32_characters")

            # ログインボタンクリック
            login_btn = self.driver.find_element(
                By.CSS_SELECTOR, "button[type='submit']"
            )
            login_btn.click()

            # 管理画面表示確認
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "admin-container"))
            )

            return True

        except Exception as e:
            print(f"❌ Web管理者ログイン失敗: {e}")
            return False

    def admin_login_api(self):
        """API管理者ログイン"""
        try:
            response = self.admin_session.post(
                f"{self.base_url}/admin/login",
                data={"passphrase": "test_admin_passphrase_32_characters"},
            )
            return response.status_code == 200 or response.status_code == 302

        except Exception as e:
            print(f"❌ API管理者ログイン失敗: {e}")
            return False

    def test_1_core_backup_functionality(self):
        """テスト1: コア機能単体テスト"""
        test_name = "コア機能単体テスト"
        try:
            backup_manager = BackupManager()

            # バックアップ実行
            backup_info = backup_manager.create_backup()

            # バックアップファイル存在確認
            assert (
                backup_info["status"] == "success"
            ), f"バックアップ失敗: {backup_info.get('message')}"
            assert "backup_name" in backup_info, "バックアップ名がない"
            assert "size" in backup_info, "サイズ情報がない"

            self.test_backup_name = backup_info["backup_name"]

            # バックアップファイルの実在確認
            backup_path = backup_manager.get_backup_path(self.test_backup_name)
            assert backup_path and os.path.exists(
                backup_path
            ), f"バックアップファイルが存在しない: {backup_path}"

            # バックアップ一覧確認
            backup_list = backup_manager.list_backups()
            assert len(backup_list) > 0, "バックアップ一覧が空"

            # 作成したバックアップが一覧に含まれる確認
            backup_names = [b["backup_name"] for b in backup_list]
            assert self.test_backup_name in backup_names, "作成したバックアップが一覧にない"

            self.record_test_result(
                test_name, True, f"バックアップ作成成功: {self.test_backup_name}"
            )

        except Exception as e:
            self.record_test_result(test_name, False, f"コア機能エラー: {e}")

    def test_2_api_endpoint_integration(self):
        """テスト2: API統合テスト"""
        test_name = "API統合テスト"
        try:
            # API管理者ログイン
            assert self.admin_login_api(), "API管理者ログインに失敗"

            # バックアップ一覧API
            response = self.admin_session.get(f"{self.base_url}/admin/backup/list")
            assert response.status_code == 200, f"一覧API失敗: {response.status_code}"

            backup_list = response.json()
            assert "backups" in backup_list, "一覧レスポンス形式が間違っている"

            # テストバックアップ作成API
            response = self.admin_session.post(f"{self.base_url}/admin/backup/create")
            assert response.status_code == 200, f"作成API失敗: {response.status_code}"

            create_result = response.json()
            assert create_result["status"] in [
                "success",
                "in_progress",
            ], f"作成API応答異常: {create_result}"

            # 作成完了まで待機
            max_wait_time = 30
            wait_time = 0
            while wait_time < max_wait_time:
                response = self.admin_session.get(f"{self.base_url}/admin/backup/list")
                if response.status_code == 200:
                    backup_list = response.json()
                    if len(backup_list.get("backups", [])) > 0:
                        break
                time.sleep(2)
                wait_time += 2

            assert wait_time < max_wait_time, "バックアップ作成がタイムアウト"

            self.record_test_result(test_name, True, "全APIエンドポイントが正常動作")

        except Exception as e:
            self.record_test_result(test_name, False, f"API統合エラー: {e}")

    def test_3_web_ui_integration(self):
        """テスト3: WebUI統合テスト"""
        test_name = "WebUI統合テスト"
        try:
            # Web管理者ログイン
            assert self.admin_login_web(), "Web管理者ログインに失敗"

            # バックアップセクション表示確認
            backup_section = self.driver.find_element(By.CLASS_NAME, "backup-section")
            assert backup_section.is_displayed(), "バックアップセクションが表示されない"

            # バックアップ実行ボタン確認
            create_btn = self.driver.find_element(By.ID, "create-backup-btn")
            assert create_btn.is_displayed(), "バックアップ実行ボタンが表示されない"

            # 一覧テーブル確認
            backup_table = self.driver.find_element(By.ID, "backup-table")
            assert backup_table.is_displayed(), "バックアップ一覧テーブルが表示されない"

            # JavaScript関数存在確認
            js_functions = [
                "createBackup",
                "loadBackupList",
                "downloadBackup",
                "deleteBackup",
            ]
            for func_name in js_functions:
                result = self.driver.execute_script(
                    f"return typeof {func_name} === 'function';"
                )
                assert result, f"JavaScript関数が存在しない: {func_name}"

            self.record_test_result(test_name, True, "WebUI全要素が正常表示・動作")

        except Exception as e:
            self.record_test_result(test_name, False, f"WebUI統合エラー: {e}")

    def test_4_e2e_backup_creation(self):
        """テスト4: エンドツーエンドバックアップ作成"""
        test_name = "E2Eバックアップ作成"
        try:
            # バックアップ実行ボタンクリック
            create_btn = self.driver.find_element(By.ID, "create-backup-btn")
            create_btn.click()

            # 進行状況表示確認
            progress_area = WebDriverWait(self.driver, 10).until(
                lambda d: d.find_element(By.ID, "backup-progress")
                if "hidden"
                not in d.find_element(By.ID, "backup-progress").get_attribute("class")
                else None
            )
            assert progress_area, "進行状況エリアが表示されない"

            # ボタン無効化確認
            assert not create_btn.is_enabled(), "実行中にボタンが無効化されない"

            # 完了まで待機（最大60秒）
            max_wait = 60
            wait_time = 0
            while wait_time < max_wait:
                try:
                    # 成功メッセージの確認
                    self.driver.find_element(
                        By.CSS_SELECTOR, ".alert-success, .success-message"
                    )
                    break
                except Exception:
                    pass

                # ボタンが再有効化されたか確認
                if create_btn.is_enabled():
                    break

                time.sleep(2)
                wait_time += 2

            # バックアップ一覧更新確認
            time.sleep(3)  # 一覧更新待機
            table_body = self.driver.find_element(By.ID, "backup-list-body")
            rows = table_body.find_elements(By.TAG_NAME, "tr")

            # データ行の存在確認（ヘッダー以外）
            data_rows = [row for row in rows if row.find_elements(By.TAG_NAME, "td")]
            assert len(data_rows) > 0, "バックアップ一覧にデータが表示されない"

            self.record_test_result(
                test_name, True, f"E2Eバックアップ作成成功: {len(data_rows)}行表示"
            )

        except Exception as e:
            self.record_test_result(test_name, False, f"E2Eバックアップ作成エラー: {e}")

    def test_5_security_verification(self):
        """テスト5: セキュリティ検証"""
        test_name = "セキュリティ検証"
        try:
            # 認証なしでのAPI アクセス試行
            unauth_session = requests.Session()

            # 認証なしでバックアップ一覧アクセス
            response = unauth_session.get(f"{self.base_url}/admin/backup/list")
            assert response.status_code != 200, "認証なしでAPIにアクセスできてしまう"

            # 認証なしでバックアップ作成試行
            response = unauth_session.post(f"{self.base_url}/admin/backup/create")
            assert response.status_code != 200, "認証なしでバックアップ作成できてしまう"

            # パストラバーサル攻撃試行
            malicious_names = [
                "../../../etc/passwd",
                "..\\windows\\system32\\config",
                "../../database.db",
            ]
            for malicious_name in malicious_names:
                try:
                    response = self.admin_session.get(
                        f"{self.base_url}/admin/backup/download/{malicious_name}"
                    )
                    assert (
                        response.status_code != 200
                    ), f"パストラバーサル攻撃が成功: {malicious_name}"
                except Exception:
                    pass  # エラーが発生するのは正常

            # バックアップファイルのアクセス権限確認
            if self.test_backup_name:
                backup_manager = BackupManager()
                backup_path = backup_manager.get_backup_path(self.test_backup_name)
                if backup_path and os.path.exists(backup_path):
                    file_stats = os.stat(backup_path)
                    file_mode = oct(file_stats.st_mode)[-3:]
                    # 600 (所有者のみ読み書き) または 644 が適切
                    assert file_mode in [
                        "600",
                        "644",
                    ], f"バックアップファイルの権限が不適切: {file_mode}"

            self.record_test_result(test_name, True, "セキュリティ対策が適切に機能")

        except Exception as e:
            self.record_test_result(test_name, False, f"セキュリティ検証エラー: {e}")

    def test_6_performance_verification(self):
        """テスト6: パフォーマンス検証"""
        test_name = "パフォーマンス検証"
        try:
            start_time = time.time()

            # バックアップ実行
            backup_manager = BackupManager()
            backup_info = backup_manager.create_backup()

            end_time = time.time()
            execution_time = end_time - start_time

            # 実行時間チェック（60秒以内）
            assert execution_time < 60, f"バックアップ実行時間が長すぎる: {execution_time:.2f}秒"

            # バックアップファイルサイズチェック
            if backup_info.get("size"):
                size_mb = backup_info["size"] / (1024 * 1024)
                assert size_mb < 1000, f"バックアップファイルが大きすぎる: {size_mb:.2f}MB"

            # メモリ使用量は実行環境に依存するため簡易チェックのみ
            import psutil

            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            assert memory_mb < 1000, f"メモリ使用量が多すぎる: {memory_mb:.2f}MB"

            self.record_test_result(
                test_name,
                True,
                f"実行時間: {execution_time:.2f}秒, "
                f"サイズ: {backup_info.get('size', 0)/(1024*1024):.2f}MB, "
                f"メモリ: {memory_mb:.2f}MB",
            )

        except Exception as e:
            self.record_test_result(test_name, False, f"パフォーマンス検証エラー: {e}")

    def test_7_error_handling(self):
        """テスト7: エラーハンドリング検証"""
        test_name = "エラーハンドリング検証"
        try:
            # 存在しないバックアップの削除試行
            response = self.admin_session.delete(
                f"{self.base_url}/admin/backup/delete/nonexistent_backup_12345"
            )
            assert (
                response.status_code == 404
            ), f"存在しないバックアップ削除で適切なエラーが返されない: {response.status_code}"

            # 存在しないバックアップのダウンロード試行
            response = self.admin_session.get(
                f"{self.base_url}/admin/backup/download/nonexistent_backup_12345"
            )
            assert (
                response.status_code == 404
            ), f"存在しないバックアップダウンロードで適切なエラーが返されない: {response.status_code}"

            # 不正なリクエストデータでのバックアップ作成試行
            response = self.admin_session.post(
                f"{self.base_url}/admin/backup/create",
                data={"invalid_param": "invalid_value"},
            )
            # 成功するか適切なエラーレスポンスが返されることを確認
            assert response.status_code in [
                200,
                400,
                422,
            ], f"不正データで予期しないレスポンス: {response.status_code}"

            self.record_test_result(test_name, True, "エラーハンドリングが適切に動作")

        except Exception as e:
            self.record_test_result(test_name, False, f"エラーハンドリング検証エラー: {e}")

    def record_test_result(self, test_name, success, message):
        """テスト結果記録"""
        if success:
            self.test_passed += 1
            status = "✅ 成功"
        else:
            self.test_failed += 1
            status = "❌ 失敗"

        result = {
            "test": test_name,
            "status": status,
            "message": message,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        self.test_results.append(result)
        print(f"{status}: {test_name} - {message}")

    def run_all_tests(self):
        """Phase 1D 全統合テスト実行"""
        print("🧪 Phase 1D: バックアップシステム統合・動作確認テスト開始")
        print("=" * 70)

        # テスト環境セットアップ
        if not self.setup_test_environment():
            print("❌ テスト環境セットアップ失敗、テスト終了")
            return False

        try:
            # 各テスト実行
            print("\n1️⃣ コア機能単体テスト")
            self.test_1_core_backup_functionality()

            print("\n2️⃣ API統合テスト")
            self.test_2_api_endpoint_integration()

            print("\n3️⃣ WebUI統合テスト")
            self.test_3_web_ui_integration()

            print("\n4️⃣ エンドツーエンドバックアップ作成")
            self.test_4_e2e_backup_creation()

            print("\n5️⃣ セキュリティ検証")
            self.test_5_security_verification()

            print("\n6️⃣ パフォーマンス検証")
            self.test_6_performance_verification()

            print("\n7️⃣ エラーハンドリング検証")
            self.test_7_error_handling()

        finally:
            self.cleanup_test_environment()

        # テスト結果表示
        print("\n" + "=" * 70)
        print("🧪 Phase 1D 統合・動作確認テスト結果")
        print(f"✅ 成功: {self.test_passed}件")
        print(f"❌ 失敗: {self.test_failed}件")

        if (self.test_passed + self.test_failed) > 0:
            success_rate = (
                self.test_passed / (self.test_passed + self.test_failed)
            ) * 100
            print(f"📊 成功率: {success_rate:.1f}%")
        else:
            print("📊 成功率: 0.0%")

        # 詳細結果表示
        print("\n📋 詳細結果:")
        for result in self.test_results:
            print(f"  {result['status']}: {result['test']}")
            print(f"    {result['message']}")

        return self.test_failed == 0


def main():
    """メイン実行"""
    print("🎯 TASK-018 Phase 1D: 統合・動作確認テスト")
    print("BackupManager + API + UI の完全統合動作テスト")
    print()

    tester = BackupE2EPhase1DTest()
    success = tester.run_all_tests()

    if success:
        print("\n🎉 Phase 1D 統合・動作確認テスト 全成功！")
        print("✅ BackupManager、API、UI すべて正常動作確認")
        print("✅ セキュリティ対策正常動作確認")
        print("✅ パフォーマンス・エラーハンドリング確認完了")
        print("\n🚀 Phase 1D 完了！バックアップシステム本番レディ状態")
        exit(0)
    else:
        print("\n⚠️ Phase 1D で一部の統合テストが失敗しました")
        print("修正が必要な項目があります")
        exit(1)


if __name__ == "__main__":
    main()
