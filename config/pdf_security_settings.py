"""
PDF直接ダウンロード防止機能の設定管理
"""
import os
import json
import sqlite3
import ipaddress
import re
from urllib.parse import urlparse
from database.models import get_setting, set_setting


def get_pdf_security_config():
    """
    PDF セキュリティ設定を取得
    優先順位: データベース設定 > 環境変数 > デフォルト値
    """
    try:
        conn = sqlite3.connect('instance/database.db')
        
        # 各設定項目を取得
        config = {
            'enabled': get_setting(
                conn, 
                'pdf_download_prevention_enabled',
                _get_env_bool('PDF_DOWNLOAD_PREVENTION_ENABLED', True)
            ),
            'allowed_referrer_domains': get_setting(
                conn,
                'pdf_allowed_referrer_domains',
                _get_env_list('PDF_ALLOWED_REFERRER_DOMAINS', ['localhost', '127.0.0.1'])
            ),
            'blocked_user_agents': get_setting(
                conn,
                'pdf_blocked_user_agents', 
                _get_env_list('PDF_BLOCKED_USER_AGENTS', ['wget', 'curl', 'python-requests'])
            ),
            'strict_mode': get_setting(
                conn,
                'pdf_strict_mode',
                _get_env_bool('PDF_STRICT_MODE', False)
            ),
            'log_blocked_attempts': get_setting(
                conn,
                'pdf_log_blocked_attempts',
                _get_env_bool('PDF_LOG_BLOCKED_ATTEMPTS', True)
            ),
            'user_agent_check_enabled': get_setting(
                conn,
                'pdf_user_agent_check_enabled',
                _get_env_bool('PDF_USER_AGENT_CHECK_ENABLED', True)
            )
        }
        
        conn.close()
        return config
        
    except Exception as e:
        print(f"設定取得エラー: {e}")
        # フォールバック: 環境変数とデフォルト値のみ使用
        return {
            'enabled': _get_env_bool('PDF_DOWNLOAD_PREVENTION_ENABLED', True),
            'allowed_referrer_domains': _get_env_list('PDF_ALLOWED_REFERRER_DOMAINS', ['localhost', '127.0.0.1']),
            'blocked_user_agents': _get_env_list('PDF_BLOCKED_USER_AGENTS', ['wget', 'curl', 'python-requests']),
            'strict_mode': _get_env_bool('PDF_STRICT_MODE', False),
            'log_blocked_attempts': _get_env_bool('PDF_LOG_BLOCKED_ATTEMPTS', True)
        }


def set_pdf_security_config(config, updated_by='admin'):
    """
    PDF セキュリティ設定を更新
    
    Args:
        config (dict): 更新する設定値の辞書
        updated_by (str): 更新者
    """
    try:
        conn = sqlite3.connect('instance/database.db')
        
        if 'enabled' in config:
            set_setting(conn, 'pdf_download_prevention_enabled', 
                       config['enabled'], updated_by)
        
        if 'allowed_referrer_domains' in config:
            set_setting(conn, 'pdf_allowed_referrer_domains',
                       config['allowed_referrer_domains'], updated_by)
        
        if 'blocked_user_agents' in config:
            set_setting(conn, 'pdf_blocked_user_agents',
                       config['blocked_user_agents'], updated_by)
        
        if 'strict_mode' in config:
            set_setting(conn, 'pdf_strict_mode',
                       config['strict_mode'], updated_by)
        
        if 'log_blocked_attempts' in config:
            set_setting(conn, 'pdf_log_blocked_attempts',
                       config['log_blocked_attempts'], updated_by)
        
        if 'user_agent_check_enabled' in config:
            set_setting(conn, 'pdf_user_agent_check_enabled',
                       config['user_agent_check_enabled'], updated_by)
        
        conn.commit()
        conn.close()
        
        print(f"PDF セキュリティ設定が更新されました (by: {updated_by})")
        return True
        
    except Exception as e:
        print(f"設定更新エラー: {e}")
        return False


