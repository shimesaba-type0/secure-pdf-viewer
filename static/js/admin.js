// PDF Upload functionality
document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('pdfFile');
    const uploadArea = document.getElementById('uploadArea');
    const uploadInfo = document.getElementById('uploadInfo');
    const uploadBtn = document.getElementById('uploadBtn');
    const clearBtn = document.getElementById('clearBtn');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    
    // SSE接続を初期化
    initializeSSE();

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

function initializeSSE() {
    // Server-Sent Events接続を初期化（管理画面用）
    try {
        const eventSource = new EventSource('/api/events');
        
        eventSource.onopen = () => {
            console.log('管理画面: SSE接続が確立されました');
        };
        
        eventSource.addEventListener('pdf_unpublished', (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('管理画面: PDF公開停止:', data.message);
                
                // 公開状況を更新するため5秒後にページをリロード
                setTimeout(() => {
                    window.location.reload();
                }, 5000);
                
                // 即座にフィードバックメッセージを表示
                showSSENotification('📄 ' + data.message, 'info');
                
            } catch (e) {
                console.warn('PDF停止イベントの処理に失敗:', e);
            }
        });
        
        eventSource.addEventListener('pdf_published', (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('管理画面: PDF公開開始:', data.message);
                
                // 公開状況を更新するため3秒後にページをリロード
                setTimeout(() => {
                    window.location.reload();
                }, 3000);
                
                // 即座にフィードバックメッセージを表示
                showSSENotification('📄 ' + data.message, 'success');
                
            } catch (e) {
                console.warn('PDF公開イベントの処理に失敗:', e);
            }
        });
        
        eventSource.onerror = (error) => {
            console.warn('管理画面: SSE接続エラー:', error);
        };
        
    } catch (e) {
        console.warn('管理画面: SSE初期化に失敗:', e);
    }
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