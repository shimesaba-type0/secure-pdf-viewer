# 管理者ロール別セッション管理システム設計書

## 概要

GitHub Issue #10 の要件に基づき、スーパー管理者（unlimited sessions）と一般管理者（最大10セッション）の差別化されたセッション管理システムを実装する。

## 要件

### 基本要件
- **スーパー管理者**: 無制限セッション許可
- **一般管理者**: 最大10セッション制限
- セッション期限切れ問題の解決
- セッションローテーション機能
- 信頼ネットワーク bypass 機能

### 技術要件
- 既存セッション管理との互換性維持
- アプリケーション統一タイムゾーンシステム準拠
- セキュリティ監視・アラート機能

## データベース設計

### admin_users テーブル拡張

```sql
-- ロールフィールド追加
ALTER TABLE admin_users ADD COLUMN role TEXT DEFAULT 'admin';

-- 可能な値: 'super_admin', 'admin'
-- 初期管理者（ADMIN_EMAIL）は 'super_admin' に設定
```

### 新規設定項目

```sql
INSERT INTO settings (key, value, value_type, description, category, is_sensitive) VALUES
('super_admin_unlimited_sessions', 'true', 'boolean', 'スーパー管理者の無制限セッション許可', 'security', FALSE),
('regular_admin_session_limit', '10', 'integer', '一般管理者のセッション制限数', 'security', FALSE),
('session_rotation_enabled', 'true', 'boolean', 'セッションローテーション機能有効化', 'security', FALSE),
('session_rotation_max_age_hours', '24', 'integer', 'セッション強制ローテーション時間（時間）', 'security', FALSE),
('session_rotation_alert_threshold', '5', 'integer', 'セッションローテーション警告閾値', 'security', FALSE),
('session_rotation_lock_threshold', '10', 'integer', 'セッションローテーションロック閾値', 'security', FALSE);
```

### admin_session_events テーブル

```sql
CREATE TABLE IF NOT EXISTS admin_session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_email TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL, -- 'created', 'rotated', 'expired', 'limit_exceeded'
    event_details JSON,
    ip_address TEXT,
    user_agent TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (admin_email) REFERENCES admin_users(email)
);

CREATE INDEX idx_admin_session_events_admin_email ON admin_session_events(admin_email);
CREATE INDEX idx_admin_session_events_created_at ON admin_session_events(created_at);
```

## 機能設計

### ロール管理機能

```python
def get_admin_role(email: str) -> str:
    """管理者のロールを取得"""
    # 'super_admin' または 'admin' を返す

def is_super_admin(email: str) -> bool:
    """スーパー管理者かチェック"""
    return get_admin_role(email) == 'super_admin'

def set_admin_role(email: str, role: str, changed_by: str):
    """管理者ロールを設定"""
    # 'super_admin' または 'admin' のみ許可
```

### セッション制限チェック

```python
def check_admin_session_limit(admin_email: str) -> dict:
    """
    管理者のセッション制限をチェック

    Returns:
        {
            'allowed': bool,
            'current_count': int,
            'max_limit': int,
            'role': str,
            'unlimited': bool
        }
    """
    role = get_admin_role(admin_email)

    if role == 'super_admin':
        unlimited_enabled = get_setting(db, 'super_admin_unlimited_sessions', True)
        if unlimited_enabled:
            return {
                'allowed': True,
                'current_count': get_admin_session_count(admin_email),
                'max_limit': None,
                'role': 'super_admin',
                'unlimited': True
            }

    # 一般管理者の制限チェック
    current_count = get_admin_session_count(admin_email)
    max_limit = get_setting(db, 'regular_admin_session_limit', 10)

    return {
        'allowed': current_count < max_limit,
        'current_count': current_count,
        'max_limit': max_limit,
        'role': role,
        'unlimited': False
    }

def get_admin_session_count(admin_email: str) -> int:
    """管理者の現在のアクティブセッション数を取得"""
    with get_db() as db:
        result = db.execute(
            "SELECT COUNT(*) FROM admin_sessions WHERE admin_email = ? AND is_active = TRUE",
            (admin_email,)
        ).fetchone()
        return result[0] if result else 0
```

### セッションローテーション

