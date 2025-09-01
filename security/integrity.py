"""
TASK-021 Sub-Phase 3D: ログ完全性保証機能

監査ログの改ざん検出・防止機能を提供
"""

import hashlib
import json
import logging
from typing import Dict, Any
from datetime import datetime

import sqlite3
from config.timezone import get_app_datetime_string


def get_db_connection():
    """データベース接続を取得"""
    return sqlite3.connect("instance/database.db")

logger = logging.getLogger(__name__)


def generate_log_checksum(log_entry: Dict[str, Any]) -> str:
    """
    監査ログエントリのチェックサムを生成

    SHA-256を使用してログの改ざん検証用ハッシュ値を作成

    Args:
        log_entry: ログエントリデータ

    Returns:
        str: SHA-256チェックサム（64文字の16進数文字列）
    """
    try:
        # チェックサム対象フィールド（改ざん検証用の重要フィールド）
        checksum_fields = [
            "admin_email",
            "action_type",
            "resource_type",
            "resource_id",
            "action_details",
            "before_state",
            "after_state",
            "ip_address",
            "user_agent",
            "risk_level",
            "success",
        ]

        # 指定フィールドのみを抽出してチェックサム用データ作成
        checksum_data = {}
        for field in checksum_fields:
            if field in log_entry and log_entry[field] is not None:
                checksum_data[field] = log_entry[field]

        # JSON文字列に変換（キーをソート、ASCII以外も保持）
        data_string = json.dumps(
            checksum_data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )

        # SHA-256ハッシュ生成
        return hashlib.sha256(data_string.encode("utf-8")).hexdigest()

    except Exception as e:
        logger.error(f"チェックサム生成エラー: {e}")
        raise


