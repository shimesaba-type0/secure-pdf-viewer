"""
Cloudflare CDN セキュリティ機能

GitHub Issue #6: Cloudflare CDN対応のためのセキュリティ機能強化

主要機能:
1. Real IP Address取得 (CF-Connecting-IP 対応)
2. Cloudflare Referrer検証
3. CDNアクセスログ記録
4. CDNセキュリティ状態監視
"""

import ipaddress
import json
import logging
import os
import sqlite3
from typing import Any, Dict
from urllib.parse import urlparse

from flask import request, session

from database.timezone_utils import get_current_app_timestamp

logger = logging.getLogger(__name__)


def get_real_ip() -> str:
    """
    CDN環境での実IPアドレス取得

    IPアドレス取得優先順位:
    1. CF-Connecting-IP (Cloudflare提供の実IP) - TRUST_CF_CONNECTING_IPが有効時
    2. X-Forwarded-For (プロキシチェーンの最初のIP)
    3. request.remote_addr (直接接続時のIP)

    環境変数による制御:
    - TRUST_CF_CONNECTING_IP: CF-Connecting-IPヘッダーを信頼するかどうか
    - STRICT_IP_VALIDATION: IP形式の厳密検証を行うかどうか

    Returns:
        str: 検証済み実IPアドレス
    """
    # 環境変数の取得
    trust_cf_ip = _get_env_bool("TRUST_CF_CONNECTING_IP", True)
    strict_validation = _get_env_bool("STRICT_IP_VALIDATION", True)

    # 1. CF-Connecting-IP header (Cloudflare専用)
    if trust_cf_ip:
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            cf_ip = cf_ip.strip()
            if not strict_validation or is_valid_ip(cf_ip):
                logger.debug(f"Real IP detected from CF-Connecting-IP: {cf_ip}")
                return cf_ip
            else:
                logger.warning(f"Invalid CF-Connecting-IP ignored: {cf_ip}")

    # 2. X-Forwarded-For header (複数IPの場合は最初のものを取得)
    x_forwarded = request.headers.get("X-Forwarded-For")
    if x_forwarded:
        first_ip = x_forwarded.split(",")[0].strip()
        if not strict_validation or is_valid_ip(first_ip):
            logger.debug(f"Real IP detected from X-Forwarded-For: {first_ip}")
            return first_ip
        else:
            logger.warning(f"Invalid X-Forwarded-For ignored: {first_ip}")

    # 3. Fallback to direct connection
    remote_addr = request.remote_addr or "unknown"
    logger.debug(f"Real IP fallback to remote_addr: {remote_addr}")
    return remote_addr


def is_valid_ip(ip_address: str) -> bool:
    """
    IPアドレス形式の検証（IPv4/IPv6対応）

    Args:
        ip_address: 検証対象のIPアドレス文字列

    Returns:
        bool: 有効なIPアドレスの場合True
    """
    if not ip_address:
        return False

    try:
        ipaddress.ip_address(ip_address)
        return True
    except (ValueError, ipaddress.AddressValueError):
        return False


def is_cloudflare_referrer_valid(referer_url: str) -> bool:
    """
    Cloudflare CDN環境でのリファラー検証

    Args:
        referer_url: 検証対象のリファラーURL

    Returns:
        bool: 検証結果（True: 許可, False: 拒否）
    """
    if not referer_url:
        return False

    # 環境変数からCloudflareドメインを取得
    cloudflare_domain = os.getenv("CLOUDFLARE_DOMAIN")
    if not cloudflare_domain:
        # Cloudflareドメインが設定されていない場合は既存検証にフォールバック
        return False

    try:
        parsed = urlparse(referer_url)
        hostname = parsed.netloc.lower()
        cloudflare_domain = cloudflare_domain.lower()

        # 完全一致またはサブドメイン一致をチェック
        is_valid = hostname == cloudflare_domain or hostname.endswith(
            "." + cloudflare_domain
        )

        logger.debug(f"Cloudflare referrer validation: {referer_url} -> {is_valid}")
        return is_valid

    except Exception as e:
        logger.error(f"Error validating Cloudflare referrer {referer_url}: {e}")
        return False


