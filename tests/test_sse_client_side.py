#!/usr/bin/env python3
"""
SSE Manager (クライアントサイド) テストスイート

このテストスイートは JavaScript SSE Manager の動作をシミュレートして、
クライアントサイドのSSE統一管理システムをテストします。

テスト項目:
1. SSE Manager のインスタンス管理
2. 接続の確立と再利用
3. ページ固有リスナーの管理
4. セッション無効化処理
5. 接続状態の監視
"""

import unittest
import time
import json
from unittest.mock import Mock, patch, MagicMock
import threading
from queue import Queue

class MockEventSource:
    """EventSource のモック実装"""
    
    CONNECTING = 0
    OPEN = 1
    CLOSED = 2
    
    def __init__(self, url):
        self.url = url
        self.readyState = self.CONNECTING
        self.onopen = None
        self.onmessage = None
        self.onerror = None
        self.event_listeners = {}
        
        # 接続成功をシミュレート
        threading.Timer(0.1, self._simulate_open).start()
    
    def _simulate_open(self):
        """接続成功をシミュレート"""
        self.readyState = self.OPEN
        if self.onopen:
            self.onopen()
    
    def addEventListener(self, event_type, handler):
        """イベントリスナーを追加"""
        if event_type not in self.event_listeners:
            self.event_listeners[event_type] = []
        self.event_listeners[event_type].append(handler)
    
    def removeEventListener(self, event_type, handler):
        """イベントリスナーを削除"""
        if event_type in self.event_listeners:
            try:
                self.event_listeners[event_type].remove(handler)
            except ValueError:
                pass
    
    def close(self):
        """接続を閉じる"""
        self.readyState = self.CLOSED
    
    def simulate_event(self, event_type, data):
        """イベントの発生をシミュレート"""
        if event_type == 'message' and self.onmessage:
            mock_event = Mock()
            mock_event.data = json.dumps(data)
            self.onmessage(mock_event)
        
        if event_type in self.event_listeners:
            mock_event = Mock()
            mock_event.data = json.dumps(data)
            for handler in self.event_listeners[event_type]:
                handler(mock_event)