```python
def cleanup_old_sessions_for_user(admin_email: str, keep_count: int = None):
    """
    ユーザーの古いセッションをクリーンアップ

    Args:
        admin_email: 管理者メールアドレス
        keep_count: 保持するセッション数（Noneの場合はロール別制限を使用）
    """
    role = get_admin_role(admin_email)

    if role == 'super_admin' and get_setting(db, 'super_admin_unlimited_sessions', True):
        # スーパー管理者は制限なし
        return

    if keep_count is None:
        keep_count = get_setting(db, 'regular_admin_session_limit', 10)

    with get_db() as db:
        # 古いセッションを削除（新しいものから keep_count 個を除く）
        sessions_to_delete = db.execute("""
            SELECT session_id FROM admin_sessions
            WHERE admin_email = ? AND is_active = TRUE
            ORDER BY last_verified_at DESC
            LIMIT -1 OFFSET ?
        """, (admin_email, keep_count)).fetchall()

        for session in sessions_to_delete:
            delete_admin_session(session['session_id'])
            log_session_event(admin_email, session['session_id'], 'rotated', {
                'reason': 'session_limit_exceeded',
                'keep_count': keep_count
            })

def rotate_session_if_needed(session_id: str, admin_email: str):
    """セッションローテーションが必要かチェックして実行"""
    if not get_setting(db, 'session_rotation_enabled', True):
        return False

    max_age_hours = get_setting(db, 'session_rotation_max_age_hours', 24)

    with get_db() as db:
        session_info = db.execute(
            "SELECT created_at FROM admin_sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()

        if session_info:
            from config.timezone import get_app_now, to_app_timezone
            from datetime import datetime, timedelta

            created_at = to_app_timezone(datetime.fromisoformat(session_info['created_at']))
            age = get_app_now() - created_at

            if age > timedelta(hours=max_age_hours):
                # セッションローテーション実行
                new_session_id = str(uuid.uuid4())
                regenerate_admin_session_id(session_id, new_session_id)

                log_session_event(admin_email, session_id, 'rotated', {
                    'reason': 'max_age_exceeded',
                    'age_hours': age.total_seconds() / 3600,
                    'new_session_id': new_session_id
                })

                return True

    return False
```

### 信頼ネットワーク bypass

```python
def is_trusted_network(ip_address: str) -> bool:
    """
    IPアドレスが信頼ネットワークかチェック

    環境変数 ADMIN_TRUSTED_NETWORKS からカンマ区切りで取得
    例: "192.168.1.0/24,10.0.0.0/8,172.16.0.0/12"
    """
    import os
    import ipaddress

    trusted_networks = os.getenv('ADMIN_TRUSTED_NETWORKS', '')
    if not trusted_networks:
        return False

    try:
        user_ip = ipaddress.ip_address(ip_address)
        for network_str in trusted_networks.split(','):
            network_str = network_str.strip()
            if not network_str:
                continue

            try:
                network = ipaddress.ip_network(network_str, strict=False)
                if user_ip in network:
                    return True
            except ValueError:
                # 単一IPアドレスの場合
                if str(user_ip) == network_str:
                    return True

        return False
    except ValueError:
        return False

def check_session_security_violations(admin_email: str, ip_address: str) -> dict:
    """セッション関連のセキュリティ違反をチェック"""

    # 信頼ネットワークからのアクセスはbypass
    if is_trusted_network(ip_address):
        return {'violated': False, 'trusted_network': True}

    # セッションローテーション回数をチェック
    rotation_count = get_session_rotation_count(admin_email, hours=24)
    alert_threshold = get_setting(db, 'session_rotation_alert_threshold', 5)
    lock_threshold = get_setting(db, 'session_rotation_lock_threshold', 10)

    violation_data = {
        'violated': False,
        'trusted_network': False,
        'rotation_count': rotation_count,
        'alert_threshold': alert_threshold,
        'lock_threshold': lock_threshold,
        'action_required': 'none'
    }

    if rotation_count >= lock_threshold:
        violation_data.update({
            'violated': True,
            'action_required': 'lock',
            'message': f'Account locked: {rotation_count} session rotations in 24h'
        })
    elif rotation_count >= alert_threshold:
        violation_data.update({
            'violated': True,
            'action_required': 'alert',
            'message': f'Security alert: {rotation_count} session rotations in 24h'
        })

    return violation_data

def get_session_rotation_count(admin_email: str, hours: int = 24) -> int:
    """指定時間内のセッションローテーション回数を取得"""
    from config.timezone import get_app_now, add_app_timedelta

    cutoff_time = add_app_timedelta(get_app_now(), hours=-hours)
    cutoff_str = cutoff_time.strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as db:
        result = db.execute("""
            SELECT COUNT(*) FROM admin_session_events
            WHERE admin_email = ? AND event_type = 'rotated' AND created_at >= ?
        """, (admin_email, cutoff_str)).fetchone()

        return result[0] if result else 0
```

