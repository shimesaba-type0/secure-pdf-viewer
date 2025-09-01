#!/usr/bin/env python3
"""
SSE統一管理システムのテストスイート

このテストは以下をテストします：
1. SSE接続の基本機能
2. セッション無効化イベントの配信
3. PDF公開/停止イベントの配信
4. 複数クライアント間での同期
5. 接続の切断とクリーンアップ
"""

import unittest
import json
import threading
import time
from queue import Queue, Empty
from unittest.mock import patch, Mock
import sys
import os

# requestsは統合テストでのみ使用するため、オプショナルインポート
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# プロジェクトルートディレクトリをパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app import app, add_sse_client, remove_sse_client, broadcast_sse_event, sse_clients

class SSEUnifiedManagementTestCase(unittest.TestCase):
    """SSE統一管理システムのテストケース"""
    
    def setUp(self):
        """テスト前の準備"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        # テスト用のアプリケーションコンテキストを作成
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        # SSEクライアントリストをクリア
        sse_clients.clear()
        
        # テスト用セッション
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['login_time'] = time.time()
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        sse_clients.clear()
        self.app_context.pop()
    
    def test_sse_client_management(self):
        """SSEクライアント管理の基本機能テスト"""
        print("\n=== SSEクライアント管理テスト ===")
        
        # 初期状態の確認
        self.assertEqual(len(sse_clients), 0)
        print(f"初期SSEクライアント数: {len(sse_clients)}")
        
        # クライアント追加テスト
        queue1 = Queue()
        queue2 = Queue()
        
        add_sse_client(queue1)
        self.assertEqual(len(sse_clients), 1)
        print(f"クライアント1追加後: {len(sse_clients)}")
        
        add_sse_client(queue2)
        self.assertEqual(len(sse_clients), 2)
        print(f"クライアント2追加後: {len(sse_clients)}")
        
        # クライアント削除テスト
        remove_sse_client(queue1)
        self.assertEqual(len(sse_clients), 1)
        print(f"クライアント1削除後: {len(sse_clients)}")
        
        remove_sse_client(queue2)
        self.assertEqual(len(sse_clients), 0)
        print(f"クライアント2削除後: {len(sse_clients)}")
        
        print("✅ SSEクライアント管理テスト完了")
    
    def test_session_invalidation_broadcast(self):
        """セッション無効化イベントの配信テスト"""
        print("\n=== セッション無効化配信テスト ===")
        
        # テスト用クライアントキューを準備
        queue1 = Queue()
        queue2 = Queue()
        
        add_sse_client(queue1)
        add_sse_client(queue2)
        
        print(f"テスト用クライアント数: {len(sse_clients)}")
        
        # セッション無効化イベントを配信
        test_data = {
            'message': 'テスト用セッション無効化',
            'redirect_url': '/auth/login'
        }
        
        broadcast_sse_event('session_invalidated', test_data)
        
        # 両方のクライアントがイベントを受信することを確認
        try:
            event1 = queue1.get(timeout=1)
            event2 = queue2.get(timeout=1)
            
            self.assertEqual(event1['event'], 'session_invalidated')
            self.assertEqual(event2['event'], 'session_invalidated')
            self.assertEqual(event1['data'], test_data)
            self.assertEqual(event2['data'], test_data)
            
            print("✅ 両クライアントでセッション無効化イベント受信確認")
            
        except Empty:
            self.fail("セッション無効化イベントがタイムアウトしました")
        
        # クリーンアップ
        remove_sse_client(queue1)
        remove_sse_client(queue2)
        
        print("✅ セッション無効化配信テスト完了")
    
    def test_pdf_event_broadcast(self):
        """PDF公開/停止イベントの配信テスト"""
        print("\n=== PDF公開/停止イベント配信テスト ===")
        
        # テスト用クライアントキューを準備
        queue = Queue()
        add_sse_client(queue)
        
        # PDF公開イベントをテスト
        publish_data = {
            'message': 'test.pdf が公開されました',
            'pdf_id': 1,
            'filename': 'test.pdf'
        }
        
        broadcast_sse_event('pdf_published', publish_data)
        
        try:
            event = queue.get(timeout=1)
            self.assertEqual(event['event'], 'pdf_published')
            self.assertEqual(event['data'], publish_data)
            print("✅ PDF公開イベント受信確認")
        except Empty:
            self.fail("PDF公開イベントがタイムアウトしました")
        
        # PDF停止イベントをテスト
        unpublish_data = {
            'message': 'test.pdf の公開が停止されました',
            'pdf_id': 1
        }
        
        broadcast_sse_event('pdf_unpublished', unpublish_data)
        
        try:
            event = queue.get(timeout=1)
            self.assertEqual(event['event'], 'pdf_unpublished')
            self.assertEqual(event['data'], unpublish_data)
            print("✅ PDF停止イベント受信確認")
        except Empty:
            self.fail("PDF停止イベントがタイムアウトしました")
        
        # クリーンアップ
        remove_sse_client(queue)
        
        print("✅ PDF公開/停止イベント配信テスト完了")
    
    def test_multiple_clients_sync(self):
        """複数クライアント間の同期テスト"""
        print("\n=== 複数クライアント同期テスト ===")
        
        # 複数のクライアントキューを準備
        client_queues = [Queue() for _ in range(5)]
        
        for queue in client_queues:
            add_sse_client(queue)
        
        print(f"テスト用クライアント数: {len(sse_clients)}")
        
        # 汎用イベントを配信
        test_data = {
            'message': '複数クライアント同期テスト',
            'timestamp': time.time()
        }
        
        broadcast_sse_event('test_sync', test_data)
        
        # 全クライアントがイベントを受信することを確認
        received_events = []
        for i, queue in enumerate(client_queues):
            try:
                event = queue.get(timeout=1)
                received_events.append(event)
                print(f"クライアント{i+1}: イベント受信確認")
            except Empty:
                self.fail(f"クライアント{i+1}でイベントタイムアウト")
        
        # 全イベントが同じ内容であることを確認
        for event in received_events:
            self.assertEqual(event['event'], 'test_sync')
            self.assertEqual(event['data'], test_data)
        
        print("✅ 全クライアントで同期確認")
        
        # クリーンアップ
        for queue in client_queues:
            remove_sse_client(queue)
        
        print("✅ 複数クライアント同期テスト完了")
    
    def test_sse_endpoint_authentication(self):
        """SSEエンドポイントの認証テスト"""
        print("\n=== SSEエンドポイント認証テスト ===")
        
        # 認証済みセッションでSSEエンドポイントにアクセス
        with self.client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['login_time'] = time.time()
        
        response = self.client.get('/api/events')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'text/event-stream; charset=utf-8')
        print("✅ 認証済みユーザーのSSEアクセス許可確認")
        
        # 未認証セッションでSSEエンドポイントにアクセス
        with self.client.session_transaction() as sess:
            sess.clear()
        
        response = self.client.get('/api/events')
        self.assertEqual(response.status_code, 401)
        print("✅ 未認証ユーザーのSSEアクセス拒否確認")
        
        print("✅ SSEエンドポイント認証テスト完了")
    
    def test_client_cleanup_on_disconnect(self):
        """クライアント切断時のクリーンアップテスト"""
        print("\n=== クライアント切断クリーンアップテスト ===")
        
        # 初期状態の確認
        initial_count = len(sse_clients)
        print(f"初期クライアント数: {initial_count}")
        
        # クライアントを追加
        queue = Queue()
        add_sse_client(queue)
        
        after_add_count = len(sse_clients)
        self.assertEqual(after_add_count, initial_count + 1)
        print(f"クライアント追加後: {after_add_count}")
        
        # クライアントを削除（切断をシミュレート）
        remove_sse_client(queue)
        
        after_remove_count = len(sse_clients)
        self.assertEqual(after_remove_count, initial_count)
        print(f"クライアント削除後: {after_remove_count}")
        
        # 存在しないクライアントを削除しようとしてもエラーにならないことを確認
        try:
            remove_sse_client(queue)  # 既に削除済み
            print("✅ 重複削除でエラーなし")
        except Exception as e:
            self.fail(f"重複削除でエラーが発生: {e}")
        
        print("✅ クライアント切断クリーンアップテスト完了")

class SSEIntegrationTestCase(unittest.TestCase):
    """SSE統合テスト（実際のHTTPリクエスト）"""
    
    def setUp(self):
        """テスト前の準備"""
        self.base_url = "http://localhost:5000"
        self.session = requests.Session()
        
        # テスト用の認証情報でログイン
        # 実際のアプリケーションが動作している場合のみ実行
        
    def test_sse_stream_integration(self):
        """SSEストリーム統合テスト"""
        print("\n=== SSEストリーム統合テスト ===")
        
        if not HAS_REQUESTS:
            print("注意: requestsモジュールがないため、統合テストをスキップします")
            self.skipTest("requests module not available")
            return
        
        print("注意: このテストは実際のアプリケーションが動作している場合のみ実行されます")
        
        # 実際のSSEストリームに接続してイベントを受信するテスト
        # これは手動テスト用のガイドとして使用
        test_script = """
        手動テスト手順:
        1. アプリケーションを起動: python app.py
        2. ブラウザで管理画面にアクセス
        3. 開発者ツールのNetworkタブでSSE接続を確認
        4. PDF公開/停止操作を実行してイベント配信を確認
        5. セッション無効化を実行してリダイレクトを確認
        """
        print(test_script)

def run_performance_test():
    """パフォーマンステスト"""
    print("\n=== SSEパフォーマンステスト ===")
    
    # 大量のクライアントでのパフォーマンステスト
    client_count = 100
    test_queues = []
    
    start_time = time.time()
    
    # 100個のクライアントを追加
    for i in range(client_count):
        queue = Queue()
        add_sse_client(queue)
        test_queues.append(queue)
    
    add_time = time.time() - start_time
    print(f"100クライアント追加時間: {add_time:.4f}秒")
    
    # 大量配信テスト
    start_time = time.time()
    test_data = {'message': 'パフォーマンステスト', 'client_count': client_count}
    broadcast_sse_event('performance_test', test_data)
    broadcast_time = time.time() - start_time
    print(f"100クライアント配信時間: {broadcast_time:.4f}秒")
    
    # 受信確認
    received_count = 0
    start_time = time.time()
    for queue in test_queues:
        try:
            queue.get(timeout=1)
            received_count += 1
        except Empty:
            pass
    
    receive_time = time.time() - start_time
    print(f"受信確認時間: {receive_time:.4f}秒")
    print(f"受信成功率: {received_count}/{client_count} ({received_count/client_count*100:.1f}%)")
    
    # クリーンアップ
    start_time = time.time()
    for queue in test_queues:
        remove_sse_client(queue)
    cleanup_time = time.time() - start_time
    print(f"100クライアント削除時間: {cleanup_time:.4f}秒")
    
    print("✅ パフォーマンステスト完了")

if __name__ == '__main__':
    print("=== SSE統一管理システム テストスイート ===")
    print("テスト開始時刻:", time.strftime("%Y-%m-%d %H:%M:%S"))
    
    # 基本的な単体テストを実行
    suite = unittest.TestLoader().loadTestsFromTestCase(SSEUnifiedManagementTestCase)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # パフォーマンステストを実行
    run_performance_test()
    
    print("\n=== テスト結果サマリー ===")
    print(f"実行テスト数: {result.testsRun}")
    print(f"失敗: {len(result.failures)}")
    print(f"エラー: {len(result.errors)}")
    
    if result.failures:
        print("\n失敗したテスト:")
        for test, trace in result.failures:
            print(f"- {test}: {trace}")
    
    if result.errors:
        print("\nエラーが発生したテスト:")
        for test, trace in result.errors:
            print(f"- {test}: {trace}")
    
    success_rate = (result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100
    print(f"\n成功率: {success_rate:.1f}%")
    
    if result.wasSuccessful():
        print("🎉 全テストが成功しました！")
    else:
        print("❌ 一部のテストが失敗しました")
    
    print("テスト終了時刻:", time.strftime("%Y-%m-%d %H:%M:%S"))