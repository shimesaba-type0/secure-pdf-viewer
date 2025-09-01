"""
Phase 2 レスポンシブUI改善のテストスイート
.form-actionsクラスのモバイル対応テスト

関連: TASK-017, docs/responsive-ui-improvement-design.md
"""

import pytest
import re
import os


class TestResponsiveUIPhase2:
    """Phase 2: .form-actions フォームボタンのレスポンシブ対応テスト"""

    @pytest.fixture
    def css_content(self):
        """CSS ファイルの内容を読み込む"""
        css_path = os.path.join(
            os.path.dirname(__file__), "..", "static", "css", "main.css"
        )
        with open(css_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_css_syntax_validation(self, css_content):
        """CSS構文の基本検証"""
        # 括弧の対応チェック
        open_braces = css_content.count("{")
        close_braces = css_content.count("}")

        assert (
            open_braces == close_braces
        ), f"括弧の対応エラー: {{ は {open_braces}個, }} は {close_braces}個"

    def test_form_actions_responsive_rules_exist(self, css_content):
        """form-actions のレスポンシブルールが存在することを確認"""
        # 768px以下のメディアクエリが存在することを確認
        media_query_exists = "@media (max-width: 768px)" in css_content
        assert media_query_exists, "768px以下のメディアクエリが見つかりません"

        # メディアクエリ内に .form-actions ルールが存在することを確認
        media_sections = re.findall(
            r"@media\s*\([^)]*max-width:\s*768px[^)]*\)\s*\{(.*?)\}(?=\s*(?:@media|$|/\*))",
            css_content,
            re.DOTALL,
        )

        form_actions_found = False
        for section in media_sections:
            if ".form-actions" in section:
                form_actions_found = True
                break

        assert form_actions_found, "768px以下のメディアクエリ内に .form-actions ルールが見つかりません"

    def test_form_actions_properties_exist(self, css_content):
        """form-actions に必要なプロパティが存在することを確認"""
        # 768px以下のメディアクエリセクションを全て取得
        media_sections = re.findall(
            r"@media\s*\([^)]*max-width:\s*768px[^)]*\)\s*\{(.*?)\}(?=\s*(?:@media|$|/\*))",
            css_content,
            re.DOTALL,
        )

        # form-actionsを含むセクションを探す
        form_actions_section = None
        for section in media_sections:
            if ".form-actions" in section:
                form_actions_section = section
                break

        assert form_actions_section, "768px以下のメディアクエリ内に .form-actions が見つかりません"

        # 必要なプロパティをチェック
        required_properties = [
            "flex-direction",
            "gap",
            "align-items",
            "width",
            "min-height",
            "padding",
            "font-size",
        ]

        for prop in required_properties:
            # .form-actions または .form-actions .btn のいずれかに存在するかチェック
            pattern = rf"\.form-actions[^{{]*\{{[^}}]*{re.escape(prop)}\s*:[^;]+;"
            btn_pattern = (
                rf"\.form-actions\s+\.btn[^{{]*\{{[^}}]*{re.escape(prop)}\s*:[^;]+;"
            )

            found = re.search(pattern, form_actions_section, re.DOTALL) or re.search(
                btn_pattern, form_actions_section, re.DOTALL
            )

            assert found, f"必要なプロパティ '{prop}' が見つかりません"

    def test_form_actions_values_validation(self, css_content):
        """form-actions の値が適切であることを確認"""
        # 768px以下のメディアクエリ内容を取得
        media_sections = re.findall(
            r"@media\s*\([^)]*max-width:\s*768px[^)]*\)\s*\{(.*?)\}(?=\s*(?:@media|$|/\*))",
            css_content,
            re.DOTALL,
        )

        form_actions_section = None
        for section in media_sections:
            if ".form-actions" in section:
                form_actions_section = section
                break

        assert form_actions_section, "form-actionsセクションが見つかりません"

        # 値の検証
        test_cases = [
            ("flex-direction", "column", ".form-actions"),
            ("gap", "0.75rem", ".form-actions"),
            ("align-items", "stretch", ".form-actions"),
            ("width", "100%", ".form-actions .btn"),
            ("min-height", "44px", ".form-actions .btn"),
            ("padding", "12px 16px", ".form-actions .btn"),
            ("font-size", "16px", ".form-actions .btn"),
        ]

        for prop, expected_value, selector in test_cases:
            if selector == ".form-actions":
                pattern = rf"\.form-actions[^{{]*\{{[^}}]*{re.escape(prop)}\s*:\s*{re.escape(expected_value)}\s*;"
            else:  # .form-actions .btn
                pattern = rf"\.form-actions\s+\.btn[^{{]*\{{[^}}]*{re.escape(prop)}\s*:\s*{re.escape(expected_value)}\s*;"

            assert re.search(
                pattern, form_actions_section, re.DOTALL
            ), f"{selector} の {prop} プロパティが期待値 '{expected_value}' ではありません"

    def test_base_form_actions_preserved(self, css_content):
        """既存の基本 .form-actions スタイルが保持されていることを確認"""
        # メディアクエリ外での基本的な .form-actions スタイル
        base_pattern = r"\.form-actions\s*\{[^}]*display\s*:\s*flex[^}]*\}"

        assert re.search(
            base_pattern, css_content, re.DOTALL
        ), "基本の .form-actions スタイル (display: flex) が見つかりません"

        # 基本的なプロパティが存在することを確認
        base_properties = ["margin-top", "gap", "flex-wrap"]

        for prop in base_properties:
            pattern = rf"\.form-actions\s*\{{[^}}]*{re.escape(prop)}\s*:[^;]+;"
            assert re.search(
                pattern, css_content, re.DOTALL
            ), f"基本の .form-actions プロパティ '{prop}' が見つかりません"

    def test_accessibility_compliance(self, css_content):
        """アクセシビリティ要件の確認"""
        media_sections = re.findall(
            r"@media\s*\([^)]*max-width:\s*768px[^)]*\)\s*\{(.*?)\}(?=\s*(?:@media|$|/\*))",
            css_content,
            re.DOTALL,
        )

        form_actions_section = None
        for section in media_sections:
            if ".form-actions" in section:
                form_actions_section = section
                break

        assert form_actions_section, "form-actionsセクションが見つかりません"

        # 最小タップ領域44pxの確認
        min_height_pattern = (
            r"\.form-actions\s+\.btn[^{]*\{[^}]*min-height\s*:\s*44px\s*;"
        )
        assert re.search(
            min_height_pattern, form_actions_section, re.DOTALL
        ), "アクセシビリティ要件: 最小タップ領域44pxが設定されていません"

        # iOS zoom防止のフォントサイズ16px確認
        font_size_pattern = (
            r"\.form-actions\s+\.btn[^{]*\{[^}]*font-size\s*:\s*16px\s*;"
        )
        assert re.search(
            font_size_pattern, form_actions_section, re.DOTALL
        ), "アクセシビリティ要件: iOS zoom防止のため16pxフォントサイズが設定されていません"

        # 適切なギャップの確認 (誤タップ防止)
        gap_pattern = r"\.form-actions[^{]*\{[^}]*gap\s*:\s*0\.75rem\s*;"
        assert re.search(
            gap_pattern, form_actions_section, re.DOTALL
        ), "アクセシビリティ要件: 適切なボタン間隔(0.75rem)が設定されていません"

    def test_responsive_layout_structure(self, css_content):
        """レスポンシブレイアウト構造の確認"""
        media_sections = re.findall(
            r"@media\s*\([^)]*max-width:\s*768px[^)]*\)\s*\{(.*?)\}(?=\s*(?:@media|$|/\*))",
            css_content,
            re.DOTALL,
        )

        form_actions_section = None
        for section in media_sections:
            if ".form-actions" in section:
                form_actions_section = section
                break

        # 縦配置の確認
        flex_direction_pattern = (
            r"\.form-actions[^{]*\{[^}]*flex-direction\s*:\s*column\s*;"
        )
        assert re.search(
            flex_direction_pattern, form_actions_section, re.DOTALL
        ), "モバイルでの縦配置 (flex-direction: column) が設定されていません"

        # フル幅ボタンの確認
        width_pattern = r"\.form-actions\s+\.btn[^{]*\{[^}]*width\s*:\s*100%\s*;"
        assert re.search(
            width_pattern, form_actions_section, re.DOTALL
        ), "フル幅ボタン (width: 100%) が設定されていません"

        # ストレッチ配置の確認
        align_items_pattern = r"\.form-actions[^{]*\{[^}]*align-items\s*:\s*stretch\s*;"
        assert re.search(
            align_items_pattern, form_actions_section, re.DOTALL
        ), "ストレッチ配置 (align-items: stretch) が設定されていません"

    def test_no_desktop_impact(self, css_content):
        """デスクトップ表示に影響がないことを確認"""
        # メディアクエリ外での基本的な .form-actions スタイルが維持されていることを確認
        base_style_pattern = r"\.form-actions\s*\{[^}]*\}"
        base_styles = re.findall(base_style_pattern, css_content, re.DOTALL)

        # 少なくとも1つの基本スタイルが存在することを確認
        assert len(base_styles) > 0, "基本的な .form-actions スタイルが見つかりません"

        # 基本スタイルにflexが含まれていることを確認
        base_content = "".join(base_styles)
        assert (
            "display" in base_content and "flex" in base_content
        ), "基本スタイルでのdisplay: flexが維持されていません"


def run_phase2_tests():
    """Phase 2テストを実行"""
    return pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_phase2_tests()
