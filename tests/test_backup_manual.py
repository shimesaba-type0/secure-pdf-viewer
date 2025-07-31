#!/usr/bin/env python3
"""
BackupManager手動動作確認スクリプト
"""
import os
import sys
import tempfile
import sqlite3
import tarfile
import json

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(__file__))

from database.backup import BackupManager


def test_backup_creation():
    """バックアップ作成の動作確認"""
    print("=== BackupManager 動作確認開始 ===")
    
    # テスト用ディレクトリ作成
    test_dir = tempfile.mkdtemp()
    print(f"テスト用ディレクトリ: {test_dir}")
    
    try:
        # テスト用データベース作成
        db_path = os.path.join(test_dir, 'test.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT,
                created_at TEXT
            )
        ''')
        cursor.execute('''
            INSERT INTO test_table (name, created_at) 
            VALUES ('Test Data', '2025-01-01 10:00:00')
        ''')
        conn.commit()
        conn.close()
        print("✓ テスト用データベース作成完了")
        
        # テスト用.envファイル作成
        env_path = os.path.join(test_dir, '.env')
        with open(env_path, 'w') as f:
            f.write('''SECRET_KEY=test_secret_123
DATABASE_URL=sqlite:///test.db
API_KEY=sensitive_key_456
NORMAL_VALUE=not_sensitive
''')
        print("✓ テスト用.envファイル作成完了")
        
        # テスト用PDFディレクトリ作成
        pdf_dir = os.path.join(test_dir, 'pdfs')
        os.makedirs(pdf_dir, exist_ok=True)
        with open(os.path.join(pdf_dir, 'test.pdf'), 'wb') as f:
            f.write(b'%PDF-1.4\nTest PDF content\n%%EOF')
        print("✓ テスト用PDFファイル作成完了")
        
        # テスト用ログファイル作成
        logs_dir = os.path.join(test_dir, 'logs')
        instance_dir = os.path.join(test_dir, 'instance')
        os.makedirs(logs_dir, exist_ok=True)
        os.makedirs(instance_dir, exist_ok=True)
        
        with open(os.path.join(logs_dir, 'app.log'), 'w') as f:
            f.write('2025-01-01 10:00:00 INFO Test log entry\n')
        
        with open(os.path.join(instance_dir, 'emergency_log.txt'), 'w') as f:
            f.write('2025-01-01 10:00:00 EMERGENCY Test emergency\n')
        print("✓ テスト用ログファイル作成完了")
        
        # BackupManager初期化
        backup_dir = os.path.join(test_dir, 'backups')
        backup_manager = BackupManager(
            db_path=db_path,
            backup_dir=backup_dir,
            env_path=env_path,
            pdf_dir=pdf_dir,
            logs_dir=logs_dir,
            instance_dir=instance_dir
        )
        print("✓ BackupManager初期化完了")
        
        # バックアップ作成
        print("\n--- バックアップ作成開始 ---")
        backup_name = backup_manager.create_backup()
        print(f"✓ バックアップ作成完了: {backup_name}")
        
        # バックアップファイル確認
        backup_file = os.path.join(backup_dir, 'manual', f'{backup_name}.tar.gz')
        if os.path.exists(backup_file):
            file_size = os.path.getsize(backup_file)
            print(f"✓ バックアップファイル存在確認: {backup_file} (サイズ: {file_size} bytes)")
        else:
            print("✗ バックアップファイルが見つかりません")
            return False
        
        # メタデータファイル確認
        metadata_file = os.path.join(backup_dir, 'metadata', f'{backup_name}.json')
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            print(f"✓ メタデータファイル確認: {metadata['files_count']} ファイル")
            print(f"  - バックアップタイプ: {metadata['type']}")
            print(f"  - チェックサム: {metadata['checksum'][:20]}...")
        else:
            print("✗ メタデータファイルが見つかりません")
            return False
        
        # アーカイブ内容確認
        print("\n--- アーカイブ内容確認 ---")
        with tarfile.open(backup_file, 'r:gz') as tar:
            members = tar.getnames()
            print(f"✓ アーカイブ内ファイル数: {len(members)}")
            for member in sorted(members):
                print(f"  - {member}")
        
        # バックアップ一覧取得テスト
        print("\n--- バックアップ一覧取得テスト ---")
        backups = backup_manager.list_backups()
        print(f"✓ バックアップ一覧取得: {len(backups)} 件")
        for backup in backups:
            print(f"  - {backup['backup_name']} ({backup['type']}, {backup['size']} bytes)")
        
        # 機密情報マスク確認
        print("\n--- 機密情報マスク確認 ---")
        with tarfile.open(backup_file, 'r:gz') as tar:
            for member in tar.getmembers():
                if member.name.endswith('.env'):
                    env_content = tar.extractfile(member).read().decode('utf-8')
                    print("✓ .envファイル内容:")
                    for line in env_content.strip().split('\n'):
                        print(f"  {line}")
                    
                    if 'SECRET_KEY=***MASKED***' in env_content:
                        print("✓ 機密情報マスク処理確認: SECRET_KEY")
                    if 'API_KEY=***MASKED***' in env_content:
                        print("✓ 機密情報マスク処理確認: API_KEY")
                    if 'NORMAL_VALUE=not_sensitive' in env_content:
                        print("✓ 通常値保持確認: NORMAL_VALUE")
        
        print("\n=== 全ての動作確認が完了しました ===")
        return True
        
    except Exception as e:
        print(f"✗ エラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # クリーンアップ
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)
        print(f"テスト用ディレクトリを削除: {test_dir}")


if __name__ == '__main__':
    success = test_backup_creation()
    if success:
        print("\n✅ BackupManager動作確認成功！")
        sys.exit(0)
    else:
        print("\n❌ BackupManager動作確認失敗")
        sys.exit(1)