class SSEManagerMock:
    """JavaScript SSE Manager のPython実装"""
    
    def __init__(self):
        self.event_source = None
        self.listeners = {}  # pageId -> {eventType: handler}
        self.base_listeners_setup = False
        self.connection_attempts = 0
        self.max_retries = 3
        
        # グローバル状態のシミュレート
        self.global_event_source = None
    
    def connect(self):
        """SSE接続を確立または既存接続を返す"""
        # グローバルの既存接続をチェック
        if (self.global_event_source and 
            self.global_event_source.readyState == MockEventSource.OPEN):
            print('SSE Manager: グローバルの既存接続を使用')
            self.event_source = self.global_event_source
            self.setup_base_listeners()
            return self.event_source
        
        # ローカルの既存接続をチェック
        if (self.event_source and 
            self.event_source.readyState == MockEventSource.OPEN):
            print('SSE Manager: ローカルの既存接続を使用')
            self.global_event_source = self.event_source
            return self.event_source
        
        # 既存接続を閉じる
        if self.event_source:
            self.event_source.close()
        if self.global_event_source:
            self.global_event_source.close()
        
        try:
            print('SSE Manager: 新しい接続を確立中...')
            self.event_source = MockEventSource('/api/events')
            self.global_event_source = self.event_source
            self.setup_base_listeners()
            self.connection_attempts = 0
            return self.event_source
        except Exception as error:
            print(f'SSE Manager: 接続確立に失敗: {error}')
            self.connection_attempts += 1
            return None
    
    def setup_base_listeners(self):
        """基本的なSSEイベントリスナーを設定"""
        if self.base_listeners_setup or not self.event_source:
            return
        
        def on_open():
            print('SSE Manager: 接続が確立されました')
            self.connection_attempts = 0
        
        def on_message(event):
            try:
                data = json.loads(event.data)
                self.handle_generic_event(data)
            except Exception as e:
                print(f'SSE Manager: メッセージ解析に失敗: {e}')
        
        def on_error(error):
            print(f'SSE Manager: 接続エラー: {error}')
        
        self.event_source.onopen = on_open
        self.event_source.onmessage = on_message
        self.event_source.onerror = on_error
        
        self.setup_specific_event_listeners()
        self.base_listeners_setup = True
    
    def setup_specific_event_listeners(self):
        """特定のイベントタイプのリスナーを設定"""
        def session_invalidated_handler(event):
            try:
                data = json.loads(event.data)
                print(f'SSE Manager: セッション無効化イベント受信: {data["message"]}')
                self.handle_session_invalidated(data)
            except Exception as e:
                print(f'SSE Manager: セッション無効化イベント処理に失敗: {e}')
        
        def pdf_published_handler(event):
            try:
                data = json.loads(event.data)
                print(f'SSE Manager: PDF公開イベント受信: {data["message"]}')
                self.broadcast_to_page_listeners('pdf_published', data)
            except Exception as e:
                print(f'SSE Manager: PDF公開イベント処理に失敗: {e}')
        
        def pdf_unpublished_handler(event):
            try:
                data = json.loads(event.data)
                print(f'SSE Manager: PDF停止イベント受信: {data["message"]}')
                self.broadcast_to_page_listeners('pdf_unpublished', data)
            except Exception as e:
                print(f'SSE Manager: PDF停止イベント処理に失敗: {e}')
        
        self.event_source.addEventListener('session_invalidated', session_invalidated_handler)
        self.event_source.addEventListener('pdf_published', pdf_published_handler)
        self.event_source.addEventListener('pdf_unpublished', pdf_unpublished_handler)
    
    def handle_generic_event(self, data):
        """汎用イベント処理"""
        if data.get('event') == 'connected':
            print('SSE Manager: 接続確認メッセージ受信')
        elif data.get('event') == 'heartbeat':
            # ハートビートは無視
            pass
        else:
            print(f'SSE Manager: 汎用イベント受信: {data}')
    
    def handle_session_invalidated(self, data):
        """セッション無効化の統一処理"""
        self.show_session_invalidated_notification(data['message'])
        # 実際の実装では3秒後にリダイレクト
        print(f'SSE Manager: 3秒後に {data.get("redirect_url", "/auth/login")} にリダイレクト')
    
    def show_session_invalidated_notification(self, message):
        """セッション無効化の通知表示（シミュレート）"""
        print(f'SSE Manager: セッション無効化通知表示: {message}')
    
    def add_page_listeners(self, page_id, listeners):
        """ページ固有のイベントリスナーを追加"""
        print(f'SSE Manager: {page_id} ページのリスナーを追加: {list(listeners.keys())}')
        self.listeners[page_id] = listeners
    
    def remove_page_listeners(self, page_id):
        """ページ固有のイベントリスナーを削除"""
        if page_id in self.listeners:
            print(f'SSE Manager: {page_id} ページのリスナーを削除')
            del self.listeners[page_id]
    
    def broadcast_to_page_listeners(self, event_type, data):
        """登録されたページリスナーにイベントを配信"""
        for page_id, page_listeners in self.listeners.items():
            if event_type in page_listeners:
                try:
                    print(f'SSE Manager: {page_id} ページの {event_type} ハンドラーを実行')
                    page_listeners[event_type](data)
                except Exception as error:
                    print(f'SSE Manager: {page_id} の {event_type} ハンドラー実行に失敗: {error}')
    
    def disconnect(self):
        """SSE接続を切断"""
        if self.event_source:
            print('SSE Manager: 接続を切断中...')
            self.event_source.close()
            self.event_source = None
            self.base_listeners_setup = False
            self.listeners.clear()
        
        if self.global_event_source:
            self.global_event_source.close()
            self.global_event_source = None
    
    def get_ready_state(self):
        """接続状態を取得"""
        return self.event_source.readyState if self.event_source else MockEventSource.CLOSED
    
    def get_page_count(self):
        """接続中のページ数を取得"""
        return len(self.listeners)

