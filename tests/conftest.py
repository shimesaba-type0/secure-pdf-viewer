"""
テスト用共通設定

GitHub Issue #10 対応: 管理者ロール別セッション管理機能のテスト
"""

import pytest
import tempfile
import os
import sys

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app():
    """テスト用Flaskアプリケーション"""
    # テスト用の一時ディレクトリとデータベース
    temp_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(temp_dir, 'test.db')

    # 環境変数設定
    os.environ['DATABASE_URL'] = f'sqlite:///{test_db_path}'
    os.environ['TESTING'] = 'True'
    os.environ['SECRET_KEY'] = 'test-secret-key-for-testing-only'
    os.environ['ADMIN_EMAIL'] = 'test-admin@example.com'

    # Flaskアプリケーションをインポートして作成
    from app import app as flask_app

    # テスト設定
    flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'DATABASE': test_db_path,
        'SECRET_KEY': 'test-secret-key-for-testing-only'
    })

    with flask_app.app_context():
        # データベース初期化
        from database import init_db, get_db
        from database.migrations import run_all_migrations

        # データベース作成
        init_db()

        # マイグレーション実行
        with get_db() as db:
            run_all_migrations(db)

        yield flask_app

    # クリーンアップ
    try:
        import shutil
        shutil.rmtree(temp_dir)
    except:
        pass


@pytest.fixture
def client(app):
    """テスト用HTTPクライアント"""
    return app.test_client()


@pytest.fixture
def runner(app):
    """テスト用CLIランナー"""
    return app.test_cli_runner()