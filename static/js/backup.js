/**
 * バックアップ機能フロントエンド処理
 * TASK-018 Phase 1C: UI実装
 * 
 * 機能:
 * - バックアップ実行とSSE進行状況表示
 * - バックアップ一覧の取得と表示
 * - ダウンロード・削除機能
 * - 統計情報表示
 */

class BackupManager {
    constructor() {
        this.eventSource = null;
        this.isBackupRunning = false;
        this.backupData = [];
        
        // DOM要素キャッシュ
        this.elements = {
            createBtn: document.getElementById('create-backup-btn'),
            progressArea: document.getElementById('backup-progress'),
            progressFill: document.getElementById('progress-fill'),
            progressText: document.getElementById('progress-text'),
            progressPercentage: document.getElementById('progress-percentage'),
            backupListBody: document.getElementById('backup-list-body'),
            totalBackups: document.getElementById('total-backups'),
            totalSize: document.getElementById('total-size'),
            latestBackup: document.getElementById('latest-backup')
        };
        
        this.init();
    }
    
    init() {
        // DOM読み込み完了後の初期化
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                this.setupEventListeners();
                this.loadBackupList();
            });
        } else {
            this.setupEventListeners();
            this.loadBackupList();
        }
    }
    
    setupEventListeners() {
        // バックアップ実行ボタン
        if (this.elements.createBtn) {
            this.elements.createBtn.addEventListener('click', () => {
                this.createBackup();
            });
        }
        
        // ページ離脱時のSSE接続クリーンアップ
        window.addEventListener('beforeunload', () => {
            this.disconnectSSE();
        });
    }
    
    /**
     * バックアップ実行
     */
    async createBackup() {
        if (this.isBackupRunning) {
            console.log('バックアップが既に実行中です');
            return;
        }
        
        try {
            console.log('バックアップ実行開始');
            this.showProgress();
            this.setBackupRunning(true);
            
            const response = await fetch('/admin/backup/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin'
            });
            
            const result = await response.json();
            console.log('API レスポンス:', result);
            
            if (result.status === 'success' || result.status === 'in_progress') {
                this.updateProgressText('バックアップ実行を開始しました');
                this.connectSSE();
            } else if (result.status === 'error') {
                throw new Error(result.message || 'バックアップの開始に失敗しました');
            } else {
                // 不明なステータスの場合はSSE接続を開始
                console.log('不明なステータスですが、SSE接続を開始します:', result.status);
                this.updateProgressText('バックアップ実行を開始しました');
                this.connectSSE();
            }
            
        } catch (error) {
            console.error('バックアップ実行エラー:', error);
            this.showError('バックアップの実行に失敗しました: ' + error.message);
            this.hideProgress();
            this.setBackupRunning(false);
        }
    }
    
    /**
     * Server-Sent Events接続
     */
    connectSSE() {
        console.log('SSE接続開始');
        
        this.eventSource = new EventSource('/admin/backup/status');
        
        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleSSEMessage(data);
            } catch (error) {
                console.error('SSEメッセージ解析エラー:', error);
            }
        };
        
        this.eventSource.onerror = (error) => {
            console.error('SSE接続エラー:', error);
            this.disconnectSSE();
            
            if (this.isBackupRunning) {
                // 接続が切れた場合、ポーリングで状況確認
                setTimeout(() => {
                    this.checkBackupStatus();
                }, 2000);
            }
        };
    }
    
    /**
     * SSE接続切断
     */
    disconnectSSE() {
        if (this.eventSource) {
            console.log('SSE接続切断');
            this.eventSource.close();
            this.eventSource = null;
        }
    }
    
    /**
     * SSEメッセージ処理
     */
    handleSSEMessage(data) {
        console.log('SSEメッセージ受信:', data);
        
        switch (data.status) {
            case 'in_progress':
                this.updateProgress(data.progress || 0, data.message || '処理中...');
                break;
                
            case 'completed':
                this.updateProgress(100, 'バックアップが完了しました');
                setTimeout(() => {
                    this.hideProgress();
                    this.setBackupRunning(false);
                    this.loadBackupList(); // 一覧を更新
                    this.showSuccess('バックアップが正常に完了しました');
                }, 2000);
                this.disconnectSSE();
                break;
                
            case 'error':
                this.showError('バックアップエラー: ' + (data.message || '不明なエラー'));
                this.hideProgress();
                this.setBackupRunning(false);
                this.disconnectSSE();
                break;
                
            default:
                console.log('未知のSSEメッセージ:', data);
        }
    }
    
    /**
     * バックアップ状況をポーリングで確認
     */
    async checkBackupStatus() {
        try {
            const response = await fetch('/admin/backup/status');
            
            if (response.headers.get('content-type')?.includes('application/json')) {
                const data = await response.json();
                this.handleSSEMessage(data);
            }
            
        } catch (error) {
            console.error('バックアップ状況確認エラー:', error);
            this.hideProgress();
            this.setBackupRunning(false);
        }
    }
    
    /**
     * バックアップ一覧読み込み
     */
    async loadBackupList() {
        try {
            console.log('バックアップ一覧読み込み開始');
            
            const response = await fetch('/admin/backup/list', {
                credentials: 'same-origin'
            });
            
            const result = await response.json();
            
            if (result.status === 'success') {
                this.backupData = result.data || [];
                this.renderBackupList();
                this.updateStats();
            } else {
                throw new Error(result.message || '一覧の取得に失敗しました');
            }
            
        } catch (error) {
            console.error('バックアップ一覧読み込みエラー:', error);
            this.renderBackupListError('バックアップ一覧の読み込みに失敗しました: ' + error.message);
        }
    }
    
    /**
     * バックアップ一覧レンダリング
     */
    renderBackupList() {
        if (!this.elements.backupListBody) return;
        
        if (this.backupData.length === 0) {
            this.elements.backupListBody.innerHTML = `
                <tr>
                    <td colspan="6" class="no-data">バックアップファイルはありません</td>
                </tr>
            `;
            return;
        }
        
        const rows = this.backupData.map(backup => {
            console.log('バックアップデータ:', backup);  // デバッグログ追加
            const createdAt = new Date(backup.created_at).toLocaleString('ja-JP');
            const size = this.formatFileSize(backup.size || 0);
            const fileCount = backup.file_count || '-';
            const status = backup.status || 'completed';
            
            let statusBadge = '';
            switch (status) {
                case 'completed':
                    statusBadge = '<span class="status-badge status-success">完了</span>';
                    break;
                case 'in_progress':
                    statusBadge = '<span class="status-badge status-warning">進行中</span>';
                    break;
                case 'error':
                    statusBadge = '<span class="status-badge status-error">エラー</span>';
                    break;
                default:
                    statusBadge = '<span class="status-badge status-unknown">不明</span>';
            }
            
            return `
                <tr>
                    <td>${createdAt}</td>
                    <td>手動</td>
                    <td>${size}</td>
                    <td>${fileCount}</td>
                    <td>${statusBadge}</td>
                    <td class="action-buttons">
                        ${status === 'completed' ? `
                            <button class="btn btn-sm btn-info download-link" onclick="window.backupManager.downloadBackup('${backup.backup_name || backup.name}')">
                                💾 ダウンロード
                            </button>
                            <button class="btn btn-sm btn-danger delete-backup-btn" onclick="window.backupManager.deleteBackup('${backup.backup_name || backup.name}')">
                                🗑️ 削除
                            </button>
                        ` : '-'}
                    </td>
                </tr>
            `;
        }).join('');
        
        this.elements.backupListBody.innerHTML = rows;
        console.log(`バックアップ一覧を表示: ${this.backupData.length}件`);
    }
    
    /**
     * バックアップ一覧エラー表示
     */
    renderBackupListError(message) {
        if (!this.elements.backupListBody) return;
        
        this.elements.backupListBody.innerHTML = `
            <tr>
                <td colspan="6" class="error-row">${message}</td>
            </tr>
        `;
    }
    
    /**
     * 統計情報更新
     */
    updateStats() {
        const completedBackups = this.backupData.filter(b => b.status === 'completed');
        const totalSize = completedBackups.reduce((sum, b) => sum + (b.size || 0), 0);
        const latestBackup = completedBackups.length > 0 ? 
            new Date(completedBackups[0].created_at).toLocaleString('ja-JP') : 'なし';
        
        if (this.elements.totalBackups) {
            this.elements.totalBackups.textContent = completedBackups.length;
        }
        if (this.elements.totalSize) {
            this.elements.totalSize.textContent = this.formatFileSize(totalSize);
        }
        if (this.elements.latestBackup) {
            this.elements.latestBackup.textContent = latestBackup;
        }
    }
    
    /**
     * バックアップダウンロード
     */
    async downloadBackup(backupName) {
        try {
            console.log(`バックアップダウンロード開始: ${backupName}`);
            
            const url = `/admin/backup/download/${encodeURIComponent(backupName)}`;
            const link = document.createElement('a');
            link.href = url;
            link.download = `${backupName}.tar.gz`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            this.showSuccess(`バックアップファイル "${backupName}" のダウンロードを開始しました`);
            
        } catch (error) {
            console.error('バックアップダウンロードエラー:', error);
            this.showError('ダウンロードに失敗しました: ' + error.message);
        }
    }
    
    /**
     * バックアップ削除
     */
    async deleteBackup(backupName) {
        if (!confirm(`バックアップ "${backupName}" を削除してもよろしいですか？\n\nこの操作は元に戻せません。`)) {
            return;
        }
        
        try {
            console.log(`バックアップ削除開始: ${backupName}`);
            
            const response = await fetch(`/admin/backup/delete/${encodeURIComponent(backupName)}`, {
                method: 'DELETE',
                credentials: 'same-origin'
            });
            
            const result = await response.json();
            
            if (result.status === 'success') {
                this.showSuccess(`バックアップ "${backupName}" を削除しました`);
                this.loadBackupList(); // 一覧を更新
            } else {
                throw new Error(result.message || '削除に失敗しました');
            }
            
        } catch (error) {
            console.error('バックアップ削除エラー:', error);
            this.showError('削除に失敗しました: ' + error.message);
        }
    }
    
    /**
     * 進行状況表示
     */
    showProgress() {
        if (this.elements.progressArea) {
            this.elements.progressArea.classList.remove('hidden');
        }
        this.updateProgress(0, '準備中...');
    }
    
    /**
     * 進行状況非表示
     */
    hideProgress() {
        if (this.elements.progressArea) {
            this.elements.progressArea.classList.add('hidden');
        }
    }
    
    /**
     * 進行状況更新
     */
    updateProgress(percentage, message) {
        if (this.elements.progressFill) {
            this.elements.progressFill.style.width = `${percentage}%`;
        }
        if (this.elements.progressText) {
            this.elements.progressText.textContent = message;
        }
        if (this.elements.progressPercentage) {
            this.elements.progressPercentage.textContent = `${Math.round(percentage)}%`;
        }
    }
    
    /**
     * 進行状況テキスト更新
     */
    updateProgressText(message) {
        if (this.elements.progressText) {
            this.elements.progressText.textContent = message;
        }
    }
    
    /**
     * バックアップ実行状態設定
     */
    setBackupRunning(isRunning) {
        this.isBackupRunning = isRunning;
        
        if (this.elements.createBtn) {
            this.elements.createBtn.disabled = isRunning;
            this.elements.createBtn.textContent = isRunning ? '⏳ バックアップ実行中...' : '💾 バックアップ実行';
        }
    }
    
    /**
     * ファイルサイズフォーマット
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    /**
     * 成功メッセージ表示
     */
    showSuccess(message) {
        console.log('成功:', message);
        // 既存の通知システムがあれば連携
        if (typeof showNotification === 'function') {
            showNotification(message, 'success');
        } else {
            alert(`✅ ${message}`);
        }
    }
    
    /**
     * エラーメッセージ表示
     */
    showError(message) {
        console.error('エラー:', message);
        // 既存の通知システムがあれば連携
        if (typeof showNotification === 'function') {
            showNotification(message, 'error');
        } else {
            alert(`❌ ${message}`);
        }
    }
}