def get_enhanced_referrer_validation(referer_url: str) -> Dict[str, Any]:
    """
    強化されたリファラー検証（ログ・監視用詳細情報付き）

    Args:
        referer_url: 検証対象のリファラーURL

    Returns:
        dict: 検証結果の詳細情報
        {
            'is_valid': bool,
            'validation_type': str,  # 'cloudflare_cdn' | 'traditional' | 'invalid'
            'cloudflare_domain': str,
            'original_referrer': str
        }
    """
    result = {
        "is_valid": False,
        "validation_type": "invalid",
        "cloudflare_domain": os.getenv("CLOUDFLARE_DOMAIN"),
        "original_referrer": referer_url,
    }

    if not referer_url:
        return result

    # Cloudflare CDN検証を最初に実行
    if is_cloudflare_referrer_valid(referer_url):
        result["is_valid"] = True
        result["validation_type"] = "cloudflare_cdn"
        logger.info(f"Referrer validated via Cloudflare CDN: {referer_url}")
    else:
        # 既存のreferrer検証システムにフォールバック
        try:
            from config.pdf_security_settings import is_referrer_allowed

            if is_referrer_allowed(referer_url):
                result["is_valid"] = True
                result["validation_type"] = "traditional"
                logger.info(f"Referrer validated via traditional method: {referer_url}")
        except ImportError:
            logger.warning("Traditional referrer validation not available")

    if not result["is_valid"]:
        logger.warning(f"Referrer validation failed: {referer_url}")

    return result


def log_cdn_access(endpoint: str, action: str, additional_info: Dict[str, Any] = None):
    """
    CDN環境でのアクセスログ記録

    Args:
        endpoint: アクセスしたエンドポイント
        action: 実行したアクション
        additional_info: 追加情報（オプション）
    """
    if not _get_env_bool("ENABLE_CDN_SECURITY", True):
        return

    try:
        from app import get_db_path

        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # CDN用アクセスログテーブルの作成（存在しない場合）
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cdn_access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                action TEXT NOT NULL,
                real_ip TEXT NOT NULL,
                cf_connecting_ip TEXT,
                x_forwarded_for TEXT,
                user_agent TEXT,
                referrer TEXT,
                referrer_validation TEXT,
                cloudflare_domain TEXT,
                session_id TEXT,
                additional_info TEXT,
                created_at TEXT NOT NULL
            )
        """
        )

        # アクセス情報の収集
        real_ip = get_real_ip()
        cf_ip = request.headers.get("CF-Connecting-IP")
        x_forwarded = request.headers.get("X-Forwarded-For")
        user_agent = request.headers.get("User-Agent")
        referrer = request.headers.get("Referer")

        # リファラー検証の実行
        referrer_validation = get_enhanced_referrer_validation(referrer)

        # セッション情報の取得
        session_id = session.get("session_id", "anonymous")

        # ログエントリの挿入
        cursor.execute(
            """
            INSERT INTO cdn_access_logs
            (endpoint, action, real_ip, cf_connecting_ip, x_forwarded_for,
             user_agent, referrer, referrer_validation, cloudflare_domain,
             session_id, additional_info, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                endpoint,
                action,
                real_ip,
                cf_ip,
                x_forwarded,
                user_agent,
                referrer,
                json.dumps(referrer_validation),
                os.getenv("CLOUDFLARE_DOMAIN"),
                session_id,
                json.dumps(additional_info or {}),
                get_current_app_timestamp(),
            ),
        )

        conn.commit()
        conn.close()

        logger.info(f"CDN access logged: {endpoint} [{action}] from {real_ip}")

    except Exception as e:
        logger.error(f"CDN access logging failed: {e}")
        # ログ記録失敗は致命的ではないので継続


def get_cdn_security_status() -> Dict[str, Any]:
    """
    CDNセキュリティ状態の取得

    Returns:
        dict: 現在のCDNセキュリティ状態
        {
            'cloudflare_domain': str,
            'ip_detection_method': str,
            'real_ip': str,
            'cdn_headers_present': bool,
            'referrer_validation_active': bool,
            'cdn_security_enabled': bool
        }
    """
    cf_connecting_ip = request.headers.get("CF-Connecting-IP")
    x_forwarded_for = request.headers.get("X-Forwarded-For")

    # IP検出方法の決定
    if cf_connecting_ip and _get_env_bool("TRUST_CF_CONNECTING_IP", True):
        ip_method = "CF-Connecting-IP"
    elif x_forwarded_for:
        ip_method = "X-Forwarded-For"
    else:
        ip_method = "remote_addr"

    status = {
        "cloudflare_domain": os.getenv("CLOUDFLARE_DOMAIN"),
        "ip_detection_method": ip_method,
        "real_ip": get_real_ip(),
        "cdn_headers_present": bool(cf_connecting_ip),
        "referrer_validation_active": bool(os.getenv("CLOUDFLARE_DOMAIN")),
        "cdn_security_enabled": _get_env_bool("ENABLE_CDN_SECURITY", True),
        "trust_cf_connecting_ip": _get_env_bool("TRUST_CF_CONNECTING_IP", True),
        "strict_ip_validation": _get_env_bool("STRICT_IP_VALIDATION", True),
    }

    logger.debug(f"CDN security status: {status}")
    return status


