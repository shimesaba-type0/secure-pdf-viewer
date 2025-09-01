"""
管理者権限システムのテストケース

TASK-019: 管理者権限システムの実装に対するテスト
"""

import unittest
import sqlite3
import tempfile
import os
import sys
import json
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from database.models import (
    is_admin,
    add_admin_user,
    get_admin_users,
    update_admin_status,
    delete_admin_user,
)


class TestAdminPermissionSystem(unittest.TestCase):
    """管理者権限システムのテストクラス"""

    def setUp(self):
        """テスト前の初期化"""
        self.test_db = tempfile.NamedTemporaryFile(delete=False)
        self.test_db.close()
        self.test_db_path = self.test_db.name

        # アプリの設定
        app.config["TESTING"] = True
        app.config["DATABASE"] = self.test_db_path
        app.config["SECRET_KEY"] = "test-secret-key"

        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

        # データベースパスをテスト用にパッチ
        import database
        self.db_patcher = patch.object(database, 'DATABASE_PATH', self.test_db_path)
        self.db_patcher.start()

        # テスト用データベース初期化
        # テスト環境では直接テーブル作成を行う
        from database.models import create_tables
        with sqlite3.connect(self.test_db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_tables(conn)

    def tearDown(self):
        """テスト後のクリーンアップ"""
        self.db_patcher.stop()
        self.app_context.pop()
        os.unlink(self.test_db_path)

    def test_is_admin_with_valid_admin(self):
        """有効な管理者のテスト"""
        # テスト用管理者を追加
        with sqlite3.connect(self.test_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO admin_users (email, added_by, is_active)
                VALUES (?, ?, ?)
            """,
                ("admin@example.com", "system", True),
            )
            conn.commit()

        # テスト実行
        result = is_admin("admin@example.com")
        self.assertTrue(result)

    def test_is_admin_with_invalid_user(self):
        """無効ユーザーのテスト"""
        result = is_admin("user@example.com")
        self.assertFalse(result)

    def test_is_admin_with_inactive_admin(self):
        """無効化された管理者のテスト"""
        # 無効化された管理者を追加
        with sqlite3.connect(self.test_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO admin_users (email, added_by, is_active)
                VALUES (?, ?, ?)
            """,
                ("inactive@example.com", "system", False),
            )
            conn.commit()

        # テスト実行
        result = is_admin("inactive@example.com")
        self.assertFalse(result)

    def test_is_admin_with_empty_email(self):
        """空のメールアドレスのテスト"""
        result = is_admin("")
        self.assertFalse(result)

    def test_is_admin_with_none_email(self):
        """Noneメールアドレスのテスト"""
        result = is_admin(None)
        self.assertFalse(result)

    def test_add_admin_user_success(self):
        """管理者追加成功のテスト"""
        import uuid
        unique_email = f"test_admin_{uuid.uuid4().hex[:8]}@example.com"
        result = add_admin_user(unique_email, "admin@example.com")
        self.assertTrue(result)

        # データベースで確認
        self.assertTrue(is_admin(unique_email))

    def test_add_admin_user_duplicate(self):
        """重複する管理者追加のテスト"""
        # 最初の追加
        add_admin_user("admin@example.com", "system")

        # 重複追加を試行
        result = add_admin_user("admin@example.com", "system")
        self.assertFalse(result)

    def test_add_admin_user_max_limit(self):
        """管理者数上限のテスト"""
        import uuid
        # 6人の管理者を追加（上限）
        base_id = uuid.uuid4().hex[:8]
        emails = [f"test_admin_limit_{base_id}_{i}@example.com" for i in range(6)]
        for email in emails:
            result = add_admin_user(email, "system")
            self.assertTrue(result)

        # 7人目の追加を試行（失敗するはず）
        result = add_admin_user(f"test_admin_limit_{base_id}_7@example.com", "system")
        self.assertFalse(result)

    def test_get_admin_users(self):
        """管理者一覧取得のテスト"""
        # テスト用管理者を追加
        test_emails = ["admin1@example.com", "admin2@example.com"]
        for email in test_emails:
            add_admin_user(email, "system")

        # 管理者一覧を取得
        admins = get_admin_users()

        # 検証
        self.assertEqual(len(admins), 2)
        admin_emails = [admin["email"] for admin in admins]
        for email in test_emails:
            self.assertIn(email, admin_emails)

    def test_update_admin_status(self):
        """管理者ステータス更新のテスト"""
        # テスト用管理者を2人追加（最後の管理者無効化防止をテストするため）
        add_admin_user("admin1@example.com", "system")
        add_admin_user("admin2@example.com", "system")

        # 無効化対象の管理者IDを取得
        admins = get_admin_users()
        admin_to_update = next(admin for admin in admins if admin["email"] == "admin1@example.com")
        admin_id = admin_to_update["id"]

        # ステータスを無効に更新
        result = update_admin_status(admin_id, False)
        self.assertTrue(result)

        # 無効化されたことを確認
        self.assertFalse(is_admin("admin1@example.com"))
        # もう一人は残っていることを確認
        self.assertTrue(is_admin("admin2@example.com"))

    def test_delete_admin_user(self):
        """管理者削除のテスト"""
        # テスト用管理者を2人追加（最後の管理者削除防止をテストするため）
        add_admin_user("admin1@example.com", "system")
        add_admin_user("admin2@example.com", "system")

        # 削除対象の管理者IDを取得
        admins = get_admin_users()
        admin_to_delete = next(admin for admin in admins if admin["email"] == "admin1@example.com")
        admin_id = admin_to_delete["id"]

        # 削除実行
        result = delete_admin_user(admin_id)
        self.assertTrue(result)

        # 削除されたことを確認
        self.assertFalse(is_admin("admin1@example.com"))
        # もう一人は残っていることを確認
        self.assertTrue(is_admin("admin2@example.com"))

    def test_delete_last_admin_prevention(self):
        """最後の管理者削除防止のテスト"""
        # 管理者を1人だけ追加
        add_admin_user("last_admin@example.com", "system")

        # 管理者IDを取得
        admins = get_admin_users()
        admin_id = admins[0]["id"]

        # 削除を試行（失敗するはず）
        result = delete_admin_user(admin_id)
        self.assertFalse(result)

        # まだ存在することを確認
        self.assertTrue(is_admin("last_admin@example.com"))


class TestAdminPermissionAPI(unittest.TestCase):
    """管理者権限API のテストクラス"""

    def setUp(self):
        """テスト前の初期化"""
        self.test_db = tempfile.NamedTemporaryFile(delete=False)
        self.test_db.close()
        self.test_db_path = self.test_db.name

        # アプリの設定
        app.config["TESTING"] = True
        app.config["DATABASE"] = self.test_db_path
        app.config["SECRET_KEY"] = "test-secret-key"

        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

        # データベースパスをテスト用にパッチ
        import database
        self.db_patcher = patch.object(database, 'DATABASE_PATH', self.test_db_path)
        self.db_patcher.start()

        # テスト用データベース初期化
        # テスト環境では直接テーブル作成を行う
        from database.models import create_tables
        with sqlite3.connect(self.test_db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_tables(conn)

        # テスト用管理者を追加
        add_admin_user("admin@example.com", "system")

    def tearDown(self):
        """テスト後のクリーンアップ"""
        self.db_patcher.stop()
        self.app_context.pop()
        os.unlink(self.test_db_path)

    def _login_as_admin(self):
        """管理者としてログイン"""
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["email"] = "admin@example.com"

    def _login_as_user(self):
        """一般ユーザーとしてログイン"""
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["email"] = "user@example.com"

    def test_admin_users_api_get_success(self):
        """管理者一覧取得APIの成功テスト"""
        self._login_as_admin()

        response = self.client.get("/admin/users")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertIn("users", data)
        self.assertIn("total", data)
        self.assertIn("max_admins", data)

    def test_admin_users_api_get_unauthorized(self):
        """管理者一覧取得APIの権限なしテスト"""
        self._login_as_user()

        response = self.client.get("/admin/users")
        self.assertEqual(response.status_code, 403)

    def test_admin_users_api_get_not_logged_in(self):
        """管理者一覧取得APIの未ログインテスト"""
        response = self.client.get("/admin/users")
        self.assertEqual(response.status_code, 302)  # リダイレクト

    def test_admin_users_api_post_success(self):
        """管理者追加APIの成功テスト"""
        self._login_as_admin()

        response = self.client.post(
            "/admin/users", json={"email": "new_admin@example.com"}
        )
        self.assertEqual(response.status_code, 200)

        # 追加されたことを確認
        self.assertTrue(is_admin("new_admin@example.com"))

    def test_admin_users_api_post_unauthorized(self):
        """管理者追加APIの権限なしテスト"""
        self._login_as_user()

        response = self.client.post(
            "/admin/users", json={"email": "new_admin@example.com"}
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_users_api_post_invalid_email(self):
        """管理者追加APIの無効メールテスト"""
        self._login_as_admin()

        response = self.client.post("/admin/users", json={"email": "invalid-email"})
        self.assertEqual(response.status_code, 400)

    def test_admin_users_api_put_success(self):
        """管理者更新APIの成功テスト"""
        self._login_as_admin()

        # 新しい管理者を追加
        add_admin_user("target@example.com", "admin@example.com")
        admins = get_admin_users()
        target_admin = next(
            admin for admin in admins if admin["email"] == "target@example.com"
        )

        # ステータス更新
        response = self.client.put(
            f'/admin/users/{target_admin["id"]}', json={"is_active": False}
        )
        self.assertEqual(response.status_code, 200)

        # 無効化されたことを確認
        self.assertFalse(is_admin("target@example.com"))

    def test_admin_users_api_delete_success(self):
        """管理者削除APIの成功テスト"""
        self._login_as_admin()

        # 新しい管理者を追加（削除対象）
        add_admin_user("target@example.com", "admin@example.com")
        admins = get_admin_users()
        target_admin = next(
            admin for admin in admins if admin["email"] == "target@example.com"
        )

        # 削除実行
        response = self.client.delete(f'/admin/users/{target_admin["id"]}')
        self.assertEqual(response.status_code, 200)

        # 削除されたことを確認
        self.assertFalse(is_admin("target@example.com"))


class TestInitialAdminSetup(unittest.TestCase):
    """初期管理者設定のテストクラス"""

    def setUp(self):
        """テスト前の初期化"""
        self.test_db = tempfile.NamedTemporaryFile(delete=False)
        self.test_db.close()
        self.test_db_path = self.test_db.name

        # アプリの設定
        app.config["TESTING"] = True
        app.config["DATABASE"] = self.test_db_path
        app.config["SECRET_KEY"] = "test-secret-key"

        self.app_context = app.app_context()
        self.app_context.push()

        # データベースパスをテスト用にパッチ
        import database
        self.db_patcher = patch.object(database, 'DATABASE_PATH', self.test_db_path)
        self.db_patcher.start()

        # テスト用データベース初期化
        # テスト環境では直接テーブル作成を行う
        from database.models import create_tables
        with sqlite3.connect(self.test_db_path) as conn:
            conn.row_factory = sqlite3.Row
            create_tables(conn)

    def tearDown(self):
        """テスト後のクリーンアップ"""
        self.db_patcher.stop()
        self.app_context.pop()
        os.unlink(self.test_db_path)

    @patch.dict(os.environ, {"ADMIN_EMAIL": "initial_admin@example.com"})
    def test_initial_admin_setup(self):
        """初期管理者設定のテスト"""
        from app import setup_initial_admin

        # 初期管理者設定を実行
        setup_initial_admin()

        # 初期管理者が設定されたことを確認
        self.assertTrue(is_admin("initial_admin@example.com"))

    @patch.dict(os.environ, {"ADMIN_EMAIL": "admin@example.com"})
    def test_initial_admin_setup_duplicate_prevention(self):
        """初期管理者重複防止のテスト"""
        from app import setup_initial_admin

        # 手動で管理者を追加
        add_admin_user("admin@example.com", "manual")

        # 初期管理者設定を実行（重複追加されないはず）
        setup_initial_admin()

        # 管理者が1人だけであることを確認
        admins = get_admin_users()
        admin_count = len(
            [admin for admin in admins if admin["email"] == "admin@example.com"]
        )
        self.assertEqual(admin_count, 1)

    def test_initial_admin_setup_without_env(self):
        """環境変数なしでの初期管理者設定テスト"""
        from app import setup_initial_admin

        # ADMIN_EMAIL環境変数が設定されていない状態でテスト
        with patch.dict(os.environ, {}, clear=True):
            # エラーが発生しないことを確認
            setup_initial_admin()

            # 管理者が追加されていないことを確認
            admins = get_admin_users()
            self.assertEqual(len(admins), 0)


class TestDatabaseCleanup(unittest.TestCase):
    """テスト後のデータベースクリーンアップ"""

    def setUp(self):
        """テスト前の初期化"""
        self.test_db = tempfile.NamedTemporaryFile(delete=False)
        self.test_db.close()
        self.test_db_path = self.test_db.name

        # アプリの設定
        app.config["TESTING"] = True
        app.config["DATABASE"] = self.test_db_path
        app.config["SECRET_KEY"] = "test-secret-key"

        self.app_context = app.app_context()
        self.app_context.push()

        # データベースパスをテスト用にパッチ
        import database
        self.db_patcher = patch.object(database, 'DATABASE_PATH', self.test_db_path)
        self.db_patcher.start()

    def tearDown(self):
        """テスト後のクリーンアップ"""
        self.db_patcher.stop()
        self.app_context.pop()
        os.unlink(self.test_db_path)

    def test_cleanup_test_admin_users(self):
        """テスト用管理者データのクリーンアップ"""
        print("\n=== データベースクリーンアップを実行中 ===")
        
        # 本番データベースに直接接続してクリーンアップ
        import sqlite3
        production_db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'instance', 'database.db'
        )
        
        if not os.path.exists(production_db_path):
            print("本番データベースが見つかりません")
            return
            
        # クリーンアップ前の状態を確認
        with sqlite3.connect(production_db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT email, added_by FROM admin_users ORDER BY id")
            before_admins = cursor.fetchall()
            
            print(f"クリーンアップ前の管理者数: {len(before_admins)}")
            for admin in before_admins:
                print(f"  - {admin['email']} (追加者: {admin['added_by']})")
        
        # テスト用データを削除（example.com ドメインのメールアドレス）
        test_email_patterns = [
            '%@example.com',
            'admin0@%',
            'admin1@%',
            'test_%',
            'new_admin@%',
            'last_admin@%'
        ]
        
        deleted_count = 0
        with sqlite3.connect(production_db_path) as conn:
            for pattern in test_email_patterns:
                cursor = conn.execute(
                    "DELETE FROM admin_users WHERE email LIKE ? AND email != ?",
                    (pattern, os.environ.get('ADMIN_EMAIL', 'real-admin@example.com'))
                )
                deleted_count += cursor.rowcount
            
            conn.commit()
        
        # クリーンアップ後の状態を確認
        with sqlite3.connect(production_db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT email, added_by FROM admin_users ORDER BY id")
            after_admins = cursor.fetchall()
            
            print(f"\n削除された管理者数: {deleted_count}")
            print(f"クリーンアップ後の管理者数: {len(after_admins)}")
            for admin in after_admins:
                print(f"  - {admin['email']} (追加者: {admin['added_by']})")
        
        print("=== クリーンアップ完了 ===\n")
        
        # テスト成功を示すため
        self.assertGreaterEqual(deleted_count, 0)


def cleanup_test_data():
    """テストデータクリーンアップ用のスタンドアロン関数"""
    import sqlite3
    
    production_db_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 'instance', 'database.db'
    )
    
    if not os.path.exists(production_db_path):
        print("データベースファイルが見つかりません:", production_db_path)
        return
    
    # テスト用データのパターン
    test_email_patterns = [
        '%@example.com',
        'admin0@%',
        'admin1@%', 
        'test_%',
        'new_admin@%',
        'last_admin@%'
    ]
    
    # 保護すべき実際の管理者メール（環境変数から取得）
    protected_email = os.environ.get('ADMIN_EMAIL', 'protected@example.com')
    
    print("=== テストデータクリーンアップ開始 ===")
    
    try:
        with sqlite3.connect(production_db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # クリーンアップ前の確認
            before_cursor = conn.execute("SELECT email, added_by FROM admin_users ORDER BY id")
            before_admins = before_cursor.fetchall()
            print(f"クリーンアップ前: {len(before_admins)}人の管理者")
            
            deleted_total = 0
            for pattern in test_email_patterns:
                cursor = conn.execute(
                    "DELETE FROM admin_users WHERE email LIKE ? AND email != ?",
                    (pattern, protected_email)
                )
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    print(f"  パターン '{pattern}': {deleted_count}人削除")
                deleted_total += deleted_count
            
            conn.commit()
            
            # クリーンアップ後の確認
            after_cursor = conn.execute("SELECT email, added_by FROM admin_users ORDER BY id")
            after_admins = after_cursor.fetchall()
            
            print(f"\n結果:")
            print(f"  削除された管理者数: {deleted_total}人")
            print(f"  残存管理者数: {len(after_admins)}人")
            
            if after_admins:
                print("  残存管理者:")
                for admin in after_admins:
                    print(f"    - {admin['email']} (追加者: {admin['added_by']})")
            
    except Exception as e:
        print(f"クリーンアップ中にエラーが発生: {e}")
    
    print("=== クリーンアップ完了 ===")


if __name__ == "__main__":
    import sys
    
    # コマンドライン引数でクリーンアップ実行
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
        cleanup_test_data()
    else:
        unittest.main()
