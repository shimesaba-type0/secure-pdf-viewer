// PDF Upload functionality
document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('pdfFile');
    const uploadArea = document.getElementById('uploadArea');
    const uploadInfo = document.getElementById('uploadInfo');
    const uploadBtn = document.getElementById('uploadBtn');
    const clearBtn = document.getElementById('clearBtn');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    
    // SSE接続を初期化（新しいマネージャー使用）
    initializeAdminSSE();
    
    // パスフレーズ管理機能を初期化
    initializePassphraseManagement();
    
    // パスワード表示/非表示ボタンを初期化
    setTimeout(() => {
        console.log('Initializing password toggle after timeout');
        initializePasswordToggle();
    }, 100);
    
    // セッション管理機能を初期化
    initializeSessionManagement();
    
    // PDF セキュリティ設定機能を初期化
    initializePdfSecuritySettings();
    

    if (fileInput) {
        // File input change event
        fileInput.addEventListener('change', function(e) {
            handleFileSelection(e.target.files[0]);
        });

        // Drag and drop functionality
        uploadArea.addEventListener('dragover', function(e) {
            e.preventDefault();
            uploadArea.classList.add('drag-over');
        });

        uploadArea.addEventListener('dragleave', function(e) {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
        });

        uploadArea.addEventListener('drop', function(e) {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                fileInput.files = files;
                handleFileSelection(files[0]);
            }
        });
    }

    function handleFileSelection(file) {
        if (file) {
            if (file.type !== 'application/pdf') {
                alert('PDFファイルのみアップロード可能です');
                clearSelection();
                return;
            }

            if (file.size > 16 * 1024 * 1024) { // 16MB
                alert('ファイルサイズが16MBを超えています');
                clearSelection();
                return;
            }

            fileName.textContent = file.name;
            fileSize.textContent = formatFileSize(file.size);
            uploadInfo.style.display = 'block';
            uploadBtn.disabled = false;
            clearBtn.disabled = false;
        }
    }

    function formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }
});

function clearSelection() {
    const fileInput = document.getElementById('pdfFile');
    const uploadInfo = document.getElementById('uploadInfo');
    const uploadBtn = document.getElementById('uploadBtn');
    const clearBtn = document.getElementById('clearBtn');

    fileInput.value = '';
    uploadInfo.style.display = 'none';
    uploadBtn.disabled = true;
    clearBtn.disabled = true;
}

function previewPDF(path) {
    // Open PDF in new window/tab
    window.open(path, '_blank');
}

function deletePDF(fileId) {
    if (confirm('このPDFファイルを削除しますか？')) {
        fetch(`/admin/delete-pdf/${fileId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload(); // Refresh page to update file list
            } else {
                alert('削除に失敗しました: ' + data.error);
            }
        })
        .catch(error => {
            alert('削除に失敗しました: ' + error);
        });
    }
}

function publishPDF(fileId) {
    if (confirm('このPDFファイルを公開対象に設定しますか？\n※他の公開中ファイルは自動的に停止されます')) {
        fetch(`/admin/publish-pdf/${fileId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload(); // Refresh page to update file list
            } else {
                alert('公開設定に失敗しました: ' + data.error);
            }
        })
        .catch(error => {
            alert('公開設定に失敗しました: ' + error);
        });
    }
}

