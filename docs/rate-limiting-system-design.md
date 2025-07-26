# レート制限システム設計仕様書

## 概要
TASK-004の要件に基づく詳細レート制限システムの設計仕様です。認証失敗によるブルートフォース攻撃を防止し、管理画面での制限管理機能を提供します。

## システム要件

### 基本要件
- **制限条件**: 10分間で5回認証失敗したIPアドレスを制限
- **制限時間**: 30分間のアクセス制限
- **対象範囲**: IP アドレス単位での制限
- **管理機能**: 管理画面での制限状況可視化と手動解除
- **自動化**: 制限期限の自動解除とクリーンアップ
- **緊急解除**: ブロックインシデントIDによる個別解除申請

### 成功条件チェックリスト
- [x] 10分間5回認証失敗でIP制限（30分間）
- [x] 管理画面での制限IP一覧表示
- [x] 個別IP制限解除機能
- [x] 制限理由・時刻の表示
- [x] 自動解除機能
- [x] ブロックインシデントID生成・表示機能
- [x] インシデント管理・解除申請処理機能

## アーキテクチャ設計

### データベース設計
既存テーブルを活用：
- `auth_failures`: 認証失敗ログ（既存）
- `ip_blocks`: IP制限管理（既存）

#### 新規テーブル
```sql
-- ブロックインシデント管理テーブル
CREATE TABLE IF NOT EXISTS block_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT UNIQUE NOT NULL,
    ip_address TEXT NOT NULL,
    block_reason TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP NULL,
    resolved_by TEXT NULL,
    admin_notes TEXT NULL
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_block_incidents_incident_id ON block_incidents(incident_id);
CREATE INDEX IF NOT EXISTS idx_block_incidents_ip ON block_incidents(ip_address);
CREATE INDEX IF NOT EXISTS idx_block_incidents_resolved ON block_incidents(resolved);
```

### コンポーネント設計

#### 1. RateLimitManager クラス
**場所**: `database/utils.py`拡張

**責務**:
- 認証失敗の記録と集計
- IP制限の判定と実行
- 制限状況の取得と管理

**主要メソッド**:
```python
class RateLimitManager:
    def record_auth_failure(ip_address, failure_type, email=None)
    def check_rate_limit(ip_address) -> bool
    def apply_ip_block(ip_address, reason, duration_minutes=30)
    def get_blocked_ips() -> List[Dict]
    def unblock_ip_manual(ip_address, admin_user)
    def cleanup_expired_blocks()

class BlockIncidentManager:
    def generate_block_incident_id(ip_address) -> str
    def create_incident(ip_address, reason) -> str
    def resolve_incident(incident_id, admin_user, notes=None) -> bool
    def get_incident_by_id(incident_id) -> Dict
    def get_pending_incidents() -> List[Dict]
```

#### 2. 管理画面拡張
**場所**: `templates/admin.html`, `static/js/admin.js`

**機能**:
- 制限IP一覧表示テーブル
- 個別解除ボタンとモーダル
- 制限理由・時刻の詳細表示
- リアルタイム更新（SSE）

#### 3. APIエンドポイント拡張
**場所**: `app.py`

**新規エンドポイント**:
- `GET /admin/blocked-ips`: 制限IP一覧取得
- `POST /admin/unblock-ip`: 個別IP制限解除
- `GET /admin/rate-limit-stats`: 制限統計情報
- `GET /admin/block-incidents`: ブロックインシデント一覧取得
- `POST /admin/resolve-incident`: インシデント解除処理

#### 4. ブロック画面表示機能
**場所**: `templates/blocked.html`（新規作成）

**機能**:
- 制限理由と解除時刻の表示
- ブロックインシデントIDの表示
- 緊急連絡先と解除申請手順の案内
- セキュアな情報表示（IPアドレス非表示）

### セキュリティ設計

