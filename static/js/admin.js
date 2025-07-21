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
        'pdf_unpublished': handlePDFUnpublished
    });
    
    console.log('管理画面: SSE接続とリスナーを初期化しました');
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
                passphraseCharCounter.classList.add('');
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

