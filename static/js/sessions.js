// セッション一覧ページ用JavaScript
let autoRefreshInterval = null;
let allSessions = []; // 全セッションデータ
let filteredSessions = []; // フィルタ後のセッションデータ
let currentSort = { column: 'start_time', direction: 'desc' }; // デフォルトソート

document.addEventListener('DOMContentLoaded', function() {
    console.log('セッション一覧ページを初期化中...');
    
    // 初期化
    initializeSessionsPage();
    
    // フィルターイベントリスナーを設定
    setupFilterListeners();
    
    // ソートイベントリスナーを設定
    setupSortListeners();
    
    // 初回データ取得
    refreshSessionList();
    
    // 自動更新を開始
    startAutoRefresh();
});

function initializeSessionsPage() {
    console.log('セッション一覧ページの初期化完了');
}

function setupFilterListeners() {
    // 全フィルター要素にイベントリスナーを追加
    const filterInputs = [
        'filterSid', 'filterEmail', 'filterMemo', 'filterDate'
    ];
    
    filterInputs.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('input', applyFilters);
        }
    });
    
    // デバイスフィルター（select）
    const deviceFilter = document.getElementById('filterDevice');
    if (deviceFilter) {
        deviceFilter.addEventListener('change', applyFilters);
    }
}

function setupSortListeners() {
    // ソート可能なヘッダーにクリックイベントを追加
    const sortableHeaders = document.querySelectorAll('.sortable');
    sortableHeaders.forEach(header => {
        header.addEventListener('click', function() {
            const column = this.getAttribute('data-sort');
            toggleSort(column);
        });
        
        // カーソルをポインターに変更
        header.style.cursor = 'pointer';
    });
}

function toggleSort(column) {
    // 同じカラムの場合は方向を反転、異なるカラムの場合は降順から開始
    if (currentSort.column === column) {
        currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        currentSort.column = column;
        currentSort.direction = 'desc';
    }
    
    // ソートインジケーターを更新
    updateSortIndicators();
    
    // データをソートして表示更新
    applySorting();
    updateSessionTable(filteredSessions);
}

function updateSortIndicators() {
    // 全てのソートインジケーターをリセット
    const indicators = document.querySelectorAll('.sort-indicator');
    indicators.forEach(indicator => {
        indicator.textContent = '';
        indicator.parentElement.classList.remove('sort-asc', 'sort-desc');
    });
    
    // 現在のソートカラムにインジケーターを設定
    const currentHeader = document.querySelector(`[data-sort="${currentSort.column}"]`);
    if (currentHeader) {
        const indicator = currentHeader.querySelector('.sort-indicator');
        if (indicator) {
            indicator.textContent = currentSort.direction === 'asc' ? ' ↑' : ' ↓';
            currentHeader.classList.add(`sort-${currentSort.direction}`);
        }
    }
}

function applySorting() {
    filteredSessions.sort((a, b) => {
        let aValue = a[currentSort.column];
        let bValue = b[currentSort.column];
        
        // 特別な処理が必要なカラム
        if (currentSort.column === 'start_time') {
            aValue = new Date(aValue);
            bValue = new Date(bValue);
        } else if (currentSort.column === 'elapsed_hours') {
            aValue = parseFloat(aValue);
            bValue = parseFloat(bValue);
        } else if (typeof aValue === 'string') {
            aValue = aValue.toLowerCase();
            bValue = bValue.toLowerCase();
        }
        
        let comparison = 0;
        if (aValue < bValue) {
            comparison = -1;
        } else if (aValue > bValue) {
            comparison = 1;
        }
        
        return currentSort.direction === 'asc' ? comparison : -comparison;
    });
}

