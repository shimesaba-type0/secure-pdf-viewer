# TASK-021 Phase 3: 管理者監査ログ強化システム設計書

## 概要
Phase 1・Phase 2で構築したセキュリティ基盤に基づき、管理者操作の詳細監査ログシステムを実装します。全ての管理者操作を記録・追跡し、コンプライアンス要件に対応した包括的な監査機能を提供します。

## 監査要件
1. **法的コンプライアンス**: 管理者操作の完全な記録
2. **インシデント調査**: 詳細な操作履歴による原因特定
3. **内部統制**: 権限濫用・誤操作の検出
4. **セキュリティ監視**: 異常操作パターンの識別

## 既存システム分析

### 現在実装済みのログテーブル
```sql
access_logs         -- 基本アクセスログ
event_logs          -- イベントログ  
security_events     -- セキュリティイベント（フロントエンド検知）
security_violations -- セキュリティ違反ログ
admin_sessions      -- 管理者セッション
```

### 実装済みのログ記録機能
```python
log_access()         -- アクセスログ記録
log_event()          -- イベントログ記録
log_security_event() -- セキュリティイベント記録
```

### Phase 3で新規実装する範囲
1. **管理者操作監査**: admin_actionsテーブル・記録機能
2. **操作詳細記録**: すべての管理画面操作の自動記録
3. **監査ログ分析**: 管理者専用操作履歴・レポート機能
4. **改ざん防止**: ログの完全性保証・チェックサム機能

## データベース設計

### admin_actionsテーブル（新規）
```sql
CREATE TABLE admin_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_email TEXT NOT NULL,                    -- 管理者メールアドレス
    action_type TEXT NOT NULL,                    -- 操作種別
    resource_type TEXT,                           -- リソース種別
    resource_id TEXT,                             -- リソースID
    action_details JSON,                          -- 操作詳細（JSON）
    before_state JSON,                            -- 操作前状態
    after_state JSON,                             -- 操作後状態
    ip_address TEXT NOT NULL,                     -- IPアドレス
    user_agent TEXT,                              -- ユーザーエージェント
    session_id TEXT,                              -- セッションID
    admin_session_id TEXT,                        -- 管理者セッションID
    created_at TEXT NOT NULL,                     -- 作成日時
    risk_level TEXT DEFAULT 'low',               -- リスクレベル
    success BOOLEAN DEFAULT TRUE,                 -- 操作成功/失敗
    error_message TEXT,                           -- エラーメッセージ
    request_id TEXT,                              -- リクエスト追跡ID
    
    -- 外部キー制約
    FOREIGN KEY (admin_session_id) REFERENCES admin_sessions(session_id)
);
```

### インデックス設計
```sql
-- パフォーマンス最適化インデックス
CREATE INDEX idx_admin_actions_admin_email ON admin_actions(admin_email);
CREATE INDEX idx_admin_actions_action_type ON admin_actions(action_type);
CREATE INDEX idx_admin_actions_resource_type ON admin_actions(resource_type);
CREATE INDEX idx_admin_actions_created_at ON admin_actions(created_at);
CREATE INDEX idx_admin_actions_risk_level ON admin_actions(risk_level);
CREATE INDEX idx_admin_actions_session_id ON admin_actions(admin_session_id);
CREATE INDEX idx_admin_actions_ip_address ON admin_actions(ip_address);

-- 複合インデックス（検索性能向上）
CREATE INDEX idx_admin_actions_email_time ON admin_actions(admin_email, created_at);
CREATE INDEX idx_admin_actions_type_time ON admin_actions(action_type, created_at);
```

## 操作分類体系

### action_type定義（主要操作）
```python
ADMIN_ACTION_TYPES = {
    # セッション管理
    "admin_login": "管理者ログイン",
    "admin_logout": "管理者ログアウト", 
    "session_regenerate": "セッションID再生成",
    
    # ユーザー管理
    "user_view": "ユーザー情報閲覧",
    "user_create": "ユーザー作成",
    "user_update": "ユーザー情報更新",
    "user_delete": "ユーザー削除",
    "permission_change": "権限変更",
    
    # システム設定
    "setting_view": "設定値閲覧", 
    "setting_update": "設定値変更",
    "security_config": "セキュリティ設定変更",
    "pdf_security_config": "PDF設定変更",
    
    # ログ・監査
    "log_view": "ログ閲覧",
    "log_export": "ログエクスポート",
    "incident_view": "インシデント閲覧",
    "incident_resolve": "インシデント解決",
    
    # システム運用
    "backup_create": "バックアップ作成",
    "backup_restore": "バックアップ復元",
    "system_maintenance": "システムメンテナンス",
    "emergency_stop": "緊急停止",
    
    # API操作
    "api_call": "API呼び出し",
    "bulk_operation": "一括操作",
    "data_export": "データエクスポート",
    "configuration_import": "設定インポート"
}
```

