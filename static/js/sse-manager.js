/**
 * SSE接続統一管理モジュール
 * ページ遷移してもSSE接続を保持し、ページ固有のイベントリスナーを管理
 */
class SSEManager {
    constructor() {
        this.eventSource = null;
        this.listeners = new Map(); // ページ固有リスナー管理: pageId -> {eventType: handler}
        this.baseListenersSetup = false;
        this.connectionAttempts = 0;
        this.maxRetries = 3;
    }
    
    /**
     * SSE接続を確立または既存接続を返す
     * @returns {EventSource} SSE接続
     */
    connect() {
        // グローバルに保存されているEventSourceを確認
        if (window.globalEventSource && window.globalEventSource.readyState === EventSource.OPEN) {
            console.log('SSE Manager: グローバルの既存接続を使用');
            this.eventSource = window.globalEventSource;
            this.setupBaseListeners();
            return this.eventSource;
        }
        
        // ローカルの既存の有効な接続がある場合はそれを返す
        if (this.eventSource && this.eventSource.readyState === EventSource.OPEN) {
            console.log('SSE Manager: ローカルの既存接続を使用');
            window.globalEventSource = this.eventSource;
            return this.eventSource;
        }
        
        // 既存の接続を閉じる
        if (this.eventSource) {
            this.eventSource.close();
        }
        if (window.globalEventSource) {
            window.globalEventSource.close();
        }
        
        try {
            console.log('SSE Manager: 新しい接続を確立中...');
            this.eventSource = new EventSource('/api/events');
            window.globalEventSource = this.eventSource;  // グローバルに保存
            this.setupBaseListeners();
            this.connectionAttempts = 0;
            return this.eventSource;
        } catch (error) {
            console.error('SSE Manager: 接続確立に失敗:', error);
            this.connectionAttempts++;
            
            if (this.connectionAttempts < this.maxRetries) {
                console.log(`SSE Manager: ${this.connectionAttempts}回目の再試行を3秒後に実行`);
                setTimeout(() => this.connect(), 3000);
            }
            return null;
        }
    }
    
