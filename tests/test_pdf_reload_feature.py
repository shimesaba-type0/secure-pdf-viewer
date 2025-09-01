"""
PDF再読み込み機能のテストコード (TASK-011)
再読み込みボタン機能の基本動作検証
"""
import unittest
import os
import sys

# Flaskアプリをテスト用にインポート
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app


class TestPDFReloadFeature(unittest.TestCase):
    """PDF再読み込み機能テスト"""
    
    def setUp(self):
        """テスト前の準備"""
        # Flaskアプリのテスト設定
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret-key'
        
        # テスト用クライアント
        self.client = app.test_client()
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        pass
    
    def test_pdf_reload_api_unauthenticated(self):
        """未認証ユーザーのアクセス拒否テスト"""
        print("\n=== 未認証ユーザーのアクセス拒否テスト ===")
        
        # 認証なしでAPI呼び出し
        response = self.client.post('/api/generate-pdf-url', 
                                  content_type='application/json')
        
        print(f"   APIレスポンス: {response.status_code}")
        
        # 期待される動作: 401 Unauthorized または リダイレクト
        self.assertIn(response.status_code, [401, 302])
        print(f"   ✅ 未認証ユーザーは正しく拒否されました")
    
    def test_pdf_reload_javascript_integration(self):
        """JavaScript関数の存在確認テスト"""
        print("\n=== JavaScript関数の存在確認テスト ===")
        
        # Static JavaScriptファイルを読み取り
        js_file_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'static', 'js', 'pdf-viewer.js'
        )
        
        if os.path.exists(js_file_path):
            with open(js_file_path, 'r', encoding='utf-8') as f:
                js_content = f.read()
            
            # reloadCurrentPDF関数の存在確認
            self.assertIn('reloadCurrentPDF', js_content, "reloadCurrentPDF関数が見つかりません")
            self.assertIn('getSignedPdfUrl', js_content, "getSignedPdfUrl関数が見つかりません")
            
            print("   ✅ JavaScript関数が正しく定義されています")
            print("   ✅ reloadCurrentPDF関数が存在します")
            print("   ✅ getSignedPdfUrl関数が存在します")
        else:
            self.fail("pdf-viewer.jsファイルが見つかりません")
    
    def test_viewer_page_template_structure(self):
        """viewer.htmlテンプレートの構造確認テスト"""
        print("\n=== viewer.htmlテンプレートの構造確認テスト ===")
        
        # HTMLテンプレートファイルを読み取り
        template_file_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'templates', 'viewer.html'
        )
        
        if os.path.exists(template_file_path):
            with open(template_file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # 再読み込みボタンの存在確認
            self.assertIn('id="reloadPdfBtn"', html_content, "再読み込みボタンのIDが見つかりません")
            self.assertIn('再読み込み', html_content, "再読み込みボタンのテキストが見つかりません")
            self.assertIn('display-controls', html_content, "display-controlsクラスが見つかりません")
            
            print("   ✅ 再読み込みボタンがHTMLテンプレートに存在します")
            print("   ✅ ボタンが適切なコンテナ内に配置されています")
        else:
            self.fail("viewer.htmlテンプレートファイルが見つかりません")


def run_pdf_reload_tests():
    """PDF再読み込み機能テストの実行"""
    print("TASK-011 PDF再読み込み機能テスト開始\n")
    
    tests = [
        'test_pdf_reload_api_unauthenticated',
        'test_pdf_reload_javascript_integration',
        'test_viewer_page_template_structure'
    ]
    
    suite = unittest.TestSuite()
    for test in tests:
        suite.addTest(TestPDFReloadFeature(test))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\n{'='*50}")
    print(f"テスト結果: {result.testsRun}件実行")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}件")
    print(f"失敗: {len(result.failures)}件")
    print(f"エラー: {len(result.errors)}件")
    
    if result.failures:
        print(f"\n失敗したテスト:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback}")
    
    if result.errors:
        print(f"\nエラーが発生したテスト:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")
    
    return len(result.failures) == 0 and len(result.errors) == 0


if __name__ == '__main__':
    success = run_pdf_reload_tests()
    exit(0 if success else 1)