/**
 * セキュリティイベント検知システム
 * PDF閲覧中の不正操作や試行を検知してサーバーに記録する
 */

class SecurityEventDetector {
    constructor() {
        this.initialized = false;
        this.currentPdfPath = null;
        this.pageViewStartTime = null;
        this.lastEventTime = 0;
        this.isDevToolsOpen = false;
        
        // イベント制限（重複送信防止）
        this.eventThrottleMs = 1000;
        this.lastEvents = new Map();
        
        this.init();
    }
    
    init() {
        if (this.initialized) return;
        
        console.log('SecurityEventDetector: Initializing...');
        
        // PDF表示イベント検知
        this.initPDFViewDetection();
        
        // ダウンロード試行検知
        this.initDownloadAttemptDetection();
        
        // 印刷試行検知
        this.initPrintAttemptDetection();
        
        // 開発者ツール検知
        this.initDevToolsDetection();
        
        // ページ離脱検知
        this.initPageLeaveDetection();
        
        // コピー試行検知
        this.initCopyAttemptDetection();
        
        // 右クリック検知
        this.initRightClickDetection();
        
        // スクリーンショット試行検知（部分的）
        this.initScreenshotDetection();
        
        this.initialized = true;
        console.log('SecurityEventDetector: Initialized successfully');
    }
    
    /**
     * PDF表示・閲覧イベント検知
     */
    initPDFViewDetection() {
        // PDF.jsのイベントを監視
        document.addEventListener('DOMContentLoaded', () => {
            // PDFが読み込まれた時
            const checkPDFLoaded = () => {
                const pdfViewer = document.querySelector('#viewer, .pdfViewer, canvas[data-pdf-page]');
                if (pdfViewer && !this.pageViewStartTime) {
                    this.pageViewStartTime = Date.now();
                    this.currentPdfPath = this.extractPdfPath();
                    
                    this.recordEvent('pdf_view', {
                        action: 'pdf_loaded',
                        pdf_path: this.currentPdfPath,
                        timestamp: this.pageViewStartTime
                    }, 'low');
                }
            };
            
            // 定期的にチェック
            const checkInterval = setInterval(() => {
                checkPDFLoaded();
                if (this.pageViewStartTime) {
                    clearInterval(checkInterval);
                }
            }, 500);
            
            // 5秒後にチェックを停止
            setTimeout(() => clearInterval(checkInterval), 5000);
        });
        
        // PDF.jsの内部イベント監視
        if (window.PDFViewerApplication) {
            window.PDFViewerApplication.eventBus.on('pagerendered', (evt) => {
                this.recordEvent('pdf_view', {
                    action: 'page_rendered',
                    page: evt.pageNumber,
                    timestamp: Date.now()
                }, 'low');
            });
        }
    }
    
    /**
     * ダウンロード試行検知
     */
    initDownloadAttemptDetection() {
        // Ctrl+S キー検知
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 's') {
                e.preventDefault();
                this.recordEvent('download_attempt', {
                    method: 'ctrl_s',
                    prevented: true,
                    key_combination: 'Ctrl+S'
                }, 'high');
            }
            