### resource_type定義
```python
RESOURCE_TYPES = {
    "user": "ユーザー",
    "session": "セッション", 
    "setting": "設定",
    "log": "ログ",
    "backup": "バックアップ",
    "pdf": "PDF文書",
    "api_endpoint": "APIエンドポイント",
    "admin_panel": "管理画面",
    "security_policy": "セキュリティポリシー"
}
```

### risk_level定義
```python
RISK_LEVELS = {
    "low": {
        "name": "低リスク",
        "actions": ["admin_login", "user_view", "log_view", "setting_view"],
        "color": "#28a745"
    },
    "medium": {
        "name": "中リスク", 
        "actions": ["user_update", "setting_update", "log_export"],
        "color": "#ffc107"
    },
    "high": {
        "name": "高リスク",
        "actions": ["user_delete", "permission_change", "backup_restore", "emergency_stop"],
        "color": "#dc3545"
    },
    "critical": {
        "name": "重要リスク",
        "actions": ["system_maintenance", "security_config", "bulk_operation"],
        "color": "#6f42c1"
    }
}
```

## API設計

### 監査ログ記録API
```python
def log_admin_action(
    admin_email: str,
    action_type: str,
    resource_type: str = None,
    resource_id: str = None,
    action_details: dict = None,
    before_state: dict = None,
    after_state: dict = None,
    ip_address: str = None,
    user_agent: str = None,
    session_id: str = None,
    admin_session_id: str = None,
    success: bool = True,
    error_message: str = None
) -> bool:
    """管理者操作をログに記録"""
```

### 監査ログ取得API
```python
def get_admin_actions(
    admin_email: str = None,
    action_type: str = None,
    resource_type: str = None,
    start_date: str = None,
    end_date: str = None,
    risk_level: str = None,
    success: bool = None,
    page: int = 1,
    limit: int = 50
) -> dict:
    """管理者監査ログを取得"""
```

### 統計API
```python
def get_admin_action_stats(
    period: str = "7d",
    group_by: str = "action_type"
) -> dict:
    """管理者操作統計を取得"""
```

## デコレータ統合

### 自動ログ記録デコレータ
```python
def log_admin_operation(
    action_type: str,
    resource_type: str = None,
    capture_state: bool = False,
    risk_level: str = "medium"
):
    """
    管理者操作を自動記録するデコレータ
    
    使用例:
    @app.route('/admin/api/update-user', methods=['POST'])
    @require_admin_session
    @log_admin_operation("user_update", "user", capture_state=True, risk_level="medium")
    def update_user():
        # ユーザー更新処理
        pass
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # 操作前状態の記録
            before_state = None
            if capture_state:
                before_state = capture_current_state(resource_type, kwargs)
            
            # リクエスト情報の収集
            admin_email = session.get('email')
            ip_address = request.remote_addr
            user_agent = request.headers.get('User-Agent', '')
            session_id = session.get('session_id')
            admin_session_id = session.get('admin_session_id')
            
            try:
                # 実際の処理実行
                result = f(*args, **kwargs)
                
                # 操作後状態の記録
                after_state = None
                if capture_state:
                    after_state = capture_current_state(resource_type, kwargs)
                
                # 成功ログ記録
                log_admin_action(
                    admin_email=admin_email,
                    action_type=action_type,
                    resource_type=resource_type,
                    action_details={"args": args, "kwargs": kwargs},
                    before_state=before_state,
                    after_state=after_state,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    session_id=session_id,
                    admin_session_id=admin_session_id,
                    success=True
                )
                
                return result
                
            except Exception as e:
                # エラーログ記録
                log_admin_action(
                    admin_email=admin_email,
                    action_type=action_type,
                    resource_type=resource_type,
                    action_details={"args": args, "kwargs": kwargs},
                    before_state=before_state,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    session_id=session_id,
                    admin_session_id=admin_session_id,
                    success=False,
                    error_message=str(e)
                )
                raise
        
        return decorated_function
    return decorator
```

