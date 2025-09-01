#!/usr/bin/env python3
"""
admin.jsの重要な関数の動作をテストするケース
JavaScript関数の期待される動作を検証します
"""

import unittest
import tempfile
import os
import sys
import re
from unittest.mock import patch, MagicMock

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestAdminJavaScriptFunctions(unittest.TestCase):
    """admin.jsの重要な関数をテストするクラス"""
    
    def setUp(self):
        """テストケース毎の初期化"""
        # admin.jsファイルを読み込み
        self.admin_js_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'static', 'js', 'admin.js'
        )
        
        with open(self.admin_js_path, 'r', encoding='utf-8') as f:
            self.admin_js_content = f.read()
            
        # admin.htmlファイルを読み込み
        self.admin_html_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'templates', 'admin.html'
        )
        
        with open(self.admin_html_path, 'r', encoding='utf-8') as f:
            self.admin_html_content = f.read()
    
    def test_viewSessionDetails_function_exists(self):
        """viewSessionDetails関数が存在することを確認"""
        function_pattern = r'function\s+viewSessionDetails\s*\('
        self.assertIsNotNone(
            re.search(function_pattern, self.admin_js_content),
            "viewSessionDetails関数が見つかりません"
        )
    
    def test_viewSessionDetails_not_using_alert(self):
        """viewSessionDetails関数がalertを使用していないことを確認（デグレ検出）"""
        # viewSessionDetails関数の内容を抽出
        function_start = re.search(r'function\s+viewSessionDetails\s*\([^)]*\)\s*\{', self.admin_js_content)
        if not function_start:
            self.fail("viewSessionDetails関数が見つかりません")
        
        # 関数の終わりを見つける（簡易的な実装）
        start_pos = function_start.end()
        brace_count = 1
        pos = start_pos
        
        while pos < len(self.admin_js_content) and brace_count > 0:
            if self.admin_js_content[pos] == '{':
                brace_count += 1
            elif self.admin_js_content[pos] == '}':
                brace_count -= 1
            pos += 1
        
        function_body = self.admin_js_content[start_pos:pos-1]
        
        # alertを使用していないことを確認
        self.assertNotIn(
            'alert(', function_body,
            "viewSessionDetails関数はalertを使用すべきではありません（今後実装予定のプレースホルダーです）"
        )
    
    def test_viewSessionDetails_uses_correct_url_pattern(self):
        """viewSessionDetails関数が正しいURL遷移を行うことを確認"""
        # viewSessionDetails関数の内容を抽出
        function_start = re.search(r'function\s+viewSessionDetails\s*\([^)]*\)\s*\{', self.admin_js_content)
        if not function_start:
            self.fail("viewSessionDetails関数が見つかりません")
        
        start_pos = function_start.end()
        brace_count = 1
        pos = start_pos
        
        while pos < len(self.admin_js_content) and brace_count > 0:
            if self.admin_js_content[pos] == '{':
                brace_count += 1
            elif self.admin_js_content[pos] == '}':
                brace_count -= 1
            pos += 1
        
        function_body = self.admin_js_content[start_pos:pos-1]
        
        # 正しいURL生成を確認
        self.assertIn(
            '/admin/sessions/', function_body,
            "viewSessionDetails関数は/admin/sessions/への遷移URLを生成すべきです"
        )
        
        # window.openを使用していることを確認
        self.assertIn(
            'window.open', function_body,
            "viewSessionDetails関数はwindow.openを使用して新しいタブで開くべきです"
        )
    
    def test_viewSessionDetails_parameter_usage(self):
        """viewSessionDetails関数がsessionIdパラメータを適切に使用することを確認"""
        function_start = re.search(r'function\s+viewSessionDetails\s*\([^)]*\)\s*\{', self.admin_js_content)
        if not function_start:
            self.fail("viewSessionDetails関数が見つかりません")
        
        # 関数定義からパラメータ名を抽出
        function_def = re.search(r'function\s+viewSessionDetails\s*\(([^)]*)\)', self.admin_js_content)
        if function_def:
            params = function_def.group(1).strip()
            if params:
                # sessionIdパラメータがURL生成で使用されていることを確認
                start_pos = function_start.end()
                brace_count = 1
                pos = start_pos
                
                while pos < len(self.admin_js_content) and brace_count > 0:
                    if self.admin_js_content[pos] == '{':
                        brace_count += 1
                    elif self.admin_js_content[pos] == '}':
                        brace_count -= 1
                    pos += 1
                
                function_body = self.admin_js_content[start_pos:pos-1]
                
                # パラメータがURL構築で使用されていることを確認
                self.assertTrue(
                    params in function_body,
                    f"viewSessionDetails関数は{params}パラメータをURL構築で使用すべきです"
                )

    def test_password_toggle_function_exists(self):
        """togglePasswordVisibility関数が存在することを確認"""
        function_pattern = r'function\s+togglePasswordVisibility\s*\('
        self.assertIsNotNone(
            re.search(function_pattern, self.admin_js_content),
            "togglePasswordVisibility関数が見つかりません"
        )

    def test_password_toggle_function_structure(self):
        """togglePasswordVisibility関数が正しい構造を持つことを確認"""
        # 関数の存在確認
        function_start = re.search(r'function\s+togglePasswordVisibility\s*\([^)]*\)\s*\{', self.admin_js_content)
        self.assertIsNotNone(function_start, "togglePasswordVisibility関数が見つかりません")
        
        # 関数の内容を抽出
        start_pos = function_start.end()
        brace_count = 1
        pos = start_pos
        
        while pos < len(self.admin_js_content) and brace_count > 0:
            if self.admin_js_content[pos] == '{':
                brace_count += 1
            elif self.admin_js_content[pos] == '}':
                brace_count -= 1
            pos += 1
        
        function_body = self.admin_js_content[start_pos:pos-1]
        
        # 重要な処理が含まれていることを確認
        self.assertIn('getElementById', function_body, "要素取得処理が含まれていません")
        self.assertIn('type === \'password\'', function_body, "パスワードタイプの判定が含まれていません")
        self.assertIn('textContent', function_body, "テキスト変更処理が含まれていません")
        self.assertIn('setAttribute', function_body, "aria-label設定処理が含まれていません")

    def test_password_toggle_html_structure(self):
        """パスワード表示ボタンのHTML構造が正しいことを確認"""
        # 新しいパスフレーズのボタン
        new_button_pattern = r'<button[^>]*id="toggleNewPassphrase"[^>]*>'
        self.assertIsNotNone(
            re.search(new_button_pattern, self.admin_html_content),
            "新しいパスフレーズの表示ボタンが見つかりません"
        )
        
        # 確認用パスフレーズのボタン
        confirm_button_pattern = r'<button[^>]*id="toggleConfirmPassphrase"[^>]*>'
        self.assertIsNotNone(
            re.search(confirm_button_pattern, self.admin_html_content),
            "確認用パスフレーズの表示ボタンが見つかりません"
        )

    def test_password_toggle_no_onclick_attributes(self):
        """表示ボタンにonclick属性が含まれていないことを確認（重複実行防止）"""
        # onclick属性が含まれていないことを確認
        onclick_pattern = r'<button[^>]*onclick[^>]*togglePasswordVisibility'
        self.assertIsNone(
            re.search(onclick_pattern, self.admin_html_content),
            "表示ボタンにonclick属性が残っています（イベントハンドラー重複の原因）"
        )

    def test_password_toggle_spans_exist(self):
        """表示ボタン内のspanエレメントが存在することを確認"""
        # toggle-textクラスを持つspanが存在することを確認
        span_pattern = r'<span[^>]*class="toggle-text"[^>]*>表示</span>'
        matches = re.findall(span_pattern, self.admin_html_content)
        self.assertGreaterEqual(
            len(matches), 2,
            "toggle-textクラスを持つspanが2つ以上存在する必要があります（新規・確認用）"
        )

    def test_password_input_fields_exist(self):
        """パスフレーズ入力フィールドが存在することを確認"""
        # 新しいパスフレーズフィールド（type="password"が後に来る場合もある）
        new_field_pattern = r'<input[^>]*id="newPassphrase"[^>]*>'
        self.assertIsNotNone(
            re.search(new_field_pattern, self.admin_html_content),
            "新しいパスフレーズ入力フィールドが見つかりません"
        )
        
        # type="password"が含まれることを確認
        self.assertIn('type="password"', self.admin_html_content, "password型の入力フィールドが見つかりません")
        
        # 確認用パスフレーズフィールド
        confirm_field_pattern = r'<input[^>]*id="confirmPassphrase"[^>]*>'
        self.assertIsNotNone(
            re.search(confirm_field_pattern, self.admin_html_content),
            "確認用パスフレーズ入力フィールドが見つかりません"
        )


if __name__ == '__main__':
    unittest.main()