function applyFilters() {
    const filters = {
        sid: document.getElementById('filterSid').value.toLowerCase(),
        email: document.getElementById('filterEmail').value.toLowerCase(),
        device: document.getElementById('filterDevice').value,
        memo: document.getElementById('filterMemo').value.toLowerCase(),
        date: document.getElementById('filterDate').value
    };
    
    filteredSessions = allSessions.filter(session => {
        // SIDフィルター
        if (filters.sid && !session.session_id.toLowerCase().includes(filters.sid)) {
            return false;
        }
        
        // メールアドレスフィルター
        if (filters.email && !session.email_address.toLowerCase().includes(filters.email)) {
            return false;
        }
        
        // デバイスフィルター
        if (filters.device && session.device_type !== filters.device) {
            return false;
        }
        
        // メモフィルター
        if (filters.memo && !session.memo.toLowerCase().includes(filters.memo)) {
            return false;
        }
        
        // 日付フィルター
        if (filters.date) {
            const sessionDate = session.start_time.split(' ')[0]; // 'YYYY-MM-DD HH:MM:SS' から日付部分を取得
            if (sessionDate !== filters.date) {
                return false;
            }
        }
        
        return true;
    });
    
    // ソートを適用
    applySorting();
    
    // テーブルを更新
    updateSessionTable(filteredSessions);
    
    // 統計を更新
    updateSessionStats(filteredSessions);
}

function clearFilters() {
    // 全フィルターをクリア
    document.getElementById('filterSid').value = '';
    document.getElementById('filterEmail').value = '';
    document.getElementById('filterDevice').value = '';
    document.getElementById('filterMemo').value = '';
    document.getElementById('filterDate').value = '';
    
    // フィルターを再適用
    applyFilters();
}

function refreshSessionList() {
    fetch('/admin/api/active-sessions')
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showSessionError(data.error);
            return;
        }
        
        // 全データを保存
        allSessions = data.sessions;
        
        // フィルターとソートを適用
        applyFilters();
        
        // 最終更新時刻を表示
        updateLastUpdateTime();
        
        console.log(`セッション情報を更新: ${data.total_count}件`);
    })
    .catch(error => {
        console.error('セッション情報取得エラー:', error);
        showSessionError('セッション情報の取得に失敗しました');
    });
}

function updateSessionStats(sessions) {
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
    
    // 統計表示を更新
    document.getElementById('totalSessions').textContent = sessions.length;
    document.getElementById('mobileCount').textContent = mobileCount;
    document.getElementById('tabletCount').textContent = tabletCount;
    document.getElementById('desktopCount').textContent = desktopCount;
}

function truncateMemo(memo) {
    if (!memo || memo === '（メモなし）') {
        return memo;
    }
    
    const maxLength = 50; // 表示する最大文字数
    if (memo.length <= maxLength) {
        return memo;
    }
    
    return memo.substring(0, maxLength) + '...';
}

