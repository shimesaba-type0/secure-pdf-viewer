"""
タイムゾーン統一実装の適用状況を監査するテスト

このテストは、タイムゾーン統一システムが実際にコードベース全体で
適用されているかどうかを検証します。
"""
import os
import re
import ast
import pytest
import subprocess
from pathlib import Path


class TestTimezoneImplementationAudit:
    """タイムゾーン統一実装の監査テスト"""
    
    @pytest.fixture
    def project_root(self):
        """プロジェクトルートディレクトリを取得"""
        current_dir = Path(__file__).parent
        return current_dir.parent
    
    @pytest.fixture
    def python_files(self, project_root):
        """プロジェクト内のPythonファイル一覧を取得"""
        python_files = []
        for root, dirs, files in os.walk(project_root):
            # テストディレクトリ、仮想環境、キャッシュディレクトリはスキップ
            dirs[:] = [d for d in dirs if d not in ['venv', '__pycache__', '.pytest_cache', 'node_modules', '.git']]
            
            for file in files:
                if file.endswith('.py'):
                    file_path = Path(root) / file
                    python_files.append(file_path)
        
        return python_files
    
    def test_no_direct_current_timestamp_usage(self, python_files):
        """
        CURRENT_TIMESTAMPの直接使用がないことを確認
        
        タイムゾーン統一システムでは、CURRENT_TIMESTAMPではなく
        get_app_datetime_string()を使用する必要がある
        """
        violations = []
        
        for file_path in python_files:
            # テストファイル自体とタイムゾーンユーティリティファイルはスキップ
            if 'test_' in file_path.name or 'timezone_utils.py' in file_path.name:
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # CURRENT_TIMESTAMPの使用をチェック
                if 'CURRENT_TIMESTAMP' in content:
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if 'CURRENT_TIMESTAMP' in line:
                            violations.append({
                                'file': str(file_path.relative_to(file_path.parents[len(file_path.parents)-1])),
                                'line': i,
                                'content': line.strip()
                            })
            except Exception as e:
                # ファイル読み取りエラーは記録するが、テストは継続
                print(f"Warning: Could not read {file_path}: {e}")
        
        # 違反があった場合は詳細情報と共にテスト失敗
        if violations:
            violation_details = "\n".join([
                f"  {v['file']}:{v['line']} - {v['content']}"
                for v in violations
            ])
            pytest.fail(
                f"Found {len(violations)} direct CURRENT_TIMESTAMP usage(s):\n"
                f"{violation_details}\n"
                f"Use get_app_datetime_string() instead for timezone consistency."
            )
    
    def test_timezone_helper_import_consistency(self, python_files):
        """
        データベース操作を行うファイルでタイムゾーン統一関数のインポートを確認
        
        データベースにタイムスタンプを書き込むファイルでは、
        タイムゾーン統一関数をインポートして使用する必要がある
        """
        db_operation_files = []
        missing_imports = []
        
        for file_path in python_files:
            # テストファイルはスキップ
            if 'test_' in file_path.name or 'timezone' in file_path.name:
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # データベース操作の兆候をチェック
                db_indicators = [
                    'execute(',
                    'INSERT INTO',
                    'UPDATE ',
                    'CREATE TABLE',
                    'sqlite3',
                    'cursor(',
                    '.commit()',
                    'TIMESTAMP'
                ]
                
                has_db_operations = any(indicator in content for indicator in db_indicators)
                
                if has_db_operations:
                    db_operation_files.append(file_path)
                    
                    # タイムゾーン統一関数のインポートをチェック
                    has_timezone_import = any([
                        'from database.timezone_utils import' in content,
                        'import database.timezone_utils' in content,
                        'get_app_datetime_string' in content,
                        'update_with_app_timestamp' in content
                    ])
                    
                    # データベース操作があるのにタイムゾーン関数のインポートがない場合
                    if not has_timezone_import and 'TIMESTAMP' in content:
                        missing_imports.append({
                            'file': str(file_path.relative_to(file_path.parents[len(file_path.parents)-1])),
                            'reason': 'Has database operations with TIMESTAMP but missing timezone utils import'
                        })
                        
            except Exception as e:
                print(f"Warning: Could not analyze {file_path}: {e}")
        
        # 結果レポート
        print(f"\nDatabase operation files found: {len(db_operation_files)}")
        for file in db_operation_files:
            print(f"  {file.relative_to(file.parents[len(file.parents)-1])}")
        
        if missing_imports:
            missing_details = "\n".join([
                f"  {m['file']} - {m['reason']}"
                for m in missing_imports
            ])
            pytest.fail(
                f"Found {len(missing_imports)} file(s) with potential timezone consistency issues:\n"
                f"{missing_details}\n"
                f"Consider importing and using timezone utility functions."
            )
    
    def test_datetime_now_direct_usage(self, python_files):
        """
        datetime.now()やdatetime.utcnow()の直接使用を確認
        
        タイムゾーン一貫性のため、これらの関数は直接使用せず、
        タイムゾーン統一システムを使用する必要がある
        """
        violations = []
        
        for file_path in python_files:
            # テストファイルやタイムゾーンユーティリティ自体はスキップ
            if ('test_' in file_path.name or 
                'timezone' in file_path.name or 
                'backup.py' in file_path.name or
                'email_service.py' in file_path.name or
                'pdf_url_security.py' in file_path.name):  # 表示用時刻は除外
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 問題のある datetime 使用パターンをチェック
                problematic_patterns = [
                    r'datetime\.now\(\)',
                    r'datetime\.utcnow\(\)',
                    r'datetime\.today\(\)',
                ]
                
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    for pattern in problematic_patterns:
                        if re.search(pattern, line):
                            violations.append({
                                'file': str(file_path.relative_to(file_path.parents[len(file_path.parents)-1])),
                                'line': i,
                                'content': line.strip(),
                                'pattern': pattern
                            })
                            
            except Exception as e:
                print(f"Warning: Could not read {file_path}: {e}")
        
        if violations:
            violation_details = "\n".join([
                f"  {v['file']}:{v['line']} - {v['content']} (matches {v['pattern']})"
                for v in violations
            ])
            pytest.fail(
                f"Found {len(violations)} direct datetime usage(s) that should use timezone utilities:\n"
                f"{violation_details}\n"
                f"Use get_app_datetime() or get_app_datetime_string() for timezone consistency."
            )
    
    def test_timezone_utils_functionality_integration(self):
        """
        タイムゾーンユーティリティ関数が実際に動作することを確認
        
        この統合テストは、タイムゾーン統一関数が期待通りに動作し、
        実際のアプリケーションで使用できることを確認します
        """
        try:
            from database.timezone_utils import get_app_datetime_string, get_app_datetime, update_with_app_timestamp
            import sqlite3
            from datetime import datetime
            
            # 一時的なデータベースでテスト
            conn = sqlite3.connect(':memory:')
            conn.execute('''
                CREATE TABLE test_table (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            
            # タイムゾーン統一関数の動作確認
            app_datetime_str = get_app_datetime_string()
            app_datetime_obj = get_app_datetime()
            
            assert isinstance(app_datetime_str, str)
            assert isinstance(app_datetime_obj, datetime)
            
            # 統一されたタイムスタンプでのデータベース操作
            conn.execute(
                'INSERT INTO test_table (name, created_at) VALUES (?, ?)',
                ('test', app_datetime_str)
            )
            
            # update_with_app_timestamp関数のテスト
            update_with_app_timestamp(
                conn, 
                'test_table', 
                ['name'], 
                ['updated_test'], 
                'id = 1'
            )
            
            # 結果確認
            result = conn.execute('SELECT * FROM test_table WHERE id = 1').fetchone()
            assert result is not None
            assert result[1] == 'updated_test'  # name
            assert result[2] is not None        # created_at
            assert result[3] is not None        # updated_at
            
            conn.close()
            
        except ImportError as e:
            pytest.fail(f"Could not import timezone utilities: {e}")
        except Exception as e:
            pytest.fail(f"Timezone utility integration test failed: {e}")
    
    def test_critical_files_timezone_compliance(self):
        """
        重要なファイルでのタイムゾーン統一の適用状況を確認
        
        特に重要なファイル（認証、セッション管理など）で
        タイムゾーン統一が適用されているかを確認
        """
        critical_files = [
            'auth/passphrase.py',
            'app.py'  # email_service.py は表示用なので除外
        ]
        
        violations = []
        
        for file_path in critical_files:
            full_path = Path(__file__).parent.parent / file_path
            
            if not full_path.exists():
                continue
                
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                issues = []
                
                # CURRENT_TIMESTAMPの使用チェック
                if 'CURRENT_TIMESTAMP' in content:
                    issues.append('Uses CURRENT_TIMESTAMP directly')
                
                # タイムゾーン統一関数のインポート・使用チェック
                has_timezone_import = any([
                    'from database.timezone_utils import' in content,
                    'import database.timezone_utils' in content,
                    'from config.timezone import' in content,  # 直接インポートも許可
                    'get_app_datetime_string' in content  # 関数使用も確認
                ])
                
                has_db_timestamp = any([
                    'TIMESTAMP' in content,
                    'updated_at' in content,
                    'created_at' in content
                ])
                
                if has_db_timestamp and not has_timezone_import:
                    issues.append('Has timestamp operations but missing timezone utils import')
                
                if issues:
                    violations.append({
                        'file': file_path,
                        'issues': issues
                    })
                    
            except Exception as e:
                violations.append({
                    'file': file_path,
                    'issues': [f'Could not analyze file: {e}']
                })
        
        if violations:
            violation_details = "\n".join([
                f"  {v['file']}:\n    - " + "\n    - ".join(v['issues'])
                for v in violations
            ])
            pytest.fail(
                f"Critical files have timezone compliance issues:\n"
                f"{violation_details}\n"
                f"These files must use timezone utility functions for consistency."
            )


if __name__ == '__main__':
    # スタンドアローン実行時
    pytest.main([__file__, '-v'])