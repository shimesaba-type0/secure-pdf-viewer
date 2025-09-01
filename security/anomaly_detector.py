"""
TASK-021 Sub-Phase 3D: 異常検出機能

管理者操作の異常パターン検出とアラート機能を提供
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from collections import defaultdict, Counter

import sqlite3
from database.models import get_admin_actions
from config.timezone import get_app_datetime_string, get_app_now


def get_db_connection():
    """データベース接続を取得"""
    return sqlite3.connect("instance/database.db")

logger = logging.getLogger(__name__)


def detect_admin_anomalies(admin_email: str, timeframe: int = 3600) -> Dict[str, Any]:
    """
    管理者の異常操作パターンを検出

    検出対象:
    - 短時間大量操作（10操作/5分以上）
    - 異常時間帯アクセス（深夜2-6時）
    - 新規IPアドレスからのアクセス
    - 高リスク操作の連続実行
    - 通常パターンからの逸脱

    Args:
        admin_email: 検査対象管理者メールアドレス
        timeframe: 検査時間範囲（秒、デフォルト: 3600秒=1時間）

    Returns:
        Dict: 異常検出結果
        {
            "anomalies_detected": bool,      # 異常検出有無
            "anomaly_types": List[str],      # 検出された異常タイプリスト
            "risk_score": int,               # リスクスコア（0-100）
            "recommendations": List[str],    # 推奨対応リスト
            "detection_details": Dict,       # 詳細な検出情報
            "admin_email": str,              # 対象管理者
            "timeframe": int,                # 検査時間範囲
            "timestamp": str                 # 検出実行時刻
        }
    """
    try:
        # 指定時間範囲内の管理者操作を取得
        start_time = get_app_now() - timedelta(seconds=timeframe)
        admin_actions_data = get_admin_actions(
            admin_email=admin_email,
            start_date=start_time.strftime("%Y-%m-%d %H:%M:%S"),
            end_date=get_app_now().strftime("%Y-%m-%d %H:%M:%S"),
            limit=1000,  # 異常検出用に大きな値を設定
        )
        
        # get_admin_actionsは{actions: list, total: int}形式で返すので、actionsを取得
        actions = admin_actions_data.get("actions", []) if isinstance(admin_actions_data, dict) else []
        
        # SQLite Rowオブジェクトを辞書に変換
        if actions and hasattr(actions[0], 'keys'):
            actions = [dict(action) for action in actions]

        if not actions:
            return {
                "anomalies_detected": False,
                "anomaly_types": [],
                "risk_score": 0,
                "recommendations": [],
                "detection_details": {"total_actions": 0},
                "admin_email": admin_email,
                "timeframe": timeframe,
                "timestamp": get_app_datetime_string(),
            }

        anomaly_types = []
        detection_details = {"total_actions": len(actions)}
        recommendations = []

        # 1. 大量操作検出
        bulk_anomaly = _detect_bulk_operations(actions, timeframe)
        if bulk_anomaly["detected"]:
            anomaly_types.append("bulk_operations")
            detection_details["bulk_operations"] = bulk_anomaly
            recommendations.append("大量操作が検出されました。操作内容を確認し、自動スクリプトの可能性を調査してください。")

        # 2. 深夜アクセス検出
        night_anomaly = _detect_night_access(actions)
        if night_anomaly["detected"]:
            anomaly_types.append("night_access")
            detection_details["night_access"] = night_anomaly
            recommendations.append("深夜時間帯での操作が検出されました。緊急対応でない場合は、アクセス時間を確認してください。")

        # 3. IP変更検出
        ip_anomaly = _detect_ip_changes(actions, timeframe)
        if ip_anomaly["detected"]:
            anomaly_types.append("ip_changes")
            detection_details["ip_changes"] = ip_anomaly
            recommendations.append("異常なIP変更パターンが検出されました。アカウントの乗っ取りや不正利用の可能性を確認してください。")

        # 4. 高リスク操作連続実行検出
        critical_anomaly = _detect_critical_operations(actions, timeframe)
        if critical_anomaly["detected"]:
            anomaly_types.append("critical_operations")
            detection_details["critical_operations"] = critical_anomaly
            recommendations.append("重要操作の連続実行が検出されました。操作の必要性と承認プロセスを確認してください。")

        # 5. 失敗率異常検出
        failure_anomaly = _detect_high_failure_rate(actions)
        if failure_anomaly["detected"]:
            anomaly_types.append("high_failure_rate")
            detection_details["high_failure_rate"] = failure_anomaly
            recommendations.append("操作失敗率が異常に高くなっています。システム問題または不正アクセスの可能性があります。")

        # リスクスコア計算
        risk_score = calculate_risk_score(actions)

        # 異常検出有無の判定
        anomalies_detected = len(anomaly_types) > 0 or risk_score >= 60

        # 結果をログ出力
        if anomalies_detected:
            logger.warning(
                f"異常検出: admin={admin_email}, types={anomaly_types}, "
                f"risk_score={risk_score}"
            )
        else:
            logger.info(
                f"異常なし: admin={admin_email}, actions={len(actions)}, "
                f"risk_score={risk_score}"
            )

        return {
            "anomalies_detected": anomalies_detected,
            "anomaly_types": anomaly_types,
            "risk_score": risk_score,
            "recommendations": recommendations,
            "detection_details": detection_details,
            "admin_email": admin_email,
            "timeframe": timeframe,
            "timestamp": get_app_datetime_string(),
        }

    except Exception as e:
        logger.error(f"異常検出エラー (admin={admin_email}): {e}")
        return {
            "anomalies_detected": False,
            "anomaly_types": [],
            "risk_score": 0,
            "recommendations": [],
            "detection_details": {"error": str(e)},
            "admin_email": admin_email,
            "timeframe": timeframe,
            "timestamp": get_app_datetime_string(),
        }


def _detect_bulk_operations(actions: List[Dict], timeframe: int) -> Dict[str, Any]:
    """短時間大量操作の検出"""
    # 5分間窓での操作数をカウント
    time_windows = defaultdict(int)

    for action in actions:
        try:
            created_at = datetime.strptime(
                action.get("created_at", ""), "%Y-%m-%d %H:%M:%S"
            )
            # 5分単位で時間窓を作成
            window = created_at.replace(second=0, microsecond=0)
            window = window - timedelta(minutes=window.minute % 5)
            time_windows[window] += 1
        except (ValueError, TypeError):
            continue

    max_operations = max(time_windows.values()) if time_windows else 0
    threshold = 10  # 5分間に10操作以上で異常

    return {
        "detected": max_operations >= threshold,
        "max_operations_per_5min": max_operations,
        "threshold": threshold,
        "total_time_windows": len(time_windows),
    }


def _detect_night_access(actions: List[Dict]) -> Dict[str, Any]:
    """深夜時間帯アクセスの検出"""
    night_operations = []

    for action in actions:
        try:
            created_at = datetime.strptime(
                action.get("created_at", ""), "%Y-%m-%d %H:%M:%S"
            )
            hour = created_at.hour

            # 深夜時間帯判定（2:00-6:00）
            if 2 <= hour <= 6:
                night_operations.append(
                    {
                        "time": created_at.strftime("%H:%M:%S"),
                        "action_type": action.get("action_type", "unknown"),
                        "risk_level": action.get("risk_level", "unknown"),
                    }
                )
        except (ValueError, TypeError):
            continue

    return {
        "detected": len(night_operations) > 0,
        "night_operations_count": len(night_operations),
        "operations": night_operations[:5],  # 最初の5件のみ返却
    }


def _detect_ip_changes(actions: List[Dict], timeframe: int) -> Dict[str, Any]:
    """IP変更異常の検出"""
    ip_timeline = []

    for action in actions:
        ip_address = action.get("ip_address")
        created_at = action.get("created_at")
        if ip_address and created_at:
            try:
                dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                ip_timeline.append((dt, ip_address))
            except (ValueError, TypeError):
                continue

    # 時刻順にソート
    ip_timeline.sort(key=lambda x: x[0])

    # 異なるIPアドレス数をカウント
    unique_ips = set([ip for _, ip in ip_timeline])
    ip_changes = []

    for i in range(1, len(ip_timeline)):
        if ip_timeline[i][1] != ip_timeline[i - 1][1]:
            ip_changes.append(
                {
                    "time": ip_timeline[i][0].strftime("%Y-%m-%d %H:%M:%S"),
                    "from_ip": ip_timeline[i - 1][1],
                    "to_ip": ip_timeline[i][1],
                }
            )

    # 1時間に3回以上のIP変更で異常
    threshold = 3 if timeframe >= 3600 else max(1, timeframe // 1200)

    return {
        "detected": len(ip_changes) >= threshold,
        "unique_ip_count": len(unique_ips),
        "ip_changes_count": len(ip_changes),
        "threshold": threshold,
        "changes": ip_changes[:10],  # 最初の10件のみ返却
    }


def _detect_critical_operations(actions: List[Dict], timeframe: int) -> Dict[str, Any]:
    """高リスク操作連続実行の検出"""
    critical_operations = []

    for action in actions:
        risk_level = action.get("risk_level", "").lower()
        if risk_level in ["critical", "high"]:
            critical_operations.append(
                {
                    "time": action.get("created_at"),
                    "action_type": action.get("action_type"),
                    "risk_level": risk_level,
                    "resource_type": action.get("resource_type"),
                }
            )

    # 時刻順にソート
    critical_operations.sort(key=lambda x: x.get("time", ""))

    # 短時間内の高リスク操作連続実行チェック
    consecutive_count = 0
    max_consecutive = 0

    for i in range(len(critical_operations)):
        if i == 0:
            consecutive_count = 1
        else:
            try:
                current_time = datetime.strptime(
                    critical_operations[i]["time"], "%Y-%m-%d %H:%M:%S"
                )
                prev_time = datetime.strptime(
                    critical_operations[i - 1]["time"], "%Y-%m-%d %H:%M:%S"
                )

                # 10分以内なら連続とみなす
                if (current_time - prev_time).total_seconds() <= 600:
                    consecutive_count += 1
                else:
                    consecutive_count = 1

                max_consecutive = max(max_consecutive, consecutive_count)
            except (ValueError, TypeError):
                consecutive_count = 1

    # 3回以上の連続高リスク操作で異常
    threshold = 3

    return {
        "detected": max_consecutive >= threshold,
        "critical_operations_count": len(critical_operations),
        "max_consecutive": max_consecutive,
        "threshold": threshold,
        "operations": critical_operations[:10],
    }


def _detect_high_failure_rate(actions: List[Dict]) -> Dict[str, Any]:
    """高失敗率の検出"""
    if not actions:
        return {"detected": False, "failure_rate": 0, "threshold": 0.3}

    failed_actions = [a for a in actions if not a.get("success", True)]
    failure_rate = len(failed_actions) / len(actions)
    threshold = 0.3  # 30%以上の失敗率で異常

    return {
        "detected": failure_rate >= threshold,
        "total_actions": len(actions),
        "failed_actions": len(failed_actions),
        "failure_rate": round(failure_rate, 3),
        "threshold": threshold,
    }


def calculate_risk_score(actions: List[Dict]) -> int:
    """
    操作パターンからリスクスコアを算出

    評価要素:
    - 操作頻度（+1点/操作、上限30点）
    - 高リスク操作比率（critical: +20点, high: +10点, medium: +5点/操作）
    - 異常時間帯操作（+15点/操作）
    - IP変更頻度（+5点/IP変更）
    - 失敗操作率（+30点 * 失敗率）

    Args:
        actions: 管理者操作リスト

    Returns:
        int: リスクスコア（0-100）
    """
    if not actions:
        return 0

    risk_score = 0

    # 1. 操作頻度スコア（上限30点）
    operation_score = min(len(actions), 30)
    risk_score += operation_score

    # 2. 高リスク操作スコア
    risk_levels = Counter(
        [action.get("risk_level", "low").lower() for action in actions]
    )
    risk_score += risk_levels.get("critical", 0) * 20
    risk_score += risk_levels.get("high", 0) * 10
    risk_score += risk_levels.get("medium", 0) * 5

    # 3. 異常時間帯操作スコア
    night_operations = 0
    for action in actions:
        try:
            created_at = datetime.strptime(
                action.get("created_at", ""), "%Y-%m-%d %H:%M:%S"
            )
            if 2 <= created_at.hour <= 6:  # 深夜2-6時
                night_operations += 1
        except (ValueError, TypeError):
            continue
    risk_score += night_operations * 15

    # 4. IP変更スコア
    unique_ips = set(
        [action.get("ip_address") for action in actions if action.get("ip_address")]
    )
    if len(unique_ips) > 1:
        risk_score += (len(unique_ips) - 1) * 5

    # 5. 失敗率スコア
    failed_count = len([a for a in actions if not a.get("success", True)])
    if len(actions) > 0:
        failure_rate = failed_count / len(actions)
        risk_score += int(30 * failure_rate)

    # 最大100点に制限
    return min(risk_score, 100)


def trigger_security_alert(anomaly_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    セキュリティアラートをトリガー

    アラート条件:
    - リスクスコア80点以上 → critical
    - リスクスコア60-79点 → high
    - リスクスコア40-59点 → medium
    - critical操作の連続実行 → critical
    - 未知IPからの管理者アクセス → high

    Args:
        anomaly_data: 異常検出結果データ

    Returns:
        Dict: アラート結果
        {
            "alert_sent": bool,       # アラート送信有無
            "severity": str,          # 重要度 (critical/high/medium/low)
            "alert_message": str,     # アラートメッセージ
            "alert_id": str,         # アラートID
            "timestamp": str         # アラート時刻
        }
    """
    try:
        risk_score = anomaly_data.get("risk_score", 0)
        anomaly_types = anomaly_data.get("anomaly_types", [])
        admin_email = anomaly_data.get("admin_email", "unknown")

        # 重要度判定
        if risk_score >= 80 or "critical_operations" in anomaly_types:
            severity = "critical"
        elif risk_score >= 60 or "ip_changes" in anomaly_types:
            severity = "high"
        elif risk_score >= 40 or len(anomaly_types) >= 2:
            severity = "medium"
        else:
            severity = "low"

        # アラート送信判定（medium以上でアラート送信）
        alert_sent = severity in ["critical", "high", "medium"]

        if not alert_sent:
            return {
                "alert_sent": False,
                "severity": severity,
                "alert_message": "",
                "alert_id": None,
                "timestamp": get_app_datetime_string(),
            }

        # アラートメッセージ生成
        alert_message = f"【{severity.upper()}】セキュリティ異常検出\\n"
        alert_message += f"管理者: {admin_email}\\n"
        alert_message += f"リスクスコア: {risk_score}/100\\n"
        alert_message += f"検出異常: {', '.join(anomaly_types)}\\n"

        # 推奨対応を追加
        recommendations = anomaly_data.get("recommendations", [])
        if recommendations:
            alert_message += "推奨対応:\\n"
            for i, rec in enumerate(recommendations[:3], 1):
                alert_message += f"{i}. {rec}\\n"

        # アラートID生成（時刻ベース）
        time_str = get_app_now().strftime('%Y%m%d_%H%M%S')
        hash_suffix = hash(admin_email) % 10000
        alert_id = f"SEC_{time_str}_{hash_suffix:04d}"

        # セキュリティアラートをログに記録
        logger.critical(
            f"SECURITY_ALERT: {alert_id} - {severity.upper()} - admin={admin_email}, "
            f"risk={risk_score}, types={anomaly_types}"
        )

        # TODO: 将来的にはメール通知、Slack通知、外部SIEM連携などを実装

        return {
            "alert_sent": True,
            "severity": severity,
            "alert_message": alert_message,
            "alert_id": alert_id,
            "timestamp": get_app_datetime_string(),
        }

    except Exception as e:
        logger.error(f"セキュリティアラート送信エラー: {e}")
        return {
            "alert_sent": False,
            "severity": "unknown",
            "alert_message": f"アラート送信エラー: {str(e)}",
            "alert_id": None,
            "timestamp": get_app_datetime_string(),
        }


def get_security_thresholds() -> Dict[str, Any]:
    """
    セキュリティ閾値設定を取得

    Returns:
        Dict: 閾値設定
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT threshold_type, threshold_value, timeframe_minutes, is_active
            FROM security_thresholds
            WHERE is_active = TRUE
        """
        )

        thresholds = {}
        for row in cursor.fetchall():
            threshold_type, value, timeframe, is_active = row
            thresholds[threshold_type] = {
                "value": value,
                "timeframe_minutes": timeframe,
                "is_active": is_active,
            }

        conn.close()
        return thresholds

    except Exception as e:
        logger.error(f"セキュリティ閾値取得エラー: {e}")
        # デフォルト閾値を返却
        return {
            "bulk_operations": {"value": 10, "timeframe_minutes": 5, "is_active": True},
            "night_access": {"value": 1, "timeframe_minutes": 60, "is_active": True},
            "ip_changes": {"value": 3, "timeframe_minutes": 60, "is_active": True},
            "critical_operations": {
                "value": 3,
                "timeframe_minutes": 10,
                "is_active": True,
            },
        }