function updateSessionTable(sessions) {
    const tbody = document.getElementById('sessionsTableBody');
    
    if (!tbody) {
        console.error('セッションテーブルが見つかりません');
        return;
    }
    
    if (sessions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="no-sessions-row">該当するセッションがありません</td></tr>';
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
                    <span class="sid-display">${session.session_id.substring(0, 16)}...</span>
                </td>
                <td class="email-address" title="${session.email_address}">
                    ${session.email_address}
                </td>
                <td class="device-type" title="${session.device_type}">
                    <span class="device-icon">${deviceInfo.icon}</span>
                    <span class="device-label">${deviceInfo.label}</span>
                </td>
                <td class="start-time">${session.start_time}</td>
                <td class="remaining-time ${isExpiring ? 'text-warning' : ''}">
                    ${session.remaining_time}
                </td>
                <td class="elapsed-time">${session.elapsed_hours}時間</td>
                <td class="memo-cell">
                    <div class="memo-display" onclick="editMemo('${session.session_id}')">
                        <span class="memo-text" id="memo-${session.session_id}">${truncateMemo(session.memo || '（メモなし）')}</span>
                        <span class="memo-edit-icon">✏️</span>
                    </div>
                    <div class="memo-edit-form" id="edit-${session.session_id}" style="display: none;">
                        <textarea class="memo-input" maxlength="500" rows="3">${session.memo || ''}</textarea>
                        <div class="memo-actions">
                            <button class="btn btn-sm btn-success" onclick="saveMemo('${session.session_id}')">保存</button>
                            <button class="btn btn-sm btn-secondary" onclick="cancelEditMemo('${session.session_id}')">キャンセル</button>
                        </div>
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
    const tbody = document.getElementById('sessionsTableBody');
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="8" class="error-row">エラー: ${message}</td></tr>`;
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

function updateLastUpdateTime() {
    const now = new Date();
    const timeString = now.toLocaleTimeString('ja-JP');
    document.getElementById('lastUpdateTime').textContent = timeString;
}

// 自動更新機能
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

// メモ編集機能（admin.jsから移植）
function editMemo(sessionId) {
    const displayDiv = document.querySelector(`#memo-${sessionId}`).parentElement;
    const editDiv = document.getElementById(`edit-${sessionId}`);
    
    displayDiv.style.display = 'none';
    editDiv.style.display = 'block';
    
    const input = editDiv.querySelector('.memo-input');
    input.focus();
    input.select();
}

function cancelEditMemo(sessionId) {
    const displayDiv = document.querySelector(`#memo-${sessionId}`).parentElement;
    const editDiv = document.getElementById(`edit-${sessionId}`);
    
    editDiv.style.display = 'none';
    displayDiv.style.display = 'block';
    
    const input = editDiv.querySelector('.memo-input');
    const originalMemo = document.getElementById(`memo-${sessionId}`).textContent;
    input.value = originalMemo === '（メモなし）' ? '' : originalMemo;
}

function saveMemo(sessionId) {
    const editDiv = document.getElementById(`edit-${sessionId}`);
    const input = editDiv.querySelector('.memo-input');
    const newMemo = input.value.trim();
    
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
            // 表示を更新（切り詰め版）
            const memoText = document.getElementById(`memo-${sessionId}`);
            memoText.textContent = truncateMemo(newMemo || '（メモなし）');
            
            // ローカルデータも更新
            const sessionIndex = allSessions.findIndex(s => s.session_id === sessionId);
            if (sessionIndex !== -1) {
                allSessions[sessionIndex].memo = newMemo;
            }
            
            // 編集モードを終了
            cancelEditMemo(sessionId);
            
            // フィルターを再適用（メモで検索している場合のため）
            applyFilters();
            
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
        saveBtn.disabled = false;
        saveBtn.textContent = originalText;
    });
}

function viewSessionDetails(sessionId) {
    // 専用URLで新しいタブを開く
    const detailUrl = `/admin/sessions/${sessionId}`;
    window.open(detailUrl, '_blank');
}

