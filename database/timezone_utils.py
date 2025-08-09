"""
データベース操作用タイムゾーン統一ユーティリティ

データベース操作におけるタイムスタンプの一貫性を保証するための
ヘルパー関数を提供する。
"""

import sqlite3
from config.timezone import get_app_datetime_string, get_app_now
from typing import List, Any, Union, Optional


def get_app_datetime():
    """
    アプリケーション統一タイムゾーンの現在時刻を取得
    
    Returns:
        datetime: タイムゾーン付きの現在時刻
    """
    return get_app_now()


def update_with_app_timestamp(db_connection, table: str, columns: List[str], 
                            values: List[Any], where_clause: str = None,
                            updated_by: str = None):
    """
    アプリケーション統一タイムスタンプを使用してデータベースを更新
    
    Args:
        db_connection: データベース接続オブジェクト
        table: テーブル名
        columns: 更新するカラム名のリスト
        values: 更新値のリスト
        where_clause: WHERE句（オプション）
        updated_by: 更新者（オプション）
    """
    # updated_at カラムがあれば自動追加
    if 'updated_at' not in columns:
        columns = columns + ['updated_at']
        values = values + [get_app_datetime_string()]
    
    # updated_by カラムがあればサポート
    if updated_by and 'updated_by' not in columns:
        # テーブル構造を確認してupdated_byカラムがあるかチェック
        cursor = db_connection.execute(f"PRAGMA table_info({table})")
        table_columns = [row[1] for row in cursor.fetchall()]
        if 'updated_by' in table_columns:
            columns = columns + ['updated_by']
            values = values + [updated_by]
    
    # UPDATE文を構築
    set_clause = ', '.join([f"{col} = ?" for col in columns])
    query = f"UPDATE {table} SET {set_clause}"
    
    if where_clause:
        query += f" WHERE {where_clause}"
    
    return db_connection.execute(query, values)


def insert_with_app_timestamp(db_connection, table: str, columns: List[str], 
                             values: List[Any], created_by: str = None):
    """
    アプリケーション統一タイムスタンプを使用してデータベースに挿入
    
    Args:
        db_connection: データベース接続オブジェクト
        table: テーブル名
        columns: カラム名のリスト
        values: 値のリスト
        created_by: 作成者（オプション）
    """
    # created_at カラムがあれば自動追加
    if 'created_at' not in columns:
        columns = columns + ['created_at']
        values = values + [get_app_datetime_string()]
    
    # created_by カラムがあればサポート
    if created_by and 'created_by' not in columns:
        # テーブル構造を確認してcreated_byカラムがあるかチェック
        cursor = db_connection.execute(f"PRAGMA table_info({table})")
        table_columns = [row[1] for row in cursor.fetchall()]
        if 'created_by' in table_columns:
            columns = columns + ['created_by']
            values = values + [created_by]
    
    # INSERT文を構築
    placeholders = ', '.join(['?' for _ in columns])
    columns_clause = ', '.join(columns)
    query = f"INSERT INTO {table} ({columns_clause}) VALUES ({placeholders})"
    
    return db_connection.execute(query, values)


def execute_with_app_timestamp_replacement(db_connection, query: str, 
                                         parameters: tuple = ()):
    """
    旧式のタイムスタンプ記法をアプリケーション統一タイムスタンプに置換して実行
    
    Args:
        db_connection: データベース接続オブジェクト
        query: SQL文（旧式タイムスタンプ記法を含む可能性がある）
        parameters: クエリパラメータ
    
    Returns:
        Cursor: 実行結果のカーソル
    """
    # 旧式タイムスタンプ記法を統一タイムスタンプに置換
    app_timestamp = get_app_datetime_string()
    modified_query = query.replace('CURRENT_TIMESTAMP', f"'{app_timestamp}'")
    
    return db_connection.execute(modified_query, parameters)


def get_database_timezone_status(db_connection) -> dict:
    """
    データベース内のタイムゾーン使用状況を取得
    
    Args:
        db_connection: データベース接続オブジェクト
    
    Returns:
        dict: タイムゾーン使用状況の情報
    """
    status = {
        'current_app_timestamp': get_app_datetime_string(),
        'tables_with_timestamps': [],
        'inconsistent_formats': []
    }
    
    try:
        # 全テーブルを取得
        cursor = db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        
        for table in tables:
            # テーブル構造を確認
            cursor = db_connection.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            
            timestamp_columns = []
            for col in columns:
                col_name = col[1]
                col_type = col[2]
                if 'TIMESTAMP' in col_type.upper() or col_name.endswith('_at'):
                    timestamp_columns.append(col_name)
            
            if timestamp_columns:
                status['tables_with_timestamps'].append({
                    'table': table,
                    'timestamp_columns': timestamp_columns
                })
        
        return status
        
    except Exception as e:
        status['error'] = str(e)
        return status


# 便利な関数のエイリアス
def get_current_app_timestamp() -> str:
    """アプリケーション統一タイムスタンプ文字列を取得（短縮名）"""
    return get_app_datetime_string()


def now_app_string() -> str:
    """現在時刻のアプリケーション統一文字列を取得（短縮名）"""
    return get_app_datetime_string()