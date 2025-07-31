#!/usr/bin/env python3
"""
初期パスフレーズセットアップスクリプト
"""
import sqlite3
import sys
import os
from database.models import create_tables, insert_initial_data
from auth.passphrase import PassphraseManager

def setup_initial_passphrase():
    """初期パスフレーズをセットアップ"""
    
    # データベースファイルの確認
    db_path = 'instance/database.db'
    
    if not os.path.exists('instance'):
        os.makedirs('instance')
    
    # データベース接続
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        # テーブル作成
        create_tables(conn)
        
        # 既存のパスフレーズ設定を確認
        existing_passphrase = conn.execute(
            'SELECT value FROM settings WHERE key = "shared_passphrase"'
        ).fetchone()
        
        if existing_passphrase:
            print("既存のパスフレーズ設定が見つかりました。")
            choice = input("新しいパスフレーズを設定しますか？ (y/N): ")
            if choice.lower() != 'y':
                print("セットアップを中止します。")
                return
        
        # 初期データ挿入（パスフレーズ含む）
        insert_initial_data(conn)
        
        # 設定を保存
        conn.commit()
        
        print("\n" + "="*50)
        print("初期セットアップが完了しました！")
        print("="*50)
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        conn.rollback()
        sys.exit(1)
    
    finally:
        conn.close()

def set_custom_passphrase():
    """カスタムパスフレーズを設定"""
    
    print("カスタムパスフレーズを設定します。")
    print("要件: 32-128文字、0-9a-zA-Z_-のみ使用可能")
    
    passphrase = input("新しいパスフレーズを入力してください: ")
    confirm = input("確認のためもう一度入力してください: ")
    
    if passphrase != confirm:
        print("パスフレーズが一致しません。")
        return False
    
    # データベース接続
    conn = sqlite3.connect('instance/database.db')
    
    try:
        # PassphraseManagerでバリデーションと設定
        manager = PassphraseManager(conn)
        manager.update_passphrase(passphrase)
        conn.commit()
        
        print("パスフレーズが正常に設定されました。")
        return True
        
    except ValueError as e:
        print(f"無効なパスフレーズです: {e}")
        return False
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("Secure PDF Viewer - 初期パスフレーズセットアップ")
    print("=" * 50)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--custom":
        # カスタムパスフレーズ設定モード
        set_custom_passphrase()
    else:
        # 通常の初期セットアップ
        setup_initial_passphrase()
        
        # カスタムパスフレーズ設定オプション
        choice = input("\nカスタムパスフレーズを設定しますか？ (y/N): ")
        if choice.lower() == 'y':
            set_custom_passphrase()