def cleanup_old_cdn_logs(days_to_keep: int = 30):
    """
    古いCDNアクセスログのクリーンアップ

    Args:
        days_to_keep: 保持する日数
    """
    try:
        from app import get_db_path
        from config.timezone import add_app_timedelta, get_app_now

        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()

        # 削除基準日の計算
        cutoff_date = add_app_timedelta(get_app_now(), days=-days_to_keep)
        cutoff_timestamp = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")

        # 古いログの削除
        cursor.execute(
            "DELETE FROM cdn_access_logs WHERE created_at < ?", (cutoff_timestamp,)
        )

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        logger.info(
            f"Cleaned up {deleted_count} old CDN access logs "
            f"(older than {days_to_keep} days)"
        )

    except Exception as e:
        logger.error(f"CDN log cleanup failed: {e}")


def get_cdn_access_statistics(hours: int = 24) -> Dict[str, Any]:
    """
    CDNアクセス統計の取得

    Args:
        hours: 統計期間（時間）

    Returns:
        dict: アクセス統計情報
    """
    try:
        from app import get_db_path
        from config.timezone import add_app_timedelta, get_app_now

        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 統計期間の開始時刻
        start_time = add_app_timedelta(get_app_now(), hours=-hours)
        start_timestamp = start_time.strftime("%Y-%m-%d %H:%M:%S")

        # 基本統計の取得
        cursor.execute(
            """
            SELECT
                COUNT(*) as total_requests,
                COUNT(DISTINCT real_ip) as unique_ips,
                COUNT(DISTINCT session_id) as unique_sessions,
                SUM(CASE WHEN cf_connecting_ip IS NOT NULL THEN 1 ELSE 0 END)
                    as cloudflare_requests
            FROM cdn_access_logs
            WHERE created_at >= ?
        """,
            (start_timestamp,),
        )

        stats = dict(cursor.fetchone())

        # 上位IPアドレスの取得
        cursor.execute(
            """
            SELECT real_ip, COUNT(*) as request_count
            FROM cdn_access_logs
            WHERE created_at >= ?
            GROUP BY real_ip
            ORDER BY request_count DESC
            LIMIT 10
        """,
            (start_timestamp,),
        )

        stats["top_ips"] = [dict(row) for row in cursor.fetchall()]

        # リファラー検証結果の統計
        cursor.execute(
            """
            SELECT
                json_extract(referrer_validation, '$.validation_type')
                    as validation_type,
                COUNT(*) as count
            FROM cdn_access_logs
            WHERE created_at >= ?
            GROUP BY validation_type
        """,
            (start_timestamp,),
        )

        stats["referrer_validation_stats"] = [dict(row) for row in cursor.fetchall()]

        conn.close()

        stats["period_hours"] = hours
        stats["generated_at"] = get_current_app_timestamp()

        return stats

    except Exception as e:
        logger.error(f"CDN statistics generation failed: {e}")
        return {"error": str(e)}


# ヘルパー関数


def _get_env_bool(key: str, default: bool = False) -> bool:
    """環境変数からbool値を取得"""
    value = os.getenv(key, "").lower()
    if value in ("true", "1", "yes", "on"):
        return True
    elif value in ("false", "0", "no", "off"):
        return False
    else:
        return default


# モジュール初期化時のログ出力
if _get_env_bool("ENABLE_CDN_SECURITY", True):
    logger.info("CDN security module initialized")
    logger.info(f"Cloudflare domain: {os.getenv('CLOUDFLARE_DOMAIN', 'not set')}")
    logger.info(
        f"Trust CF-Connecting-IP: {_get_env_bool('TRUST_CF_CONNECTING_IP', True)}"
    )
    logger.info(f"Strict IP validation: {_get_env_bool('STRICT_IP_VALIDATION', True)}")
else:
    logger.info("CDN security module disabled")
