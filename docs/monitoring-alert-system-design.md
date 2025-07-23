# 監視・アラートシステム設計書

## 概要
本システムは、TASK-003-5で実装されたセッション制限監視機能を基盤として、将来のTASK-007（メール通知システム）に向けた包括的な監視・アラート機能の設計書です。

## 現在の実装状況（2025-07-23時点）

### ✅ 実装完了機能

#### 1. セッション制限監視機能（TASK-003-5）
- **制限設定**: 管理画面での制限数設定（1-1000、デフォルト100）
- **リアルタイム監視**: 30秒間隔での自動更新
- **警告システム**: 80%/90%での段階的警告
- **認証時制限**: OTP認証完了前の制限チェックと拒否
- **SSE通知**: リアルタイム警告配信

#### 2. 基盤技術
- **メール送信基盤**: TASK-001で完成済み（`mail/email_service.py`）
- **SSE統一管理システム**: リアルタイム通知機能完成
- **データベース設定管理**: 動的な設定値管理

## 将来の拡張設計

### TASK-007対応: 汎用監視アラートシステム

#### 監視対象項目
1. **セッション関連**
   - 同時接続数制限（既存）
   - セッション異常パターン検知
   - 認証失敗率監視

2. **システム関連**
   - CPU・メモリ使用率
   - ディスク容量
   - エラー発生率

3. **セキュリティ関連**
   - IP制限発動数
   - 異常アクセスパターン
   - 管理者アクション頻度

#### データベース設計

```sql
-- 汎用監視アラート設定テーブル
CREATE TABLE monitoring_alert_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_email TEXT NOT NULL,
    alert_type TEXT NOT NULL,  -- 'session_limit', 'auth_failure', 'system_error', 'access_spike'
    alert_enabled BOOLEAN DEFAULT FALSE,
    warning_threshold INTEGER,
    critical_threshold INTEGER,
    recovery_notification BOOLEAN DEFAULT TRUE,
    cooldown_minutes INTEGER DEFAULT 60,
    last_alert_level TEXT DEFAULT 'normal',
    last_alert_time TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(admin_email, alert_type)
);

-- 監視アラート履歴テーブル
CREATE TABLE monitoring_alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_email TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    alert_level TEXT NOT NULL,  -- 'warning', 'critical', 'recovery'
    current_value INTEGER NOT NULL,
    threshold_value INTEGER NOT NULL,
    percentage REAL,
    message TEXT,
    details TEXT,  -- JSON形式での詳細情報
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_email, alert_type) REFERENCES monitoring_alert_settings(admin_email, alert_type)
);
```

### メールアラート機能設計

#### 1. 管理者別アラート設定
```python
class AlertManager:
    def __init__(self):
        self.email_service = EmailService()  # 既存のメールサービス活用
    
    def get_alert_settings(self, admin_email, alert_type):
        """管理者のアラート設定取得"""
        
    def should_send_alert(self, admin_email, alert_type, current_level):
        """アラート送信判定（クールダウン考慮）"""
        
    def send_alert_email(self, admin_email, alert_data):
        """アラートメール送信"""
```

#### 2. アラートレベル判定ロジック
```python
def evaluate_session_limit_alert(current_sessions, max_sessions, last_level):
    """
    セッション制限アラートレベル判定
    
    Args:
        current_sessions: 現在のセッション数
        max_sessions: 制限セッション数
        last_level: 前回のアラートレベル
    
    Returns:
        dict: {
            'level': 'normal'|'warning'|'critical',
            'should_notify': bool,
            'is_recovery': bool
        }
    """
    usage_rate = (current_sessions / max_sessions) * 100
    
    if usage_rate >= 95:
        new_level = 'critical'
    elif usage_rate >= 80:
        new_level = 'warning'  
    else:
        new_level = 'normal'
    
    # 復旧判定
    is_recovery = (last_level in ['warning', 'critical'] and new_level == 'normal')
    
    # 通知判定（レベル変更時のみ）
    should_notify = (new_level != last_level) or is_recovery
    
    return {
        'level': new_level,
        'should_notify': should_notify,
        'is_recovery': is_recovery,
        'usage_rate': usage_rate
    }
```

#### 3. メールテンプレート設計

