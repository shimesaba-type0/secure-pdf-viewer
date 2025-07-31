#!/usr/bin/env python3
"""
320px幅対応の簡易検証スクリプト
"""

import os


def validate_320px_simple():
    """320px幅対応の簡易検証"""
    
    css_path = os.path.join('static', 'css', 'main.css')
    
    if not os.path.exists(css_path):
        print("❌ main.cssファイルが見つかりません")
        return False
    
    with open(css_path, 'r', encoding='utf-8') as f:
        css_content = f.read()
    
    print("=== 320px幅対応 簡易検証 ===\n")
    
    # 基本チェック
    checks = [
        ("320px幅対応コメント", "320px幅対応: 超小画面での表示改善"),
        ("480px以下メディアクエリ", "@media (max-width: 480px)"),
        (".card padding修正", ".card {\n        padding: 0.75rem;"),
        (".rate-limit-stats修正", ".rate-limit-stats {\n        grid-template-columns: 1fr;"),
        (".rate-limit-settings修正", ".rate-limit-settings {\n        grid-template-columns: 1fr;"),
        (".incident-stats修正", ".incident-stats {\n        flex-direction: column;"),
        (".pdf-security-container修正", ".pdf-security-container {\n        padding: 8px;"),
        (".security-log-table修正", ".security-log-table {\n        display: block;\n        overflow-x: auto;")
    ]
    
    success = True
    
    for name, pattern in checks:
        if pattern in css_content:
            print(f"✅ {name}")
        else:
            print(f"❌ {name}")
            success = False
    
    # CSS構文チェック
    open_braces = css_content.count('{')
    close_braces = css_content.count('}')
    
    if open_braces == close_braces:
        print(f"✅ CSS構文: 括弧の対応が正しい ({open_braces}個)")
    else:
        print(f"❌ CSS構文: 括弧の対応エラー ({{ {open_braces}個, }} {close_braces}個)")
        success = False
    
    print(f"\n=== 検証結果: {'✅ 成功' if success else '❌ 失敗'} ===")
    return success


def print_test_summary():
    """テスト結果サマリーを出力"""
    
    print("\n" + "="*60)
    print("320px幅対応 実装サマリー")
    print("="*60)
    
    print("\n📱 対応内容:")
    fixes = [
        ".card: padding を 1.5rem (24px) → 0.75rem (12px) に削減",
        "rate-limit-stats: grid を 1カラムに変更",
        "rate-limit-settings: grid を 1カラムに変更", 
        "incident-stats: flexbox を縦並びに変更",
        "pdf-security-container: padding を 20px → 8px に削減",
        "security-log-table: 横スクロール対応 (min-width: 600px)"
    ]
    
    for i, fix in enumerate(fixes, 1):
        print(f"  {i}. {fix}")
    
    print("\n🔍 ブラウザテスト:")
    print("  1. http://localhost:5001/admin にアクセス")
    print("  2. 開発者ツール → デバイスエミュレーション → 320px幅")
    print("  3. 各セクションが横にはみ出さないことを確認")
    
    print("\n✅ 期待される改善:")
    print("  - 横スクロールが不要になる")
    print("  - コンテンツが見やすく配置される")
    print("  - テーブルのみ横スクロール対応")


if __name__ == "__main__":
    success = validate_320px_simple()
    print_test_summary()
    
    if success:
        print("\n🎉 320px幅対応の実装が正常に完了しました!")
    else:
        print("\n⚠️  実装の確認が必要です。")