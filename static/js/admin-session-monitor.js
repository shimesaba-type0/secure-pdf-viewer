/**
 * 管理者セッション監視機能
 * GitHub Issue #10 対応
 */

class AdminSessionMonitor {
    constructor() {
        this.autoRefreshInterval = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadData();
        this.startAutoRefresh();
        this.updateLastUpdated();
    }

    setupEventListeners() {
        const autoRefreshCheckbox = document.getElementById('auto-refresh');
        if (autoRefreshCheckbox) {
            autoRefreshCheckbox.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.startAutoRefresh();
                } else {
                    this.stopAutoRefresh();
                }
            });
        }
    }

    async loadData() {
        try {
            const [statsResponse, sessionsResponse] = await Promise.all([
                fetch('/admin/api/session-stats'),
                fetch('/admin/api/admin-sessions')
            ]);

            if (!statsResponse.ok || !sessionsResponse.ok) {
                throw new Error('APIリクエストが失敗しました');
            }

            const statsData = await statsResponse.json();
            const sessionsData = await sessionsResponse.json();

            if (!statsData.success || !sessionsData.success) {
                throw new Error(statsData.error || sessionsData.error || 'APIエラー');
            }

            this.updateStats(statsData);
            this.updateSessionTable(sessionsData);
            this.updateLastUpdated();
            this.clearMessages();

        } catch (error) {
            console.error('データ取得エラー:', error);
            this.showError(`データの取得に失敗しました: ${error.message}`);
        }
    }

    updateStats(data) {
        const elements = {
            'total-sessions': data.total_sessions || 0,
            'super-admin-sessions': data.super_admin_sessions || 0,
            'regular-admin-sessions': data.regular_admin_sessions || 0,
            'warning-count': data.warning_count || 0
        };

        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        });
    }

    updateSessionTable(data) {
        const tbody = document.getElementById('admin-session-list');
        if (!tbody) return;

        tbody.innerHTML = '';

        if (!data.admin_sessions || data.admin_sessions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="loading">管理者セッションが見つかりません</td></tr>';
            return;
        }

        data.admin_sessions.forEach(admin => {
            const row = this.createAdminRow(admin);
            tbody.appendChild(row);
        });
    }

    createAdminRow(admin) {
        const row = document.createElement('tr');

        const statusClass = this.getStatusClass(admin.status);
        const limitText = admin.role === 'super_admin' ? '無制限' : `${admin.current_sessions}/${admin.max_limit}`;
        const lastLogin = admin.last_login ? this.formatDateTime(admin.last_login) : '-';

        row.innerHTML = `
            <td>${this.escapeHtml(admin.email)}</td>
            <td>
                <span class="role-badge role-${admin.role}">
                    ${admin.role === 'super_admin' ? 'スーパー管理者' : '一般管理者'}
                </span>
            </td>
            <td>${admin.current_sessions}</td>
            <td>${limitText}</td>
            <td>${lastLogin}</td>
            <td>${admin.rotation_count_24h || 0}</td>
            <td>
                <span class="status-badge status-${statusClass}">
                    ${this.getStatusText(admin.status)}
                </span>
            </td>
            <td>
                <button class="btn btn-sm btn-info" onclick="sessionMonitor.showSessionDetails('${this.escapeHtml(admin.email)}')">
                    詳細
                </button>
                ${admin.role !== 'super_admin' ? `
                    <button class="btn btn-sm btn-warning" onclick="sessionMonitor.cleanupSessions('${this.escapeHtml(admin.email)}')">
                        クリーンアップ
                    </button>
                ` : ''}
            </td>
        `;

        return row;
    }

    getStatusClass(status) {
        const statusMap = {
            'normal': 'normal',
            'warning': 'warning',
            'critical': 'critical',
            'locked': 'danger'
        };
        return statusMap[status] || 'normal';
    }

    getStatusText(status) {
        const statusMap = {
            'normal': '正常',
            'warning': '警告',
            'critical': '危険',
            'locked': 'ロック'
        };
        return statusMap[status] || '不明';
    }

    async showSessionDetails(adminEmail) {
        try {
            const response = await fetch(`/admin/api/admin-sessions/${encodeURIComponent(adminEmail)}`);

            if (!response.ok) {
                throw new Error('セッション詳細の取得に失敗しました');
            }

            const data = await response.json();
            this.displaySessionDetails(data);

        } catch (error) {
            console.error('セッション詳細取得エラー:', error);
            this.showError(`セッション詳細の取得に失敗しました: ${error.message}`);
        }
    }

    displaySessionDetails(data) {
        const container = document.getElementById('session-details');
        const title = document.getElementById('session-details-title');
        const content = document.getElementById('session-details-content');

        if (!container || !title || !content) return;

        title.textContent = `${data.admin_email} のセッション詳細`;

        if (!data.sessions || data.sessions.length === 0) {
            content.innerHTML = '<p>アクティブなセッションがありません。</p>';
        } else {
            content.innerHTML = `
                <div class="session-list">
                    ${data.sessions.map(session => `
                        <div class="session-item">
                            <div class="session-info">
                                <strong>セッションID:</strong> ${this.escapeHtml(session.session_id.substring(0, 16))}...<br>
                                <strong>作成日時:</strong> ${this.formatDateTime(session.created_at)}<br>
                                <strong>最終確認:</strong> ${this.formatDateTime(session.last_verified_at)}<br>
                                <strong>IPアドレス:</strong> ${this.escapeHtml(session.ip_address)}<br>
                                <strong>ユーザーエージェント:</strong> ${this.escapeHtml(this.truncateText(session.user_agent, 60))}<br>
                                <strong>ステータス:</strong> ${session.is_active ? 'アクティブ' : '非アクティブ'}
                            </div>
                            <div class="session-actions">
                                ${session.is_active ? `
                                    <button class="btn btn-sm btn-danger" onclick="sessionMonitor.terminateSession('${this.escapeHtml(session.session_id)}')">
                                        セッション終了
                                    </button>
                                ` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        container.style.display = 'block';
        container.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    hideSessionDetails() {
        const container = document.getElementById('session-details');
        if (container) {
            container.style.display = 'none';
        }
    }

    async cleanupSessions(adminEmail) {
        if (!confirm(`${adminEmail} の古いセッションをクリーンアップしますか？`)) {
            return;
        }

        try {
            const response = await fetch('/admin/api/cleanup-sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ admin_email: adminEmail })
            });

            if (!response.ok) {
                throw new Error('クリーンアップリクエストが失敗しました');
            }

            const result = await response.json();

            if (result.success) {
                this.showSuccess(`${result.cleaned_count} 個のセッションをクリーンアップしました`);
                this.loadData(); // データを再読み込み
            } else {
                throw new Error(result.error || 'クリーンアップに失敗しました');
            }

        } catch (error) {
            console.error('セッションクリーンアップエラー:', error);
            this.showError(`セッションクリーンアップに失敗しました: ${error.message}`);
        }
    }

    async terminateSession(sessionId) {
        if (!confirm('このセッションを終了しますか？')) {
            return;
        }

        try {
            const response = await fetch('/admin/api/terminate-session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId })
            });

            if (!response.ok) {
                throw new Error('セッション終了リクエストが失敗しました');
            }

            const result = await response.json();

            if (result.success) {
                this.showSuccess('セッションを終了しました');
                this.loadData(); // データを再読み込み
                this.hideSessionDetails();
            } else {
                throw new Error(result.error || 'セッション終了に失敗しました');
            }

        } catch (error) {
            console.error('セッション終了エラー:', error);
            this.showError(`セッション終了に失敗しました: ${error.message}`);
        }
    }

    startAutoRefresh() {
        this.stopAutoRefresh();
        this.autoRefreshInterval = setInterval(() => {
            this.loadData();
        }, 30000); // 30秒間隔
    }

    stopAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
    }

    updateLastUpdated() {
        const element = document.getElementById('last-updated');
        if (element) {
            const now = new Date();
            element.textContent = `最終更新: ${this.formatDateTime(now.toISOString())}`;
        }
    }

    showSuccess(message) {
        this.showMessage(message, 'success');
    }

    showError(message) {
        this.showMessage(message, 'error');
    }

    showMessage(message, type) {
        const messageArea = document.getElementById('message-area');
        if (!messageArea) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = type === 'error' ? 'error-message' : 'success-message';
        messageDiv.textContent = message;

        messageArea.appendChild(messageDiv);

        // 5秒後に自動削除
        setTimeout(() => {
            if (messageDiv.parentNode) {
                messageDiv.parentNode.removeChild(messageDiv);
            }
        }, 5000);
    }

    clearMessages() {
        const messageArea = document.getElementById('message-area');
        if (messageArea) {
            messageArea.innerHTML = '';
        }
    }

    // ユーティリティ関数
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    truncateText(text, maxLength) {
        if (!text) return '';
        return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
    }

    formatDateTime(isoString) {
        if (!isoString) return '-';

        try {
            const date = new Date(isoString);
            return date.toLocaleString('ja-JP', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        } catch (error) {
            return isoString;
        }
    }
}

// グローバル変数として初期化
let sessionMonitor;

document.addEventListener('DOMContentLoaded', () => {
    sessionMonitor = new AdminSessionMonitor();
});

// グローバル関数として公開（HTMLから呼び出し用）
function refreshData() {
    if (sessionMonitor) {
        sessionMonitor.loadData();
    }
}

function hideSessionDetails() {
    if (sessionMonitor) {
        sessionMonitor.hideSessionDetails();
    }
}