## フロントエンド設計

### 監査ログ専用画面（新規）
**URL**: `/admin/audit-logs`

#### 画面構成
1. **ダッシュボード**
   - 管理者別操作統計
   - リスクレベル別統計
   - 時系列トレンド分析

2. **詳細検索**
   - 管理者・操作種別・リソース別フィルター
   - 時間範囲・リスクレベル・成功/失敗フィルター
   - 高速検索（インデックス最適化）

3. **操作詳細表示**
   - 操作前後の状態比較表示
   - JSON形式の詳細情報表示
   - 関連セッション・リクエストの追跡

4. **エクスポート機能**
   - CSV・JSON・PDF形式対応
   - 監査レポート自動生成
   - 期間指定・フィルター条件保存

### Chart.js統合（拡張）
```javascript
// 新規グラフ種別
const auditChartTypes = {
    adminActivity: "管理者別活動状況",      // 管理者別操作数
    riskTrend: "リスクレベル推移",         // 時系列リスク分析
    resourceAccess: "リソース別アクセス",   // リソース種別統計
    errorAnalysis: "エラー分析",           // 失敗操作分析
    sessionCorrelation: "セッション相関"   // セッション・操作の相関
};
```

## セキュリティ機能

### ログ完全性保証
```python
def generate_log_checksum(log_entry: dict) -> str:
    """
    ログエントリのチェックサムを生成（改ざん検証用）
    """
    import hashlib
    import json
    
    # 重要フィールドからハッシュ生成
    checksum_data = {
        "admin_email": log_entry["admin_email"],
        "action_type": log_entry["action_type"], 
        "created_at": log_entry["created_at"],
        "action_details": log_entry["action_details"],
        "before_state": log_entry["before_state"],
        "after_state": log_entry["after_state"]
    }
    
    checksum_json = json.dumps(checksum_data, sort_keys=True)
    return hashlib.sha256(checksum_json.encode()).hexdigest()

def verify_log_integrity(log_id: int) -> bool:
    """
    ログの完全性を検証
    """
    # チェックサム再計算・比較による改ざん検証
    pass
```

### アノマリー検出
```python
def detect_admin_anomalies(admin_email: str, timeframe: int = 3600) -> dict:
    """
    管理者の異常操作パターンを検出
    
    検出項目:
    - 短時間大量操作
    - 通常と異なる時間帯での操作
    - 高リスク操作の連続実行
    - 異なるIPアドレスからの同時アクセス
    - 失敗操作の連続発生
    """
    anomalies = []
    
    # 短時間大量操作検出
    recent_actions = get_admin_actions(
        admin_email=admin_email,
        start_date=datetime.now() - timedelta(seconds=timeframe)
    )
    
    if len(recent_actions) > 50:  # しきい値
        anomalies.append({
            "type": "high_frequency_operations",
            "severity": "medium",
            "count": len(recent_actions),
            "threshold": 50
        })
    
    return {
        "admin_email": admin_email,
        "anomalies": anomalies,
        "checked_at": datetime.now().isoformat()
    }
```

## 実装フェーズ

### Sub-Phase 3A: データベース基盤構築
1. **admin_actionsテーブル作成**
   - テーブル設計・マイグレーション実装
   - インデックス最適化
   - 基本CRUD関数実装

2. **ログ記録機能実装**
   - `log_admin_action()`関数
   - バッチ記録機能
   - エラーハンドリング

3. **テスト実装**
   - 単体テスト（10テストケース）
   - データベース統合テスト

### Sub-Phase 3B: デコレータ統合
1. **自動ログ記録デコレータ**
   - `@log_admin_operation`実装
   - 状態キャプチャ機能
   - エラーハンドリング統合

2. **既存エンドポイント適用**
   - 全管理者APIへの適用（19エンドポイント）
   - 管理画面操作への適用
   - パフォーマンス最適化