            // Ctrl+Shift+S (名前を付けて保存)
            if (e.ctrlKey && e.shiftKey && e.key === 'S') {
                e.preventDefault();
                this.recordEvent('download_attempt', {
                    method: 'ctrl_shift_s',
                    prevented: true,
                    key_combination: 'Ctrl+Shift+S'
                }, 'high');
            }
        });
        
        // ブラウザのダウンロードメニュー検知（完全ではない）
        document.addEventListener('contextmenu', (e) => {
            // PDF要素での右クリック
            const target = e.target;
            if (this.isPDFElement(target)) {
                e.preventDefault();
                this.recordEvent('download_attempt', {
                    method: 'right_click_menu',
                    prevented: true,
                    target: target.tagName
                }, 'high');
            }
        });
    }
    
    /**
     * 印刷試行検知
     */
    initPrintAttemptDetection() {
        // Ctrl+P キー検知
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'p') {
                e.preventDefault();
                this.recordEvent('print_attempt', {
                    method: 'ctrl_p',
                    prevented: true,
                    key_combination: 'Ctrl+P'
                }, 'high');
            }
        });
        
        // beforeprint イベント
        window.addEventListener('beforeprint', (e) => {
            e.preventDefault();
            this.recordEvent('print_attempt', {
                method: 'browser_print',
                prevented: true,
                event_type: 'beforeprint'
            }, 'high');
        });
        
        // afterprint イベント
        window.addEventListener('afterprint', (e) => {
            this.recordEvent('print_attempt', {
                method: 'browser_print',
                prevented: false,
                event_type: 'afterprint'
            }, 'high');
        });
    }
    
    /**
     * 開発者ツール検知
     */
    initDevToolsDetection() {
        // F12キー検知
        document.addEventListener('keydown', (e) => {
            if (e.key === 'F12') {
                e.preventDefault();
                this.recordEvent('devtools_open', {
                    method: 'f12_key',
                    prevented: true
                }, 'high');
            }
        });
        
        // Ctrl+Shift+I 検知
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.shiftKey && e.key === 'I') {
                e.preventDefault();
                this.recordEvent('devtools_open', {
                    method: 'ctrl_shift_i',
                    prevented: true
                }, 'high');
            }
        });
        
        // 右クリック + 検証 検知
        document.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            this.recordEvent('devtools_open', {
                method: 'right_click_inspect',
                prevented: true
            }, 'high');
        });
        
        // DevToolsの検知（サイズベース）
        this.startDevToolsMonitoring();
    }
    
    /**
     * 開発者ツールのサイズベース検知
     */
    startDevToolsMonitoring() {
        const threshold = 160;
        let isOpen = false;
        
        const checkDevTools = () => {
            const widthThreshold = window.outerWidth - window.innerWidth > threshold;
            const heightThreshold = window.outerHeight - window.innerHeight > threshold;
            const orientation = widthThreshold ? 'vertical' : 'horizontal';
            
            if ((heightThreshold && orientation === 'horizontal') || 
                (widthThreshold && orientation === 'vertical')) {
                if (!isOpen) {
                    isOpen = true;
                    this.isDevToolsOpen = true;
                    this.recordEvent('devtools_open', {
                        method: 'size_detection',
                        prevented: false,
                        orientation: orientation
                    }, 'high');
                }
            } else {
                if (isOpen) {
                    isOpen = false;
                    this.isDevToolsOpen = false;
                    this.recordEvent('devtools_open', {
                        method: 'devtools_closed',
                        prevented: false
                    }, 'medium');
                }
            }
        };
        
        // 定期的にチェック
        setInterval(checkDevTools, 1000);
        
        // リサイズイベントでもチェック
        window.addEventListener('resize', checkDevTools);
    }
    
    /**
     * ページ離脱検知
     */
    initPageLeaveDetection() {
        // beforeunload イベント
        window.addEventListener('beforeunload', (e) => {
            const duration = this.pageViewStartTime ? Date.now() - this.pageViewStartTime : 0;
            
            // Navigator.sendBeacon で即座に送信
            this.recordEventSync('page_leave', {
                method: 'beforeunload',
                duration_ms: duration,
                timestamp: Date.now()
            }, 'low');
        });
        
        // visibilitychange イベント
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.recordEvent('page_leave', {
                    method: 'visibility_hidden',
                    timestamp: Date.now()
                }, 'low');
            }
        });
        
        // pagehide イベント
        window.addEventListener('pagehide', (e) => {
            const duration = this.pageViewStartTime ? Date.now() - this.pageViewStartTime : 0;
            
            this.recordEventSync('page_leave', {
                method: 'pagehide',
                persisted: e.persisted,
                duration_ms: duration
            }, 'low');
        });
    }
    
    /**
     * コピー試行検知
     */
    initCopyAttemptDetection() {
        // Ctrl+C キー検知
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'c') {
                e.preventDefault();
                this.recordEvent('copy_attempt', {
                    method: 'ctrl_c',
                    prevented: true,
                    selection_length: window.getSelection().toString().length
                }, 'medium');
            }
        });
        
        // Ctrl+A キー検知（全選択）
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'a') {
                e.preventDefault();
                this.recordEvent('copy_attempt', {
                    method: 'ctrl_a',
                    prevented: true,
                    intent: 'select_all'
                }, 'medium');
            }
        });
        
        // copy イベント
        document.addEventListener('copy', (e) => {
            e.preventDefault();
            this.recordEvent('copy_attempt', {
                method: 'copy_event',
                prevented: true,
                clipboard_data: e.clipboardData ? 'present' : 'absent'
            }, 'medium');
        });
        
        // 選択無効化
        document.addEventListener('selectstart', (e) => {
            e.preventDefault();
        });
    }
    
    /**
     * 右クリック検知
     */
    initRightClickDetection() {
        document.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            
            this.recordEvent('unauthorized_action', {
                method: 'right_click',
                prevented: true,
                target: e.target.tagName,
                coordinates: {
                    x: e.clientX,
                    y: e.clientY
                }
            }, 'medium');
        });
    }
    
    /**
     * スクリーンショット試行検知（部分的）
     */
    initScreenshotDetection() {
        // PrintScreen キー検知
        document.addEventListener('keydown', (e) => {
            if (e.key === 'PrintScreen') {
                this.recordEvent('screenshot_attempt', {
                    method: 'print_screen',
                    prevented: false,
                    note: 'Cannot prevent system-level screenshot'
                }, 'medium');
            }
        });
        
        // Alt+PrintScreen キー検知
        document.addEventListener('keydown', (e) => {
            if (e.altKey && e.key === 'PrintScreen') {
                this.recordEvent('screenshot_attempt', {
                    method: 'alt_print_screen',
                    prevented: false,
                    note: 'Window screenshot attempt'
                }, 'medium');
            }
        });
        
        // Windows Snipping Tool検知 (Win+Shift+S)
        document.addEventListener('keydown', (e) => {
            if (e.metaKey && e.shiftKey && e.key === 'S') {
                this.recordEvent('screenshot_attempt', {
                    method: 'snipping_tool',
                    prevented: false,
                    key_combination: 'Win+Shift+S'
                }, 'medium');
            }
        });
    }
    
    /**
     * PDF要素かどうかを判定
     */
    isPDFElement(element) {
        if (!element) return false;
        
        // PDF.jsの要素を検知
        return element.closest('#viewer') || 
               element.closest('.pdfViewer') ||
               element.tagName === 'CANVAS' ||
               element.classList.contains('page') ||
               element.hasAttribute('data-pdf-page');
    }
    
    /**
     * 現在のPDFパスを抽出
     */
    extractPdfPath() {
        // URLパラメータから取得
        const urlParams = new URLSearchParams(window.location.search);
        const pdfParam = urlParams.get('pdf') || urlParams.get('file');
        
        if (pdfParam) return pdfParam;
        
        // パスから推測
        const path = window.location.pathname;
        if (path.includes('.pdf')) return path;
        
        return window.location.pathname;
    }
    
    /**
     * イベントの重複チェック
     */
    isDuplicateEvent(eventType, eventDetails) {
        const key = `${eventType}_${JSON.stringify(eventDetails)}`;
        const now = Date.now();
        const lastTime = this.lastEvents.get(key) || 0;
        
        if (now - lastTime < this.eventThrottleMs) {
            return true;
        }
        
        this.lastEvents.set(key, now);
        return false;
    }
    
    /**
     * セキュリティイベントを記録（非同期）
     */
    recordEvent(eventType, eventDetails, riskLevel = 'low') {
        // 重複チェック
        if (this.isDuplicateEvent(eventType, eventDetails)) {
            return;
        }
        
        const eventData = {
            event_type: eventType,
            event_details: {
                ...eventDetails,
                client_timestamp: Date.now(),
                user_agent: navigator.userAgent,
                screen_resolution: `${screen.width}x${screen.height}`,
                viewport_size: `${window.innerWidth}x${window.innerHeight}`,
                devtools_open: this.isDevToolsOpen
            },
            risk_level: riskLevel,
            pdf_file_path: this.currentPdfPath || this.extractPdfPath()
        };
        
        console.log('SecurityEventDetector: Recording event', eventData);
        
        // APIに送信
        fetch('/api/security-event', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(eventData)
        })
        .then(response => {
            if (!response.ok) {
                console.error('Failed to record security event:', response.status);
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                console.log('Security event recorded successfully');
            } else {
                console.error('Security event recording failed:', data.message);
            }
        })
        .catch(error => {
            console.error('Error recording security event:', error);
        });
    }
    
    /**
     * セキュリティイベントを記録（同期、ページ離脱時用）
     */
    recordEventSync(eventType, eventDetails, riskLevel = 'low') {
        const eventData = {
            event_type: eventType,
            event_details: {
                ...eventDetails,
                client_timestamp: Date.now(),
                user_agent: navigator.userAgent,
                sync: true
            },
            risk_level: riskLevel,
            pdf_file_path: this.currentPdfPath || this.extractPdfPath()
        };
        
        // Navigator.sendBeacon を使用（ページ離脱時でも送信可能）
        if (navigator.sendBeacon) {
            const blob = new Blob([JSON.stringify(eventData)], {
                type: 'application/json'
            });
            navigator.sendBeacon('/api/security-event', blob);
        } else {
            // フォールバック（同期XHR）
            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/security-event', false); // 同期
            xhr.setRequestHeader('Content-Type', 'application/json');
            try {
                xhr.send(JSON.stringify(eventData));
            } catch (e) {
                console.error('Failed to send sync event:', e);
            }
        }
    }
}

// インスタンス作成とグローバル登録
window.securityEventDetector = new SecurityEventDetector();

// デバッグ用（開発時のみ）
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    window.debugSecurityEvents = () => {
        console.log('Security Event Detector Debug Info:');
        console.log('- Initialized:', window.securityEventDetector.initialized);
        console.log('- Current PDF Path:', window.securityEventDetector.currentPdfPath);
        console.log('- Page View Start:', window.securityEventDetector.pageViewStartTime);
        console.log('- DevTools Open:', window.securityEventDetector.isDevToolsOpen);
        console.log('- Last Events:', window.securityEventDetector.lastEvents);
    };
}