function unpublishPDF(fileId) {
    if (confirm('このPDFファイルの公開を停止しますか？')) {
        fetch(`/admin/unpublish-pdf/${fileId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload(); // Refresh page to update file list
            } else {
                alert('公開停止に失敗しました: ' + data.error);
            }
        })
        .catch(error => {
            alert('公開停止に失敗しました: ' + error);
        });
    }
}

function resetAuthorName() {
    const authorInput = document.getElementById('authorName');
    if (confirm('著作者名をデフォルト値（Default_Author）にリセットしますか？')) {
        authorInput.value = 'Default_Author';
    }
}

function clearPublishEndTime() {
    const publishEndInput = document.getElementById('publishEndDateTime');
    if (confirm('公開終了日時設定をクリアしますか？（無制限公開になります）')) {
        publishEndInput.value = '';
    }
}

function resetSessionLimits() {
    const maxSessionsInput = document.getElementById('maxConcurrentSessions');
    const enabledCheckbox = document.getElementById('sessionLimitEnabled');
    
    if (confirm('セッション制限設定をデフォルト値（100セッション、監視有効）に戻しますか？')) {
        maxSessionsInput.value = '100';
        enabledCheckbox.checked = true;
    }
}

function updateSessionLimitStatus() {
    // セッション制限状況を更新する関数
    fetch('/admin/api/session-limit-status')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const currentCount = document.getElementById('currentSessionCount');
                const usageRate = document.getElementById('sessionUsageRate');
                const warning = document.getElementById('sessionWarning');
                
                if (currentCount) currentCount.textContent = data.current_sessions;
                if (usageRate) {
                    const percentage = Math.round((data.current_sessions / data.max_sessions) * 100);
                    usageRate.textContent = `${percentage}% (${data.current_sessions}/${data.max_sessions})`;
                }
                
                // 警告表示の制御（80%以上で警告）
                if (warning) {
                    if (data.current_sessions >= data.max_sessions * 0.8) {
                        warning.style.display = 'block';
                        warning.querySelector('.warning-text').textContent = 
                            data.current_sessions >= data.max_sessions ? 
                            '制限に達しています' : '制限に近づいています';
                    } else {
                        warning.style.display = 'none';
                    }
                }
            }
        })
        .catch(error => {
            console.error('セッション制限状況の取得に失敗:', error);
        });
}

function initializeAdminSSE() {
    // SSE Manager を使用して接続確立
    if (!window.sseManager) {
        console.error('管理画面: SSE Manager が利用できません');
        return;
    }
    
    // SSE接続を確立
    window.sseManager.connect();
    
    // 管理画面固有のイベントリスナーを登録
    window.sseManager.addPageListeners('admin', {
        'pdf_published': handlePDFPublished,
        'pdf_unpublished': handlePDFUnpublished,
        'emergency_stop': handleEmergencyStop,
        'session_limit_warning': handleSessionLimitWarning,
        'session_limit_updated': handleSessionLimitUpdated
    });
    
    console.log('管理画面: SSE接続とリスナーを初期化しました');
    
    // 初期のセッション制限状況を更新
    updateSessionLimitStatus();
    
    // 30秒ごとにセッション制限状況を更新（セッションリスト更新と同期）
    setInterval(updateSessionLimitStatus, 30000);
}

// ページ離脱時のクリーンアップ
window.addEventListener('beforeunload', () => {
    if (window.sseManager) {
        window.sseManager.removePageListeners('admin');
    }
});

// 管理画面固有のイベントハンドラー

function handlePDFPublished(data) {
    console.log('管理画面: PDF公開開始:', data.message);
    
    // 即座にフィードバックメッセージを表示
    showSSENotification('📄 ' + data.message, 'success');
    
    // 公開状況を更新するため3秒後にページをリロード
    setTimeout(() => {
        window.location.reload();
    }, 3000);
}

function handlePDFUnpublished(data) {
    console.log('管理画面: PDF公開停止:', data.message);
    
    // 即座にフィードバックメッセージを表示
    showSSENotification('📄 ' + data.message, 'info');
    
    // 公開状況を更新するため5秒後にページをリロード
    setTimeout(() => {
        window.location.reload();
    }, 5000);
}

function handleEmergencyStop(data) {
    console.log('管理画面: 緊急停止実行:', data.message);
    
    // 即座に警告メッセージを表示
    showSSENotification('🚨 ' + data.message, 'warning');
    
    // 詳細情報をアラートで表示
    const details = [
        `📄 公開停止PDF: ${data.unpublished_pdfs || 0}件`,
        `🔐 無効化セッション: ${data.deleted_sessions || 0}件`,
        `🔑 削除OTPトークン: ${data.deleted_otps || 0}件`,
        `⏰ 実行時刻: ${data.timestamp || '不明'}`
    ].join('\n');
    
    setTimeout(() => {
        alert(`🚨 緊急停止が実行されました\n\n${details}`);
    }, 1000);
    
    // セッションクリア指示がある場合はクライアント側のセッションストレージもクリア
    if (data.clear_session) {
        try {
            if (typeof(Storage) !== "undefined") {
                sessionStorage.clear();
                localStorage.removeItem('session_data');
            }
            console.log('管理画面: クライアント側セッションストレージをクリアしました');
        } catch (e) {
            console.log('クライアント側セッションクリアでエラー:', e);
        }
    }
    
    // 8秒後にページをリロード（緊急停止の場合は少し長めに待つ）
    setTimeout(() => {
        window.location.reload();
    }, 8000);
}

function handleSessionLimitWarning(data) {
    console.log('管理画面: セッション制限警告:', data.message);
    
    // 警告メッセージを表示
    showSSENotification('⚠️ ' + data.message, 'warning');
    
    // セッション制限状況を更新
    updateSessionLimitStatus();
    
    // 使用率が90%以上の場合はより目立つ警告を表示
    if (data.usage_percentage >= 90) {
        setTimeout(() => {
            const warningDetails = [
                `現在のセッション数: ${data.current_count}`,
                `制限値: ${data.max_limit}`,
                `使用率: ${data.usage_percentage}%`,
                '',
                '新規ユーザーの接続が拒否される可能性があります。'
            ].join('\n');
            
            alert(`🚨 セッション数制限に近づいています\n\n${warningDetails}`);
        }, 1000);
    }
}

function handleSessionLimitUpdated(data) {
    console.log('管理画面: セッション制限設定更新:', data);
    
    // 設定更新通知を表示
    const message = `セッション制限設定が更新されました（制限: ${data.max_sessions}、監視: ${data.enabled ? '有効' : '無効'}）`;
    showSSENotification('⚙️ ' + message, 'info');
    
    // セッション制限状況を更新
    updateSessionLimitStatus();
    
    // 設定フォームの値を更新
    const maxSessionsInput = document.getElementById('maxConcurrentSessions');
    const enabledCheckbox = document.getElementById('sessionLimitEnabled');
    
    if (maxSessionsInput) maxSessionsInput.value = data.max_sessions;
    if (enabledCheckbox) enabledCheckbox.checked = data.enabled;
}

function showSSENotification(message, type = 'info') {
    // SSE通知用の一時的なメッセージを表示
    const notification = document.createElement('div');
    notification.className = `sse-notification sse-${type}`;
    notification.innerHTML = `
        <div class="sse-notification-content">
            <span>${message}</span>
            <button class="sse-close" onclick="this.parentElement.parentElement.remove()">×</button>
        </div>
    `;
    
    // ページ上部に挿入
    document.body.insertBefore(notification, document.body.firstChild);
    
    // 10秒後に自動削除
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 10000);
}

// パスフレーズ管理機能
function initializePassphraseManagement() {
    const newPassphraseInput = document.getElementById('newPassphrase');
    const confirmPassphraseInput = document.getElementById('confirmPassphrase');
    const updatePassphraseBtn = document.getElementById('updatePassphraseBtn');
    const passphraseCharCounter = document.getElementById('passphraseCharCounter');
    
    if (!newPassphraseInput || !confirmPassphraseInput) {
        return; // 管理画面にパスフレーズ設定がない場合
    }
    
    // リアルタイム文字数カウンターとバリデーション
    function updatePassphraseValidation() {
        const newValue = newPassphraseInput.value;
        const confirmValue = confirmPassphraseInput.value;
        const length = newValue.length;
        
        // 文字数カウンター更新
        if (passphraseCharCounter) {
            passphraseCharCounter.textContent = `${length} / 128 文字`;
            passphraseCharCounter.classList.remove('warning', 'error', 'success');
            
            if (length === 0) {
                // 長さが0の場合は何もクラスを追加しない
            } else if (length < 32) {
                passphraseCharCounter.classList.add('warning');
            } else if (length > 128) {
                passphraseCharCounter.classList.add('error');
            } else {
                passphraseCharCounter.classList.add('success');
            }
        }
        
        // バリデーション
        const isValidLength = length >= 32 && length <= 128;
        const isValidChars = /^[0-9a-zA-Z_-]+$/.test(newValue);
        const isMatching = newValue === confirmValue && confirmValue.length > 0;
        const isValid = isValidLength && isValidChars && isMatching && length > 0;
        
        // 送信ボタンの有効/無効
        updatePassphraseBtn.disabled = !isValid;
        
        // エラーメッセージの表示
        let errorMessage = '';
        if (length > 0) {
            if (!isValidLength) {
                errorMessage = length < 32 ? 'パスフレーズは32文字以上である必要があります' : 
                              length > 128 ? 'パスフレーズは128文字以下である必要があります' : '';
            } else if (!isValidChars) {
                errorMessage = '使用可能な文字は英数字・アンダースコア・ハイフンのみです';
            } else if (confirmValue.length > 0 && !isMatching) {
                errorMessage = 'パスフレーズが一致しません';
            }
        }
        
        // エラーメッセージの表示/非表示
        let errorDiv = document.querySelector('.passphrase-validation-error');
        if (errorMessage) {
            if (!errorDiv) {
                errorDiv = document.createElement('div');
                errorDiv.className = 'passphrase-validation-error alert alert-error';
                errorDiv.style.fontSize = '0.8rem';
                errorDiv.style.marginTop = '0.5rem';
                // 入力コンテナの外（親要素の後）に追加
                const confirmContainer = confirmPassphraseInput.parentNode;
                const formGroup = confirmContainer.parentNode;
                formGroup.appendChild(errorDiv);
            }
            errorDiv.textContent = errorMessage;
        } else if (errorDiv) {
            errorDiv.remove();
        }
    }
    
    // イベントリスナーを追加
    newPassphraseInput.addEventListener('input', updatePassphraseValidation);
    confirmPassphraseInput.addEventListener('input', updatePassphraseValidation);
    
    // 初期化
    updatePassphraseValidation();
}

function clearPassphraseForm() {
    const newPassphraseInput = document.getElementById('newPassphrase');
    const confirmPassphraseInput = document.getElementById('confirmPassphrase');
    
    if (confirm('パスフレーズフォームをクリアしますか？')) {
        newPassphraseInput.value = '';
        confirmPassphraseInput.value = '';
        
        // エラーメッセージを削除
        const errorDiv = document.querySelector('.passphrase-validation-error');
        if (errorDiv) {
            errorDiv.remove();
        }
        
        // バリデーション状態を更新
        if (window.initializePassphraseManagement) {
            const event = new Event('input');
            newPassphraseInput.dispatchEvent(event);
        }
    }
}

// グローバル関数（インライン onclick用）
function togglePasswordVisibility(inputId, button) {
    console.log('togglePasswordVisibility called with:', inputId, button);
    
    const inputField = document.getElementById(inputId);
    const toggleText = button.querySelector('.toggle-text');
    
    if (inputField && toggleText) {
        if (inputField.type === 'password') {
            inputField.type = 'text';
            toggleText.textContent = '隠す';
            button.setAttribute('aria-label', 'パスフレーズを隠す');
            console.log('Changed to text for', inputId);
        } else {
            inputField.type = 'password';
            toggleText.textContent = '表示';
            button.setAttribute('aria-label', 'パスフレーズを表示');
            console.log('Changed to password for', inputId);
        }
    } else {
        console.log('Elements not found:', inputField, toggleText);
    }
}

// パスワード表示/非表示機能
function initializePasswordToggle() {
    console.log('initializePasswordToggle called');
    
    const toggleButtons = [
        {
            btnId: 'toggleNewPassphrase',
            inputId: 'newPassphrase'
        },
        {
            btnId: 'toggleConfirmPassphrase',
            inputId: 'confirmPassphrase'
        }
    ];
    
    toggleButtons.forEach(({ btnId, inputId }) => {
        const toggleBtn = document.getElementById(btnId);
        const inputField = document.getElementById(inputId);
        
        console.log(`Looking for button: ${btnId}, input: ${inputId}`);
        console.log(`Button found: ${!!toggleBtn}, Input found: ${!!inputField}`);
        
        if (toggleBtn && inputField) {
            console.log(`Setting up event listener for ${btnId}`);
            
            toggleBtn.addEventListener('click', function(event) {
                event.preventDefault();
                console.log(`Toggle button clicked for ${inputId}`);
                
                const toggleText = toggleBtn.querySelector('.toggle-text');
                console.log(`Toggle text element:`, toggleText);
                
                if (inputField.type === 'password') {
                    inputField.type = 'text';
                    if (toggleText) toggleText.textContent = '隠す';
                    toggleBtn.setAttribute('aria-label', 'パスフレーズを隠す');
                    console.log(`Changed to text type for ${inputId}`);
                } else {
                    inputField.type = 'password';
                    if (toggleText) toggleText.textContent = '表示';
                    toggleBtn.setAttribute('aria-label', 'パスフレーズを表示');
                    console.log(`Changed to password type for ${inputId}`);
                }
            });
            
            // 初期状態のアクセシビリティ属性
            toggleBtn.setAttribute('aria-label', 'パスフレーズを表示');
        } else {
            console.log(`Missing elements - Button: ${!!toggleBtn}, Input: ${!!inputField}`);
        }
    });
}

// セッション管理機能
function invalidateAllSessions() {
    if (!confirm('本当に全セッションを無効化しますか？\n全ユーザーは再度ログインが必要になります。')) {
        return;
    }
    
    const btn = document.getElementById('invalidateSessionsBtn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '実行中...';
    
    fetch('/admin/invalidate-all-sessions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(`全セッション無効化が完了しました。\n削除されたセッション: ${data.deleted_sessions}\n削除されたOTPトークン: ${data.deleted_otps}`);
            location.reload(); // ページをリロードして最新状態を表示
        } else {
            alert(`エラーが発生しました: ${data.message || data.error}`);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('ネットワークエラーが発生しました。');
    })
    .finally(() => {
        btn.disabled = false;
        btn.textContent = originalText;
    });
}

function clearInvalidationSchedule() {
    if (!confirm('設定時刻セッション無効化のスケジュールを解除しますか？')) {
        return;
    }
    
    // バナーを即座に非表示にして視覚的フィードバック
    const banner = document.querySelector('.session-invalidation-banner');
    if (banner) {
        banner.style.opacity = '0.5';
        banner.style.pointerEvents = 'none';
    }
    
    fetch('/admin/clear-session-invalidation-schedule', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // 成功時はバナーを完全に削除
            if (banner) {
                banner.style.transition = 'all 0.5s ease';
                banner.style.transform = 'translateY(-20px)';
                banner.style.opacity = '0';
                setTimeout(() => {
                    banner.remove();
                    // フラッシュメッセージなしでページをリロード
                    location.reload();
                }, 500);
            } else {
                location.reload();
            }
        } else {
            // エラー時は元に戻す
            if (banner) {
                banner.style.opacity = '1';
                banner.style.pointerEvents = 'auto';
            }
            alert(`エラーが発生しました: ${data.message || data.error}`);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        // エラー時は元に戻す
        if (banner) {
            banner.style.opacity = '1';
            banner.style.pointerEvents = 'auto';
        }
        alert('ネットワークエラーが発生しました。');
    });
}

// セッション管理機能
let autoRefreshInterval = null;

function initializeSessionManagement() {
    console.log('セッション管理機能を初期化中...');
    
    // 初回データ取得
    refreshSessionList();
    
    // 少し遅延してから自動更新を開始（DOM要素の確実な読み込みを待つ）
    setTimeout(() => {
        startAutoRefresh();
        console.log('自動更新タイマーを開始しました:', autoRefreshInterval);
    }, 500);
}

function refreshSessionList() {
    fetch('/admin/api/active-sessions')
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showSessionError(data.error);
            return;
        }
        
        updateSessionStats(data.total_count, data.session_timeout_hours);
        updateSessionTable(data.sessions);
        updateDashboardStats(data.sessions);
        
        console.log(`セッション情報を更新: ${data.total_count}件`);
    })
    .catch(error => {
        console.error('セッション情報取得エラー:', error);
        showSessionError('セッション情報の取得に失敗しました');
    });
}

function updateSessionStats(count, timeoutHours) {
    const countElement = document.getElementById('activeSessionCount');
    const timeoutElement = document.getElementById('sessionTimeoutHours');
    
    if (countElement) {
        countElement.textContent = count;
    }
    
    if (timeoutElement) {
        timeoutElement.textContent = `${timeoutHours}時間`;
    }
}

function updateDashboardStats(sessions) {
    // ダッシュボードの統計を更新
    const dashboardActiveCount = document.getElementById('dashboardActiveCount');
    const dashboardMobileCount = document.getElementById('dashboardMobileCount');
    const dashboardTabletCount = document.getElementById('dashboardTabletCount');
    const dashboardDesktopCount = document.getElementById('dashboardDesktopCount');
    
    // デバイス別の集計
    let mobileCount = 0;
    let tabletCount = 0;
    let desktopCount = 0;
    
    sessions.forEach(session => {
        switch (session.device_type) {
            case 'mobile':
                mobileCount++;
                break;
            case 'tablet':
                tabletCount++;
                break;
            case 'desktop':
                desktopCount++;
                break;
        }
    });
    
    // ダッシュボードの表示を更新
    if (dashboardActiveCount) {
        dashboardActiveCount.textContent = sessions.length;
    }
    if (dashboardMobileCount) {
        dashboardMobileCount.textContent = mobileCount;
    }
    if (dashboardTabletCount) {
        dashboardTabletCount.textContent = tabletCount;
    }
    if (dashboardDesktopCount) {
        dashboardDesktopCount.textContent = desktopCount;
    }
}

function updateSessionTable(sessions) {
    const tbody = document.getElementById('sessionTableBody');
    
    if (!tbody) {
        console.error('セッションテーブルが見つかりません');
        return;
    }
    
    if (sessions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="no-sessions-row">アクティブセッションはありません</td></tr>';
        return;
    }
    
    let html = '';
    sessions.forEach(session => {
        const isExpiring = session.remaining_time.includes('時間') && 
                          parseInt(session.remaining_time) <= 2;
        const rowClass = isExpiring ? 'session-row-expiring' : '';
        
        // デバイスタイプのアイコンとラベル
        const deviceInfo = getDeviceInfo(session.device_type);
        
        html += `
            <tr class="${rowClass}">
                <td class="session-id" title="${session.session_id}">
                    <span class="sid-display">${session.session_id.substring(0, 12)}...</span>
                </td>
                <td class="email-address" title="${session.email_address}">
                    ${session.email_address}
                </td>
                <td class="device-type" title="${session.device_type}">
                    <span class="device-icon">${deviceInfo.icon}</span>
                    <span class="device-label">${deviceInfo.label}</span>
                </td>
                <td class="start-time">${session.start_time}</td>
                <td class="memo-cell">
                    <div class="memo-display" onclick="editMemo('${session.session_id}')">
                        <span class="memo-text" id="memo-${session.session_id}">${session.memo || '（メモなし）'}</span>
                        <span class="memo-edit-icon">✏️</span>
                    </div>
                    <div class="memo-edit-form" id="edit-${session.session_id}" style="display: none;">
                        <input type="text" class="memo-input" value="${session.memo || ''}" maxlength="500">
                        <button class="btn btn-sm btn-success" onclick="saveMemo('${session.session_id}')">保存</button>
                        <button class="btn btn-sm btn-secondary" onclick="cancelEditMemo('${session.session_id}')">キャンセル</button>
                    </div>
                </td>
                <td class="actions">
                    <button class="btn btn-info btn-sm" onclick="viewSessionDetails('${session.session_id}')">
                        詳細
                    </button>
                </td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

function showSessionError(message) {
    const tbody = document.getElementById('sessionTableBody');
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="6" class="error-row">エラー: ${message}</td></tr>`;
    }
}

function getDeviceInfo(deviceType) {
    // デバイスタイプに応じたアイコンとラベルを返す
    const deviceMap = {
        'mobile': { icon: '📱', label: 'スマホ' },
        'tablet': { icon: '📱', label: 'タブレット' },
        'desktop': { icon: '💻', label: 'PC' },
        'web': { icon: '🌐', label: 'Web' },
        'other': { icon: '❓', label: 'その他' }
    };
    
    return deviceMap[deviceType] || deviceMap['other'];
}

function toggleAutoRefresh() {
    const checkbox = document.getElementById('autoRefreshCheckbox');
    
    if (checkbox.checked) {
        startAutoRefresh();
        console.log('自動更新を有効にしました');
    } else {
        stopAutoRefresh();
        console.log('自動更新を無効にしました');
    }
}

function startAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    
    autoRefreshInterval = setInterval(() => {
        refreshSessionList();
    }, 30000); // 30秒間隔
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// ページ離脱時のクリーンアップに自動更新停止を追加
window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
    if (window.sseManager) {
        window.sseManager.removePageListeners('admin');
    }
});

// メモ編集機能
function editMemo(sessionId) {
    // 表示部分を隠し、編集フォームを表示
    const displayDiv = document.querySelector(`#memo-${sessionId}`).parentElement;
    const editDiv = document.getElementById(`edit-${sessionId}`);
    
    displayDiv.style.display = 'none';
    editDiv.style.display = 'block';
    
    // 入力フィールドにフォーカス
    const input = editDiv.querySelector('.memo-input');
    input.focus();
    input.select();
}

function cancelEditMemo(sessionId) {
    // 編集フォームを隠し、表示部分を元に戻す
    const displayDiv = document.querySelector(`#memo-${sessionId}`).parentElement;
    const editDiv = document.getElementById(`edit-${sessionId}`);
    
    editDiv.style.display = 'none';
    displayDiv.style.display = 'block';
    
    // 入力値を元に戻す
    const input = editDiv.querySelector('.memo-input');
    const originalMemo = document.getElementById(`memo-${sessionId}`).textContent;
    input.value = originalMemo === '（メモなし）' ? '' : originalMemo;
}

function saveMemo(sessionId) {
    const editDiv = document.getElementById(`edit-${sessionId}`);
    const input = editDiv.querySelector('.memo-input');
    const newMemo = input.value.trim();
    
    // 保存ボタンを無効化
    const saveBtn = editDiv.querySelector('.btn-success');
    const originalText = saveBtn.textContent;
    saveBtn.disabled = true;
    saveBtn.textContent = '保存中...';
    
    fetch('/admin/api/update-session-memo', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            session_id: sessionId,
            memo: newMemo
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // 表示を更新
            const memoText = document.getElementById(`memo-${sessionId}`);
            memoText.textContent = newMemo || '（メモなし）';
            
            // 編集モードを終了
            cancelEditMemo(sessionId);
            
            // 成功メッセージを表示
            showNotification('メモを更新しました', 'success');
        } else {
            alert(`エラー: ${data.error || data.message}`);
        }
    })
    .catch(error => {
        console.error('メモ更新エラー:', error);
        alert('メモの更新に失敗しました');
    })
    .finally(() => {
        // ボタンを元に戻す
        saveBtn.disabled = false;
        saveBtn.textContent = originalText;
    });
}

function viewSessionDetails(sessionId) {
    // セッション詳細ページへ遷移
    const detailUrl = `/admin/sessions/${sessionId}`;
    window.open(detailUrl, '_blank');
}

function showNotification(message, type = 'info') {
    // 一時的な通知を表示
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <span>${message}</span>
        <button class="notification-close" onclick="this.parentElement.remove()">×</button>
    `;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${type === 'success' ? '#d4edda' : '#f8d7da'};
        color: ${type === 'success' ? '#155724' : '#721c24'};
        padding: 10px 15px;
        border-radius: 4px;
        border: 1px solid ${type === 'success' ? '#c3e6cb' : '#f5c6cb'};
        z-index: 1000;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    `;
    
    document.body.appendChild(notification);
    
    // 5秒後に自動削除
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// 緊急停止機能
function emergencyStop() {
    // 第一段階の確認：基本的な確認ダイアログ
    if (!confirm('⚠️ 緊急停止を実行しますか？\n\n実行内容：\n✗ 全PDF公開を即座に停止\n✗ 全セッションを無効化\n\n全ユーザーは再度ログインが必要になります。')) {
        return;
    }
    
    // 第二段階の確認：誤操作防止のための詳細確認
    const confirmText = prompt('本当に緊急停止を実行する場合は、「緊急停止」と入力してください：');
    if (confirmText !== '緊急停止') {
        if (confirmText !== null) { // キャンセル以外の場合
            alert('入力が正しくありません。緊急停止はキャンセルされました。');
        }
        return;
    }
    
    // 実行中の視覚的フィードバック
    const originalBtn = document.querySelector('button[onclick="emergencyStop()"]');
    if (originalBtn) {
        originalBtn.disabled = true;
        originalBtn.innerHTML = '⏳ 緊急停止実行中...';
        originalBtn.style.opacity = '0.6';
    }
    
    // 画面全体にオーバーレイを表示
    const overlay = document.createElement('div');
    overlay.id = 'emergency-overlay';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(220, 53, 69, 0.8);
        color: white;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        z-index: 9999;
        font-size: 1.5rem;
        text-align: center;
    `;
    overlay.innerHTML = `
        <div>
            <div style="font-size: 3rem; margin-bottom: 1rem;">⚠️</div>
            <div>緊急停止実行中...</div>
            <div style="font-size: 1rem; margin-top: 1rem; opacity: 0.8;">
                全PDF公開停止 + 全セッション無効化
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    
    // 緊急停止API呼び出し
    fetch('/admin/emergency-stop', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        // オーバーレイを削除
        if (overlay.parentNode) {
            overlay.remove();
        }
        
        if (data.success) {
            // 成功時の詳細メッセージ
            const details = [
                `📄 公開停止PDF: ${data.unpublished_pdfs || 0}件`,
                `🔐 無効化セッション: ${data.deleted_sessions || 0}件`,
                `🔑 削除OTPトークン: ${data.deleted_otps || 0}件`
            ].join('\n');
            
            alert(`✅ 緊急停止が完了しました。\n\n${details}\n\n実行時刻: ${data.timestamp || '不明'}`);
            
            // SSE通知も表示
            showSSENotification('🚨 緊急停止が実行されました', 'warning');
            
            // 5秒後にページをリロード
            setTimeout(() => {
                location.reload();
            }, 5000);
        } else {
            alert(`❌ 緊急停止でエラーが発生しました:\n${data.message || data.error}`);
        }
    })
    .catch(error => {
        // オーバーレイを削除
        if (overlay.parentNode) {
            overlay.remove();
        }
        
        console.error('緊急停止エラー:', error);
        alert('❌ 緊急停止でネットワークエラーが発生しました。\n管理者に連絡してください。');
    })
    .finally(() => {
        // ボタンを元に戻す
        if (originalBtn) {
            originalBtn.disabled = false;
            originalBtn.innerHTML = '⚠️ 緊急停止';
            originalBtn.style.opacity = '1';
        }
    });
}

// PDF セキュリティ設定機能
function initializePdfSecuritySettings() {
    console.log('PDF セキュリティ設定機能を初期化中...');
    
    // 設定を読み込む
    loadPdfSecuritySettings();
    
    // 機能有効/無効の切り替え
    const enabledCheckbox = document.getElementById('pdfPreventionEnabled');
    if (enabledCheckbox) {
        enabledCheckbox.addEventListener('change', function() {
            const detailsSection = document.getElementById('pdfSettingsDetails');
            if (this.checked) {
                detailsSection.style.display = 'block';
            } else {
                detailsSection.style.display = 'none';
            }
            updatePdfPreventionStatus();
        });
    }
    
    // リアルタイム検証
    const domainsTextarea = document.getElementById('allowedReferrerDomains');
    if (domainsTextarea) {
        domainsTextarea.addEventListener('input', debounce(validatePdfSettings, 500));
    }
}

function loadPdfSecuritySettings() {
    console.log('PDF セキュリティ設定を読み込み中...');
    
    fetch('/admin/api/pdf-security-settings')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const settings = data.settings;
                
                // 各設定値をフォームに反映
                document.getElementById('pdfPreventionEnabled').checked = settings.enabled || false;
                
                // 許可ドメインの処理（文字列または配列に対応）
                let allowedDomains = settings.allowed_referrer_domains;
                if (typeof allowedDomains === 'string') {
                    allowedDomains = allowedDomains.split(',').map(d => d.trim()).filter(d => d);
                }
                document.getElementById('allowedReferrerDomains').value = 
                    Array.isArray(allowedDomains) ? allowedDomains.join(', ') : allowedDomains || '';
                
                // ブロックUA の処理（文字列または配列に対応）
                let blockedAgents = settings.blocked_user_agents;
                if (typeof blockedAgents === 'string') {
                    blockedAgents = blockedAgents.split(',').map(a => a.trim()).filter(a => a);
                }
                document.getElementById('blockedUserAgents').value = 
                    Array.isArray(blockedAgents) ? blockedAgents.join(', ') : blockedAgents || '';
                
                document.getElementById('pdfStrictMode').checked = settings.strict_mode || false;
                document.getElementById('pdfUserAgentCheckEnabled').checked = settings.user_agent_check_enabled !== false;
                document.getElementById('pdfLogBlockedAttempts').checked = settings.log_blocked_attempts !== false;
                
                // 現在の設定表示を更新
                updateCurrentSettingsDisplay(allowedDomains, blockedAgents);
                
                // 詳細セクションの表示/非表示
                const detailsSection = document.getElementById('pdfSettingsDetails');
                if (settings.enabled) {
                    detailsSection.style.display = 'block';
                } else {
                    detailsSection.style.display = 'none';
                }
                
                updatePdfPreventionStatus();
                showPdfMessage('設定を読み込みました', 'success');
            } else {
                showPdfMessage('設定の読み込みに失敗しました: ' + data.error, 'error');
            }
        })
        .catch(error => {
            console.error('PDF設定読み込みエラー:', error);
            showPdfMessage('設定の読み込み中にエラーが発生しました', 'error');
        });
}