    /**
     * 基本的なSSEイベントリスナーを設定
     */
    setupBaseListeners() {
        if (this.baseListenersSetup || !this.eventSource) {
            return;
        }
        
        this.eventSource.onopen = () => {
            console.log('SSE Manager: 接続が確立されました');
            this.connectionAttempts = 0;
        };
        
        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleGenericEvent(data);
            } catch (e) {
                console.warn('SSE Manager: メッセージ解析に失敗:', e);
            }
        };
        
        this.eventSource.onerror = (error) => {
            console.warn('SSE Manager: 接続エラー:', error);
            
            // 接続が切断された場合の自動再接続
            if (this.eventSource.readyState === EventSource.CLOSED) {
                console.log('SSE Manager: 接続が切断されました。再接続を試行します');
                setTimeout(() => this.connect(), 2000);
            }
        };
        
        // 特定のイベントタイプのリスナーを設定
        this.setupSpecificEventListeners();
        
        this.baseListenersSetup = true;
    }
    
    /**
     * 特定のイベントタイプのリスナーを設定
     */
    setupSpecificEventListeners() {
        // session_invalidated は全ページ共通で最優先処理
        this.eventSource.addEventListener('session_invalidated', (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('SSE Manager: セッション無効化イベント受信:', data.message);
                this.handleSessionInvalidated(data);
            } catch (e) {
                console.warn('SSE Manager: セッション無効化イベント処理に失敗:', e);
            }
        });
        
        // pdf_published イベント
        this.eventSource.addEventListener('pdf_published', (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('SSE Manager: PDF公開イベント受信:', data.message);
                this.broadcastToPageListeners('pdf_published', data);
            } catch (e) {
                console.warn('SSE Manager: PDF公開イベント処理に失敗:', e);
            }
        });
        
        // pdf_unpublished イベント
        this.eventSource.addEventListener('pdf_unpublished', (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('SSE Manager: PDF停止イベント受信:', data.message);
                this.broadcastToPageListeners('pdf_unpublished', data);
            } catch (e) {
                console.warn('SSE Manager: PDF停止イベント処理に失敗:', e);
            }
        });
    }
    
    /**
     * 汎用イベント処理（onmessage用）
     */
    handleGenericEvent(data) {
        if (data.event === 'connected') {
            console.log('SSE Manager: 接続確認メッセージ受信');
        } else if (data.event === 'heartbeat') {
            // ハートビートは無視（ログ出力なし）
        } else {
            console.log('SSE Manager: 汎用イベント受信:', data);
        }
    }
    
    /**
     * セッション無効化の統一処理（全ページ共通）
     */
    handleSessionInvalidated(data) {
        // クライアント側セッションストレージをクリア
        if (data.clear_session) {
            console.log('SSE Manager: クライアント側セッションストレージをクリア中...');
            // sessionStorageとlocalStorageをクリア
            if (typeof(Storage) !== "undefined") {
                sessionStorage.clear();
                localStorage.clear();
            }
        }
        
        // 視覚的フィードバック
        this.showSessionInvalidatedNotification(data.message);
        
        // 3秒後にログインページにリダイレクト
        setTimeout(() => {
            console.log('SSE Manager: ログインページにリダイレクト中...');
            window.location.href = data.redirect_url || '/auth/login';
        }, 3000);
    }
    
    /**
     * セッション無効化の通知表示
     */
    showSessionInvalidatedNotification(message) {
        // 既存の通知を削除
        const existingNotification = document.querySelector('.session-invalidated-notification');
        if (existingNotification) {
            existingNotification.remove();
        }
        
        // 新しい通知を作成
        const notification = document.createElement('div');
        notification.className = 'session-invalidated-notification';
        notification.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: 10000;
            background: linear-gradient(135deg, #ff6b6b, #ee5a52);
            color: white;
            padding: 2rem 3rem;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            text-align: center;
            font-size: 1.1rem;
            font-weight: bold;
            max-width: 400px;
            animation: slideInScale 0.3s ease-out;
        `;
        
        notification.innerHTML = `
            <div style="margin-bottom: 1rem; font-size: 2rem;">⚠️</div>
            <div>${message}</div>
            <div style="margin-top: 1rem; font-size: 0.9rem; opacity: 0.9;">3秒後にログインページに移動します...</div>
        `;
        
        // アニメーション追加
        if (!document.querySelector('#session-invalidated-animation')) {
            const style = document.createElement('style');
            style.id = 'session-invalidated-animation';
            style.textContent = `
                @keyframes slideInScale {
                    from {
                        opacity: 0;
                        transform: translate(-50%, -50%) scale(0.8);
                    }
                    to {
                        opacity: 1;
                        transform: translate(-50%, -50%) scale(1);
                    }
                }
            `;
            document.head.appendChild(style);
        }
        
        document.body.appendChild(notification);
    }
    
    /**
     * ページ固有のイベントリスナーを追加
     * @param {string} pageId ページ識別子
     * @param {Object} listeners イベントタイプとハンドラーのマップ
     */
    addPageListeners(pageId, listeners) {
        console.log(`SSE Manager: ${pageId} ページのリスナーを追加:`, Object.keys(listeners));
        this.listeners.set(pageId, listeners);
    }
    
    /**
     * ページ固有のイベントリスナーを削除
     * @param {string} pageId ページ識別子
     */
    removePageListeners(pageId) {
        if (this.listeners.has(pageId)) {
            console.log(`SSE Manager: ${pageId} ページのリスナーを削除`);
            this.listeners.delete(pageId);
        }
    }
    
    /**
     * 登録されたページリスナーにイベントを配信
     * @param {string} eventType イベントタイプ
     * @param {Object} data イベントデータ
     */
    broadcastToPageListeners(eventType, data) {
        this.listeners.forEach((pageListeners, pageId) => {
            if (pageListeners[eventType]) {
                try {
                    console.log(`SSE Manager: ${pageId} ページの ${eventType} ハンドラーを実行`);
                    pageListeners[eventType](data);
                } catch (error) {
                    console.error(`SSE Manager: ${pageId} の ${eventType} ハンドラー実行に失敗:`, error);
                }
            }
        });
    }
    
    /**
     * SSE接続を切断
     */
    disconnect() {
        if (this.eventSource) {
            console.log('SSE Manager: 接続を切断中...');
            this.eventSource.close();
            this.eventSource = null;
            this.baseListenersSetup = false;
            this.listeners.clear();
        }
        // グローバル接続もクリア
        if (window.globalEventSource) {
            window.globalEventSource.close();
            window.globalEventSource = null;
        }
    }
    
    /**
     * 接続状態を取得
     * @returns {number} EventSource の readyState
     */
    getReadyState() {
        return this.eventSource ? this.eventSource.readyState : EventSource.CLOSED;
    }
    
    /**
     * 接続中のページ数を取得
     * @returns {number} 登録されているページリスナー数
     */
    getPageCount() {
        return this.listeners.size;
    }
}

// グローバルインスタンス作成（既存インスタンスがある場合は再利用）
if (!window.sseManager) {
    window.sseManager = new SSEManager();
    console.log('SSE Manager: 新しいグローバルインスタンスを作成');
} else {
    console.log('SSE Manager: 既存のグローバルインスタンスを再利用');
}

// タブ閉じ時の自動クリーンアップ
window.addEventListener('beforeunload', () => {
    if (window.sseManager) {
        window.sseManager.disconnect();
    }
});

// デバッグ用（本番では削除）
window.addEventListener('load', () => {
    console.log('SSE Manager: グローバルインスタンス準備完了');
});