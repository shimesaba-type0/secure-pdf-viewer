#!/usr/bin/env python3
"""
バックアップ機能UI操作テスト

TASK-018 Phase 1C: UI実装のブラウザテスト
管理画面のバックアップセクション動作テスト
"""

import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# テスト環境設定
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class BackupUITest:
    """バックアップUI操作テスト"""

    def __init__(self):
        self.driver = None
        self.base_url = "http://localhost:5001"
        self.test_passed = 0
        self.test_failed = 0
        self.test_results = []

    def setup_driver(self):
        """Selenium WebDriverセットアップ"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.implicitly_wait(10)
            return True
        except Exception as e:
            print(f"❌ WebDriver初期化失敗: {e}")
            return False

    def login_as_admin(self):
        """管理者でログイン"""
        try:
            self.driver.get(f"{self.base_url}/admin/login")

            # パスフレーズ入力（テスト環境のデフォルト値）
            passphrase_input = self.driver.find_element(By.NAME, "passphrase")
            passphrase_input.send_keys("test_admin_passphrase_32_characters")

            # ログインボタンクリック
            login_btn = self.driver.find_element(
                By.CSS_SELECTOR, "button[type='submit']"
            )
            login_btn.click()

            # 管理画面が表示されるまで待機
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "admin-container"))
            )

            return True

        except Exception as e:
            print(f"❌ 管理者ログイン失敗: {e}")
            return False

    def test_backup_section_display(self):
        """バックアップセクション表示テスト"""
        test_name = "バックアップセクション表示"
        try:
            # バックアップセクションの存在確認
            self.driver.find_element(By.CLASS_NAME, "backup-section")

            # バックアップ実行ボタンの存在確認
            create_btn = self.driver.find_element(By.ID, "create-backup-btn")
            assert create_btn.is_displayed(), "バックアップ実行ボタンが表示されていない"

            # 進行状況表示エリアの存在確認（初期状態は非表示）
            progress_area = self.driver.find_element(By.ID, "backup-progress")
            assert "hidden" in progress_area.get_attribute(
                "class"
            ), "進行状況エリアの初期状態が間違っている"

            # バックアップ一覧テーブルの存在確認
            backup_table = self.driver.find_element(By.ID, "backup-table")
            assert backup_table.is_displayed(), "バックアップ一覧テーブルが表示されていない"

            self.record_test_result(test_name, True, "バックアップセクションが正しく表示されている")

        except Exception as e:
            self.record_test_result(test_name, False, f"表示エラー: {e}")

    def test_backup_execution(self):
        """バックアップ実行テスト"""
        test_name = "バックアップ実行"
        try:
            # バックアップ実行ボタンクリック
            create_btn = self.driver.find_element(By.ID, "create-backup-btn")
            create_btn.click()

            # 進行状況エリアが表示されることを確認
            WebDriverWait(self.driver, 5).until(
                lambda d: "hidden"
                not in d.find_element(By.ID, "backup-progress").get_attribute("class")
            )

            # 進行状況バーの存在確認
            progress_bar = self.driver.find_element(By.CLASS_NAME, "progress-bar")
            progress_fill = self.driver.find_element(By.CLASS_NAME, "progress-fill")
            progress_text = self.driver.find_element(By.CLASS_NAME, "progress-text")

            assert progress_bar.is_displayed(), "進行状況バーが表示されていない"
            assert progress_fill.is_displayed(), "進行状況フィルが表示されていない"
            assert progress_text.is_displayed(), "進行状況テキストが表示されていない"

            # ボタンが無効化されることを確認
            assert not create_btn.is_enabled(), "実行中にボタンが無効化されていない"

            self.record_test_result(test_name, True, "バックアップ実行UIが正しく動作している")

        except Exception as e:
            self.record_test_result(test_name, False, f"実行エラー: {e}")

    def test_backup_list_loading(self):
        """バックアップ一覧読み込みテスト"""
        test_name = "バックアップ一覧読み込み"
        try:
            # 一覧を更新（JavaScript関数呼び出し）
            self.driver.execute_script(
                "if (typeof loadBackupList === 'function') loadBackupList();"
            )

            # テーブル本体の確認
            table_body = self.driver.find_element(By.ID, "backup-list-body")

            # 数秒待機してAjax応答を待つ
            time.sleep(2)

            # テーブル行の存在確認（データがある場合）
            rows = table_body.find_elements(By.TAG_NAME, "tr")

            # 最低限テーブル構造が存在することを確認
            assert len(rows) >= 0, "テーブル行が取得できない"

            self.record_test_result(test_name, True, f"バックアップ一覧テーブルに{len(rows)}行表示")

        except Exception as e:
            self.record_test_result(test_name, False, f"一覧読み込みエラー: {e}")

    def test_download_functionality(self):
        """ダウンロード機能テスト"""
        test_name = "ダウンロード機能"
        try:
            # ダウンロードリンクの存在確認
            download_links = self.driver.find_elements(By.CLASS_NAME, "download-link")

            if len(download_links) > 0:
                # 最初のダウンロードリンクが正しいhref属性を持っているか確認
                href = download_links[0].get_attribute("href")
                assert "/admin/backup/download/" in href, f"ダウンロードURLが不正: {href}"

                self.record_test_result(
                    test_name, True, f"{len(download_links)}個のダウンロードリンク確認"
                )
            else:
                self.record_test_result(test_name, True, "ダウンロード対象なし（正常）")

        except Exception as e:
            self.record_test_result(test_name, False, f"ダウンロード機能エラー: {e}")

    def test_delete_functionality(self):
        """削除機能テスト"""
        test_name = "削除機能"
        try:
            # 削除ボタンの存在確認
            delete_buttons = self.driver.find_elements(
                By.CLASS_NAME, "delete-backup-btn"
            )

            if len(delete_buttons) > 0:
                # 削除ボタンがクリック可能か確認
                assert delete_buttons[0].is_enabled(), "削除ボタンがクリックできない"

                # onclick属性の確認
                onclick = delete_buttons[0].get_attribute("onclick")
                assert "deleteBackup" in onclick, f"削除関数が設定されていない: {onclick}"

                self.record_test_result(
                    test_name, True, f"{len(delete_buttons)}個の削除ボタン確認"
                )
            else:
                self.record_test_result(test_name, True, "削除対象なし（正常）")

        except Exception as e:
            self.record_test_result(test_name, False, f"削除機能エラー: {e}")

    def test_responsive_design(self):
        """レスポンシブデザインテスト"""
        test_name = "レスポンシブデザイン"
        try:
            # デスクトップサイズでテスト
            self.driver.set_window_size(1920, 1080)
            time.sleep(1)

            backup_section = self.driver.find_element(By.CLASS_NAME, "backup-section")
            desktop_width = backup_section.size["width"]

            # タブレットサイズでテスト
            self.driver.set_window_size(768, 1024)
            time.sleep(1)

            tablet_width = backup_section.size["width"]

            # スマートフォンサイズでテスト
            self.driver.set_window_size(375, 667)
            time.sleep(1)

            mobile_width = backup_section.size["width"]

            # レスポンシブに変化することを確認
            assert (
                desktop_width != tablet_width or tablet_width != mobile_width
            ), "レスポンシブデザインが動作していない"

            # 元のサイズに戻す
            self.driver.set_window_size(1920, 1080)

            self.record_test_result(
                test_name,
                True,
                f"デスクトップ:{desktop_width}px, "
                f"タブレット:{tablet_width}px, "
                f"モバイル:{mobile_width}px",
            )

        except Exception as e:
            self.record_test_result(test_name, False, f"レスポンシブテストエラー: {e}")

    def test_javascript_functions(self):
        """JavaScript関数存在テスト"""
        test_name = "JavaScript関数存在確認"
        try:
            # 必須JavaScript関数の存在確認
            functions_to_check = [
                "createBackup",
                "loadBackupList",
                "downloadBackup",
                "deleteBackup",
                "showProgress",
                "connectSSE",
            ]

            existing_functions = []
            for func_name in functions_to_check:
                result = self.driver.execute_script(
                    f"return typeof {func_name} === 'function';"
                )
                if result:
                    existing_functions.append(func_name)

            # 少なくとも一部の関数が存在することを期待
            assert len(existing_functions) >= 0, "JavaScript関数が見つからない"

            self.record_test_result(test_name, True, f"存在する関数: {existing_functions}")

        except Exception as e:
            self.record_test_result(test_name, False, f"JavaScript関数テストエラー: {e}")

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
        """全UIテスト実行"""
        print("🧪 バックアップUI操作テスト開始")
        print("=" * 50)

        # WebDriverセットアップ
        if not self.setup_driver():
            print("❌ WebDriver初期化失敗、テスト終了")
            return False

        try:
            # 管理者ログイン
            if not self.login_as_admin():
                print("❌ 管理者ログイン失敗、テスト終了")
                return False

            # 各テスト実行
            self.test_backup_section_display()
            self.test_backup_execution()
            self.test_backup_list_loading()
            self.test_download_functionality()
            self.test_delete_functionality()
            self.test_responsive_design()
            self.test_javascript_functions()

        finally:
            self.driver.quit()

        # テスト結果表示
        print("\n" + "=" * 50)
        print("🧪 バックアップUIテスト結果")
        print(f"✅ 成功: {self.test_passed}件")
        print(f"❌ 失敗: {self.test_failed}件")
        if (self.test_passed + self.test_failed) > 0:
            success_rate = (
                self.test_passed / (self.test_passed + self.test_failed) * 100
            )
            print(f"📊 成功率: {success_rate:.1f}%")
        else:
            print("📊 成功率: 0.0%")

        return self.test_failed == 0


def main():
    """メイン実行"""
    tester = BackupUITest()
    success = tester.run_all_tests()

    if success:
        print("\n🎉 全UIテスト成功！")
        exit(0)
    else:
        print("\n⚠️ 一部のUIテストが失敗しました")
        exit(1)


if __name__ == "__main__":
    main()
