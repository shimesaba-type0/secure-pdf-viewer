#!/usr/bin/env python3
"""
Phase 2: .form-actions ボタンのブラウザレスポンシブテスト

手動ブラウザテスト用のチェックリスト生成
"""


def print_test_checklist():
    """ブラウザテスト用のチェックリストを出力"""

    print("=== Phase 2: .form-actions レスポンシブテスト チェックリスト ===\n")

    print("🌐 テスト対象URL:")
    print("   http://localhost:5001/admin (管理者でログイン)")
    print()

    print("📱 テスト解像度:")
    test_widths = [320, 480, 768, 1024, 1200]
    for width in test_widths:
        print(f"   - {width}px幅")
    print()

    print("🔍 テスト対象セクション:")
    sections = ["パスフレーズ更新フォーム", "パスワード変更フォーム", "削除設定フォーム", "PDF削除フォーム"]
    for i, section in enumerate(sections, 1):
        print(f"   {i}. {section}")
    print()

    print("✅ チェック項目 (768px以下):")
    checklist = [
        "フォームボタンが縦に配置されている",
        "ボタンが横幅いっぱいに表示されている",
        "ボタンの高さが44px以上でタップしやすい",
        "ボタン間の間隔が適切 (0.75rem)",
        "フォントサイズが16px (iOS zoom防止)",
        "ボタンテキストが読みやすい",
    ]
    for i, item in enumerate(checklist, 1):
        print(f"   □ {i}. {item}")
    print()

    print("✅ チェック項目 (769px以上):")
    desktop_checklist = [
        "フォームボタンが横に配置されている",
        "デスクトップ表示が変更前と同じ",
        "ボタンサイズが適切",
        "既存機能が正常動作",
    ]
    for i, item in enumerate(desktop_checklist, 1):
        print(f"   □ {i}. {item}")
    print()

    print("🔧 ブラウザ開発者ツールでの確認方法:")
    print("   1. F12でDevToolsを開く")
    print("   2. デバイスエミュレーションモードに切り替え")
    print("   3. 各解像度でテスト")
    print("   4. Elementsタブで.form-actionsスタイル確認")
    print()

    print("🎯 期待される動作:")
    print("   - 768px以下: ボタンが縦配置でフル幅")
    print("   - 769px以上: 既存の横配置を維持")
    print("   - 全解像度: ボタンが正常にクリック可能")


def print_css_verification():
    """CSS確認用の情報を出力"""

    print("\n=== CSS確認用情報 ===\n")

    print("📄 実装されたCSS (main.css 末尾):")
    css_code = """
@media (max-width: 768px) {
    .form-actions {
        flex-direction: column;    /* 縦配置に変更 */
        gap: 0.75rem;             /* ボタン間隔を調整 */
        align-items: stretch;     /* ボタンを横幅いっぱいに */
    }

    .form-actions .btn {
        width: 100%;              /* フル幅でタップしやすく */
        min-height: 44px;         /* タップ領域確保 */
        padding: 12px 16px;       /* 内側余白調整 */
        font-size: 16px;          /* iOS zoom防止 */
    }
}"""
    print(css_code)

    print("\n🔍 DevToolsでの確認ポイント:")
    properties = [
        ("flex-direction", "column (768px以下)"),
        ("gap", "0.75rem (768px以下)"),
        ("align-items", "stretch (768px以下)"),
        ("width", "100% (768px以下のbtn)"),
        ("min-height", "44px (768px以下のbtn)"),
        ("font-size", "16px (768px以下のbtn)"),
    ]

    for prop, expected in properties:
        print(f"   - {prop}: {expected}")


if __name__ == "__main__":
    print_test_checklist()
    print_css_verification()

    print("\n" + "=" * 60)
    print("手動テスト完了後、結果をこのスクリプトと共に記録してください。")
    print("=" * 60)