### セッション監視機能

```python
def log_session_event(admin_email: str, session_id: str, event_type: str, details: dict = None):
    """セッションイベントをログに記録"""
    from config.timezone import get_app_datetime_string
    import json

    with get_db() as db:
        insert_with_app_timestamp(
            db,
            'admin_session_events',
            ['admin_email', 'session_id', 'event_type', 'event_details'],
            [admin_email, session_id, event_type, json.dumps(details) if details else None],
            timestamp_columns=['created_at']
        )

def get_admin_session_stats(admin_email: str = None, hours: int = 24) -> dict:
    """管理者セッション統計を取得"""
    from config.timezone import get_app_now, add_app_timedelta

    cutoff_time = add_app_timedelta(get_app_now(), hours=-hours)
    cutoff_str = cutoff_time.strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as db:
        db.row_factory = sqlite3.Row

        where_clause = "WHERE created_at >= ?"
        params = [cutoff_str]

        if admin_email:
            where_clause += " AND admin_email = ?"
            params.append(admin_email)

        # イベント種別統計
        events = db.execute(f"""
            SELECT event_type, COUNT(*) as count
            FROM admin_session_events {where_clause}
            GROUP BY event_type
        """, params).fetchall()

        # 管理者別統計
        admin_stats = db.execute(f"""
            SELECT admin_email, COUNT(*) as total_events,
                   SUM(CASE WHEN event_type = 'rotated' THEN 1 ELSE 0 END) as rotations
            FROM admin_session_events {where_clause}
            GROUP BY admin_email
        """, params).fetchall()

        return {
            'period_hours': hours,
            'events': {row['event_type']: row['count'] for row in events},
            'admin_stats': [dict(row) for row in admin_stats]
        }
```

## 管理者セッション監視ページ設計

### URL構成
- `/admin/session-monitor`: 全管理者セッション監視（スーパー管理者専用）
- `/admin/my-sessions`: 自分のセッション情報（全管理者）

### テンプレート: templates/admin_session_monitor.html

```html
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>管理者セッション監視 - Secure PDF Viewer</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/main.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/admin.css') }}">
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>管理者セッション監視</h1>
            <div class="header-actions">
                <button class="btn btn-secondary" onclick="location.href='/admin'">← 管理画面に戻る</button>
                <button class="btn btn-primary" onclick="refreshData()">🔄 更新</button>
                <div class="auto-refresh-setting">
                    <label>
                        <input type="checkbox" id="auto-refresh" checked> 自動更新(30秒)
                    </label>
                </div>
            </div>
        </header>

        <!-- セッション統計 -->
        <div class="stats-grid">
            <div class="stat-card">
                <h3>総セッション数</h3>
                <div class="stat-value" id="total-sessions">-</div>
            </div>
            <div class="stat-card">
                <h3>スーパー管理者</h3>
                <div class="stat-value" id="super-admin-sessions">-</div>
            </div>
            <div class="stat-card">
                <h3>一般管理者</h3>
                <div class="stat-value" id="regular-admin-sessions">-</div>
            </div>
            <div class="stat-card">
                <h3>警告レベル</h3>
                <div class="stat-value" id="warning-count">-</div>
            </div>
        </div>

        <!-- 管理者別セッション情報 -->
        <div class="session-table-container">
            <h2>管理者別セッション状況</h2>
            <table class="session-table" id="admin-session-table">
                <thead>
                    <tr>
                        <th>管理者</th>
                        <th>ロール</th>
                        <th>アクティブセッション数</th>
                        <th>制限</th>
                        <th>最新ログイン</th>
                        <th>ローテーション回数(24h)</th>
                        <th>ステータス</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody id="admin-session-list">
                    <!-- JavaScriptで動的生成 -->
                </tbody>
            </table>
        </div>

        <!-- セッション詳細 -->
        <div class="session-details-container" id="session-details" style="display: none;">
            <h2>セッション詳細</h2>
            <div id="session-details-content">
                <!-- JavaScriptで動的生成 -->
            </div>
        </div>
    </div>

    <script src="{{ url_for('static', filename='js/admin-session-monitor.js') }}"></script>
</body>
</html>
```

### JavaScript: static/js/admin-session-monitor.js

