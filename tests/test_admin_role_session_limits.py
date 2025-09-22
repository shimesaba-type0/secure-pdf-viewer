"""
管理者ロール別セッション制限機能のテスト

GitHub Issue #10 対応: スーパー管理者無制限、一般管理者制限(10セッション)
"""

import pytest
import sqlite3
import uuid
from unittest.mock import patch, MagicMock
from config.timezone import get_app_now, get_app_datetime_string


class TestAdminRoleSessionLimits:
    """管理者ロール別セッション制限テスト"""

    @pytest.fixture
    def setup_database(self, app):
        """テスト用データベースセットアップ"""
        with app.app_context():
            from database import get_db
            from database.models import create_tables, insert_initial_data

            # テーブル作成
            with get_db() as db:
                create_tables(db)

                # マイグレーション004の手動実行（ロールフィールド追加）
                try:
                    db.execute('ALTER TABLE admin_users ADD COLUMN role TEXT DEFAULT "admin"')
                except sqlite3.OperationalError:
                    pass  # カラムが既に存在する場合

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

                # テスト用設定追加
                settings = [
                    ('super_admin_unlimited_sessions', 'true', 'boolean', 'スーパー管理者の無制限セッション許可', 'security', False),
                    ('regular_admin_session_limit', '10', 'integer', '一般管理者のセッション制限数', 'security', False),
                    ('session_rotation_enabled', 'true', 'boolean', 'セッションローテーション機能有効化', 'security', False),
                    ('session_rotation_max_age_hours', '24', 'integer', 'セッション強制ローテーション時間（時間）', 'security', False),
                ]

                for setting in settings:
                    db.execute('''
                        INSERT OR IGNORE INTO settings (key, value, value_type, description, category, is_sensitive)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', setting)

                # テスト用管理者追加
                test_admins = [
                    ('super@example.com', 'super_admin'),
                    ('admin1@example.com', 'admin'),
                    ('admin2@example.com', 'admin'),
                ]

                for email, role in test_admins:
                    db.execute('''
                        INSERT OR IGNORE INTO admin_users (email, role, added_by, is_active)
                        VALUES (?, ?, ?, ?)
                    ''', (email, role, 'system', True))

                db.commit()

    def test_get_admin_role(self, app, setup_database):
        """管理者ロール取得テスト"""
        with app.app_context():
            from database.models import get_admin_role

            # スーパー管理者
            assert get_admin_role('super@example.com') == 'super_admin'

            # 一般管理者
            assert get_admin_role('admin1@example.com') == 'admin'

            # 存在しない管理者
            assert get_admin_role('nonexistent@example.com') is None

    def test_is_super_admin(self, app, setup_database):
        """スーパー管理者判定テスト"""
        with app.app_context():
            from database.models import is_super_admin

            assert is_super_admin('super@example.com') is True
            assert is_super_admin('admin1@example.com') is False
            assert is_super_admin('nonexistent@example.com') is False

    def test_super_admin_unlimited_sessions(self, app, setup_database):
        """スーパー管理者無制限セッションテスト"""
        with app.app_context():
            from database.models import check_admin_session_limit, create_admin_session

            super_admin_email = 'super@example.com'

            # 初期状態: セッション制限チェック
            limit_check = check_admin_session_limit(super_admin_email)
            assert limit_check['allowed'] is True
            assert limit_check['unlimited'] is True
            assert limit_check['role'] == 'super_admin'
            assert limit_check['max_limit'] is None

            # 大量セッション作成
            for i in range(50):  # 通常の制限を大幅に超える数
                session_id = str(uuid.uuid4())
                create_admin_session(
                    super_admin_email,
                    session_id,
                    '127.0.0.1',
                    'TestAgent'
                )

            # セッション制限チェック（大量セッション後）
            limit_check = check_admin_session_limit(super_admin_email)
            assert limit_check['allowed'] is True
            assert limit_check['unlimited'] is True
            assert limit_check['current_count'] == 50

    def test_regular_admin_session_limit(self, app, setup_database):
        """一般管理者セッション制限テスト"""
        with app.app_context():
            from database.models import check_admin_session_limit, create_admin_session

            admin_email = 'admin1@example.com'

            # 初期状態: セッション制限チェック
            limit_check = check_admin_session_limit(admin_email)
            assert limit_check['allowed'] is True
            assert limit_check['unlimited'] is False
            assert limit_check['role'] == 'admin'
            assert limit_check['max_limit'] == 10

            # 制限以内のセッション作成（9個）
            for i in range(9):
                session_id = str(uuid.uuid4())
                create_admin_session(
                    admin_email,
                    session_id,
                    '127.0.0.1',
                    'TestAgent'
                )

            # 制限チェック（まだ許可されるべき）
            limit_check = check_admin_session_limit(admin_email)
            assert limit_check['allowed'] is True
            assert limit_check['current_count'] == 9

            # 10個目のセッション作成
            session_id = str(uuid.uuid4())
            create_admin_session(admin_email, session_id, '127.0.0.1', 'TestAgent')

            # 制限チェック（制限に達した）
            limit_check = check_admin_session_limit(admin_email)
            assert limit_check['allowed'] is False
            assert limit_check['current_count'] == 10

    def test_cleanup_old_sessions_for_user(self, app, setup_database):
        """ユーザー古いセッションクリーンアップテスト"""
        with app.app_context():
            from database.models import (
                cleanup_old_sessions_for_user,
                create_admin_session,
                get_admin_session_count
            )

            admin_email = 'admin2@example.com'

            # 15個のセッション作成
            session_ids = []
            for i in range(15):
                session_id = str(uuid.uuid4())
                session_ids.append(session_id)
                create_admin_session(admin_email, session_id, '127.0.0.1', 'TestAgent')

            # セッション数確認
            assert get_admin_session_count(admin_email) == 15

            # クリーンアップ実行（10個まで保持）
            cleanup_old_sessions_for_user(admin_email, keep_count=10)

            # セッション数確認（10個まで削減されている）
            assert get_admin_session_count(admin_email) == 10

    def test_super_admin_no_cleanup(self, app, setup_database):
        """スーパー管理者のクリーンアップ除外テスト"""
        with app.app_context():
            from database.models import (
                cleanup_old_sessions_for_user,
                create_admin_session,
                get_admin_session_count
            )

            super_admin_email = 'super@example.com'

            # 20個のセッション作成
            for i in range(20):
                session_id = str(uuid.uuid4())
                create_admin_session(super_admin_email, session_id, '127.0.0.1', 'TestAgent')

            # セッション数確認
            assert get_admin_session_count(super_admin_email) == 20

            # クリーンアップ実行（スーパー管理者は対象外）
            cleanup_old_sessions_for_user(super_admin_email)

            # セッション数確認（変化なし）
            assert get_admin_session_count(super_admin_email) == 20

    def test_set_admin_role(self, app, setup_database):
        """管理者ロール設定テスト"""
        with app.app_context():
            from database.models import set_admin_role, get_admin_role

            # 一般管理者をスーパー管理者に昇格
            set_admin_role('admin1@example.com', 'super_admin', 'super@example.com')
            assert get_admin_role('admin1@example.com') == 'super_admin'

            # スーパー管理者を一般管理者に降格
            set_admin_role('admin1@example.com', 'admin', 'super@example.com')
            assert get_admin_role('admin1@example.com') == 'admin'

    def test_invalid_role_rejection(self, app, setup_database):
        """無効なロール設定の拒否テスト"""
        with app.app_context():
            from database.models import set_admin_role, get_admin_role

            # 無効なロール設定を試行
            with pytest.raises(ValueError):
                set_admin_role('admin1@example.com', 'invalid_role', 'super@example.com')

            # ロールが変更されていないことを確認
            assert get_admin_role('admin1@example.com') == 'admin'

    def test_session_limit_disabled_for_super_admin(self, app, setup_database):
        """スーパー管理者制限無効化設定テスト"""
        with app.app_context():
            from database.models import (
                check_admin_session_limit,
                create_admin_session,
                set_setting
            )

            super_admin_email = 'super@example.com'

            # 無制限機能を無効化
            from database import get_db
            with get_db() as db:
                set_setting(db, 'super_admin_unlimited_sessions', 'false', 'test')

            # セッション制限チェック（制限が適用されるべき）
            limit_check = check_admin_session_limit(super_admin_email)
            assert limit_check['unlimited'] is False
            assert limit_check['max_limit'] == 10  # 一般管理者と同じ制限

    def test_session_events_logging(self, app, setup_database):
        """セッションイベントログテスト"""
        with app.app_context():
            from database.models import log_session_event

            admin_email = 'admin1@example.com'
            session_id = str(uuid.uuid4())

            # セッションイベントログ記録
            log_session_event(admin_email, session_id, 'created', {
                'ip_address': '127.0.0.1',
                'user_agent': 'TestAgent'
            })

            # ログ記録確認
            from database import get_db
            with get_db() as db:
                db.row_factory = sqlite3.Row
                events = db.execute('''
                    SELECT * FROM admin_session_events
                    WHERE admin_email = ? AND session_id = ?
                ''', (admin_email, session_id)).fetchall()

                assert len(events) == 1
                assert events[0]['event_type'] == 'created'
                assert events[0]['admin_email'] == admin_email


class TestSessionRotation:
    """セッションローテーション機能テスト"""

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

                # ローテーション設定
                db.execute('''
                    INSERT OR IGNORE INTO settings (key, value, value_type, description, category, is_sensitive)
                    VALUES ('session_rotation_enabled', 'true', 'boolean', 'セッションローテーション機能有効化', 'security', FALSE)
                ''')

                db.commit()

    @patch('database.models.get_app_now')
    def test_rotate_session_if_needed(self, mock_now, app, setup_database):
        """セッションローテーション必要性判定テスト"""
        with app.app_context():
            from database.models import (
                rotate_session_if_needed,
                create_admin_session,
                get_admin_session_info
            )
            from datetime import datetime, timedelta
            from config.timezone import to_app_timezone

            admin_email = 'test@example.com'
            session_id = str(uuid.uuid4())

            # 現在時刻設定
            current_time = to_app_timezone(datetime(2024, 1, 1, 12, 0, 0))
            mock_now.return_value = current_time

            # セッション作成（25時間前）
            old_time = current_time - timedelta(hours=25)

            # セッション作成をmock時刻で実行
            with patch('database.models.get_app_datetime_string') as mock_datetime_string:
                mock_datetime_string.return_value = old_time.strftime("%Y-%m-%d %H:%M:%S")
                create_admin_session(admin_email, session_id, '127.0.0.1', 'TestAgent')

            # ローテーション実行
            rotated = rotate_session_if_needed(session_id, admin_email)

            # ローテーションが実行されたことを確認
            assert rotated is True

    def test_get_session_rotation_count(self, app, setup_database):
        """セッションローテーション回数取得テスト"""
        with app.app_context():
            from database.models import (
                log_session_event,
                get_session_rotation_count
            )

            admin_email = 'test@example.com'

            # 複数回のローテーションイベントを記録
            for i in range(7):
                session_id = str(uuid.uuid4())
                log_session_event(admin_email, session_id, 'rotated', {
                    'reason': 'test_rotation'
                })

            # ローテーション回数確認
            count = get_session_rotation_count(admin_email, hours=24)
            assert count == 7


class TestTrustedNetwork:
    """信頼ネットワーク機能テスト"""

    def test_is_trusted_network_ipv4(self, app):
        """IPv4信頼ネットワークテスト"""
        with app.app_context():
            from database.models import is_trusted_network

            # 環境変数設定をmock
            with patch('os.getenv') as mock_getenv:
                mock_getenv.return_value = '192.168.1.0/24,10.0.0.0/8'

                # 信頼ネットワーク内のIP
                assert is_trusted_network('192.168.1.100') is True
                assert is_trusted_network('10.0.0.1') is True

                # 信頼ネットワーク外のIP
                assert is_trusted_network('172.16.0.1') is False
                assert is_trusted_network('8.8.8.8') is False

    def test_is_trusted_network_single_ip(self, app):
        """単一IP信頼ネットワークテスト"""
        with app.app_context():
            from database.models import is_trusted_network

            with patch('os.getenv') as mock_getenv:
                mock_getenv.return_value = '192.168.1.100'

                assert is_trusted_network('192.168.1.100') is True
                assert is_trusted_network('192.168.1.101') is False

    def test_check_session_security_violations(self, app):
        """セッションセキュリティ違反チェックテスト"""
        with app.app_context():
            from database.models import check_session_security_violations

            admin_email = 'test@example.com'

            # 信頼ネットワークからのアクセス
            with patch('database.models.is_trusted_network') as mock_trusted:
                mock_trusted.return_value = True

                result = check_session_security_violations(admin_email, '192.168.1.100')
                assert result['violated'] is False
                assert result['trusted_network'] is True

            # 非信頼ネットワークからのアクセス（正常範囲）
            with patch('database.models.is_trusted_network') as mock_trusted:
                with patch('database.models.get_session_rotation_count') as mock_count:
                    mock_trusted.return_value = False
                    mock_count.return_value = 3  # 警告閾値以下

                    result = check_session_security_violations(admin_email, '8.8.8.8')
                    assert result['violated'] is False
                    assert result['action_required'] == 'none'

            # セキュリティ違反（警告レベル）
            with patch('database.models.is_trusted_network') as mock_trusted:
                with patch('database.models.get_session_rotation_count') as mock_count:
                    mock_trusted.return_value = False
                    mock_count.return_value = 7  # 警告閾値以上、ロック閾値未満

                    result = check_session_security_violations(admin_email, '8.8.8.8')
                    assert result['violated'] is True
                    assert result['action_required'] == 'alert'

            # セキュリティ違反（ロックレベル）
            with patch('database.models.is_trusted_network') as mock_trusted:
                with patch('database.models.get_session_rotation_count') as mock_count:
                    mock_trusted.return_value = False
                    mock_count.return_value = 12  # ロック閾値以上

                    result = check_session_security_violations(admin_email, '8.8.8.8')
                    assert result['violated'] is True
                    assert result['action_required'] == 'lock'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])