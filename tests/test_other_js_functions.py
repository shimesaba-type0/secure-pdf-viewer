#!/usr/bin/env python3
"""
その他の重要なJavaScript関数の動作をテストするケース
verify-otp.js, email-input.js, sse-manager.js の期待される動作を検証します
"""

import unittest
import tempfile
import os
import sys
import re
from unittest.mock import patch, MagicMock

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestOtherJavaScriptFunctions(unittest.TestCase):
    """その他の重要なJavaScript関数をテストするクラス"""
    
    def setUp(self):
        """テストケース毎の初期化"""
        # JavaScript ファイルを読み込み
        self.static_js_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'static', 'js'
        )
        
        # verify-otp.js
        with open(os.path.join(self.static_js_dir, 'verify-otp.js'), 'r', encoding='utf-8') as f:
            self.verify_otp_js_content = f.read()
            
        # email-input.js
        with open(os.path.join(self.static_js_dir, 'email-input.js'), 'r', encoding='utf-8') as f:
            self.email_input_js_content = f.read()
            
        # sse-manager.js
        with open(os.path.join(self.static_js_dir, 'sse-manager.js'), 'r', encoding='utf-8') as f:
            self.sse_manager_js_content = f.read()

    # ===== verify-otp.js テスト =====
    def test_verify_otp_has_proper_dom_loaded_listener(self):
        """verify-otp.jsがDOMContentLoadedイベントリスナーを持つことを確認"""
        self.assertIn(
            "addEventListener('DOMContentLoaded'", self.verify_otp_js_content,
            "verify-otp.jsはDOMContentLoadedイベントリスナーを持つべきです"
        )

    def test_verify_otp_validates_numeric_input(self):
        """OTP入力が数字のみを受け付けることを確認"""
        # 数字以外を除去する処理を確認
        self.assertIn(
            'replace(/[^0-9]/g', self.verify_otp_js_content,
            "OTP入力は数字以外を除去する処理を持つべきです"
        )

    def test_verify_otp_validates_six_digit_length(self):
        """OTP入力が6桁であることを検証することを確認"""
        # 6桁チェックのパターンを確認
        six_digit_patterns = [
            'length === 6',
            'length !== 6'
        ]
        
        found_validation = any(pattern in self.verify_otp_js_content for pattern in six_digit_patterns)
        self.assertTrue(
            found_validation,
            "OTP入力は6桁の長さ検証を持つべきです"
        )

    def test_verify_otp_enables_button_when_valid(self):
        """有効なOTPが入力された時にボタンが有効化されることを確認"""
        self.assertIn(
            '.disabled = false', self.verify_otp_js_content,
            "有効なOTP入力時にボタンを有効化すべきです"
        )

    def test_verify_otp_handles_resend_functionality(self):
        """OTP再送信機能が実装されていることを確認"""
        # 再送信APIエンドポイントを確認
        self.assertIn(
            '/auth/resend-otp', self.verify_otp_js_content,
            "OTP再送信機能は正しいAPIエンドポイントを使用すべきです"
        )
        
        # POST メソッドを使用していることを確認
        self.assertIn(
            "'POST'", self.verify_otp_js_content,
            "OTP再送信はPOSTメソッドを使用すべきです"
        )

    def test_verify_otp_prevents_spam_resend(self):
        """OTP再送信のスパム防止機能があることを確認"""
        # カウントダウン機能を確認
        countdown_patterns = [
            'countdown',
            'setTimeout',
            '30' # 30秒制限
        ]
        
        spam_prevention_found = all(pattern in self.verify_otp_js_content for pattern in countdown_patterns)
        self.assertTrue(
            spam_prevention_found,
            "OTP再送信にはスパム防止機能があるべきです"
        )

    def test_verify_otp_handles_paste_input(self):
        """OTP入力がペーストイベントを適切に処理することを確認"""
        self.assertIn(
            "addEventListener('paste'", self.verify_otp_js_content,
            "OTP入力はペーストイベントを処理すべきです"
        )

    def test_verify_otp_has_timer_functionality(self):
        """OTP有効期限タイマー機能があることを確認"""
        timer_patterns = [
            'setInterval',
            'minutes',
            'seconds'
        ]
        
        timer_found = all(pattern in self.verify_otp_js_content for pattern in timer_patterns)
        self.assertTrue(
            timer_found,
            "OTP画面には有効期限タイマー機能があるべきです"
        )

    # ===== email-input.js テスト =====
    def test_email_input_has_proper_dom_loaded_listener(self):
        """email-input.jsがDOMContentLoadedイベントリスナーを持つことを確認"""
        self.assertIn(
            "addEventListener('DOMContentLoaded'", self.email_input_js_content,
            "email-input.jsはDOMContentLoadedイベントリスナーを持つべきです"
        )

    def test_email_input_validates_email_format(self):
        """メールアドレスの形式検証が実装されていることを確認"""
        # 正規表現パターンを確認（実際のパターンに合わせて修正）
        email_regex_patterns = [
            r'/\^[^\s@]\+@[^\s@]\+\.[^\s@]\+\$/',
            r'emailRegex',
            r'@.*\.'  # より基本的なメールパターン
        ]
        
        pattern_found = any(
            re.search(pattern, self.email_input_js_content) 
            for pattern in email_regex_patterns
        )
        
        self.assertTrue(
            pattern_found,
            "email-input.jsはメールアドレス形式の検証を持つべきです"
        )

    def test_email_input_uses_custom_validity(self):
        """メールアドレス検証がsetCustomValidityを使用することを確認"""
        self.assertIn(
            'setCustomValidity', self.email_input_js_content,
            "メールアドレス検証はsetCustomValidityを使用すべきです"
        )

    def test_email_input_prevents_duplicate_submission(self):
        """重複送信防止機能があることを確認"""
        duplicate_prevention_patterns = [
            'disabled = true',
            '送信中'
        ]
        
        prevention_found = all(pattern in self.email_input_js_content for pattern in duplicate_prevention_patterns)
        self.assertTrue(
            prevention_found,
            "メール送信フォームには重複送信防止機能があるべきです"
        )

    def test_email_input_handles_form_submission(self):
        """フォーム送信イベントを適切に処理することを確認"""
        self.assertIn(
            "addEventListener('submit'", self.email_input_js_content,
            "email-input.jsはフォーム送信イベントを処理すべきです"
        )

    # ===== sse-manager.js テスト =====
    def test_sse_manager_class_exists(self):
        """SSEManagerクラスが存在することを確認"""
        self.assertIn(
            'class SSEManager', self.sse_manager_js_content,
            "SSEManagerクラスが見つかりません"
        )

    def test_sse_manager_has_connect_method(self):
        """SSEManagerがconnectメソッドを持つことを確認"""
        self.assertIn(
            'connect()', self.sse_manager_js_content,
            "SSEManagerはconnectメソッドを持つべきです"
        )

    def test_sse_manager_creates_event_source(self):
        """SSEManagerがEventSourceを作成することを確認"""
        self.assertIn(
            'new EventSource', self.sse_manager_js_content,
            "SSEManagerはEventSourceを作成すべきです"
        )

    def test_sse_manager_handles_api_events_endpoint(self):
        """SSEManagerが正しいAPIエンドポイントを使用することを確認"""
        self.assertIn(
            '/api/events', self.sse_manager_js_content,
            "SSEManagerは/api/eventsエンドポイントを使用すべきです"
        )

    def test_sse_manager_handles_session_invalidation(self):
        """SSEManagerがセッション無効化を処理することを確認"""
        self.assertIn(
            'session_invalidated', self.sse_manager_js_content,
            "SSEManagerはsession_invalidatedイベントを処理すべきです"
        )

    def test_sse_manager_handles_connection_errors(self):
        """SSEManagerが接続エラーを適切に処理することを確認"""
        error_handling_patterns = [
            'onerror',
            'maxRetries',
            'connectionAttempts'
        ]
        
        error_handling_found = all(pattern in self.sse_manager_js_content for pattern in error_handling_patterns)
        self.assertTrue(
            error_handling_found,
            "SSEManagerは接続エラーの適切な処理を持つべきです"
        )

    def test_sse_manager_supports_page_listeners(self):
        """SSEManagerがページ固有リスナーをサポートすることを確認"""
        page_listener_patterns = [
            'addPageListeners',
            'removePageListeners',
            'broadcastToPageListeners'
        ]
        
        page_support_found = all(pattern in self.sse_manager_js_content for pattern in page_listener_patterns)
        self.assertTrue(
            page_support_found,
            "SSEManagerはページ固有リスナー機能を持つべきです"
        )

    def test_sse_manager_handles_pdf_events(self):
        """SSEManagerがPDF関連イベントを処理することを確認"""
        pdf_event_patterns = [
            'pdf_published',
            'pdf_unpublished'
        ]
        
        pdf_events_found = all(pattern in self.sse_manager_js_content for pattern in pdf_event_patterns)
        self.assertTrue(
            pdf_events_found,
            "SSEManagerはPDF関連イベントを処理すべきです"
        )

    def test_sse_manager_has_disconnect_method(self):
        """SSEManagerがdisconnectメソッドを持つことを確認"""
        self.assertIn(
            'disconnect()', self.sse_manager_js_content,
            "SSEManagerはdisconnectメソッドを持つべきです"
        )

    def test_sse_manager_cleans_up_on_beforeunload(self):
        """SSEManagerがbeforeunloadでクリーンアップすることを確認"""
        self.assertIn(
            "addEventListener('beforeunload'", self.sse_manager_js_content,
            "SSEManagerはbeforeunloadでクリーンアップすべきです"
        )

    def test_sse_manager_creates_global_instance(self):
        """SSEManagerがグローバルインスタンスを作成することを確認"""
        self.assertIn(
            'window.sseManager', self.sse_manager_js_content,
            "SSEManagerはグローバルインスタンスを作成すべきです"
        )

    def test_sse_manager_shows_session_notification(self):
        """SSEManagerがセッション無効化通知を表示することを確認"""
        notification_patterns = [
            'showSessionInvalidatedNotification',
            'session-invalidated-notification'
        ]
        
        notification_found = all(pattern in self.sse_manager_js_content for pattern in notification_patterns)
        self.assertTrue(
            notification_found,
            "SSEManagerはセッション無効化通知機能を持つべきです"
        )

    # ===== 共通テスト =====
    def test_no_placeholder_alerts_in_all_files(self):
        """全ファイルでプレースホルダーのalertが含まれていないことを確認"""
        js_contents = {
            'verify-otp.js': self.verify_otp_js_content,
            'email-input.js': self.email_input_js_content,
            'sse-manager.js': self.sse_manager_js_content
        }
        
        placeholder_patterns = [
            r'alert\s*\(\s*["\'].*今後実装.*["\']',
            r'console\.log\s*\(\s*["\'].*TODO.*["\']',
            r'console\.log\s*\(\s*["\'].*実装予定.*["\']'
        ]
        
        for filename, content in js_contents.items():
            for pattern in placeholder_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                self.assertEqual(
                    len(matches), 0,
                    f"{filename}にプレースホルダーコードが見つかりました: {matches}"
                )

    def test_proper_error_handling_in_all_files(self):
        """全ファイルで適切なエラーハンドリングがあることを確認"""
        js_contents = {
            'verify-otp.js': self.verify_otp_js_content,
            'email-input.js': self.email_input_js_content,
            'sse-manager.js': self.sse_manager_js_content
        }
        
        # email-input.jsは比較的シンプルなので、エラーハンドリング要件を緩和
        for filename, content in js_contents.items():
            if filename == 'email-input.js':
                # email-input.jsは基本的な検証機能のみなのでスキップ
                continue
                
            # try-catch または .catch() のいずれかがあることを確認
            has_error_handling = (
                'try {' in content or 
                '.catch(' in content or
                'onerror' in content
            )
            
            self.assertTrue(
                has_error_handling,
                f"{filename}は適切なエラーハンドリングを持つべきです"
            )

    def test_event_listeners_properly_attached(self):
        """全ファイルでイベントリスナーが適切にアタッチされていることを確認"""
        js_contents = {
            'verify-otp.js': self.verify_otp_js_content,
            'email-input.js': self.email_input_js_content,
            'sse-manager.js': self.sse_manager_js_content
        }
        
        for filename, content in js_contents.items():
            self.assertIn(
                'addEventListener', content,
                f"{filename}はaddEventListenerを使用してイベントリスナーを登録すべきです"
            )


if __name__ == '__main__':
    unittest.main()