function savePdfSecuritySettings() {
    console.log('PDF セキュリティ設定を保存中...');
    
    const settings = {
        enabled: document.getElementById('pdfPreventionEnabled').checked,
        allowed_referrer_domains: document.getElementById('allowedReferrerDomains').value,
        blocked_user_agents: document.getElementById('blockedUserAgents').value,
        strict_mode: document.getElementById('pdfStrictMode').checked,
        user_agent_check_enabled: document.getElementById('pdfUserAgentCheckEnabled').checked,
        log_blocked_attempts: document.getElementById('pdfLogBlockedAttempts').checked
    };
    
    fetch('/admin/api/pdf-security-settings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(settings)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showPdfMessage('設定を保存しました', 'success');
            updatePdfPreventionStatus();
            // 設定保存後に再読込して表示を更新
            loadPdfSecuritySettings();
        } else {
            let errorMsg = data.error;
            if (data.details && Array.isArray(data.details)) {
                errorMsg += '\n詳細: ' + data.details.join(', ');
            }
            showPdfMessage('設定の保存に失敗しました: ' + errorMsg, 'error');
        }
    })
    .catch(error => {
        console.error('PDF設定保存エラー:', error);
        showPdfMessage('設定の保存中にエラーが発生しました', 'error');
    });
}

