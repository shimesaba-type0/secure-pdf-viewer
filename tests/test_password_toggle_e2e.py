#!/usr/bin/env python3
"""
パスワード表示ボタンのE2Eテスト
実際のブラウザ操作でUI動作を検証します
"""

import unittest
import time
import os
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestPasswordToggleE2E(unittest.TestCase):
    """パスワード表示ボタンのE2Eテストクラス"""
    
    @classmethod
    def setUpClass(cls):
        """テストクラス全体の初期化"""
        # Chromeオプションの設定
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # ヘッドレスモード
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        
        try:
            cls.driver = webdriver.Chrome(options=chrome_options)
            cls.driver.implicitly_wait(10)
        except Exception as e:
            raise unittest.SkipTest(f"Chrome WebDriverが利用できません: {e}")
    
    @classmethod
    def tearDownClass(cls):
        """テストクラス全体の終了処理"""
        if hasattr(cls, 'driver'):
            cls.driver.quit()
    
    def setUp(self):
        """各テストケースの初期化"""
        # アプリケーションのベースURL（実際の環境に合わせて調整）
        self.base_url = "http://localhost:5000"
        
        # 管理画面にアクセス
        self.driver.get(f"{self.base_url}/admin")
        
        # ページロードを待機
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "toggleNewPassphrase"))
            )
        except TimeoutException:
            self.skipTest("管理画面が正常に読み込まれませんでした")
    
    def test_new_passphrase_toggle_functionality(self):
        """新しいパスフレーズフィールドの表示ボタンが正常に動作することを確認"""
        # 要素を取得
        input_field = self.driver.find_element(By.ID, "newPassphrase")
        toggle_button = self.driver.find_element(By.ID, "toggleNewPassphrase")
        toggle_text = toggle_button.find_element(By.CLASS_NAME, "toggle-text")
        
        # 初期状態の確認
        self.assertEqual(input_field.get_attribute("type"), "password")
        self.assertEqual(toggle_text.text, "表示")
        
        # テスト用のパスフレーズを入力
        test_passphrase = "test_passphrase_12345"
        input_field.send_keys(test_passphrase)
        
        # 表示ボタンをクリック
        toggle_button.click()
        
        # 少し待機
        time.sleep(0.5)
        
        # 表示状態の確認
        self.assertEqual(input_field.get_attribute("type"), "text")
        self.assertEqual(toggle_text.text, "隠す")
        self.assertEqual(input_field.get_attribute("value"), test_passphrase)
        
        # 再度ボタンをクリックして隠す
        toggle_button.click()
        
        # 少し待機
        time.sleep(0.5)
        
        # 非表示状態の確認
        self.assertEqual(input_field.get_attribute("type"), "password")
        self.assertEqual(toggle_text.text, "表示")
    
    def test_confirm_passphrase_toggle_functionality(self):
        """確認用パスフレーズフィールドの表示ボタンが正常に動作することを確認"""
        # 要素を取得
        input_field = self.driver.find_element(By.ID, "confirmPassphrase")
        toggle_button = self.driver.find_element(By.ID, "toggleConfirmPassphrase")
        toggle_text = toggle_button.find_element(By.CLASS_NAME, "toggle-text")
        
        # 初期状態の確認
        self.assertEqual(input_field.get_attribute("type"), "password")
        self.assertEqual(toggle_text.text, "表示")
        
        # テスト用のパスフレーズを入力
        test_passphrase = "confirm_passphrase_12345"
        input_field.send_keys(test_passphrase)
        
        # 表示ボタンをクリック
        toggle_button.click()
        
        # 少し待機
        time.sleep(0.5)
        
        # 表示状態の確認
        self.assertEqual(input_field.get_attribute("type"), "text")
        self.assertEqual(toggle_text.text, "隠す")
        self.assertEqual(input_field.get_attribute("value"), test_passphrase)
        
        # 再度ボタンをクリックして隠す
        toggle_button.click()
        
        # 少し待機
        time.sleep(0.5)
        
        # 非表示状態の確認
        self.assertEqual(input_field.get_attribute("type"), "password")
        self.assertEqual(toggle_text.text, "表示")
    
    def test_both_toggles_independent(self):
        """両方の表示ボタンが独立して動作することを確認"""
        # 要素を取得
        new_input = self.driver.find_element(By.ID, "newPassphrase")
        confirm_input = self.driver.find_element(By.ID, "confirmPassphrase")
        new_toggle = self.driver.find_element(By.ID, "toggleNewPassphrase")
        confirm_toggle = self.driver.find_element(By.ID, "toggleConfirmPassphrase")
        new_text = new_toggle.find_element(By.CLASS_NAME, "toggle-text")
        confirm_text = confirm_toggle.find_element(By.CLASS_NAME, "toggle-text")
        
        # 初期状態
        self.assertEqual(new_input.get_attribute("type"), "password")
        self.assertEqual(confirm_input.get_attribute("type"), "password")
        
        # 新しいパスフレーズの表示ボタンのみクリック
        new_toggle.click()
        time.sleep(0.5)
        
        # 新しいパスフレーズのみ表示状態になることを確認
        self.assertEqual(new_input.get_attribute("type"), "text")
        self.assertEqual(confirm_input.get_attribute("type"), "password")
        self.assertEqual(new_text.text, "隠す")
        self.assertEqual(confirm_text.text, "表示")
        
        # 確認用パスフレーズの表示ボタンもクリック
        confirm_toggle.click()
        time.sleep(0.5)
        
        # 両方とも表示状態になることを確認
        self.assertEqual(new_input.get_attribute("type"), "text")
        self.assertEqual(confirm_input.get_attribute("type"), "text")
        self.assertEqual(new_text.text, "隠す")
        self.assertEqual(confirm_text.text, "隠す")
    
    def test_aria_labels_update(self):
        """aria-label属性が適切に更新されることを確認"""
        toggle_button = self.driver.find_element(By.ID, "toggleNewPassphrase")
        
        # 初期状態のaria-label確認
        initial_label = toggle_button.get_attribute("aria-label")
        self.assertIn("表示", initial_label)
        
        # ボタンをクリック
        toggle_button.click()
        time.sleep(0.5)
        
        # 更新後のaria-label確認
        updated_label = toggle_button.get_attribute("aria-label")
        self.assertIn("隠す", updated_label)
    
    def test_no_javascript_errors(self):
        """JavaScriptエラーが発生しないことを確認"""
        # ブラウザのコンソールログを取得
        logs = self.driver.get_log('browser')
        
        # 表示ボタンをクリック
        new_toggle = self.driver.find_element(By.ID, "toggleNewPassphrase")
        new_toggle.click()
        time.sleep(0.5)
        
        # 確認用も同様にクリック
        confirm_toggle = self.driver.find_element(By.ID, "toggleConfirmPassphrase")
        confirm_toggle.click()
        time.sleep(0.5)
        
        # 新しいログを取得
        new_logs = self.driver.get_log('browser')
        
        # エラーログがないことを確認
        error_logs = [log for log in new_logs if log['level'] == 'SEVERE']
        self.assertEqual(len(error_logs), 0, f"JavaScriptエラーが発生しました: {error_logs}")


if __name__ == '__main__':
    # テストの実行前にWebDriverの利用可能性をチェック
    try:
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        print("Seleniumの依存関係が利用可能です")
    except ImportError as e:
        print(f"Seleniumが利用できません: {e}")
        print("pip install seleniumでインストールしてください")
        sys.exit(1)
    
    unittest.main()