def verify_log_integrity(log_id: int) -> Dict[str, Any]:
    """
    指定された監査ログエントリの完全性を検証

    Args:
        log_id: 検証対象ログのID

    Returns:
        Dict: 検証結果
        {
            "valid": bool,          # 検証結果（True=完全, False=改ざん検出）
            "expected": str,        # 保存されているチェックサム
            "actual": str,          # 現在のデータから計算されたチェックサム
            "timestamp": str,       # 検証実行時刻
            "log_id": int          # ログID
        }
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # ログエントリとチェックサムを取得
        cursor.execute(
            """
            SELECT id, admin_email, action_type, resource_type, resource_id,
                   action_details, before_state, after_state, ip_address, user_agent,
                   risk_level, success, checksum, integrity_status
            FROM admin_actions
            WHERE id = ?
        """,
            (log_id,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return {
                "valid": False,
                "expected": None,
                "actual": None,
                "timestamp": get_app_datetime_string(),
                "log_id": log_id,
                "error": "ログエントリが見つかりません",
            }

        # カラム名とデータのマッピング
        columns = [
            "id",
            "admin_email",
            "action_type",
            "resource_type",
            "resource_id",
            "action_details",
            "before_state",
            "after_state",
            "ip_address",
            "user_agent",
            "risk_level",
            "success",
            "checksum",
            "integrity_status",
        ]
        log_data = dict(zip(columns, row))

        expected_checksum = log_data.get("checksum")

        # チェックサム未設定の場合
        if not expected_checksum:
            actual_checksum = generate_log_checksum(log_data)
            return {
                "valid": False,
                "expected": None,
                "actual": actual_checksum,
                "timestamp": get_app_datetime_string(),
                "log_id": log_id,
                "error": "チェックサム未設定",
            }

        # 現在のデータからチェックサムを再計算
        actual_checksum = generate_log_checksum(log_data)

        # チェックサム比較
        is_valid = expected_checksum == actual_checksum

        # 検証結果をログに記録
        if not is_valid:
            logger.warning(
                f"ログ完全性違反検出: log_id={log_id}, "
                f"expected={expected_checksum[:16]}..., "
                f"actual={actual_checksum[:16]}..."
            )

        return {
            "valid": is_valid,
            "expected": expected_checksum,
            "actual": actual_checksum,
            "timestamp": get_app_datetime_string(),
            "log_id": log_id,
        }

    except Exception as e:
        logger.error(f"ログ完全性検証エラー (log_id={log_id}): {e}")
        return {
            "valid": False,
            "expected": None,
            "actual": None,
            "timestamp": get_app_datetime_string(),
            "log_id": log_id,
            "error": str(e),
        }


def verify_all_logs_integrity(batch_size: int = 1000) -> Dict[str, Any]:
    """
    全監査ログの完全性を一括検証

    大量データ処理のためバッチ処理で実行

    Args:
        batch_size: バッチサイズ（デフォルト: 1000件）

    Returns:
        Dict: 一括検証結果
        {
            "total_logs": int,        # 総ログ数
            "valid_logs": int,        # 有効ログ数
            "invalid_logs": int,      # 無効ログ数
            "unverified_logs": int,   # 未検証ログ数
            "tampered_log_ids": List[int],  # 改ざん検出ログID
            "processing_time": float, # 処理時間（秒）
            "timestamp": str         # 検証実行時刻
        }
    """
    try:
        start_time = datetime.now()

        conn = get_db_connection()
        cursor = conn.cursor()

        # 総ログ数を取得
        cursor.execute("SELECT COUNT(*) FROM admin_actions")
        total_logs = cursor.fetchone()[0]

        valid_count = 0
        invalid_count = 0
        unverified_count = 0
        tampered_log_ids = []

        # バッチ処理でログを検証
        offset = 0
        while offset < total_logs:
            cursor.execute(
                """
                SELECT id FROM admin_actions
                ORDER BY id
                LIMIT ? OFFSET ?
            """,
                (batch_size, offset),
            )

            batch_log_ids = [row[0] for row in cursor.fetchall()]

            # バッチ内の各ログを検証
            for log_id in batch_log_ids:
                result = verify_log_integrity(log_id)

                if result.get("error") == "チェックサム未設定":
                    unverified_count += 1
                elif result["valid"]:
                    valid_count += 1
                else:
                    invalid_count += 1
                    tampered_log_ids.append(log_id)

            offset += batch_size

            # プログレスログ（大量データの場合）
            if total_logs > 5000 and offset % (batch_size * 10) == 0:
                logger.info(
                    f"ログ完全性検証進捗: {offset}/{total_logs} ({offset/total_logs*100:.1f}%)"
                )

        conn.close()

        processing_time = (datetime.now() - start_time).total_seconds()

        result = {
            "total_logs": total_logs,
            "valid_logs": valid_count,
            "invalid_logs": invalid_count,
            "unverified_logs": unverified_count,
            "tampered_log_ids": tampered_log_ids,
            "processing_time": processing_time,
            "timestamp": get_app_datetime_string(),
        }

        # 結果サマリーをログ出力
        logger.info(
            f"ログ完全性一括検証完了: 総数={total_logs}, 有効={valid_count}, "
            f"無効={invalid_count}, 未検証={unverified_count}, 処理時間={processing_time:.2f}秒"
        )

        if tampered_log_ids:
            suffix = "..." if len(tampered_log_ids) > 10 else ""
            logger.warning(f"改ざん検出ログID: {tampered_log_ids[:10]}{suffix}")

        return result

    except Exception as e:
        logger.error(f"ログ完全性一括検証エラー: {e}")
        raise


def add_checksum_to_existing_logs() -> Dict[str, Any]:
    """
    既存の監査ログにチェックサムを追加

    チェックサム未設定のログに対してチェックサムを生成・追加する

    Returns:
        Dict: 処理結果
        {
            "processed_logs": int,    # 処理対象ログ数
            "updated_logs": int,      # 更新成功ログ数
            "failed_logs": int,       # 更新失敗ログ数
            "processing_time": float, # 処理時間（秒）
            "timestamp": str         # 処理実行時刻
        }
    """
    try:
        start_time = datetime.now()

        conn = get_db_connection()
        cursor = conn.cursor()

        # チェックサム未設定のログを取得
        cursor.execute(
            """
            SELECT id, admin_email, action_type, resource_type, resource_id,
                   action_details, before_state, after_state, ip_address, user_agent,
                   risk_level, success
            FROM admin_actions
            WHERE checksum IS NULL OR checksum = ''
            ORDER BY id
        """
        )

        rows = cursor.fetchall()
        processed_count = len(rows)
        updated_count = 0
        failed_count = 0

        if processed_count == 0:
            conn.close()
            return {
                "processed_logs": 0,
                "updated_logs": 0,
                "failed_logs": 0,
                "processing_time": 0.0,
                "timestamp": get_app_datetime_string(),
            }

        logger.info(f"既存ログへのチェックサム追加開始: {processed_count}件")

        # 各ログにチェックサムを追加
        columns = [
            "id",
            "admin_email",
            "action_type",
            "resource_type",
            "resource_id",
            "action_details",
            "before_state",
            "after_state",
            "ip_address",
            "user_agent",
            "risk_level",
            "success",
        ]

        for row in rows:
            try:
                log_data = dict(zip(columns, row))
                log_id = log_data["id"]

                # チェックサム生成
                checksum = generate_log_checksum(log_data)

                # データベース更新
                cursor.execute(
                    """
                    UPDATE admin_actions
                    SET checksum = ?, integrity_status = 'verified', verified_at = ?
                    WHERE id = ?
                """,
                    (checksum, get_app_datetime_string(), log_id),
                )

                updated_count += 1

            except Exception as e:
                logger.error(f"ログID {log_id} のチェックサム追加失敗: {e}")
                failed_count += 1

        conn.commit()
        conn.close()

        processing_time = (datetime.now() - start_time).total_seconds()

        result = {
            "processed_logs": processed_count,
            "updated_logs": updated_count,
            "failed_logs": failed_count,
            "processing_time": processing_time,
            "timestamp": get_app_datetime_string(),
        }

        logger.info(
            f"既存ログチェックサム追加完了: 処理={processed_count}, 成功={updated_count}, "
            f"失敗={failed_count}, 処理時間={processing_time:.2f}秒"
        )

        return result

    except Exception as e:
        logger.error(f"既存ログチェックサム追加エラー: {e}")
        raise


def update_database_schema():
    """
    ログ完全性保証用のデータベーススキーマ更新

    admin_actionsテーブルにchecksum関連カラムを追加
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 既存カラム確認
        cursor.execute("PRAGMA table_info(admin_actions)")
        existing_columns = [column[1] for column in cursor.fetchall()]

        # checksum関連カラムを追加（存在しない場合のみ）
        schema_updates = [
            ("checksum", "TEXT", "ログの完全性検証用チェックサム"),
            ("verified_at", "TEXT", "完全性検証実行時刻"),
            ("integrity_status", "TEXT DEFAULT 'unverified'", "完全性ステータス"),
        ]

        for column_name, column_type, description in schema_updates:
            if column_name not in existing_columns:
                cursor.execute(
                    f"ALTER TABLE admin_actions ADD COLUMN {column_name} {column_type}"
                )
                logger.info(f"admin_actionsテーブルに{column_name}カラムを追加: {description}")

        # インデックス追加（パフォーマンス向上）
        indexes = [
            ("idx_admin_actions_integrity", "integrity_status, created_at"),
            ("idx_admin_actions_checksum", "checksum"),
        ]

        for index_name, index_columns in indexes:
            try:
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS {index_name} "
                    f"ON admin_actions({index_columns})"
                )
                logger.info(f"インデックス作成: {index_name}")
            except Exception as e:
                logger.warning(f"インデックス作成スキップ ({index_name}): {e}")

        conn.commit()
        conn.close()

        logger.info("ログ完全性保証用スキーマ更新完了")

    except Exception as e:
        logger.error(f"データベーススキーマ更新エラー: {e}")
        raise


# モジュール初期化時にスキーマ更新を実行
try:
    update_database_schema()
except Exception as e:
    logger.warning(f"スキーマ更新スキップ: {e}")
