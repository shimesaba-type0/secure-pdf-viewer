"""
信頼ネットワーク機能のテスト

GitHub Issue #10 対応: ADMIN_TRUSTED_NETWORKS 環境変数による信頼ネットワーク bypass
"""

import pytest
from unittest.mock import patch, MagicMock
import os


class TestTrustedNetworkDetection:
    """信頼ネットワーク検出機能テスト"""

    def test_trusted_network_ipv4_cidr(self, app):
        """IPv4 CIDR記法での信頼ネットワークテスト"""
        with app.app_context():
            from database.models import is_trusted_network

            # プライベートネットワーク設定
            with patch.dict(os.environ, {'ADMIN_TRUSTED_NETWORKS': '192.168.1.0/24,10.0.0.0/8,172.16.0.0/16'}):
                # 信頼ネットワーク内のIP
                assert is_trusted_network('192.168.1.1') is True
                assert is_trusted_network('192.168.1.100') is True
                assert is_trusted_network('192.168.1.254') is True
                assert is_trusted_network('10.0.0.1') is True
                assert is_trusted_network('10.255.255.254') is True
                assert is_trusted_network('172.16.0.1') is True
                assert is_trusted_network('172.16.255.254') is True

                # 信頼ネットワーク外のIP
                assert is_trusted_network('192.168.2.1') is False
                assert is_trusted_network('172.17.0.1') is False
                assert is_trusted_network('8.8.8.8') is False
                assert is_trusted_network('1.1.1.1') is False

    def test_trusted_network_single_ip(self, app):
        """単一IPアドレスでの信頼ネットワークテスト"""
        with app.app_context():
            from database.models import is_trusted_network

            with patch.dict(os.environ, {'ADMIN_TRUSTED_NETWORKS': '192.168.1.100,10.0.0.50'}):
                # 指定されたIPは信頼
                assert is_trusted_network('192.168.1.100') is True
                assert is_trusted_network('10.0.0.50') is True

                # 指定されていないIPは非信頼
                assert is_trusted_network('192.168.1.101') is False
                assert is_trusted_network('10.0.0.51') is False

    def test_trusted_network_mixed_format(self, app):
        """混合フォーマット（CIDR + 単一IP）での信頼ネットワークテスト"""
        with app.app_context():
            from database.models import is_trusted_network

            with patch.dict(os.environ, {'ADMIN_TRUSTED_NETWORKS': '192.168.1.0/24,203.0.113.10,172.16.0.0/16'}):
                # CIDRネットワーク内
                assert is_trusted_network('192.168.1.50') is True
                assert is_trusted_network('172.16.100.200') is True

                # 単一IP
                assert is_trusted_network('203.0.113.10') is True

                # 信頼ネットワーク外
                assert is_trusted_network('203.0.113.11') is False
                assert is_trusted_network('192.168.2.50') is False

    def test_trusted_network_empty_config(self, app):
        """空の信頼ネットワーク設定テスト"""
        with app.app_context():
            from database.models import is_trusted_network

            with patch.dict(os.environ, {'ADMIN_TRUSTED_NETWORKS': ''}):
                # 空設定では全てのIPが非信頼
                assert is_trusted_network('192.168.1.1') is False
                assert is_trusted_network('127.0.0.1') is False

    def test_trusted_network_no_config(self, app):
        """信頼ネットワーク設定なしテスト"""
        with app.app_context():
            from database.models import is_trusted_network

            # 環境変数が設定されていない場合
            with patch('os.getenv') as mock_getenv:
                mock_getenv.return_value = ''

                assert is_trusted_network('192.168.1.1') is False
                assert is_trusted_network('127.0.0.1') is False

    def test_trusted_network_invalid_ip(self, app):
        """無効なIPアドレスでのテスト"""
        with app.app_context():
            from database.models import is_trusted_network

            with patch.dict(os.environ, {'ADMIN_TRUSTED_NETWORKS': '192.168.1.0/24'}):
                # 無効なIPアドレス
                assert is_trusted_network('invalid-ip') is False
                assert is_trusted_network('999.999.999.999') is False
                assert is_trusted_network('') is False

    def test_trusted_network_invalid_cidr(self, app):
        """無効なCIDR記法でのテスト"""
        with app.app_context():
            from database.models import is_trusted_network

            with patch.dict(os.environ, {'ADMIN_TRUSTED_NETWORKS': '192.168.1.0/33,invalid-network'}):
                # 有効なIPは通常通り処理される
                assert is_trusted_network('192.168.1.1') is False  # 無効なCIDRなので処理されない

    def test_trusted_network_ipv6_support(self, app):
        """IPv6アドレスでのテスト（将来対応確認）"""
        with app.app_context():
            from database.models import is_trusted_network

            with patch.dict(os.environ, {'ADMIN_TRUSTED_NETWORKS': '::1,2001:db8::/32'}):
                # IPv6ローカルホスト
                assert is_trusted_network('::1') is True

                # IPv6ネットワーク内
                assert is_trusted_network('2001:db8::1') is True
                assert is_trusted_network('2001:db8:1234::5678') is True

                # IPv6ネットワーク外
                assert is_trusted_network('2001:db9::1') is False

    def test_trusted_network_whitespace_handling(self, app):
        """空白文字を含む設定の処理テスト"""
        with app.app_context():
            from database.models import is_trusted_network

            # 空白文字を含む設定
            with patch.dict(os.environ, {'ADMIN_TRUSTED_NETWORKS': ' 192.168.1.0/24 , 10.0.0.1 , '}):
                assert is_trusted_network('192.168.1.100') is True
                assert is_trusted_network('10.0.0.1') is True