def initialize_pdf_security_settings():
    """
    PDF セキュリティ設定の初期値をデータベースに投入
    既存の設定がある場合は上書きしない
    """
    try:
        conn = sqlite3.connect('instance/database.db')
        
        # 既存設定の確認と初期値投入
        settings_to_initialize = [
            ('pdf_download_prevention_enabled', 
             _get_env_bool('PDF_DOWNLOAD_PREVENTION_ENABLED', True), 
             'boolean'),
            ('pdf_allowed_referrer_domains',
             _get_env_list('PDF_ALLOWED_REFERRER_DOMAINS', ['localhost', '127.0.0.1']),
             'json'),
            ('pdf_blocked_user_agents',
             _get_env_list('PDF_BLOCKED_USER_AGENTS', ['wget', 'curl', 'python-requests']),
             'json'),
            ('pdf_strict_mode',
             _get_env_bool('PDF_STRICT_MODE', False),
             'boolean'),
            ('pdf_log_blocked_attempts',
             _get_env_bool('PDF_LOG_BLOCKED_ATTEMPTS', True),
             'boolean'),
            ('pdf_user_agent_check_enabled',
             _get_env_bool('PDF_USER_AGENT_CHECK_ENABLED', True),
             'boolean')
        ]
        
        initialized_count = 0
        for key, default_value, value_type in settings_to_initialize:
            existing = get_setting(conn, key)
            if existing is None:
                set_setting(conn, key, default_value, 'system_init')
                initialized_count += 1
                print(f"初期設定を投入: {key} = {default_value}")
        
        conn.commit()
        conn.close()
        
        if initialized_count > 0:
            print(f"PDF セキュリティ設定の初期化完了 ({initialized_count}件)")
        else:
            print("PDF セキュリティ設定は既に存在します")
        
        return True
        
    except Exception as e:
        print(f"初期設定投入エラー: {e}")
        return False


def _get_env_bool(key, default):
    """環境変数からブール値を取得"""
    value = os.environ.get(key, '').lower()
    if value in ('true', '1', 'yes', 'on'):
        return True
    elif value in ('false', '0', 'no', 'off'):
        return False
    else:
        return default


def _get_env_list(key, default):
    """環境変数からリスト値を取得（カンマ区切り）"""
    value = os.environ.get(key, '')
    if value:
        return [item.strip() for item in value.split(',') if item.strip()]
    else:
        return default


def is_referrer_allowed(referer_url, allowed_domains):
    """
    Referrerが許可されているかチェック（ドメイン名・IP範囲対応）
    
    Args:
        referer_url (str): ReferrerのURL
        allowed_domains (list): 許可されたドメイン/IP範囲のリスト
    
    Returns:
        bool: 許可されている場合True
    
    対応形式:
        - ドメイン名: 'example.com', 'localhost'
        - IPアドレス: '127.0.0.1', '192.168.1.100'
        - CIDR表記: '10.0.0.0/24', '192.168.0.0/16'
        - IP範囲（ハイフン）: '192.168.1.1-192.168.1.100'
    """
    if not referer_url or not allowed_domains:
        return False
    
    try:
        # URLからホスト部分を抽出
        parsed = urlparse(referer_url)
        host = parsed.hostname or parsed.netloc
        
        if not host:
            return False
        
        # 各許可パターンとチェック
        for allowed in allowed_domains:
            allowed = allowed.strip()
            if not allowed:
                continue
            
            # 1. 完全一致（ドメイン名・IP）
            if host == allowed:
                return True
            
            # 2. ドメイン名の部分一致（サブドメイン対応）
            if _is_domain_match(host, allowed):
                return True
            
            # 3. CIDR表記のチェック
            if '/' in allowed and _is_ip_in_cidr(host, allowed):
                return True
            
            # 4. IP範囲（ハイフン区切り）のチェック
            if '-' in allowed and _is_ip_in_range(host, allowed):
                return True
        
        return False
        
    except Exception as e:
        print(f"Referrerチェックエラー: {e} (referer: {referer_url})")
        return False