##### セッション制限警告メール
```html
<!DOCTYPE html>
<html>
<head>
    <title>セッション制限警告 - Secure PDF Viewer</title>
    <style>
        .warning { background-color: #fff3cd; border-color: #ffeaa7; }
        .critical { background-color: #f8d7da; border-color: #f5c6cb; }
        .recovery { background-color: #d4edda; border-color: #c3e6cb; }
    </style>
</head>
<body>
    <div class="{{ alert_level }}">
        <h2>🚨 セッション制限{{ alert_type_name }}</h2>
        
        <p><strong>現在の状況:</strong></p>
        <ul>
            <li>現在のセッション数: {{ current_sessions }}</li>
            <li>制限値: {{ max_sessions }}</li>
            <li>使用率: {{ usage_percentage }}%</li>
            <li>発生時刻: {{ timestamp }}</li>
        </ul>
        
        {% if alert_level == 'critical' %}
        <p><strong>⚠️ 緊急対応が必要です</strong></p>
        <p>新規ユーザーの認証が拒否される状態です。</p>
        {% elif alert_level == 'warning' %}
        <p><strong>注意: 制限に近づいています</strong></p>
        {% else %}
        <p><strong>✅ 状況が復旧しました</strong></p>
        {% endif %}
        
        <p><a href="{{ admin_url }}">管理画面で詳細を確認</a></p>
    </div>
</body>
</html>
```

### API設計

#### アラート設定管理API
```python
@app.route('/admin/api/alert-settings', methods=['GET', 'POST'])
def manage_alert_settings():
    """管理者のアラート設定管理"""
    
@app.route('/admin/api/alert-settings/<alert_type>', methods=['PUT'])
def update_alert_setting():
    """特定のアラート設定更新"""
    
@app.route('/admin/api/alert-history')
def get_alert_history():
    """アラート履歴取得"""
```

#### 管理画面UI設計
```html
<!-- セッション監視アラート設定 -->
<div class="alert-settings">
    <h4>セッション制限アラート</h4>
    <form>
        <label>
            <input type="checkbox" name="alert_enabled"> アラートメール送信を有効にする
        </label>
        
        <div class="threshold-settings">
            <label>警告閾値: <input type="number" name="warning_threshold" value="80" min="1" max="99">%</label>
            <label>クリティカル閾値: <input type="number" name="critical_threshold" value="95" min="1" max="99">%</label>
        </div>
        
        <label>
            <input type="checkbox" name="recovery_notification"> 復旧通知を送信する
        </label>
        
        <label>クールダウン時間: <input type="number" name="cooldown_minutes" value="60" min="1">分</label>
        
        <button type="submit">設定を保存</button>
    </form>
</div>
```

## 実装ロードマップ

### Phase 1: セッション監視メールアラート（優先度: 高）
1. データベーステーブル作成
2. 管理画面でのアラート設定UI
3. セッション制限判定ロジックの拡張
4. メールテンプレート作成
5. 送信機能統合

### Phase 2: 汎用監視システム（優先度: 中）
1. 認証失敗監視
2. システムエラー監視
3. アクセス異常検知

### Phase 3: 高度な分析機能（優先度: 低）
1. 統計ダッシュボード
2. 予測アラート
3. CSVエクスポート機能

## セキュリティ考慮事項

### メール送信のセキュリティ
- **認証情報保護**: SMTP設定の暗号化保存
- **スパム防止**: クールダウン機能による頻度制限
- **権限管理**: 管理者のみがアラート設定を変更可能

### データ保護
- **個人情報**: メールアドレスのハッシュ化（必要に応じて）
- **ログ保持**: アラート履歴の適切な保持期間設定
- **監査**: アラート設定変更の履歴記録

## 運用上の考慮事項

### 誤報防止
- **閾値調整**: 運用実績に基づく適切な警告レベル設定
- **クールダウン**: 短時間での重複通知防止
- **テスト機能**: アラート設定のテスト送信機能

### 可用性
- **フォールバック**: メール送信失敗時のログ記録
- **監視の監視**: アラートシステム自体の稼働監視
- **手動通知**: 緊急時の手動アラート送信機能

この設計により、現在のセッション制限監視機能を基盤として、包括的で拡張性の高い監視・アラートシステムを構築できます。