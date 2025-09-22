"""
セッションローテーション機能のテスト

GitHub Issue #10 対応: セッション期限切れ問題の解決
"""

import pytest
import sqlite3
import uuid
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from config.timezone import get_app_now, get_app_datetime_string, to_app_timezone


class TestSessionRotationCore:
    """セッションローテーション核機能テスト"""

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

                # ローテーション関連設定
                settings = [
                    ('session_rotation_enabled', 'true', 'boolean', 'セッションローテーション機能有効化', 'security', False),
                    ('session_rotation_max_age_hours', '24', 'integer', 'セッション強制ローテーション時間（時間）', 'security', False),
                    ('session_rotation_alert_threshold', '5', 'integer', 'セッションローテーション警告閾値', 'security', False),
                    ('session_rotation_lock_threshold', '10', 'integer', 'セッションローテーションロック閾値', 'security', False),
                ]

                for setting in settings:
                    db.execute('''
                        INSERT OR IGNORE INTO settings (key, value, value_type, description, category, is_sensitive)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', setting)

                db.commit()

    @patch('database.models.get_app_now')
    @patch('database.models.get_app_datetime_string')
    def test_rotate_session_by_age(self, mock_datetime_string, mock_now, app, setup_database):
        """時間経過によるセッションローテーションテスト"""
        with app.app_context():
            from database.models import (
                rotate_session_if_needed,
                create_admin_session,
                regenerate_admin_session_id
            )

            admin_email = 'test@example.com'
            old_session_id = str(uuid.uuid4())
            new_session_id = str(uuid.uuid4())

            # 26時間前の時刻
            old_time = to_app_timezone(datetime(2024, 1, 1, 10, 0, 0))
            current_time = old_time + timedelta(hours=26)

            # セッション作成時の時刻を設定
            mock_datetime_string.return_value = old_time.strftime("%Y-%m-%d %H:%M:%S")
            create_admin_session(admin_email, old_session_id, '127.0.0.1', 'TestAgent')

            # 現在時刻を設定
            mock_now.return_value = current_time

            # regenerate_admin_session_id をmock
            with patch('database.models.regenerate_admin_session_id') as mock_regenerate:
                with patch('uuid.uuid4') as mock_uuid:
                    mock_uuid.return_value = MagicMock()
                    mock_uuid.return_value.__str__ = lambda x: new_session_id

                    # ローテーション実行
                    result = rotate_session_if_needed(old_session_id, admin_email)

                    # ローテーションが実行されたことを確認
                    assert result is True
                    mock_regenerate.assert_called_once()

    def test_rotation_disabled(self, app, setup_database):
        """ローテーション機能無効時のテスト"""
        with app.app_context():
            from database.models import rotate_session_if_needed, set_setting
            from database import get_db

            # ローテーション機能を無効化
            with get_db() as db:
                set_setting(db, 'session_rotation_enabled', 'false', 'test')

            admin_email = 'test@example.com'
            session_id = str(uuid.uuid4())

            # ローテーション実行（無効化されているため実行されない）
            result = rotate_session_if_needed(session_id, admin_email)
            assert result is False

    def test_session_event_logging(self, app, setup_database):
        """セッションイベントログ機能テスト"""
        with app.app_context():
            from database.models import log_session_event

            admin_email = 'test@example.com'
            session_id = str(uuid.uuid4())

            # ローテーションイベント記録
            event_details = {
                'reason': 'max_age_exceeded',
                'age_hours': 25.5,
                'new_session_id': str(uuid.uuid4())
            }

            log_session_event(admin_email, session_id, 'rotated', event_details)

            # ログ記録確認
            from database import get_db
            with get_db() as db:
                db.row_factory = sqlite3.Row
                events = db.execute('''
                    SELECT * FROM admin_session_events
                    WHERE admin_email = ? AND session_id = ? AND event_type = ?
                ''', (admin_email, session_id, 'rotated')).fetchall()

                assert len(events) == 1
                event = events[0]
                assert event['admin_email'] == admin_email
                assert event['event_type'] == 'rotated'

                # JSON詳細の確認
                details = json.loads(event['event_details'])
                assert details['reason'] == 'max_age_exceeded'
                assert details['age_hours'] == 25.5

    def test_rotation_count_tracking(self, app, setup_database):
        """ローテーション回数追跡テスト"""
        with app.app_context():
            from database.models import (
                log_session_event,
                get_session_rotation_count
            )

            admin_email = 'test@example.com'

            # 複数回のローテーションを記録
            rotation_events = [
                ('session1', 'test_rotation_1'),
                ('session2', 'test_rotation_2'),
                ('session3', 'max_age_exceeded'),
                ('session4', 'session_limit_exceeded'),
                ('session5', 'manual_rotation'),
            ]

            for session_id, reason in rotation_events:
                log_session_event(admin_email, session_id, 'rotated', {
                    'reason': reason,
                    'timestamp': get_app_datetime_string()
                })

            # 24時間以内のローテーション回数確認
            count = get_session_rotation_count(admin_email, hours=24)
            assert count == 5

    @patch('database.models.get_app_now')
    def test_rotation_count_time_filtering(self, mock_now, app, setup_database):
        """ローテーション回数の時間フィルタリングテスト"""
        with app.app_context():
            from database.models import (
                log_session_event,
                get_session_rotation_count
            )
            from database import get_db

            admin_email = 'test@example.com'
            current_time = to_app_timezone(datetime(2024, 1, 2, 12, 0, 0))
            mock_now.return_value = current_time

            # 異なる時刻のローテーションイベントを手動挿入
            with get_db() as db:
                events = [
                    # 12時間前（カウント対象）
                    (admin_email, 'session1', 'rotated', '{}', '2024-01-02 00:00:00'),
                    # 30時間前（カウント対象外）
                    (admin_email, 'session2', 'rotated', '{}', '2024-01-01 06:00:00'),
                    # 6時間前（カウント対象）
                    (admin_email, 'session3', 'rotated', '{}', '2024-01-02 06:00:00'),
                ]

                for event in events:
                    db.execute('''
                        INSERT INTO admin_session_events
                        (admin_email, session_id, event_type, event_details, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    ''', event)

                db.commit()

            # 24時間以内のローテーション回数確認
            count = get_session_rotation_count(admin_email, hours=24)
            assert count == 2  # 30時間前のイベントは除外される


class TestSessionRotationIntegration:
    """セッションローテーション統合テスト"""

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

                # 設定追加
                settings = [
                    ('session_rotation_enabled', 'true', 'boolean', 'セッションローテーション機能有効化', 'security', False),
                    ('session_rotation_max_age_hours', '1', 'integer', 'セッション強制ローテーション時間（時間）', 'security', False),
                ]

                for setting in settings:
                    db.execute('''
                        INSERT OR IGNORE INTO settings (key, value, value_type, description, category, is_sensitive)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', setting)

                db.commit()

    @patch('database.models.get_app_now')
    @patch('database.models.get_app_datetime_string')
    def test_full_rotation_workflow(self, mock_datetime_string, mock_now, app, setup_database):
        """完全なローテーションワークフローテスト"""
        with app.app_context():
            from database.models import (
                create_admin_session,
                rotate_session_if_needed,
                get_admin_session_info,
                regenerate_admin_session_id
            )

            admin_email = 'workflow@example.com'
            original_session_id = str(uuid.uuid4())
            new_session_id = str(uuid.uuid4())

            # 2時間前にセッション作成
            old_time = to_app_timezone(datetime(2024, 1, 1, 10, 0, 0))
            current_time = old_time + timedelta(hours=2)

            # セッション作成
            mock_datetime_string.return_value = old_time.strftime("%Y-%m-%d %H:%M:%S")
            create_admin_session(admin_email, original_session_id, '127.0.0.1', 'TestAgent')

            # セッション情報確認（作成直後）
            session_info = get_admin_session_info(original_session_id)
            assert session_info is not None
            assert session_info['admin_email'] == admin_email

            # 現在時刻設定
            mock_now.return_value = current_time

            # ローテーション実行をmock
            with patch('database.models.regenerate_admin_session_id') as mock_regenerate:
                with patch('uuid.uuid4') as mock_uuid:
                    mock_uuid.return_value = MagicMock()
                    mock_uuid.return_value.__str__ = lambda x: new_session_id

                    # ローテーション実行
                    rotated = rotate_session_if_needed(original_session_id, admin_email)

                    # ローテーション実行確認
                    assert rotated is True
                    mock_regenerate.assert_called_once_with(original_session_id, new_session_id)

    def test_rotation_with_security_monitoring(self, app, setup_database):
        """セキュリティ監視と連携したローテーションテスト"""
        with app.app_context():
            from database.models import (
                log_session_event,
                get_session_rotation_count,
                check_session_security_violations
            )

            admin_email = 'security@example.com'

            # 複数回のローテーション実行をシミュレート
            for i in range(7):  # 警告閾値を超える回数
                session_id = str(uuid.uuid4())
                log_session_event(admin_email, session_id, 'rotated', {
                    'reason': 'max_age_exceeded',
                    'rotation_number': i + 1
                })

            # ローテーション回数確認
            count = get_session_rotation_count(admin_email, hours=24)
            assert count == 7

            # セキュリティ違反チェック
            with patch('database.models.is_trusted_network') as mock_trusted:
                mock_trusted.return_value = False  # 非信頼ネットワーク

                violation = check_session_security_violations(admin_email, '8.8.8.8')
                assert violation['violated'] is True
                assert violation['action_required'] == 'alert'
                assert violation['rotation_count'] == 7

    def test_rotation_performance_with_many_sessions(self, app, setup_database):
        """大量セッションでのローテーション性能テスト"""
        with app.app_context():
            from database.models import (
                create_admin_session,
                log_session_event,
                get_session_rotation_count
            )

            admin_email = 'performance@example.com'

            # 大量のセッションとローテーションイベント作成
            for i in range(100):
                session_id = str(uuid.uuid4())
                create_admin_session(admin_email, session_id, '127.0.0.1', f'Agent{i}')

                # 一部のセッションでローテーションイベント記録
                if i % 10 == 0:
                    log_session_event(admin_email, session_id, 'rotated', {
                        'reason': 'performance_test',
                        'session_number': i
                    })

            # ローテーション回数取得（性能確認）
            import time
            start_time = time.time()
            count = get_session_rotation_count(admin_email, hours=24)
            end_time = time.time()

            # 実行時間が1秒以内であることを確認
            execution_time = end_time - start_time
            assert execution_time < 1.0

            # 正しい回数が取得されていることを確認
            assert count == 10  # 100個中10個のローテーションイベント


class TestSessionRotationEdgeCases:
    """セッションローテーション境界条件テスト"""

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

                db.commit()

    def test_rotation_nonexistent_session(self, app, setup_database):
        """存在しないセッションのローテーションテスト"""
        with app.app_context():
            from database.models import rotate_session_if_needed

            # 存在しないセッションIDでローテーション試行
            result = rotate_session_if_needed('nonexistent-session', 'test@example.com')
            assert result is False

    def test_rotation_with_invalid_timestamps(self, app, setup_database):
        """無効なタイムスタンプでのローテーションテスト"""
        with app.app_context():
            from database.models import rotate_session_if_needed
            from database import get_db

            admin_email = 'invalid@example.com'
            session_id = str(uuid.uuid4())

            # 無効なタイムスタンプでセッション作成
            with get_db() as db:
                db.execute('''
                    INSERT INTO admin_sessions
                    (session_id, admin_email, created_at, last_verified_at, ip_address, user_agent, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (session_id, admin_email, 'invalid-timestamp', 'invalid-timestamp', '127.0.0.1', 'TestAgent', True))

                db.commit()

            # ローテーション試行（エラーハンドリング確認）
            result = rotate_session_if_needed(session_id, admin_email)
            # 無効なタイムスタンプの場合はローテーションしない
            assert result is False

    def test_zero_rotation_count(self, app, setup_database):
        """ローテーション回数0のテスト"""
        with app.app_context():
            from database.models import get_session_rotation_count

            # ローテーションイベントが一切ない管理者
            count = get_session_rotation_count('norotation@example.com', hours=24)
            assert count == 0

    def test_rotation_with_database_transaction_failure(self, app, setup_database):
        """データベーストランザクション失敗時のローテーションテスト"""
        with app.app_context():
            from database.models import log_session_event

            admin_email = 'transaction@example.com'
            session_id = str(uuid.uuid4())

            # データベース接続をmockしてエラーを発生させる
            with patch('database.get_db') as mock_get_db:
                mock_db = MagicMock()
                mock_db.__enter__ = MagicMock(return_value=mock_db)
                mock_db.__exit__ = MagicMock(return_value=None)
                mock_db.execute.side_effect = sqlite3.OperationalError("Database locked")
                mock_get_db.return_value = mock_db

                # ログ記録試行（エラーハンドリング確認）
                try:
                    log_session_event(admin_email, session_id, 'rotated', {})
                    # エラーが適切にハンドリングされることを確認
                except sqlite3.OperationalError:
                    pass  # 期待されるエラー


if __name__ == '__main__':
    pytest.main([__file__, '-v'])