function viewSessionDetailsOld(sessionId) {
    // 該当セッションのデータを取得
    const session = allSessions.find(s => s.session_id === sessionId);
    if (!session) {
        alert('セッション情報が見つかりません');
        return;
    }
    
    // デバイス情報を取得
    const deviceInfo = getDeviceInfo(session.device_type);
    
    // 詳細情報のHTMLを作成（旧版：使用しない）
    const detailsHtml = `
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>セッション詳細 - ${session.session_id.substring(0, 16)}...</title>
    <style>
        body {
            font-family: 'Helvetica Neue', Helvetica, Arial, 'Hiragino Kaku Gothic ProN', 'ヒラギノ角ゴ ProN W3', Meiryo, メイリオ, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 2rem;
            background: #f8f9fa;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            margin-top: 0;
            border-bottom: 2px solid #e1e5e9;
            padding-bottom: 1rem;
        }
        .detail-item {
            margin-bottom: 1.5rem;
            padding: 1rem;
            background: #f8f9fa;
            border-radius: 6px;
            border-left: 4px solid #3498db;
        }
        .detail-label {
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 0.5rem;
        }
        .detail-value {
            color: #555;
        }
        .session-id {
            font-family: 'Courier New', monospace;
            background: #e9ecef;
            padding: 4px 8px;
            border-radius: 4px;
            word-break: break-all;
        }
        .memo-area {
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 1rem;
            min-height: 100px;
            white-space: pre-wrap;
            font-family: inherit;
            max-height: 300px;
            overflow-y: auto;
        }
        .device-info {
            font-size: 1.1rem;
        }
        .back-button {
            background: #6c757d;
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1rem;
            margin-top: 2rem;
        }
        .back-button:hover {
            background: #5a6268;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 セッション詳細情報</h1>
        
        <div class="detail-item">
            <div class="detail-label">📋 セッションID</div>
            <div class="detail-value session-id">${session.session_id}</div>
        </div>
        
        <div class="detail-item">
            <div class="detail-label">📧 メールアドレス</div>
            <div class="detail-value">${session.email_address}</div>
        </div>
        
        <div class="detail-item">
            <div class="detail-label">📱 デバイス</div>
            <div class="detail-value device-info">${deviceInfo.icon} ${deviceInfo.label}</div>
        </div>
        
        <div class="detail-item">
            <div class="detail-label">⏰ 開始時刻</div>
            <div class="detail-value">${session.start_time}</div>
        </div>
        
        <div class="detail-item">
            <div class="detail-label">⏳ 残り時間</div>
            <div class="detail-value">${session.remaining_time}</div>
        </div>
        
        <div class="detail-item">
            <div class="detail-label">⌛ 経過時間</div>
            <div class="detail-value">${session.elapsed_hours}時間</div>
        </div>
        
        <div class="detail-item">
            <div class="detail-label">📝 管理者メモ</div>
            <div class="detail-value">
                <div class="memo-area" id="detail-memo-display-${session.session_id}" onclick="editDetailMemo('${session.session_id}')" style="cursor: pointer; position: relative;">
                    ${session.memo || '（メモなし）'}
                    <span style="position: absolute; top: 0.5rem; right: 0.5rem; opacity: 0.7; font-size: 0.8rem;">✏️</span>
                </div>
                <div id="detail-memo-edit-${session.session_id}" style="display: none;">
                    <textarea id="detail-memo-input-${session.session_id}" style="width: 100%; min-height: 100px; padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; resize: vertical;" maxlength="500">${session.memo || ''}</textarea>
                    <div style="margin-top: 0.5rem; text-align: right;">
                        <button onclick="saveDetailMemo('${session.session_id}')" style="background: #28a745; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; margin-right: 0.5rem; cursor: pointer;">保存</button>
                        <button onclick="cancelDetailMemo('${session.session_id}')" style="background: #6c757d; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">キャンセル</button>
                    </div>
                </div>
            </div>
        </div>
        
        <button class="back-button" onclick="window.close()">
            ← このタブを閉じる
        </button>
    </div>
    
    <script>
        // 詳細ページでのメモ編集機能
        function editDetailMemo(sessionId) {
            document.getElementById('detail-memo-display-' + sessionId).style.display = 'none';
            document.getElementById('detail-memo-edit-' + sessionId).style.display = 'block';
            document.getElementById('detail-memo-input-' + sessionId).focus();
        }
        
        function cancelDetailMemo(sessionId) {
            document.getElementById('detail-memo-display-' + sessionId).style.display = 'block';
            document.getElementById('detail-memo-edit-' + sessionId).style.display = 'none';
        }
        
        function saveDetailMemo(sessionId) {
            const textarea = document.getElementById('detail-memo-input-' + sessionId);
            const newMemo = textarea.value.trim();
            
            // APIに保存リクエスト送信
            fetch(window.opener ? '/admin/api/update-session-memo' : '/admin/api/update-session-memo', {
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
                    const displayDiv = document.getElementById('detail-memo-display-' + sessionId);
                    displayDiv.innerHTML = newMemo || '（メモなし）' + '<span style="position: absolute; top: 0.5rem; right: 0.5rem; opacity: 0.7; font-size: 0.8rem;">✏️</span>';
                    
                    // 編集モードを終了
                    cancelDetailMemo(sessionId);
                    
                    // 親ウィンドウのデータも更新（存在する場合）
                    if (window.opener && window.opener.refreshSessionList) {
                        window.opener.refreshSessionList();
                    }
                    
                    alert('メモを更新しました');
                } else {
                    alert('エラー: ' + (data.error || data.message));
                }
            })
            .catch(error => {
                console.error('メモ更新エラー:', error);
                alert('メモの更新に失敗しました');
            });
        }
    </script>
</body>
</html>
    `;
    
    // 新しいタブで詳細を表示
    const newWindow = window.open('', '_blank');
    newWindow.document.write(detailsHtml);
    newWindow.document.close();
}

function showNotification(message, type = 'info') {
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
    
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// ページ離脱時のクリーンアップ
window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
});