```javascript
class AdminSessionMonitor {
    constructor() {
        this.autoRefreshInterval = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadData();
        this.startAutoRefresh();
    }

    setupEventListeners() {
        document.getElementById('auto-refresh').addEventListener('change', (e) => {
            if (e.target.checked) {
                this.startAutoRefresh();
            } else {
                this.stopAutoRefresh();
            }
        });
    }

    async loadData() {
        try {
            const [statsResponse, sessionsResponse] = await Promise.all([
                fetch('/admin/api/session-stats'),
                fetch('/admin/api/admin-sessions')
            ]);

            const statsData = await statsResponse.json();
            const sessionsData = await sessionsResponse.json();

            this.updateStats(statsData);
            this.updateSessionTable(sessionsData);
        } catch (error) {
            console.error('データ取得エラー:', error);
            this.showError('データの取得に失敗しました');
        }
    }

    updateStats(data) {
        document.getElementById('total-sessions').textContent = data.total_sessions || 0;
        document.getElementById('super-admin-sessions').textContent = data.super_admin_sessions || 0;
        document.getElementById('regular-admin-sessions').textContent = data.regular_admin_sessions || 0;
        document.getElementById('warning-count').textContent = data.warning_count || 0;
    }

    updateSessionTable(data) {
        const tbody = document.getElementById('admin-session-list');
        tbody.innerHTML = '';

        data.admin_sessions.forEach(admin => {
            const row = this.createAdminRow(admin);
            tbody.appendChild(row);
        });
    }

    createAdminRow(admin) {
        const row = document.createElement('tr');

        const statusClass = this.getStatusClass(admin.status);
        const limitText = admin.role === 'super_admin' ? '無制限' : `${admin.current_sessions}/${admin.max_limit}`;

        row.innerHTML = `
            <td>${admin.email}</td>
            <td>
                <span class="role-badge role-${admin.role}">
                    ${admin.role === 'super_admin' ? 'スーパー管理者' : '一般管理者'}
                </span>
            </td>
            <td>${admin.current_sessions}</td>
            <td>${limitText}</td>
            <td>${admin.last_login || '-'}</td>
            <td>${admin.rotation_count_24h || 0}</td>
            <td>
                <span class="status-badge status-${statusClass}">
                    ${this.getStatusText(admin.status)}
                </span>
            </td>
            <td>
                <button class="btn btn-sm btn-info" onclick="sessionMonitor.showSessionDetails('${admin.email}')">
                    詳細
                </button>
                ${admin.role !== 'super_admin' ? `
                    <button class="btn btn-sm btn-warning" onclick="sessionMonitor.cleanupSessions('${admin.email}')">
                        クリーンアップ
                    </button>
                ` : ''}
            </td>
        `;

        return row;
    }

    getStatusClass(status) {
        switch (status) {
            case 'normal': return 'normal';
            case 'warning': return 'warning';
            case 'critical': return 'critical';
            case 'locked': return 'danger';
            default: return 'normal';
        }
    }

    getStatusText(status) {
        switch (status) {
            case 'normal': return '正常';
            case 'warning': return '警告';
            case 'critical': return '危険';
            case 'locked': return 'ロック';
            default: return '不明';
        }
    }

    async showSessionDetails(adminEmail) {
        try {
            const response = await fetch(`/admin/api/admin-sessions/${encodeURIComponent(adminEmail)}`);
            const data = await response.json();

            this.displaySessionDetails(data);
        } catch (error) {
            console.error('セッション詳細取得エラー:', error);
            this.showError('セッション詳細の取得に失敗しました');
        }
    }

    displaySessionDetails(data) {
        const container = document.getElementById('session-details');
        const content = document.getElementById('session-details-content');

        content.innerHTML = `
            <div class="session-details-header">
                <h3>${data.admin_email} のセッション詳細</h3>
                <button class="btn btn-secondary" onclick="sessionMonitor.hideSessionDetails()">閉じる</button>
            </div>

            <div class="session-list">
                ${data.sessions.map(session => `
                    <div class="session-item">
                        <div class="session-info">
                            <strong>セッションID:</strong> ${session.session_id.substring(0, 16)}...<br>
                            <strong>作成日時:</strong> ${session.created_at}<br>
                            <strong>最終確認:</strong> ${session.last_verified_at}<br>
                            <strong>IPアドレス:</strong> ${session.ip_address}<br>
                            <strong>ユーザーエージェント:</strong> ${session.user_agent}
                        </div>
                        <div class="session-actions">
                            <button class="btn btn-sm btn-danger" onclick="sessionMonitor.terminateSession('${session.session_id}')">
                                セッション終了
                            </button>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        container.style.display = 'block';
    }

    hideSessionDetails() {
        document.getElementById('session-details').style.display = 'none';
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

            const result = await response.json();

            if (result.success) {
                this.showSuccess(`${result.cleaned_count} 個のセッションをクリーンアップしました`);
                this.loadData();
            } else {
                this.showError(result.message);
            }
        } catch (error) {
            console.error('セッションクリーンアップエラー:', error);
            this.showError('セッションクリーンアップに失敗しました');
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

            const result = await response.json();

            if (result.success) {
                this.showSuccess('セッションを終了しました');
                this.loadData();
                this.hideSessionDetails();
            } else {
                this.showError(result.message);
            }
        } catch (error) {
            console.error('セッション終了エラー:', error);
            this.showError('セッション終了に失敗しました');
        }
    }

    startAutoRefresh() {
        this.stopAutoRefresh();
        this.autoRefreshInterval = setInterval(() => {
            this.loadData();
        }, 30000);
    }

    stopAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
    }

    showSuccess(message) {
        // 成功メッセージ表示実装
        console.log('Success:', message);
    }

    showError(message) {
        // エラーメッセージ表示実装
        console.error('Error:', message);
    }
}

// グローバル変数として初期化
let sessionMonitor;

document.addEventListener('DOMContentLoaded', () => {
    sessionMonitor = new AdminSessionMonitor();
});

// refreshData関数をグローバルスコープに公開
function refreshData() {
    sessionMonitor.loadData();
}
```

## API エンドポイント設計

### セッション統計API

```python
@app.route('/admin/api/session-stats')
@require_admin_session
def api_session_stats():
    """セッション統計データを取得"""
    try:
        email = session.get('email')

        # スーパー管理者のみ全データ表示
        if not is_super_admin(email):
            return jsonify({'error': 'スーパー管理者権限が必要です'}), 403

        stats = get_admin_session_stats()

        return jsonify({
            'success': True,
            'total_sessions': stats.get('total_sessions', 0),
            'super_admin_sessions': stats.get('super_admin_sessions', 0),
            'regular_admin_sessions': stats.get('regular_admin_sessions', 0),
            'warning_count': stats.get('warning_count', 0)
        })

    except Exception as e:
        return jsonify({'error': f'統計データの取得に失敗しました: {str(e)}'}), 500

@app.route('/admin/api/admin-sessions')
@require_admin_session
def api_admin_sessions():
    """管理者セッション一覧を取得"""
    try:
        email = session.get('email')

        # スーパー管理者のみ全データ表示
        if not is_super_admin(email):
            return jsonify({'error': 'スーパー管理者権限が必要です'}), 403

        sessions_data = get_all_admin_sessions_with_stats()

        return jsonify({
            'success': True,
            'admin_sessions': sessions_data
        })

    except Exception as e:
        return jsonify({'error': f'セッション一覧の取得に失敗しました: {str(e)}'}), 500
```

## タイムゾーン対応

本アプリケーションの統一タイムゾーンシステムに準拠：

```python
# 全時刻処理で config.timezone の関数を使用
from config.timezone import (
    get_app_now,
    get_app_datetime_string,
    to_app_timezone,
    add_app_timedelta
)

def check_session_age(session_id: str) -> timedelta:
    """セッション経過時間をアプリ統一タイムゾーンで計算"""
    with get_db() as db:
        session_info = db.execute(
            "SELECT created_at FROM admin_sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()

        if session_info:
            created_at = to_app_timezone(datetime.fromisoformat(session_info['created_at']))
            return get_app_now() - created_at

        return timedelta(0)
```

## ブラウザテストシナリオ

### テストシナリオ1: スーパー管理者無制限セッション
1. スーパー管理者でログイン
2. 複数ブラウザ・シークレットモードで同時ログイン
3. セッション監視ページで無制限表示確認

### テストシナリオ2: 一般管理者セッション制限
1. 一般管理者でログイン
2. 10セッション以上作成を試行
3. 制限によるログイン拒否確認

### テストシナリオ3: セッションローテーション
1. 管理者でログイン後、24時間経過をシミュレート
2. 自動ローテーション動作確認
3. ローテーション回数による警告・ロック確認

### 期待ログ
- `logs/app.log`: セッション制限チェック、ローテーション実行ログ
- ブラウザコンソール: JavaScript UI エラー、API レスポンス確認