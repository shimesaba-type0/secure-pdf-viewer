#!/usr/bin/env python3
"""
SSE統一管理システム 統合テストランナー

このスクリプトは以下のテストを順番に実行します：
1. サーバーサイド SSE テスト
2. クライアントサイド SSE Manager テスト  
3. 統合テスト
4. パフォーマンステスト
5. 手動テストガイド

使用方法:
    python tests/run_sse_tests.py
    python tests/run_sse_tests.py --verbose
    python tests/run_sse_tests.py --performance-only
"""

import sys
import os
import argparse
import subprocess
import time
from pathlib import Path

# プロジェクトルートディレクトリをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def print_banner(text, char="="):
    """バナーを表示"""
    width = 60
    print(f"\n{char * width}")
    print(f"{text:^{width}}")
    print(f"{char * width}")

def run_test_file(test_file, description):
    """個別のテストファイルを実行"""
    print_banner(f"{description} 実行中", "-")
    
    try:
        start_time = time.time()
        result = subprocess.run([
            sys.executable, str(project_root / "tests" / test_file)
        ], capture_output=True, text=True, cwd=project_root)
        
        execution_time = time.time() - start_time
        
        print(f"実行時間: {execution_time:.2f}秒")
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"テスト実行中にエラーが発生しました: {e}")
        return False

def run_manual_test_guide():
    """手動テストガイドを表示"""
    print_banner("手動テストガイド")
    
    manual_tests = """
🔧 手動テスト項目

1. SSE接続の基本確認
   - アプリケーションを起動: python app.py
   - ブラウザで http://localhost:5000 にアクセス
   - 認証してログイン
   - 開発者ツール → Network → EventStream で /api/events 接続を確認

2. セッション無効化テスト
   - 管理画面でセッション無効化スケジュールを設定
   - 設定時刻になったときの自動リダイレクトを確認
   - 手動でセッション無効化を実行して即座リダイレクトを確認

3. PDF公開/停止イベントテスト
   - 管理画面でPDFファイルを公開
   - ビューワーページでリアルタイム更新を確認
   - PDFファイルを停止
   - ビューワーページでリアルタイム更新を確認

4. 複数タブでの動作確認
   - 複数のブラウザタブで同じページを開く
   - 1つのタブで操作（PDF公開など）
   - 他のタブでリアルタイム更新されることを確認

5. ページ遷移時の接続確認
   - 管理画面 → ビューワー → 管理画面 のページ遷移
   - サーバーログでSSEクライアント数の変動を確認
   - 一時的に増加後、適切に減少することを確認

6. ネットワーク切断テスト
   - Wi-Fi/ネットワークを一時的に切断
   - 復旧後の自動再接続を確認

7. 長時間接続テスト
   - ページを長時間開いたまま放置
   - ハートビート機能による接続維持を確認
   - タイムアウト後の自動再接続を確認

🛠️ テスト確認ポイント:

✅ SSE接続が適切に確立される
✅ イベントがリアルタイムで配信される
✅ ページ遷移で接続が適切に管理される
✅ セッション無効化で確実にリダイレクトされる
✅ 複数クライアント間でイベントが同期される
✅ 接続エラー時に適切に再接続される
✅ メモリリークや接続蓄積が発生しない

📋 ログ確認コマンド:
    tail -f logs/app.log | grep SSE
    
📊 パフォーマンス確認:
    - 同時接続数: 管理画面で表示される値
    - メモリ使用量: htop, psコマンド
    - CPU使用率: topコマンド
"""
    
    print(manual_tests)

def check_prerequisites():
    """前提条件をチェック"""
    print_banner("前提条件チェック")
    
    # 必要なファイルの存在確認
    required_files = [
        "app.py",
        "static/js/sse-manager.js",
        "static/js/admin.js",
        "static/js/pdf-viewer.js",
        "tests/test_sse_unified_management.py",
        "tests/test_sse_client_side.py"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not (project_root / file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ 以下のファイルが見つかりません:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    
    print("✅ 必要なファイルがすべて存在します")
    
    # Python モジュールの確認
    try:
        import flask
        import sqlite3
        print("✅ 必要なPythonモジュールがインストールされています")
    except ImportError as e:
        print(f"❌ 必要なPythonモジュールが不足しています: {e}")
        return False
    
    return True

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description="SSE統一管理システム テストランナー")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細出力")
    parser.add_argument("--performance-only", "-p", action="store_true", help="パフォーマンステストのみ実行")
    parser.add_argument("--manual-guide", "-m", action="store_true", help="手動テストガイドのみ表示")
    parser.add_argument("--skip-prerequisites", action="store_true", help="前提条件チェックをスキップ")
    
    args = parser.parse_args()
    
    print_banner("SSE統一管理システム テストスイート")
    print(f"開始時刻: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if args.manual_guide:
        run_manual_test_guide()
        return
    
    # 前提条件チェック
    if not args.skip_prerequisites:
        if not check_prerequisites():
            print("❌ 前提条件チェックに失敗しました")
            sys.exit(1)
    
    results = {}
    
    if not args.performance_only:
        # サーバーサイドテスト
        results["server_side"] = run_test_file(
            "test_sse_unified_management.py",
            "サーバーサイド SSE テスト"
        )
        
        # クライアントサイドテスト
        results["client_side"] = run_test_file(
            "test_sse_client_side.py", 
            "クライアントサイド SSE Manager テスト"
        )
    else:
        print_banner("パフォーマンステストのみ実行")
        
        # パフォーマンステストのみ実行
        print("サーバーサイド パフォーマンステスト:")
        run_test_file("test_sse_unified_management.py", "サーバーサイド パフォーマンス")
        
        print("\nクライアントサイド パフォーマンステスト:")
        run_test_file("test_sse_client_side.py", "クライアントサイド パフォーマンス")
    
    # 結果サマリー
    print_banner("テスト結果サマリー")
    
    if not args.performance_only:
        total_tests = len(results)
        passed_tests = sum(1 for result in results.values() if result)
        
        print(f"実行テストスイート数: {total_tests}")
        print(f"成功: {passed_tests}")
        print(f"失敗: {total_tests - passed_tests}")
        print(f"成功率: {passed_tests/total_tests*100:.1f}%")
        
        print("\n詳細結果:")
        for test_name, result in results.items():
            status = "✅ 成功" if result else "❌ 失敗"
            print(f"  {test_name}: {status}")
        
        if all(results.values()):
            print("\n🎉 全テストスイートが成功しました！")
        else:
            print("\n❌ 一部のテストスイートが失敗しました")
            
        # 次のステップ
        print_banner("次のステップ")
        if all(results.values()):
            print("🚀 手動テストを実行してください:")
            print("   python tests/run_sse_tests.py --manual-guide")
            print("\n📋 実際のアプリケーションでの動作確認:")
            print("   1. python app.py でアプリケーションを起動")
            print("   2. ブラウザで動作確認")
            print("   3. 開発者ツールでSSE接続を監視")
        else:
            print("🔧 失敗したテストを確認して修正してください")
    
    print(f"\n終了時刻: {time.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()