// グローバル関数（テンプレートから呼び出し用）
function loadBackupList() {
    if (window.backupManager) {
        window.backupManager.loadBackupList();
    }
}

function createBackup() {
    if (window.backupManager) {
        window.backupManager.createBackup();
    }
}

function downloadBackup(backupName) {
    if (window.backupManager) {
        window.backupManager.downloadBackup(backupName);
    }
}

function deleteBackup(backupName) {
    if (window.backupManager) {
        window.backupManager.deleteBackup(backupName);
    }
}

// ===== Phase 2: 定期バックアップ設定管理クラス =====

/**
 * バックアップ設定管理クラス
 */
class BackupSettingsManager {
    constructor() {
        this.baseUrl = '/admin/backup/settings';
        this.statsUrl = '/admin/backup/statistics';
        this.cleanupUrl = '/admin/backup/cleanup';
        this.scheduleUrl = '/admin/backup/check-schedule';
    }

    /**
     * 初期化 - イベントリスナー設定
     */
    init() {
        this.attachEventListeners();
        this.loadSettings();
        this.loadStatistics();
    }

    /**
     * イベントリスナー設定
     */
    attachEventListeners() {
        // 設定保存ボタン
        const saveBtn = document.getElementById('save-backup-settings');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveSettings());
        }

        // 設定読み込みボタン
        const loadBtn = document.getElementById('load-backup-settings');
        if (loadBtn) {
            loadBtn.addEventListener('click', () => this.loadSettings());
        }

        // クリーンアップボタン
        const cleanupBtn = document.getElementById('cleanup-backups');
        if (cleanupBtn) {
            cleanupBtn.addEventListener('click', () => this.cleanupBackups());
        }

        // 自動バックアップ有効/無効の切り替え
        const autoEnabledCheckbox = document.getElementById('auto-backup-enabled');
        if (autoEnabledCheckbox) {
            autoEnabledCheckbox.addEventListener('change', (e) => {
                this.updateAutoBackupStatus(e.target.checked);
            });
        }
    }

    /**
     * バックアップ設定読み込み
     */
    async loadSettings() {
        try {
            const response = await fetch(this.baseUrl, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            
            if (result.status === 'success') {
                this.populateSettingsForm(result.data);
                console.log('バックアップ設定読み込み完了');
            } else {
                throw new Error(result.message || '設定読み込みに失敗しました');
            }

        } catch (error) {
            console.error('設定読み込みエラー:', error);
            this.showError(`設定読み込みエラー: ${error.message}`);
        }
    }

    /**
     * バックアップ設定保存
     */
    async saveSettings() {
        try {
            const settings = this.collectSettingsFromForm();
            
            const response = await fetch(this.baseUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(settings)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            
            if (result.status === 'success') {
                this.showSuccess('バックアップ設定が保存されました');
                this.loadStatistics(); // 統計情報更新
            } else {
                throw new Error(result.message || '設定保存に失敗しました');
            }

        } catch (error) {
            console.error('設定保存エラー:', error);
            this.showError(`設定保存エラー: ${error.message}`);
        }
    }

    /**
     * フォームから設定値を収集
     */
    collectSettingsFromForm() {
        return {
            auto_backup_enabled: document.getElementById('auto-backup-enabled')?.checked || false,
            backup_interval: document.getElementById('backup-interval')?.value || 'daily',
            backup_time: document.getElementById('backup-time')?.value || '02:00',
            retention_days: parseInt(document.getElementById('retention-days')?.value) || 30,
            max_backup_size: parseInt(document.getElementById('max-backup-size')?.value) || 1024
        };
    }

    /**
     * 設定値をフォームに反映
     */
    populateSettingsForm(settings) {
        // 自動バックアップ有効/無効
        const autoEnabledCheckbox = document.getElementById('auto-backup-enabled');
        if (autoEnabledCheckbox) {
            autoEnabledCheckbox.checked = settings.auto_backup_enabled || false;
        }

        // バックアップ間隔
        const intervalSelect = document.getElementById('backup-interval');
        if (intervalSelect) {
            intervalSelect.value = settings.backup_interval || 'daily';
        }

        // 実行時刻
        const timeInput = document.getElementById('backup-time');
        if (timeInput) {
            timeInput.value = settings.backup_time || '02:00';
        }

        // 保持日数
        const retentionInput = document.getElementById('retention-days');
        if (retentionInput) {
            retentionInput.value = settings.retention_days || 30;
        }

        // 最大バックアップサイズ
        const maxSizeInput = document.getElementById('max-backup-size');
        if (maxSizeInput) {
            maxSizeInput.value = settings.max_backup_size || 1024;
        }

        // 統計情報更新
        this.updateAutoBackupStatus(settings.auto_backup_enabled || false);
    }

    /**
     * バックアップ統計情報読み込み
     */
    async loadStatistics() {
        try {
            const response = await fetch(this.statsUrl, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            
            if (result.status === 'success') {
                this.updateStatisticsDisplay(result.data);
            } else {
                throw new Error(result.message || '統計情報取得に失敗しました');
            }

        } catch (error) {
            console.error('統計情報読み込みエラー:', error);
            // 統計情報のエラーは表示しない（ユーザビリティ向上）
        }
    }

    /**
     * 統計情報表示更新
     */
    updateStatisticsDisplay(stats) {
        // 自動バックアップ数
        const autoCountElement = document.getElementById('auto-backup-count');
        if (autoCountElement) {
            autoCountElement.textContent = stats.auto_backups || 0;
        }

        // 手動バックアップ数
        const manualCountElement = document.getElementById('manual-backup-count');
        if (manualCountElement) {
            manualCountElement.textContent = stats.manual_backups || 0;
        }

        // 次回自動バックアップ時刻
        const nextBackupElement = document.getElementById('next-backup-time');
        if (nextBackupElement) {
            if (stats.next_auto_backup) {
                const nextDate = new Date(stats.next_auto_backup);
                nextBackupElement.textContent = this.formatDateTime(nextDate);
            } else {
                nextBackupElement.textContent = '-';
            }
        }
    }

    /**
     * 自動バックアップステータス更新
     */
    updateAutoBackupStatus(enabled) {
        const statusElement = document.getElementById('auto-backup-status');
        if (statusElement) {
            statusElement.textContent = enabled ? '有効' : '無効';
            statusElement.style.color = enabled ? '#28a745' : '#6c757d';
        }
    }

    /**
     * バックアップクリーンアップ実行
     */
    async cleanupBackups() {
        if (!confirm('古いバックアップファイルを削除しますか？\n設定された保持日数を基準に削除されます。')) {
            return;
        }

        try {
            const response = await fetch(this.cleanupUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({})
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            
            if (result.status === 'success') {
                this.showSuccess(`${result.data.deleted_count}個のバックアップファイルを削除しました`);
                // バックアップリストと統計情報を更新
                if (window.backupManager) {
                    window.backupManager.loadBackupList();
                }
                this.loadStatistics();
            } else {
                throw new Error(result.message || 'クリーンアップに失敗しました');
            }

        } catch (error) {
            console.error('クリーンアップエラー:', error);
            this.showError(`クリーンアップエラー: ${error.message}`);
        }
    }

    /**
     * 日時フォーマット
     */
    formatDateTime(date) {
        return new Intl.DateTimeFormat('ja-JP', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            timeZone: 'Asia/Tokyo'
        }).format(date);
    }

    /**
     * 成功メッセージ表示
     */
    showSuccess(message) {
        console.log('成功:', message);
        if (typeof showNotification === 'function') {
            showNotification(message, 'success');
        } else {
            alert(`✅ ${message}`);
        }
    }

    /**
     * エラーメッセージ表示
     */
    showError(message) {
        console.error('エラー:', message);
        if (typeof showNotification === 'function') {
            showNotification(message, 'error');
        } else {
            alert(`❌ ${message}`);
        }
    }
}

// バックアップマネージャーインスタンス作成
document.addEventListener('DOMContentLoaded', function() {
    window.backupManager = new BackupManager();
    window.backupSettingsManager = new BackupSettingsManager();
    
    // Phase 2設定管理を初期化
    window.backupSettingsManager.init();
});