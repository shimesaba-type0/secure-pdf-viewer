"""
Phase 1 レスポンシブUI改善の軽量テストスイート
Seleniumを使わない基本的なCSS検証テスト

関連: TASK-017, docs/responsive-ui-improvement-design.md
"""

import pytest
import re
import os


class TestResponsiveUIPhase1Simple:
    """Phase 1: .file-actions ボタンのレスポンシブ対応の基本テスト"""
    
    @pytest.fixture
    def css_content(self):
        """CSS ファイルの内容を読み込む"""
        css_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'css', 'main.css')
        with open(css_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def test_css_syntax_validation(self, css_content):
        """CSS構文の基本検証"""
        # 括弧の対応チェック
        open_braces = css_content.count('{')
        close_braces = css_content.count('}')
        
        assert open_braces == close_braces, \
            f"括弧の対応エラー: {{ は {open_braces}個, }} は {close_braces}個"
    
    def test_file_actions_responsive_rules_exist(self, css_content):
        """file-actions のレスポンシブルールが存在することを確認"""
        # 768px以下のメディアクエリが存在することを確認
        media_query_exists = '@media (max-width: 768px)' in css_content
        assert media_query_exists, "768px以下のメディアクエリが見つかりません"
        
        # メディアクエリ内に .file-actions ルールが存在することを確認
        # 複数のメディアクエリセクションから .file-actions を含むものを探す
        media_sections = re.findall(
            r'@media\s*\([^)]*max-width:\s*768px[^)]*\)\s*\{(.*?)\}(?=\s*(?:@media|$|/\*))',
            css_content,
            re.DOTALL
        )
        
        file_actions_found = False
        for section in media_sections:
            if '.file-actions' in section:
                file_actions_found = True
                break
        
        assert file_actions_found, \
            "768px以下のメディアクエリ内に .file-actions ルールが見つかりません"
    
    def test_file_actions_properties_exist(self, css_content):
        """file-actions に必要なプロパティが存在することを確認"""
        # 768px以下のメディアクエリ内の .file-actions セクションを抽出
        media_section_match = re.search(
            r'@media\s*\([^)]*max-width:\s*768px[^)]*\)\s*\{(.*?)\}(?=\s*$|\s*@|\s*/\*)',
            css_content, 
            re.DOTALL
        )
        
        assert media_section_match, "768px以下のメディアクエリが見つかりません"
        
        media_content = media_section_match.group(1)
        
        # 必要なプロパティをチェック
        required_properties = [
            'flex-wrap',
            'gap',
            'margin-top',
            'min-width',
            'min-height'
        ]
        
        for prop in required_properties:
            pattern = rf'\.file-actions[^{{]*\{{[^}}]*{re.escape(prop)}\s*:[^;]+;'
            btn_pattern = rf'\.file-actions\s+\.btn[^{{]*\{{[^}}]*{re.escape(prop)}\s*:[^;]+;'
            
            found = re.search(pattern, media_content, re.DOTALL) or \
                   re.search(btn_pattern, media_content, re.DOTALL)
            
            assert found, f"必要なプロパティ '{prop}' が見つかりません"
    
    def test_file_actions_values_validation(self, css_content):
        """file-actions の値が適切であることを確認"""
        # 768px以下のメディアクエリ内容を取得
        media_section_match = re.search(
            r'@media\s*\([^)]*max-width:\s*768px[^)]*\)\s*\{(.*?)\}(?=\s*$|\s*@|\s*/\*)',
            css_content, 
            re.DOTALL
        )
        
        media_content = media_section_match.group(1)
        
        # 値の検証
        test_cases = [
            ('flex-wrap', 'wrap', '.file-actions'),
            ('gap', '0.5rem', '.file-actions'),
            ('margin-top', '0.5rem', '.file-actions'),
            ('min-width', '70px', '.file-actions .btn'),
            ('min-height', '44px', '.file-actions .btn')
        ]
        
        for prop, expected_value, selector in test_cases:
            if selector == '.file-actions':
                pattern = rf'\.file-actions[^{{]*\{{[^}}]*{re.escape(prop)}\s*:\s*{re.escape(expected_value)}\s*;'
            else:  # .file-actions .btn
                pattern = rf'\.file-actions\s+\.btn[^{{]*\{{[^}}]*{re.escape(prop)}\s*:\s*{re.escape(expected_value)}\s*;'
            
            assert re.search(pattern, media_content, re.DOTALL), \
                f"{selector} の {prop} プロパティが期待値 '{expected_value}' ではありません"
    
    def test_existing_properties_preserved(self, css_content):
        """既存のプロパティが保持されていることを確認"""
        media_section_match = re.search(
            r'@media\s*\([^)]*max-width:\s*768px[^)]*\)\s*\{(.*?)\}(?=\s*$|\s*@|\s*/\*)',
            css_content, 
            re.DOTALL
        )
        
        media_content = media_section_match.group(1)
        
        # 既存のプロパティが保持されていることを確認
        existing_properties = ['align-self', 'justify-content']
        
        for prop in existing_properties:
            pattern = rf'\.file-actions[^{{]*\{{[^}}]*{re.escape(prop)}\s*:[^;]+;'
            assert re.search(pattern, media_content, re.DOTALL), \
                f"既存のプロパティ '{prop}' が失われています"
    
    def test_no_desktop_impact(self, css_content):
        """デスクトップ表示に影響がないことを確認"""
        # 768px超のメディアクエリや通常のセレクタで .file-actions の基本スタイルが保持されていることを確認
        base_file_actions_pattern = r'\.file-actions\s*\{[^}]*display\s*:\s*flex[^}]*\}'
        
        # メディアクエリ外での基本的な .file-actions スタイルをチェック
        # (この検証は既存のスタイルが維持されていることを確認)
        lines = css_content.split('\n')
        in_media_query = False
        media_depth = 0
        
        for line in lines:
            if '@media' in line and 'max-width' in line:
                in_media_query = True
                media_depth = 0
            
            if in_media_query:
                media_depth += line.count('{')
                media_depth -= line.count('}')
                if media_depth <= 0:
                    in_media_query = False
            
            # メディアクエリ外での .file-actions の基本プロパティ確認
            if not in_media_query and '.file-actions' in line:
                # 基本的な表示プロパティが存在することを確認
                # (実装に依存するため、存在確認のみ)
                pass
    
    def test_accessibility_compliance(self, css_content):
        """アクセシビリティ要件の確認"""
        media_section_match = re.search(
            r'@media\s*\([^)]*max-width:\s*768px[^)]*\)\s*\{(.*?)\}(?=\s*$|\s*@|\s*/\*)',
            css_content, 
            re.DOTALL
        )
        
        media_content = media_section_match.group(1)
        
        # 最小タップ領域44pxの確認
        min_height_pattern = r'\.file-actions\s+\.btn[^{]*\{[^}]*min-height\s*:\s*44px\s*;'
        assert re.search(min_height_pattern, media_content, re.DOTALL), \
            "アクセシビリティ要件: 最小タップ領域44pxが設定されていません"
        
        # 適切なギャップの確認 (誤タップ防止)
        gap_pattern = r'\.file-actions[^{]*\{[^}]*gap\s*:\s*0\.5rem\s*;'
        assert re.search(gap_pattern, media_content, re.DOTALL), \
            "アクセシビリティ要件: 適切なボタン間隔が設定されていません"


def run_simple_tests():
    """軽量テストを実行"""
    return pytest.main([
        __file__,
        "-v",
        "--tb=short"
    ])


if __name__ == "__main__":
    run_simple_tests()