function validatePdfSettings() {
    console.log('PDF設定を検証中...');
    
    const domains = document.getElementById('allowedReferrerDomains').value;
    
    fetch('/admin/api/pdf-security-validate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            allowed_referrer_domains: domains
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const validation = data.validation;
            const validationDiv = document.getElementById('domainValidation');
            
            if (validation.valid) {
                validationDiv.innerHTML = '<span style="color: green;">✅ 設定は有効です</span>';
                if (validation.warnings && validation.warnings.length > 0) {
                    validationDiv.innerHTML += '<br><span style="color: orange;">⚠️ 警告: ' + 
                        validation.warnings.join(', ') + '</span>';
                }
            } else {
                validationDiv.innerHTML = '<span style="color: red;">❌ エラー: ' + 
                    validation.errors.join(', ') + '</span>';
            }
        } else {
            showPdfMessage('検証中にエラーが発生しました: ' + data.error, 'error');
        }
    })
    .catch(error => {
        console.error('PDF設定検証エラー:', error);
        showPdfMessage('検証中にエラーが発生しました', 'error');
    });
}

function updatePdfPreventionStatus() {
    const enabled = document.getElementById('pdfPreventionEnabled').checked;
    const statusElement = document.getElementById('pdfPreventionStatus');
    
    if (enabled) {
        statusElement.textContent = '有効';
        statusElement.style.color = 'green';
        statusElement.style.fontWeight = 'bold';
    } else {
        statusElement.textContent = '無効';
        statusElement.style.color = 'red';
        statusElement.style.fontWeight = 'bold';
    }
}

