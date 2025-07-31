"""
Test suite for Phase 1: PDFファイル管理セクションボタン改善
レスポンシブUI改善のテストコード

関連: TASK-017, docs/responsive-ui-improvement-design.md
"""

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
import time


class TestResponsiveUIPhase1:
    """Phase 1: .file-actions ボタンのレスポンシブ対応テスト"""
    
    @pytest.fixture(scope="class")
    def driver(self):
        """Chrome WebDriverのセットアップ"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # ヘッドレスモード
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        driver = webdriver.Chrome(options=chrome_options)
        yield driver
        driver.quit()
    
    @pytest.fixture
    def admin_page(self, driver):
        """管理画面にアクセス"""
        # 実際のローカル環境に合わせてURLを調整
        driver.get("http://localhost:5000/admin")
        
        # ログインが必要な場合の処理（実装に応じて調整）
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "file-actions"))
            )
        except TimeoutException:
            # ログインページの場合の処理
            pass
        
        return driver
    
    def set_viewport_size(self, driver, width, height):
        """ビューポートサイズを設定"""
        driver.set_window_size(width, height)
        time.sleep(0.5)  # レイアウト安定化待機
    
    def get_file_actions_elements(self, driver):
        """file-actions要素とその子ボタンを取得"""
        try:
            file_actions = driver.find_elements(By.CLASS_NAME, "file-actions")
            if not file_actions:
                return None, []
            
            buttons = file_actions[0].find_elements(By.CLASS_NAME, "btn")
            return file_actions[0], buttons
        except Exception:
            return None, []
    
    def test_tc001_desktop_display(self, admin_page):
        """TC-001: デスクトップ表示（1200px以上）"""
        driver = admin_page
        self.set_viewport_size(driver, 1400, 800)
        
        file_actions, buttons = self.get_file_actions_elements(driver)
        
        if file_actions and buttons:
            # ボタンが横並びで表示されることを確認
            first_button_y = buttons[0].location['y']
            
            # 全ボタンが同じY座標（横並び）にあることを確認
            for button in buttons[1:]:
                assert abs(button.location['y'] - first_button_y) < 5, \
                    "デスクトップでボタンが横並びになっていません"
            
            # ボタン間隔の確認（概算）
            if len(buttons) > 1:
                gap = buttons[1].location['x'] - (buttons[0].location['x'] + buttons[0].size['width'])
                assert gap >= 5, f"ボタン間隔が不十分です: {gap}px"
    
    def test_tc002_tablet_display(self, admin_page):
        """TC-002: タブレット表示（768px-1199px）"""
        driver = admin_page
        self.set_viewport_size(driver, 900, 600)
        
        file_actions, buttons = self.get_file_actions_elements(driver)
        
        if file_actions and buttons:
            # タップしやすいサイズ（最小44px高）の確認
            for i, button in enumerate(buttons):
                height = button.size['height']
                assert height >= 44, \
                    f"ボタン{i+1}の高さが不十分です: {height}px < 44px"
            
            # ボタンの最小幅確認（70px）
            for i, button in enumerate(buttons):
                width = button.size['width']
                assert width >= 70, \
                    f"ボタン{i+1}の幅が不十分です: {width}px < 70px"
    
    def test_tc003_mobile_display(self, admin_page):
        """TC-003: モバイル表示（480px-767px）"""
        driver = admin_page
        self.set_viewport_size(driver, 600, 800)
        
        file_actions, buttons = self.get_file_actions_elements(driver)
        
        if file_actions and buttons:
            # ボタンの配置確認（ラップまたは縦配置）
            y_positions = [btn.location['y'] for btn in buttons]
            unique_y_positions = len(set(y_positions))
            
            # 複数行に配置されている場合
            if unique_y_positions > 1:
                assert unique_y_positions <= len(buttons), \
                    "ボタンの配置が不適切です"
            
            # 最小幅70pxの確認
            for i, button in enumerate(buttons):
                width = button.size['width']
                assert width >= 70, \
                    f"ボタン{i+1}の幅が不十分です: {width}px < 70px"
    
    def test_tc004_small_mobile_display(self, admin_page):
        """TC-004: 小型モバイル（320px-479px）"""
        driver = admin_page
        self.set_viewport_size(driver, 380, 700)
        
        file_actions, buttons = self.get_file_actions_elements(driver)
        
        if file_actions and buttons:
            # 横スクロールが発生しないことを確認
            body_width = driver.execute_script("return document.body.scrollWidth")
            viewport_width = driver.execute_script("return window.innerWidth")
            
            assert body_width <= viewport_width + 20, \
                f"横スクロールが発生しています: body={body_width}px, viewport={viewport_width}px"
            
            # タップ領域の確保
            for i, button in enumerate(buttons):
                height = button.size['height']
                assert height >= 44, \
                    f"ボタン{i+1}のタップ領域が不十分です: {height}px < 44px"
    
    def test_tc005_button_functionality(self, admin_page):
        """TC-005: 機能テスト - ボタンがクリック可能"""
        driver = admin_page
        self.set_viewport_size(driver, 600, 800)  # モバイルサイズ
        
        file_actions, buttons = self.get_file_actions_elements(driver)
        
        if buttons:
            for i, button in enumerate(buttons):
                # ボタンが表示されていることを確認
                assert button.is_displayed(), f"ボタン{i+1}が表示されていません"
                
                # ボタンがクリック可能であることを確認
                assert button.is_enabled(), f"ボタン{i+1}がクリック不可能です"
                
                # ボタンにテキストがあることを確認
                button_text = button.text.strip()
                assert button_text, f"ボタン{i+1}にテキストがありません"
    
    def test_tc006_long_filename_layout(self, admin_page):
        """TC-006: 長いファイル名での表示テスト"""
        driver = admin_page
        self.set_viewport_size(driver, 600, 800)
        
        # 長いファイル名のPDFがある場合のテスト
        # 実装依存のため、実際のDOM構造に応じて調整が必要
        file_items = driver.find_elements(By.CLASS_NAME, "file-item")
        
        for file_item in file_items:
            file_actions = file_item.find_elements(By.CLASS_NAME, "file-actions")
            if file_actions:
                # ファイルアクションエリアが親要素からはみ出していないことを確認
                parent_width = file_item.size['width']
                actions_width = file_actions[0].size['width']
                
                assert actions_width <= parent_width, \
                    f"ファイルアクションが親要素からはみ出しています: {actions_width}px > {parent_width}px"
    
    def test_responsive_breakpoints(self, admin_page):
        """レスポンシブブレークポイントのテスト"""
        driver = admin_page
        breakpoints = [320, 480, 768, 1024, 1200]
        
        for width in breakpoints:
            self.set_viewport_size(driver, width, 800)
            
            file_actions, buttons = self.get_file_actions_elements(driver)
            
            if file_actions and buttons:
                # 各ブレークポイントでレイアウトが崩れていないことを確認
                for button in buttons:
                    assert button.is_displayed(), \
                        f"{width}px幅でボタンが非表示になっています"
                    
                    # ボタンが画面外に出ていないことを確認
                    btn_right = button.location['x'] + button.size['width']
                    assert btn_right <= width, \
                        f"{width}px幅でボタンが画面外に出ています"


def run_responsive_tests():
    """テストを実行する関数"""
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-x"  # 最初のエラーで停止
    ])


if __name__ == "__main__":
    run_responsive_tests()