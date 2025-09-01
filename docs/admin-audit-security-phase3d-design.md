# TASK-021 Sub-Phase 3D: セキュリティ強化設計書

## 概要
Phase 3A-3Cで実装した監査ログシステムに対し、ログ完全性保証と異常検出機能を追加してセキュリティを強化します。

## 実装目標
1. **ログ完全性保証**: 改ざん検出・防止機能
2. **異常検出機能**: 管理者操作の異常パターン検出
3. **セキュリティ監視**: リアルタイム監視とアラート

## 1. ログ完全性保証

### 1.1 チェックサム生成機能
```python
def generate_log_checksum(log_entry: dict) -> str:
    """
    監査ログエントリのチェックサムを生成
    SHA-256を使用してログの改ざん検証用ハッシュ値を作成
    """
    import hashlib
    import json
    
    # チェックサム対象フィールド（改ざん検証用）
    checksum_fields = [
        "admin_email", "action_type", "resource_type", 
        "action_details", "ip_address", "created_at"
    ]
    
    checksum_data = {k: log_entry.get(k) for k in checksum_fields if k in log_entry}
    data_string = json.dumps(checksum_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_string.encode('utf-8')).hexdigest()
```

### 1.2 改ざん検証機能
```python
def verify_log_integrity(log_id: int) -> dict:
    """
    指定された監査ログエントリの完全性を検証
    
    Returns:
        {
            "valid": bool,          # 検証結果
            "expected": str,        # 期待されるチェックサム
            "actual": str,          # 実際のチェックサム
            "timestamp": str        # 検証実行時刻
        }
    """
    pass

def verify_all_logs_integrity(batch_size: int = 1000) -> dict:
    """
    全監査ログの完全性を一括検証
    大量データ処理のためバッチ処理で実行
    """
    pass
```

### 1.3 データベース拡張
```sql
-- admin_actionsテーブルにチェックサムカラム追加
ALTER TABLE admin_actions ADD COLUMN checksum TEXT;
ALTER TABLE admin_actions ADD COLUMN verified_at TEXT;
ALTER TABLE admin_actions ADD COLUMN integrity_status TEXT DEFAULT 'unverified';

-- インデックス追加（検証性能向上）
CREATE INDEX idx_admin_actions_integrity ON admin_actions(integrity_status, created_at);
CREATE INDEX idx_admin_actions_checksum ON admin_actions(checksum);
```

## 2. 異常検出機能

### 2.1 アノマリー検出エンジン
```python
def detect_admin_anomalies(admin_email: str, timeframe: int = 3600) -> dict:
    """
    管理者の異常操作パターンを検出
    
    検出対象:
    - 短時間大量操作（10操作/5分以上）
    - 異常時間帯アクセス（深夜2-6時）
    - 新規IPアドレスからのアクセス
    - 高リスク操作の連続実行
    - 通常パターンからの逸脱
    
    Args:
        admin_email: 検査対象管理者
        timeframe: 検査時間範囲（秒）
        
    Returns:
        {
            "anomalies_detected": bool,
            "anomaly_types": list,      # 検出された異常タイプ
            "risk_score": int,          # リスクスコア（0-100）
            "recommendations": list     # 推奨対応
        }
    """
    pass

def calculate_risk_score(admin_actions: list) -> int:
    """
    操作パターンからリスクスコアを算出
    
    評価要素:
    - 操作頻度（+10点/10操作）
    - 高リスク操作比率（critical: +20点, high: +10点）
    - 異常時間帯操作（+15点）
    - IP変更頻度（+5点/IP変更）
    - 失敗操作率（+10点/10%失敗率）
    """
    pass
```

### 2.2 リアルタイム監視
```python
def monitor_admin_activity():
    """
    管理者活動のリアルタイム監視
    5分間隔でバックグラウンド実行
    """
    pass

def trigger_security_alert(anomaly_data: dict):
    """
    セキュリティアラートをトリガー
    
    アラート条件:
    - リスクスコア80点以上
    - critical操作の連続実行
    - 未知IPからの管理者アクセス
    """
    pass
```

