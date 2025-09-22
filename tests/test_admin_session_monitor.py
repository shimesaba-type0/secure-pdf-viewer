"""
管理者セッション監視機能のテスト

GitHub Issue #10 対応: 管理者セッション状況監視ページ
"""

import pytest
import sqlite3
import uuid
import json
from unittest.mock import patch, MagicMock
from flask import session


class TestAdminSessionMonitorAPI:
    """管理者セッション監視API テスト"""

    @pytest.fixture
    def setup_database(self, app):
        """テスト用データベースセットアップ"""
        with app.app_context():
            from database import get_db
            from database.models import create_tables

            with get_db() as db:
                create_tables(db)

                # admin_usersテーブルにroleカラム追加
                try:
                    db.execute('ALTER TABLE admin_users ADD COLUMN role TEXT DEFAULT "admin"')
                except sqlite3.OperationalError:
                    pass

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

                # テスト用管理者セッション追加
                from config.timezone import get_app_datetime_string
                current_time = get_app_datetime_string()

                test_sessions = [
                    ('session1', 'super@example.com', '192.168.1.100', 'Mozilla/5.0 Super'),
                    ('session2', 'super@example.com', '192.168.1.101', 'Mozilla/5.0 Super'),
                    ('session3', 'admin1@example.com', '192.168.1.200', 'Mozilla/5.0 Admin'),
                    ('session4', 'admin2@example.com', '192.168.1.201', 'Mozilla/5.0 Admin'),
                ]

                for session_id, email, ip, ua in test_sessions:
                    db.execute('''
                        INSERT OR IGNORE INTO admin_sessions
                        (session_id, admin_email, created_at, last_verified_at, ip_address, user_agent, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (session_id, email, current_time, current_time, ip, ua, True))

                db.commit()

    def test_session_stats_api_super_admin(self, app, client, setup_database):
        """セッション統計API（スーパー管理者）テスト"""
        with app.app_context():
            # スーパー管理者でログイン
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['email'] = 'super@example.com'
                sess['session_id'] = 'session1'

            # セッション統計取得
            with patch('database.models.is_super_admin') as mock_is_super:
                mock_is_super.return_value = True

                with patch('database.models.get_admin_session_stats') as mock_stats:
                    mock_stats.return_value = {
                        'total_sessions': 4,
                        'super_admin_sessions': 2,
                        'regular_admin_sessions': 2,
                        'warning_count': 0
                    }

                    response = client.get('/admin/api/session-stats')
                    assert response.status_code == 200

                    data = response.get_json()
                    assert data['success'] is True
                    assert data['total_sessions'] == 4
                    assert data['super_admin_sessions'] == 2
                    assert data['regular_admin_sessions'] == 2

    def test_session_stats_api_regular_admin_forbidden(self, app, client, setup_database):
        """セッション統計API（一般管理者：アクセス禁止）テスト"""
        with app.app_context():
            # 一般管理者でログイン
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['email'] = 'admin1@example.com'
                sess['session_id'] = 'session3'

            # セッション統計取得（アクセス禁止）
            with patch('database.models.is_super_admin') as mock_is_super:
                mock_is_super.return_value = False

                response = client.get('/admin/api/session-stats')
                assert response.status_code == 403

                data = response.get_json()
                assert 'error' in data
                assert 'スーパー管理者権限が必要です' in data['error']

    def test_admin_sessions_api(self, app, client, setup_database):
        """管理者セッション一覧API テスト"""
        with app.app_context():
            # スーパー管理者でログイン
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['email'] = 'super@example.com'
                sess['session_id'] = 'session1'

            with patch('database.models.is_super_admin') as mock_is_super:
                mock_is_super.return_value = True

                with patch('database.models.get_all_admin_sessions_with_stats') as mock_sessions:
                    mock_sessions.return_value = [
                        {
                            'email': 'super@example.com',
                            'role': 'super_admin',
                            'current_sessions': 2,
                            'max_limit': None,
                            'last_login': '2024-01-01 12:00:00',
                            'rotation_count_24h': 0,
                            'status': 'normal'
                        },
                        {
                            'email': 'admin1@example.com',
                            'role': 'admin',
                            'current_sessions': 1,
                            'max_limit': 10,
                            'last_login': '2024-01-01 11:00:00',
                            'rotation_count_24h': 2,
                            'status': 'normal'
                        }
                    ]

                    response = client.get('/admin/api/admin-sessions')
                    assert response.status_code == 200

                    data = response.get_json()
                    assert data['success'] is True
                    assert len(data['admin_sessions']) == 2

                    # スーパー管理者のデータ確認
                    super_admin = data['admin_sessions'][0]
                    assert super_admin['email'] == 'super@example.com'
                    assert super_admin['role'] == 'super_admin'
                    assert super_admin['max_limit'] is None

    def test_admin_session_details_api(self, app, client, setup_database):
        """管理者セッション詳細API テスト"""
        with app.app_context():
            # スーパー管理者でログイン
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['email'] = 'super@example.com'
                sess['session_id'] = 'session1'

            with patch('database.models.is_super_admin') as mock_is_super:
                mock_is_super.return_value = True

                with patch('database.models.get_admin_session_details') as mock_details:
                    mock_details.return_value = {
                        'admin_email': 'admin1@example.com',
                        'sessions': [
                            {
                                'session_id': 'session3',
                                'created_at': '2024-01-01 11:00:00',
                                'last_verified_at': '2024-01-01 12:00:00',
                                'ip_address': '192.168.1.200',
                                'user_agent': 'Mozilla/5.0 Admin'
                            }
                        ]
                    }

                    response = client.get('/admin/api/admin-sessions/admin1%40example.com')
                    assert response.status_code == 200

                    data = response.get_json()
                    assert data['admin_email'] == 'admin1@example.com'
                    assert len(data['sessions']) == 1

    def test_cleanup_sessions_api(self, app, client, setup_database):
        """セッションクリーンアップAPI テスト"""
        with app.app_context():
            # スーパー管理者でログイン
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['email'] = 'super@example.com'
                sess['session_id'] = 'session1'

            with patch('database.models.is_super_admin') as mock_is_super:
                mock_is_super.return_value = True

                with patch('database.models.cleanup_old_sessions_for_user') as mock_cleanup:
                    mock_cleanup.return_value = 5  # クリーンアップされたセッション数

                    response = client.post('/admin/api/cleanup-sessions',
                                         json={'admin_email': 'admin1@example.com'},
                                         content_type='application/json')

                    assert response.status_code == 200

                    data = response.get_json()
                    assert data['success'] is True
                    assert data['cleaned_count'] == 5

                    # クリーンアップ関数が呼ばれたことを確認
                    mock_cleanup.assert_called_once_with('admin1@example.com')

    def test_terminate_session_api(self, app, client, setup_database):
        """セッション終了API テスト"""
        with app.app_context():
            # スーパー管理者でログイン
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['email'] = 'super@example.com'
                sess['session_id'] = 'session1'

            with patch('database.models.is_super_admin') as mock_is_super:
                mock_is_super.return_value = True

                with patch('database.models.delete_admin_session') as mock_delete:
                    mock_delete.return_value = True

                    response = client.post('/admin/api/terminate-session',
                                         json={'session_id': 'session3'},
                                         content_type='application/json')

                    assert response.status_code == 200

                    data = response.get_json()
                    assert data['success'] is True

                    # セッション削除関数が呼ばれたことを確認
                    mock_delete.assert_called_once_with('session3')


class TestAdminSessionMonitorPage:
    """管理者セッション監視ページテスト"""

    @pytest.fixture
    def setup_database(self, app):
        """テスト用データベースセットアップ"""
        with app.app_context():
            from database import get_db
            from database.models import create_tables

            with get_db() as db:
                create_tables(db)

                # admin_usersテーブルにroleカラム追加
                try:
                    db.execute('ALTER TABLE admin_users ADD COLUMN role TEXT DEFAULT "admin"')
                except sqlite3.OperationalError:
                    pass

                # テスト用スーパー管理者追加
                db.execute('''
                    INSERT OR IGNORE INTO admin_users (email, role, added_by, is_active)
                    VALUES (?, ?, ?, ?)
                ''', ('super@example.com', 'super_admin', 'system', True))

                db.commit()

    def test_session_monitor_page_access_super_admin(self, app, client, setup_database):
        """セッション監視ページアクセス（スーパー管理者）テスト"""
        with app.app_context():
            # スーパー管理者でログイン
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['email'] = 'super@example.com'
                sess['session_id'] = 'test_session'

            with patch('database.models.is_super_admin') as mock_is_super:
                mock_is_super.return_value = True

                with patch('database.models.verify_admin_session') as mock_verify:
                    mock_verify.return_value = {'admin_email': 'super@example.com'}

                    response = client.get('/admin/session-monitor')
                    assert response.status_code == 200
                    assert b'管理者セッション監視' in response.data

    def test_session_monitor_page_access_regular_admin_forbidden(self, app, client, setup_database):
        """セッション監視ページアクセス（一般管理者：アクセス禁止）テスト"""
        with app.app_context():
            # 一般管理者でログイン
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['email'] = 'admin@example.com'
                sess['session_id'] = 'test_session'

            with patch('database.models.is_super_admin') as mock_is_super:
                mock_is_super.return_value = False

                with patch('database.models.verify_admin_session') as mock_verify:
                    mock_verify.return_value = {'admin_email': 'admin@example.com'}

                    response = client.get('/admin/session-monitor')
                    # リダイレクトまたは403エラー
                    assert response.status_code in [302, 403]

    def test_my_sessions_page_access(self, app, client, setup_database):
        """自分のセッションページアクセステスト"""
        with app.app_context():
            # 一般管理者でログイン
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['email'] = 'admin@example.com'
                sess['session_id'] = 'test_session'

            with patch('database.models.verify_admin_session') as mock_verify:
                mock_verify.return_value = {'admin_email': 'admin@example.com'}

                with patch('database.models.get_admin_session_details') as mock_details:
                    mock_details.return_value = {
                        'admin_email': 'admin@example.com',
                        'sessions': []
                    }

                    response = client.get('/admin/my-sessions')
                    assert response.status_code == 200


class TestSessionStatsCalculation:
    """セッション統計計算テスト"""

    @pytest.fixture
    def setup_database(self, app):
        """テスト用データベースセットアップ"""
        with app.app_context():
            from database import get_db
            from database.models import create_tables

            with get_db() as db:
                create_tables(db)

                # admin_usersテーブルにroleカラム追加
                try:
                    db.execute('ALTER TABLE admin_users ADD COLUMN role TEXT DEFAULT "admin"')
                except sqlite3.OperationalError:
                    pass

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

                db.commit()

    def test_get_admin_session_stats(self, app, setup_database):
        """管理者セッション統計取得テスト"""
        with app.app_context():
            from database.models import get_admin_session_stats
            from database import get_db

            # テストデータ準備
            with get_db() as db:
                # 管理者追加
                admins = [
                    ('super1@example.com', 'super_admin'),
                    ('super2@example.com', 'super_admin'),
                    ('admin1@example.com', 'admin'),
                    ('admin2@example.com', 'admin'),
                    ('admin3@example.com', 'admin'),
                ]

                for email, role in admins:
                    db.execute('''
                        INSERT OR IGNORE INTO admin_users (email, role, added_by, is_active)
                        VALUES (?, ?, ?, ?)
                    ''', (email, role, 'system', True))

                # セッション追加
                from config.timezone import get_app_datetime_string
                current_time = get_app_datetime_string()

                sessions = [
                    ('session1', 'super1@example.com'),
                    ('session2', 'super1@example.com'),
                    ('session3', 'super2@example.com'),
                    ('session4', 'admin1@example.com'),
                    ('session5', 'admin2@example.com'),
                    ('session6', 'admin3@example.com'),
                ]

                for session_id, email in sessions:
                    db.execute('''
                        INSERT OR IGNORE INTO admin_sessions
                        (session_id, admin_email, created_at, last_verified_at, ip_address, user_agent, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (session_id, email, current_time, current_time, '127.0.0.1', 'TestAgent', True))

                db.commit()

            # 統計取得
            with patch('database.models.get_all_admin_sessions_with_stats') as mock_get_all:
                mock_get_all.return_value = [
                    {'role': 'super_admin', 'current_sessions': 2, 'status': 'normal'},
                    {'role': 'super_admin', 'current_sessions': 1, 'status': 'normal'},
                    {'role': 'admin', 'current_sessions': 1, 'status': 'normal'},
                    {'role': 'admin', 'current_sessions': 1, 'status': 'warning'},
                    {'role': 'admin', 'current_sessions': 1, 'status': 'normal'},
                ]

                stats = get_admin_session_stats()

                assert stats['total_sessions'] == 6
                assert stats['super_admin_sessions'] == 3
                assert stats['regular_admin_sessions'] == 3
                assert stats['warning_count'] == 1

    def test_get_all_admin_sessions_with_stats(self, app, setup_database):
        """全管理者セッション統計付き取得テスト"""
        with app.app_context():
            from database.models import get_all_admin_sessions_with_stats
            from database import get_db

            # テストデータ準備
            with get_db() as db:
                # 管理者追加
                db.execute('''
                    INSERT OR IGNORE INTO admin_users (email, role, added_by, is_active)
                    VALUES (?, ?, ?, ?)
                ''', ('test@example.com', 'admin', 'system', True))

                # セッション追加
                from config.timezone import get_app_datetime_string
                current_time = get_app_datetime_string()

                db.execute('''
                    INSERT OR IGNORE INTO admin_sessions
                    (session_id, admin_email, created_at, last_verified_at, ip_address, user_agent, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', ('test_session', 'test@example.com', current_time, current_time, '127.0.0.1', 'TestAgent', True))

                # ローテーションイベント追加
                db.execute('''
                    INSERT INTO admin_session_events
                    (admin_email, session_id, event_type, event_details, created_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', ('test@example.com', 'test_session', 'rotated', '{}', current_time))

                db.commit()

            # 統計付きセッション情報取得
            with patch('database.models.get_admin_role') as mock_role:
                with patch('database.models.get_session_rotation_count') as mock_count:
                    mock_role.return_value = 'admin'
                    mock_count.return_value = 1

                    sessions = get_all_admin_sessions_with_stats()

                    assert len(sessions) == 1
                    session = sessions[0]
                    assert session['email'] == 'test@example.com'
                    assert session['role'] == 'admin'
                    assert session['current_sessions'] == 1
                    assert session['rotation_count_24h'] == 1

    def test_admin_session_status_calculation(self, app, setup_database):
        """管理者セッションステータス計算テスト"""
        with app.app_context():
            from database.models import calculate_admin_session_status

            # 正常状態
            status = calculate_admin_session_status(rotation_count=2, is_trusted=False)
            assert status == 'normal'

            # 警告状態（5回以上のローテーション）
            status = calculate_admin_session_status(rotation_count=7, is_trusted=False)
            assert status == 'warning'

            # 危険状態（10回以上のローテーション）
            status = calculate_admin_session_status(rotation_count=12, is_trusted=False)
            assert status == 'critical'

            # 信頼ネットワークからは常に正常
            status = calculate_admin_session_status(rotation_count=15, is_trusted=True)
            assert status == 'normal'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])