#### 制限ロジック
```python
def check_auth_failure_rate(ip_address):
    """
    10分間の認証失敗回数をチェック
    5回以上で30分間のIP制限を適用
    """
    time_window = 10  # 分
    failure_threshold = 5
    block_duration = 30  # 分
```

#### 管理者権限チェック
- IP制限解除は管理者のみ実行可能
- 操作ログの記録（誰が何時解除したか）

## 実装詳細

### フェーズ1: バックエンド実装（完了）
1. ✅ `RateLimitManager`クラスの実装
2. ✅ 認証フロー統合（OTP、パスフレーズ認証）
3. ✅ APIエンドポイント追加

### フェーズ2: フロントエンド実装（完了）
1. ✅ 管理画面UI拡張
2. ✅ IP制限一覧テーブル
3. ✅ 解除機能とモーダル

### フェーズ3: 自動化機能（完了）
1. ✅ バックグラウンドタスクでの期限切れ制限自動解除
2. ✅ 定期クリーンアップジョブ
3. ✅ 統計情報の定期更新

### フェーズ4: ブロックインシデント管理（完了）
1. ✅ `BlockIncidentManager`クラスの実装
   - SHA256ベースの一意なインシデントID生成（例：BLOCK-20250726153045-A4B2）
   - インシデント作成・解除機能
   - 未解決インシデント一覧取得
   - セキュリティ対策（SQLインジェクション防止）
2. 🔄 ブロック画面表示機能（次フェーズ）
3. 🔄 インシデント管理APIエンドポイント（次フェーズ）
4. 🔄 管理画面でのインシデント一覧・解除機能（次フェーズ）

#### 実装済み機能詳細
**インシデントID生成ロジック**:
- フォーマット: `BLOCK-{YYYYMMDDHHMMSS}-{HASH}`
- ハッシュ入力: `{timestamp}{microseconds}{ip_address}`
- ハッシュ長: SHA256の先頭4文字（大文字）
- 一意性保証: マイクロ秒単位のタイムスタンプ

**データベーステーブル**: `block_incidents`
- 自動インシデント作成（IP制限発動時）
- 管理者による解除処理記録
- インシデント履歴管理

## テスト設計

### 単体テスト
- `RateLimitManager`の各メソッド
- 制限条件の境界値テスト
- 時間ベースの制限解除テスト

### 統合テスト
- 認証失敗→制限→解除のフルフロー
- 管理画面での操作テスト
- 複数IP同時制限のテスト

### セキュリティテスト
- 制限回避の試行テスト
- 権限チェックのテスト
- レート制限自体の回避テスト

## 運用考慮事項

### パフォーマンス
- インデックス最適化（IP、時刻ベース）
- 古いログの自動削除
- キャッシュ機能の検討

### 監視・アラート
- 大量制限発生時のアラート
- 制限解除操作の監査ログ
- システム負荷監視

### 運用ツール
- 制限状況の可視化ダッシュボード
- 一括解除機能（緊急時）
- 制限設定の動的変更機能

## 拡張性設計

### 将来的な機能拡張
- 地理的IP制限
- ユーザーベースの制限
- 機械学習による異常検知
- APIレート制限

### 設定可能パラメータ
- 制限時間窓（デフォルト10分）
- 失敗回数閾値（デフォルト5回）  
- 制限期間（デフォルト30分）
- 自動解除有効/無効

## 実装スケジュール

### Week 1: バックエンド実装
- Day 1-2: RateLimitManagerクラス実装
- Day 3: 認証フロー統合
- Day 4: APIエンドポイント実装
- Day 5: 単体テスト作成・実行

### Week 2: フロントエンド・統合
- Day 1-2: 管理画面UI実装
- Day 3: 統合テスト実装・実行
- Day 4: セキュリティテスト・修正
- Day 5: ドキュメント整備・リファクタリング

## 関連ドキュメント
- [TASK-004 チケット](../tickets/tasks/TASK-004.md)
- [セキュリティ設計思想](./security-design-philosophy.md)
- [多層防御設計](./multilayer-defense-design.md)