3. **テスト・動作確認**
   - デコレータ統合テスト（8テストケース）
   - ブラウザ動作確認

### Sub-Phase 3C: 監査ログ分析機能
1. **専用分析画面実装**
   - `/admin/audit-logs`画面
   - Chart.js統合（5種類のグラフ）
   - 高度フィルタリング

2. **統計・レポート機能**
   - 管理者別統計
   - リスク分析レポート
   - エクスポート機能（CSV/JSON/PDF）

3. **テスト・動作確認**
   - UI統合テスト
   - パフォーマンステスト

### Sub-Phase 3D: セキュリティ強化
1. **ログ完全性保証**
   - チェックサム生成・検証
   - 改ざん検出機能
   - バックアップ・アーカイブ

2. **異常検出機能**
   - アノマリー検出アルゴリズム
   - 自動アラート機能
   - ダッシュボード統合

3. **最終統合テスト**
   - エンドツーエンドテスト
   - セキュリティテスト
   - パフォーマンステスト

## データ保持・クリーンアップ

### 保持期間設定
```python
AUDIT_LOG_RETENTION = {
    "admin_actions": 2 * 365,      # 2年間（法的要件）
    "high_risk_actions": 5 * 365,  # 5年間（重要操作）
    "system_config": 7 * 365,      # 7年間（システム設定変更）
    "user_management": 3 * 365     # 3年間（ユーザー管理操作）
}
```

### 自動クリーンアップ
```python
def cleanup_audit_logs():
    """
    保持期間を過ぎた監査ログをクリーンアップ
    
    - アーカイブ作成後に削除
    - 重要操作は長期保持
    - チェックサム検証後に実行
    """
    pass
```

## テスト戦略

### 単体テスト（15テストケース）
1. **データベース機能**
   - `log_admin_action()` テスト（5ケース）
   - `get_admin_actions()` フィルタリングテスト（5ケース）
   - チェックサム生成・検証テスト（3ケース）
   - 異常検出テスト（2ケース）

### 統合テスト（10テストケース）
1. **デコレータ統合テスト**
   - 自動ログ記録テスト（4ケース）
   - エラーハンドリングテスト（3ケース）
   - 状態キャプチャテスト（3ケース）

### エンドツーエンドテスト（5シナリオ）
1. **管理者操作ライフサイクル**
   - ログイン→操作→ログアウトの完全記録
2. **異常操作検出**
   - 大量操作・異常アクセスパターンの検出
3. **監査レポート生成**
   - フィルタリング・エクスポート・完全性検証
4. **権限昇格攻撃対策**
   - 不正な権限操作の記録・阻止
5. **インシデント調査**
   - 操作履歴からの問題特定・追跡

## パフォーマンス考慮事項

### データベース最適化
1. **インデックス戦略**
   - 検索頻度の高いカラムに最適化インデックス
   - 複合インデックスによる範囲検索高速化

2. **パーティショニング**
   - 月次テーブル分割（大量データ対応）
   - アーカイブテーブルへの移動

3. **非同期処理**
   - ログ記録の非同期実行
   - バックグラウンド統計生成

### フロントエンド最適化
1. **データローディング**
   - ページネーション最適化
   - 増分ロード・キャッシュ活用

2. **グラフ描画**
   - Chart.js最適化
   - データ集約・サンプリング

## 成功基準

### 機能要件
- [ ] 全管理者操作が自動記録される（100%カバレッジ）
- [ ] 操作前後の状態変更が記録される
- [ ] リスクレベル分類が適切に動作する
- [ ] 高速検索・フィルタリングが可能（<2秒）
- [ ] エクスポート機能が完全動作する

### セキュリティ要件
- [ ] ログの改ざん検出が機能する
- [ ] 異常操作パターンが検出される
- [ ] アクセス制御が適切に動作する
- [ ] データの暗号化・ハッシュ化が機能する

### パフォーマンス要件
- [ ] ログ記録のオーバーヘッドが最小限（<50ms）
- [ ] 大量データでの検索が高速（10万件で<5秒）
- [ ] 同時アクセスに耐える（100セッション）

### 運用要件
- [ ] 自動クリーンアップが適切に動作する
- [ ] 監査レポートが生成できる
- [ ] 障害時の復旧が可能
- [ ] ログの完全性が保証される