class TestTrustedNetworkSecurity:
    """信頼ネットワークセキュリティ機能テスト"""

    @pytest.fixture
    def setup_database(self, app):
        """テスト用データベースセットアップ"""
        with app.app_context():
            from database import get_db
            from database.models import create_tables

            with get_db() as db:
                create_tables(db)

                # admin_session_events テーブル作成
                db.execute('''
                    CREATE TABLE IF NOT EXISTS admin_session_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        admin_email TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        event_details JSON,
                        ip_address TEXT,
                        user_agent TEXT,
                        created_at TEXT NOT NULL
                    )
                ''')

                # セキュリティ設定
                settings = [
                    ('session_rotation_alert_threshold', '5', 'integer', 'セッションローテーション警告閾値', 'security', False),
                    ('session_rotation_lock_threshold', '10', 'integer', 'セッションローテーションロック閾値', 'security', False),
                ]

                for setting in settings:
                    db.execute('''
                        INSERT OR IGNORE INTO settings (key, value, value_type, description, category, is_sensitive)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', setting)

                db.commit()

    def test_trusted_network_bypass_security_checks(self, app, setup_database):
        """信頼ネットワークからのセキュリティチェック bypass テスト"""
        with app.app_context():
            from database.models import check_session_security_violations

            admin_email = 'trusted@example.com'

            # 信頼ネットワークからのアクセス
            with patch('database.models.is_trusted_network') as mock_trusted:
                mock_trusted.return_value = True

                # セッションローテーション回数に関係なくbypass
                with patch('database.models.get_session_rotation_count') as mock_count:
                    mock_count.return_value = 15  # ロック閾値を超える回数

                    result = check_session_security_violations(admin_email, '192.168.1.100')

                    assert result['violated'] is False
                    assert result['trusted_network'] is True
                    # ローテーション回数のチェック自体が実行されない

    def test_untrusted_network_security_checks(self, app, setup_database):
        """非信頼ネットワークからのセキュリティチェックテスト"""
        with app.app_context():
            from database.models import check_session_security_violations

            admin_email = 'untrusted@example.com'

            # 非信頼ネットワークからのアクセス
            with patch('database.models.is_trusted_network') as mock_trusted:
                mock_trusted.return_value = False

                # 正常範囲のローテーション回数
                with patch('database.models.get_session_rotation_count') as mock_count:
                    mock_count.return_value = 3

                    result = check_session_security_violations(admin_email, '8.8.8.8')

                    assert result['violated'] is False
                    assert result['trusted_network'] is False
                    assert result['action_required'] == 'none'

                # 警告レベルのローテーション回数
                with patch('database.models.get_session_rotation_count') as mock_count:
                    mock_count.return_value = 7

                    result = check_session_security_violations(admin_email, '8.8.8.8')

                    assert result['violated'] is True
                    assert result['trusted_network'] is False
                    assert result['action_required'] == 'alert'

                # ロックレベルのローテーション回数
                with patch('database.models.get_session_rotation_count') as mock_count:
                    mock_count.return_value = 12

                    result = check_session_security_violations(admin_email, '8.8.8.8')

                    assert result['violated'] is True
                    assert result['trusted_network'] is False
                    assert result['action_required'] == 'lock'

    def test_trusted_network_logging(self, app, setup_database):
        """信頼ネットワークアクセスのログ記録テスト"""
        with app.app_context():
            from database.models import check_session_security_violations, log_session_event

            admin_email = 'logging@example.com'

            # 信頼ネットワークからのアクセスログ記録
            log_session_event(admin_email, 'session123', 'trusted_network_access', {
                'ip_address': '192.168.1.100',
                'trusted_network': True,
                'bypass_reason': 'admin_trusted_networks'
            })

            # ログ記録確認
            from database import get_db
            import sqlite3
            with get_db() as db:
                db.row_factory = sqlite3.Row
                events = db.execute('''
                    SELECT * FROM admin_session_events
                    WHERE admin_email = ? AND event_type = ?
                ''', (admin_email, 'trusted_network_access')).fetchall()

                assert len(events) == 1
                event = events[0]
                assert event['admin_email'] == admin_email
                assert event['event_type'] == 'trusted_network_access'

    def test_security_threshold_configuration(self, app, setup_database):
        """セキュリティ閾値設定のテスト"""
        with app.app_context():
            from database.models import check_session_security_violations, get_setting, set_setting
            from database import get_db

            admin_email = 'threshold@example.com'

            # カスタム閾値設定
            with get_db() as db:
                set_setting(db, 'session_rotation_alert_threshold', '3', 'test')
                set_setting(db, 'session_rotation_lock_threshold', '6', 'test')

            # 非信頼ネットワークからのアクセス
            with patch('database.models.is_trusted_network') as mock_trusted:
                mock_trusted.return_value = False

                # 警告レベル（3回以上）
                with patch('database.models.get_session_rotation_count') as mock_count:
                    mock_count.return_value = 4

                    result = check_session_security_violations(admin_email, '8.8.8.8')

                    assert result['violated'] is True
                    assert result['action_required'] == 'alert'
                    assert result['alert_threshold'] == 3

                # ロックレベル（6回以上）
                with patch('database.models.get_session_rotation_count') as mock_count:
                    mock_count.return_value = 7

                    result = check_session_security_violations(admin_email, '8.8.8.8')

                    assert result['violated'] is True
                    assert result['action_required'] == 'lock'
                    assert result['lock_threshold'] == 6


class TestTrustedNetworkIntegration:
    """信頼ネットワーク統合テスト"""

    def test_real_world_network_scenarios(self, app):
        """実世界のネットワークシナリオテスト"""
        with app.app_context():
            from database.models import is_trusted_network

            # 典型的な企業ネットワーク設定
            corporate_networks = '192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,203.0.113.0/24'

            with patch.dict(os.environ, {'ADMIN_TRUSTED_NETWORKS': corporate_networks}):
                # プライベートネットワーク内
                assert is_trusted_network('192.168.10.50') is True
                assert is_trusted_network('10.1.2.3') is True
                assert is_trusted_network('172.16.100.200') is True
                assert is_trusted_network('172.31.255.254') is True  # 172.16.0.0/12 の範囲内

                # 特定の公開IP
                assert is_trusted_network('203.0.113.100') is True

                # インターネット上のIP
                assert is_trusted_network('8.8.8.8') is False
                assert is_trusted_network('1.1.1.1') is False
                assert is_trusted_network('203.0.114.1') is False

    def test_docker_kubernetes_scenarios(self, app):
        """Docker/Kubernetesシナリオテスト"""
        with app.app_context():
            from database.models import is_trusted_network

            # Docker/K8sネットワーク設定
            container_networks = '172.17.0.0/16,10.244.0.0/16,192.168.99.0/24'

            with patch.dict(os.environ, {'ADMIN_TRUSTED_NETWORKS': container_networks}):
                # Docker デフォルトネットワーク
                assert is_trusted_network('172.17.0.2') is True

                # Kubernetes Pod ネットワーク
                assert is_trusted_network('10.244.1.50') is True

                # Minikube
                assert is_trusted_network('192.168.99.100') is True

                # ホストネットワーク外
                assert is_trusted_network('172.18.0.1') is False

    def test_cloudflare_proxy_scenarios(self, app):
        """Cloudflare プロキシシナリオテスト"""
        with app.app_context():
            from database.models import is_trusted_network

            # CloudflareのIPレンジ（簡略版）
            cloudflare_ips = '103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,104.16.0.0/13'

            with patch.dict(os.environ, {'ADMIN_TRUSTED_NETWORKS': cloudflare_ips}):
                # Cloudflare IP
                assert is_trusted_network('103.21.244.10') is True
                assert is_trusted_network('104.16.1.1') is True

                # 非Cloudflare IP
                assert is_trusted_network('103.20.244.10') is False
                assert is_trusted_network('8.8.8.8') is False

    def test_performance_with_large_network_list(self, app):
        """大量ネットワークリストでの性能テスト"""
        with app.app_context():
            from database.models import is_trusted_network

            # 50個のネットワークを定義
            large_network_list = ','.join([f'10.{i}.0.0/24' for i in range(50)])

            with patch.dict(os.environ, {'ADMIN_TRUSTED_NETWORKS': large_network_list}):
                import time

                # 性能測定
                start_time = time.time()

                # 複数回のチェック実行
                for i in range(100):
                    is_trusted_network(f'10.{i % 50}.0.1')

                end_time = time.time()
                execution_time = end_time - start_time

                # 実行時間が1秒以内であることを確認
                assert execution_time < 1.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])