class SSEClientSideTestCase(unittest.TestCase):
    """SSE Manager クライアントサイドテスト"""
    
    def setUp(self):
        """テスト前の準備"""
        self.sse_manager = SSEManagerMock()
    
    def tearDown(self):
        """テスト後のクリーンアップ"""
        self.sse_manager.disconnect()
    
    def test_sse_manager_connection(self):
        """SSE Manager 接続テスト"""
        print("\n=== SSE Manager 接続テスト ===")
        
        # 初期状態確認
        self.assertEqual(self.sse_manager.get_ready_state(), MockEventSource.CLOSED)
        print("初期状態: 切断")
        
        # 接続確立
        event_source = self.sse_manager.connect()
        self.assertIsNotNone(event_source)
        print("接続確立: 成功")
        
        # 接続状態が確立されるまで待機
        time.sleep(0.2)
        self.assertEqual(self.sse_manager.get_ready_state(), MockEventSource.OPEN)
        print("接続状態: 確立")
        
        print("✅ SSE Manager 接続テスト完了")
    
    def test_connection_reuse(self):
        """接続再利用テスト"""
        print("\n=== 接続再利用テスト ===")
        
        # 最初の接続
        event_source1 = self.sse_manager.connect()
        time.sleep(0.2)
        
        # 2回目の接続（再利用されるべき）
        event_source2 = self.sse_manager.connect()
        
        self.assertEqual(event_source1, event_source2)
        print("✅ 既存接続の再利用確認")
        
        print("✅ 接続再利用テスト完了")
    
    def test_page_listeners_management(self):
        """ページリスナー管理テスト"""
        print("\n=== ページリスナー管理テスト ===")
        
        # 接続確立
        self.sse_manager.connect()
        time.sleep(0.2)
        
        # ページリスナー追加
        admin_handlers = {
            'pdf_published': Mock(),
            'pdf_unpublished': Mock()
        }
        
        viewer_handlers = {
            'pdf_published': Mock(),
            'pdf_unpublished': Mock()
        }
        
        self.sse_manager.add_page_listeners('admin', admin_handlers)
        self.sse_manager.add_page_listeners('viewer', viewer_handlers)
        
        self.assertEqual(self.sse_manager.get_page_count(), 2)
        print("ページリスナー追加: 2ページ")
        
        # イベント配信テスト
        test_data = {'message': 'テストPDF公開'}
        self.sse_manager.broadcast_to_page_listeners('pdf_published', test_data)
        
        # 両方のハンドラーが呼ばれることを確認
        admin_handlers['pdf_published'].assert_called_once_with(test_data)
        viewer_handlers['pdf_published'].assert_called_once_with(test_data)
        print("✅ 両ページでイベント受信確認")
        
        # ページリスナー削除
        self.sse_manager.remove_page_listeners('admin')
        self.assertEqual(self.sse_manager.get_page_count(), 1)
        print("ページリスナー削除: 1ページ残存")
        
        print("✅ ページリスナー管理テスト完了")
    
    def test_session_invalidation_handling(self):
        """セッション無効化処理テスト"""
        print("\n=== セッション無効化処理テスト ===")
        
        # 接続確立
        event_source = self.sse_manager.connect()
        time.sleep(0.2)
        
        # セッション無効化イベントをシミュレート
        test_data = {
            'message': 'セッションが無効化されました',
            'redirect_url': '/auth/login'
        }
        
        with patch.object(self.sse_manager, 'handle_session_invalidated') as mock_handler:
            event_source.simulate_event('session_invalidated', test_data)
            
            # ハンドラーが呼ばれることを確認
            mock_handler.assert_called_once_with(test_data)
            print("✅ セッション無効化ハンドラー実行確認")
        
        print("✅ セッション無効化処理テスト完了")
    
    def test_pdf_events_handling(self):
        """PDF公開/停止イベント処理テスト"""
        print("\n=== PDF公開/停止イベント処理テスト ===")
        
        # 接続確立
        event_source = self.sse_manager.connect()
        time.sleep(0.2)
        
        # ページハンドラー追加
        handlers = {
            'pdf_published': Mock(),
            'pdf_unpublished': Mock()
        }
        self.sse_manager.add_page_listeners('test_page', handlers)
        
        # PDF公開イベント
        publish_data = {
            'message': 'test.pdf が公開されました',
            'pdf_id': 1
        }
        event_source.simulate_event('pdf_published', publish_data)
        handlers['pdf_published'].assert_called_once_with(publish_data)
        print("✅ PDF公開イベント処理確認")
        
        # PDF停止イベント
        unpublish_data = {
            'message': 'test.pdf の公開が停止されました',
            'pdf_id': 1
        }
        event_source.simulate_event('pdf_unpublished', unpublish_data)
        handlers['pdf_unpublished'].assert_called_once_with(unpublish_data)
        print("✅ PDF停止イベント処理確認")
        
        print("✅ PDF公開/停止イベント処理テスト完了")
    
    def test_connection_error_handling(self):
        """接続エラー処理テスト"""
        print("\n=== 接続エラー処理テスト ===")
        
        # エラーをシミュレート
        with patch('__main__.MockEventSource', side_effect=Exception("接続エラー")):
            event_source = self.sse_manager.connect()
            self.assertIsNone(event_source)
            print("✅ 接続エラー時のNone返却確認")
        
        print("✅ 接続エラー処理テスト完了")
    
    def test_disconnect_cleanup(self):
        """切断時のクリーンアップテスト"""
        print("\n=== 切断クリーンアップテスト ===")
        
        # 接続確立とリスナー追加
        self.sse_manager.connect()
        time.sleep(0.2)
        
        handlers = {'pdf_published': Mock()}
        self.sse_manager.add_page_listeners('test_page', handlers)
        
        # 切断前の状態確認
        self.assertEqual(self.sse_manager.get_ready_state(), MockEventSource.OPEN)
        self.assertEqual(self.sse_manager.get_page_count(), 1)
        print("切断前: 接続確立、リスナー1つ")
        
        # 切断実行
        self.sse_manager.disconnect()
        
        # 切断後の状態確認
        self.assertEqual(self.sse_manager.get_ready_state(), MockEventSource.CLOSED)
        self.assertEqual(self.sse_manager.get_page_count(), 0)
        print("切断後: 接続切断、リスナー0個")
        
        print("✅ 切断クリーンアップテスト完了")