function updateCurrentSettingsDisplay(allowedDomains, blockedAgents) {
    // 許可ドメインの表示
    const currentDomainsElement = document.getElementById('currentAllowedDomains');
    if (currentDomainsElement) {
        if (Array.isArray(allowedDomains) && allowedDomains.length > 0) {
            let displayHtml = '<ul class="setting-list">';
            allowedDomains.forEach(domain => {
                let type = getDomainType(domain);
                displayHtml += `<li><span class="domain-type">[${type}]</span> <code>${domain}</code></li>`;
            });
            displayHtml += '</ul>';
            currentDomainsElement.innerHTML = displayHtml;
        } else {
            currentDomainsElement.innerHTML = '<span class="no-setting">設定なし</span>';
        }
    }
    
    // ブロックUser-Agentの表示
    const currentAgentsElement = document.getElementById('currentBlockedAgents');
    if (currentAgentsElement) {
        if (Array.isArray(blockedAgents) && blockedAgents.length > 0) {
            let displayHtml = '<ul class="setting-list">';
            blockedAgents.forEach(agent => {
                displayHtml += `<li><code>${agent}</code></li>`;
            });
            displayHtml += '</ul>';
            currentAgentsElement.innerHTML = displayHtml;
        } else {
            currentAgentsElement.innerHTML = '<span class="no-setting">設定なし</span>';
        }
    }
}

function getDomainType(domain) {
    if (!domain) return '不明';
    
    // CIDR記法
    if (domain.includes('/')) {
        return 'CIDR';
    }
    
    // IP範囲
    if (domain.includes('-')) {
        return 'IP範囲';
    }
    
    // IPアドレスかチェック
    const ipPattern = /^(\d{1,3}\.){3}\d{1,3}$/;
    if (ipPattern.test(domain)) {
        return 'IP';
    }
    
    // サブドメイン許可
    if (domain.startsWith('.')) {
        return 'サブドメイン';
    }
    
    // 通常のドメイン
    return 'ドメイン';
}

function showPdfMessage(message, type) {
    const messageContainer = document.getElementById('pdfSettingsMessage');
    const className = type === 'success' ? 'message-success' : 'message-error';
    
    messageContainer.innerHTML = `<div class="${className}">${message}</div>`;
    
    // 3秒後に消去
    setTimeout(() => {
        messageContainer.innerHTML = '';
    }, 3000);
}

// デバウンス関数（入力中の連続実行を防ぐ）
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