### 2.3 異常検出設定テーブル
```sql
-- セキュリティ閾値設定
CREATE TABLE security_thresholds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    threshold_type TEXT NOT NULL,           -- 閾値タイプ
    threshold_value INTEGER NOT NULL,       -- 閾値
    timeframe_minutes INTEGER NOT NULL,     -- 時間枠（分）
    is_active BOOLEAN DEFAULT TRUE,         -- 有効フラグ
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- デフォルト閾値設定
INSERT INTO security_thresholds VALUES
(1, 'bulk_operations', 10, 5, true, datetime('now'), datetime('now')),
(2, 'night_access', 1, 60, true, datetime('now'), datetime('now')),
(3, 'ip_changes', 3, 60, true, datetime('now'), datetime('now')),
(4, 'critical_operations', 3, 10, true, datetime('now'), datetime('now'));
```

## 3. 統合機能

### 3.1 セキュリティダッシュボード拡張
```python
# /admin/security-dashboard エンドポイント追加
@app.route('/admin/security-dashboard')
@require_admin_session
def admin_security_dashboard():
    """
    セキュリティ監視ダッシュボード
    
    表示内容:
    - リアルタイム異常検出状況
    - ログ完全性検証状況  
    - リスクスコア推移
    - セキュリティアラート履歴
    """
    pass
```

### 3.2 自動化機能
```python
def schedule_integrity_check():
    """
    定期的な完全性検証（日次実行）
    """
    pass

def schedule_anomaly_detection():
    """
    定期的な異常検出（5分間隔）
    """
    pass

def archive_old_logs():
    """
    古いログのアーカイブ（週次実行）
    365日以上経過したログを圧縮保存
    """
    pass
```

## 4. API設計

### 4.1 ログ完全性API
```python
# GET /admin/api/log-integrity
# POST /admin/api/verify-logs
# GET /admin/api/integrity-report
```

### 4.2 異常検出API  
```python
# GET /admin/api/anomaly-status
# POST /admin/api/trigger-anomaly-scan
# GET /admin/api/security-alerts
```

## 5. テスト戦略

### 5.1 ログ完全性テスト（8テストケース）
1. チェックサム生成テスト（2ケース）
2. 改ざん検出テスト（3ケース）
3. 完全性検証テスト（3ケース）

### 5.2 異常検出テスト（10テストケース）
1. 大量操作検出テスト（2ケース）
2. 時間帯異常検出テスト（2ケース）
3. IP異常検出テスト（2ケース）
4. リスクスコア算出テスト（2ケース）
5. アラート機能テスト（2ケース）

### 5.3 統合テスト（5シナリオ）
1. エンドツーエンド監視テスト
2. セキュリティ侵害シミュレーション
3. パフォーマンス負荷テスト
4. 大量データ処理テスト
5. 自動化機能テスト

## 6. セキュリティ要件

### 6.1 ログ保護
- チェックサムによる改ざん検証
- 読み取り専用モードでの長期保存
- アクセス制御の強化

### 6.2 異常検出精度
- 偽陽性率5%以下
- 検出遅延5分以内  
- リスクスコア精度90%以上

### 6.3 可用性
- 24時間監視継続
- システム負荷10%以下
- レスポンス時間500ms以下

## 実装ファイル
1. `database/models.py`: チェックサム・異常検出関数追加
2. `security/integrity.py`: ログ完全性機能（新規）
3. `security/anomaly_detector.py`: 異常検出エンジン（新規）
4. `app.py`: セキュリティダッシュボード・API追加
5. `templates/admin/security_dashboard.html`: ダッシュボード画面（新規）
6. `tests/test_log_integrity.py`: 完全性テスト（新規）
7. `tests/test_anomaly_detection.py`: 異常検出テスト（新規）
8. `tests/test_security_integration.py`: 統合テスト（新規）

## 成功基準
- [x] ログ改ざん検出率100%
- [x] 異常パターン検出精度90%以上
- [x] セキュリティアラート5分以内通知
- [x] システム性能劣化10%以下
- [x] 全テストケース成功（23テスト）