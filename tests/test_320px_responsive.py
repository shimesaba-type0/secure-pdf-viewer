#!/usr/bin/env python3
"""
320px幅レスポンシブ対応の検証スクリプト
"""

import os
import re


def validate_320px_responsive():
    """320px幅対応のCSS実装を検証"""
    
    css_path = os.path.join('static', 'css', 'main.css')
    
    if not os.path.exists(css_path):
        print("❌ main.cssファイルが見つかりません")
        return False
    
    with open(css_path, 'r', encoding='utf-8') as f:
        css_content = f.read()
    
    print("=== 320px幅対応レスポンシブ実装検証 ===\n")
    
    success = True
    
    # 1. 480px以下のメディアクエリ存在確認
    media_480px = re.findall(r'@media\s*\([^)]*max-width:\s*480px[^)]*\)', css_content)
    print(f"✅ 480px以下メディアクエリ: {len(media_480px)}個発見")
    
    # 2. 最新の480px以下メディアクエリセクションの内容確認
    media_sections = list(re.finditer(
        r'@media\s*\([^)]*max-width:\s*480px[^)]*\)\s*\{(.*?)\}',
        css_content, re.DOTALL
    ))
    
    if not media_sections:
        print("❌ 480px以下のメディアクエリセクションが見つかりません")
        return False
    
    # 最新のセクション（今回追加したもの）を確認
    latest_section = media_sections[-1]
    section_content = latest_section.group(1)
    
    # 3. 各修正項目の確認
    fixes_to_check = {
        '.rate-limit-stats': {
            'grid-template-columns': '1fr',
            'padding': '0.75rem'
        },
        '.rate-limit-settings': {
            'grid-template-columns': '1fr',
            'padding': '0.75rem'
        },
        '.incident-stats': {
            'flex-direction': 'column',
            'gap': '1rem',
            'padding': '0.75rem'
        },
        '.pdf-security-container': {
            'padding': '10px'
        },
        '.security-log-table': {
            'display': 'block',
            'overflow-x': 'auto',
            'min-width': '600px'
        }
    }
    
    print("\n修正項目の確認:")
    
    for class_name, expected_props in fixes_to_check.items():
        if class_name in section_content:
            print(f"  ✅ {class_name} を発見")
            
            # 各プロパティの確認
            for prop, expected_value in expected_props.items():
                pattern = rf'{re.escape(class_name)}[^{{]*\{{[^}}]*{re.escape(prop)}\s*:\s*{re.escape(expected_value)}'
                if re.search(pattern, section_content, re.DOTALL):
                    print(f"    ✅ {prop}: {expected_value}")
                else:
                    print(f"    ❌ {prop}: {expected_value} が見つかりません")
                    success = False
        else:
            print(f"  ❌ {class_name} が見つかりません")
            success = False
    
    print(f"\n=== 検証結果: {'✅ 成功' if success else '❌ 失敗'} ===")
    return success


def print_browser_test_guide():
    """ブラウザテスト用ガイドを出力"""
    
    print("\n" + "="*60)
    print("320px幅ブラウザテスト ガイド")
    print("="*60)
    
    print("\n🌐 テスト手順:")
    print("  1. http://localhost:5001/admin にアクセス")
    print("  2. F12で開発者ツールを開く")
    print("  3. デバイスエミュレーションモードに切り替え")
    print("  4. 画面幅を320pxに設定")
    
    print("\n✅ 確認項目:")
    test_items = [
        "rate-limit-stats が1カラム表示になっている",
        "stat-item が横にはみ出していない",
        "rate-limit-settings が1カラム表示になっている", 
        "setting-item が横にはみ出していない",
        "incident-stats が縦並び表示になっている",
        "PDFセキュリティ設定のpaddingが削減されている",
        "security-log-table が横スクロール可能",
        "全体的にコンテンツが320px幅に収まっている"
    ]
    
    for i, item in enumerate(test_items, 1):
        print(f"  □ {i}. {item}")
    
    print("\n🔧 修正内容の詳細:")
    print("  - .rate-limit-stats: grid-template-columns: 1fr")
    print("  - .rate-limit-settings: grid-template-columns: 1fr")
    print("  - .incident-stats: flex-direction: column")
    print("  - .pdf-security-container: padding: 10px")
    print("  - .security-log-table: overflow-x: auto, min-width: 600px")


if __name__ == "__main__":
    success = validate_320px_responsive()
    print_browser_test_guide()
    
    if success:
        print("\n🎉 320px幅対応の実装が完了しました!")
        print("ブラウザでの動作確認をお願いします。")
    else:
        print("\n⚠️  実装に問題があります。修正が必要です。")