def _is_domain_match(host, allowed_domain):
    """ドメイン名のマッチング（サブドメイン対応）"""
    try:
        # IPアドレスの場合は部分一致しない
        ipaddress.ip_address(host)
        return False
    except ValueError:
        # ドメイン名の場合
        if allowed_domain.startswith('.'):
            # .example.com形式：サブドメインを許可
            return host.endswith(allowed_domain) or host == allowed_domain[1:]
        else:
            # example.com形式：完全一致または末尾一致
            return host == allowed_domain or host.endswith('.' + allowed_domain)


def _is_ip_in_cidr(host, cidr_range):
    """IPアドレスがCIDR範囲内かチェック"""
    try:
        host_ip = ipaddress.ip_address(host)
        network = ipaddress.ip_network(cidr_range, strict=False)
        return host_ip in network
    except (ValueError, ipaddress.AddressValueError, ipaddress.NetmaskValueError):
        return False


def _is_ip_in_range(host, ip_range):
    """IPアドレスが範囲内かチェック（192.168.1.1-192.168.1.100形式）"""
    try:
        host_ip = ipaddress.ip_address(host)
        start_str, end_str = ip_range.split('-', 1)
        start_ip = ipaddress.ip_address(start_str.strip())
        end_ip = ipaddress.ip_address(end_str.strip())
        
        return start_ip <= host_ip <= end_ip
    except (ValueError, ipaddress.AddressValueError):
        return False


def validate_allowed_domains(domains):
    """
    許可ドメインリストの妥当性チェック
    
    Args:
        domains (list): チェック対象のドメインリスト
    
    Returns:
        dict: {'valid': bool, 'errors': list, 'warnings': list}
    """
    result = {'valid': True, 'errors': [], 'warnings': []}
    
    for domain in domains:
        domain = domain.strip()
        if not domain:
            continue
        
        try:
            # CIDR表記のチェック
            if '/' in domain:
                ipaddress.ip_network(domain, strict=False)
                continue
            
            # IP範囲のチェック
            if '-' in domain:
                start_str, end_str = domain.split('-', 1)
                start_ip = ipaddress.ip_address(start_str.strip())
                end_ip = ipaddress.ip_address(end_str.strip())
                if start_ip > end_ip:
                    result['errors'].append(f"不正なIP範囲: {domain} (開始IPが終了IPより大きい)")
                    result['valid'] = False
                continue
            
            # IPアドレスのチェック
            try:
                ipaddress.ip_address(domain)
                continue
            except ValueError:
                pass
            
            # ドメイン名のチェック（簡易）
            if not re.match(r'^[a-zA-Z0-9.-]+$', domain):
                result['warnings'].append(f"疑わしいドメイン名: {domain}")
            
        except (ValueError, ipaddress.AddressValueError, ipaddress.NetmaskValueError) as e:
            result['errors'].append(f"不正な形式: {domain} ({str(e)})")
            result['valid'] = False
    
    return result


# テスト用関数
def test_pdf_security_config():
    """設定管理のテスト"""
    print("=== PDF セキュリティ設定テスト ===")
    
    # 初期化
    initialize_pdf_security_settings()
    
    # 現在の設定を取得
    config = get_pdf_security_config()
    print(f"現在の設定: {json.dumps(config, indent=2, ensure_ascii=False)}")
    
    # 設定変更テスト
    test_config = {
        'enabled': False,
        'allowed_referrer_domains': ['localhost', 'test.example.com']
    }
    print(f"テスト設定を適用: {test_config}")
    set_pdf_security_config(test_config, 'test_user')
    
    # 変更後の設定を取得
    updated_config = get_pdf_security_config()
    print(f"更新後の設定: {json.dumps(updated_config, indent=2, ensure_ascii=False)}")


if __name__ == '__main__':
    test_pdf_security_config()