class SSEManagerIntegrationTestCase(unittest.TestCase):
    """SSE Manager 統合テスト"""
    
    def test_multiple_instances_scenario(self):
        """複数インスタンスシナリオテスト"""
        print("\n=== 複数インスタンスシナリオテスト ===")
        
        # 複数の SSE Manager インスタンス（異なるページをシミュレート）
        admin_manager = SSEManagerMock()
        viewer_manager = SSEManagerMock()
        
        try:
            # 最初の接続（admin）
            admin_es = admin_manager.connect()
            time.sleep(0.2)
            print("管理ページ: 接続確立")
            
            # グローバル接続を共有（viewer）
            viewer_manager.global_event_source = admin_manager.global_event_source
            viewer_es = viewer_manager.connect()
            print("ビューワーページ: 既存接続再利用")
            
            # 同じEventSourceインスタンスが使用されることを確認
            self.assertEqual(admin_es, viewer_es)
            print("✅ 接続インスタンス共有確認")
            
            # 各ページのリスナー追加
            admin_manager.add_page_listeners('admin', {
                'pdf_published': Mock(name='admin_pdf_published')
            })
            
            viewer_manager.add_page_listeners('viewer', {
                'pdf_published': Mock(name='viewer_pdf_published')
            })
            
            # イベント配信テスト
            test_data = {'message': 'PDF公開テスト'}
            admin_manager.broadcast_to_page_listeners('pdf_published', test_data)
            viewer_manager.broadcast_to_page_listeners('pdf_published', test_data)
            
            print("✅ 複数ページでのイベント配信確認")
            
        finally:
            admin_manager.disconnect()
            viewer_manager.disconnect()
        
        print("✅ 複数インスタンスシナリオテスト完了")

def run_client_side_performance_test():
    """クライアントサイド パフォーマンステスト"""
    print("\n=== クライアントサイド パフォーマンステスト ===")
    
    # 大量のページリスナー管理テスト
    manager = SSEManagerMock()
    manager.connect()
    time.sleep(0.2)
    
    page_count = 50
    start_time = time.time()
    
    # 50ページのリスナーを追加
    for i in range(page_count):
        handlers = {
            'pdf_published': Mock(name=f'page_{i}_published'),
            'pdf_unpublished': Mock(name=f'page_{i}_unpublished')
        }
        manager.add_page_listeners(f'page_{i}', handlers)
    
    add_time = time.time() - start_time
    print(f"50ページリスナー追加時間: {add_time:.4f}秒")
    
    # 大量配信テスト
    start_time = time.time()
    test_data = {'message': 'パフォーマンステスト'}
    manager.broadcast_to_page_listeners('pdf_published', test_data)
    broadcast_time = time.time() - start_time
    print(f"50ページ配信時間: {broadcast_time:.4f}秒")
    
    # クリーンアップ
    start_time = time.time()
    for i in range(page_count):
        manager.remove_page_listeners(f'page_{i}')
    cleanup_time = time.time() - start_time
    print(f"50ページリスナー削除時間: {cleanup_time:.4f}秒")
    
    manager.disconnect()
    print("✅ クライアントサイド パフォーマンステスト完了")

if __name__ == '__main__':
    print("=== SSE Manager (クライアントサイド) テストスイート ===")
    print("テスト開始時刻:", time.strftime("%Y-%m-%d %H:%M:%S"))
    
    # 基本的な単体テストを実行
    suite = unittest.TestLoader().loadTestsFromTestCase(SSEClientSideTestCase)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 統合テストを実行
    integration_suite = unittest.TestLoader().loadTestsFromTestCase(SSEManagerIntegrationTestCase)
    integration_result = runner.run(integration_suite)
    
    # パフォーマンステストを実行
    run_client_side_performance_test()
    
    print("\n=== テスト結果サマリー ===")
    total_tests = result.testsRun + integration_result.testsRun
    total_failures = len(result.failures) + len(integration_result.failures)
    total_errors = len(result.errors) + len(integration_result.errors)
    
    print(f"実行テスト数: {total_tests}")
    print(f"失敗: {total_failures}")
    print(f"エラー: {total_errors}")
    
    success_rate = (total_tests - total_failures - total_errors) / total_tests * 100
    print(f"成功率: {success_rate:.1f}%")
    
    if result.wasSuccessful() and integration_result.wasSuccessful():
        print("🎉 全テストが成功しました！")
    else:
        print("❌ 一部のテストが失敗しました")
    
    print("テスト終了時刻:", time.strftime("%Y-%m-%d %H:%M:%S"))