# 管理者権限システム - 技術設計仕様書

## 概要

Secure PDF Viewerに管理者権限システムを実装し、管理画面へのアクセス制御と管理者の管理機能を提供する。初期管理者は.envのADMIN_EMAILで設定し、その管理者が最大5人まで追加管理者を設定できる仕組みを構築する。

## システム要件

### 機能要件

1. **初期管理者の自動設定**
   - `.env`の`ADMIN_EMAIL`を一人目の管理者とする
   - アプリケーション起動時に自動的に管理者テーブルに追加
   - 既存データがある場合は重複追加しない

2. **管理者権限チェック**
   - メールアドレスベースの権限確認機能
   - セッション管理との連携
   - 管理画面ルートでの権限検証

3. **管理者管理機能**
   - 管理者の追加（最大5人まで）
   - 管理者の一覧表示
   - 管理者の有効/無効切り替え
   - 管理者の削除（論理削除・物理削除対応）

4. **操作ログ記録**
   - 管理者の追加・削除・変更履歴
   - タイムスタンプと操作者の記録
   - セキュリティイベントとしてログ出力

### 非機能要件

1. **セキュリティ**
   - 最大管理者数の制限（初期1人+追加5人=6人）
   - 最後の管理者削除防止
   - 操作権限の厳密なチェック

2. **パフォーマンス**
   - 権限チェックの高速化（キャッシュ機能検討）
   - データベースクエリの最適化

3. **可用性**
   - 初期管理者設定の冗長性確保
   - エラー時の適切なフォールバック

## データベース設計

### admin_users テーブル（既存）

```sql
CREATE TABLE admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    added_by TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
```

### インデックス設計

```sql
-- メールアドレスでの高速検索用
CREATE INDEX idx_admin_users_email ON admin_users(email);

-- アクティブな管理者の検索用
CREATE INDEX idx_admin_users_active ON admin_users(is_active);
```

## API設計

### 権限チェックAPI

#### `is_admin(email: str) -> bool`
- **目的**: メールアドレスが有効な管理者かチェック
- **戻り値**: True/False
- **実装場所**: `database/models.py`

```python
def is_admin(email: str) -> bool:
    """
    メールアドレスが有効な管理者かチェック
    
    Args:
        email: チェック対象のメールアドレス
        
    Returns:
        bool: 有効な管理者の場合True
    """
```

### 管理者管理API

#### `GET /admin/users`
- **目的**: 管理者一覧取得
- **権限**: 管理者のみ
- **レスポンス**:
```json
{
    "users": [
        {
            "id": 1,
            "email": "admin@example.com",
            "added_by": "system",
            "added_at": "2025-01-01T00:00:00+09:00",
            "is_active": true
        }
    ],
    "total": 1,
    "max_admins": 6
}
```

#### `POST /admin/users`
- **目的**: 新規管理者追加
- **権限**: 管理者のみ
- **リクエスト**:
```json
{
    "email": "new-admin@example.com"
}
```

#### `PUT /admin/users/<id>`
- **目的**: 管理者情報更新（有効/無効切り替え）
- **権限**: 管理者のみ
- **リクエスト**:
```json
{
    "is_active": false
}
```

#### `DELETE /admin/users/<id>`
- **目的**: 管理者削除
- **権限**: 管理者のみ
- **クエリパラメータ**: `?permanent=true` で物理削除

## セキュリティ設計

### 権限チェック実装

```python
def require_admin_permission(f):
    """管理者権限必須デコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect('/login')
        
        email = session.get('email')
        if not email or not is_admin(email):
            return render_template('error.html', 
                                 error="管理者権限が必要です"), 403
        
        return f(*args, **kwargs)
    return decorated_function
```

### 操作ログ記録

管理者権限関連の操作は全て `security_event_log` テーブルに記録：

```python
def log_admin_operation(operation: str, target_email: str, 
                       operator_email: str, details: dict = None):
    """管理者操作ログの記録"""
    log_security_event(
        event_type="admin_operation",
        user_identifier=operator_email,
        details={
            "operation": operation,
            "target_email": target_email,
            "timestamp": get_current_time(),
            **details
        }
    )
```

## タイムゾーン対応

本アプリケーションのタイムゾーン統一管理システムに準拠：

```python
# config/timezone.py の関数を使用
from config.timezone import get_current_time, format_datetime_display

def add_admin_user(email: str, added_by: str):
    """管理者追加時のタイムゾーン対応"""
    current_time = get_current_time()  # 統一タイムゾーン取得
    
    # データベース保存
    cursor.execute("""
        INSERT INTO admin_users (email, added_by, added_at)
        VALUES (?, ?, ?)
    """, (email, added_by, current_time))
```

## フロントエンド設計

### 管理画面UI拡張

`templates/admin.html` に「管理者管理」タブを追加：

```html
<div class="tab-content" id="admins">
    <h3>管理者管理</h3>
    
    <!-- 管理者一覧 -->
    <div class="admin-list">
        <table id="admin-table">
            <thead>
                <tr>
                    <th>メールアドレス</th>
                    <th>追加者</th>
                    <th>追加日時</th>
                    <th>状態</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody id="admin-list-body">
                <!-- JavaScriptで動的生成 -->
            </tbody>
        </table>
    </div>
    
    <!-- 管理者追加フォーム -->
    <div class="add-admin-form">
        <h4>新規管理者追加</h4>
        <form id="add-admin-form">
            <input type="email" id="admin-email" placeholder="メールアドレス" required>
            <button type="submit">追加</button>
        </form>
        <p class="limit-info">最大6人まで管理者を設定できます</p>
    </div>
</div>
```

### JavaScript機能

`static/js/admin.js` に管理者管理機能を追加：

```javascript
// 管理者一覧の取得・表示
async function loadAdminUsers() {
    try {
        const response = await fetch('/admin/users');
        const data = await response.json();
        displayAdminUsers(data.users);
        updateAdminCount(data.total, data.max_admins);
    } catch (error) {
        showError('管理者一覧の取得に失敗しました');
    }
}

// 管理者追加
async function addAdminUser(email) {
    try {
        const response = await fetch('/admin/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        
        if (response.ok) {
            showSuccess('管理者を追加しました');
            loadAdminUsers();
        } else {
            const error = await response.json();
            showError(error.message);
        }
    } catch (error) {
        showError('管理者の追加に失敗しました');
    }
}
```

## 実装フェーズ

### Phase 1: 基盤機能

1. **権限チェック関数の実装**
   - `database/models.py` に `is_admin()` 関数追加
   - `@require_admin_permission` デコレータ実装

2. **初期管理者の自動設定**
   - アプリ起動時の初期化処理
   - `.env` の `ADMIN_EMAIL` 読み込み
   - 既存チェックと重複防止

3. **管理画面への権限制御追加**
   - 全管理画面ルートに権限チェック適用
   - 非認証ユーザーのリダイレクト処理

### Phase 2: 管理機能

1. **管理者管理APIの実装**
   - RESTful APIエンドポイント実装
   - バリデーション・エラーハンドリング
   - 操作ログ記録機能

2. **管理画面UIの実装**
   - HTMLテンプレート拡張
   - CSS スタイリング
   - JavaScript機能実装

3. **管理者追加/削除機能**
   - フォーム処理
   - 確認ダイアログ
   - リアルタイム更新

### Phase 3: セキュリティ強化

1. **操作ログの記録**
   - 全管理者操作のログ出力
   - セキュリティイベント統合

2. **エラーハンドリング**
   - 包括的なエラー処理
   - ユーザーフレンドリーなメッセージ

3. **テストケースの作成**
   - 単体テスト・統合テスト
   - セキュリティテスト

## テスト設計

### 単体テスト

```python
def test_is_admin_valid_user():
    """有効な管理者のテスト"""
    assert is_admin("admin@example.com") == True

def test_is_admin_invalid_user():
    """無効ユーザーのテスト"""
    assert is_admin("user@example.com") == False

def test_is_admin_inactive_user():
    """無効化された管理者のテスト"""
    assert is_admin("inactive@example.com") == False
```

### 統合テスト

```python
def test_admin_add_max_limit():
    """管理者数上限テスト"""
    # 5人追加後、6人目の追加が失敗することを確認

def test_admin_delete_last_admin():
    """最後の管理者削除防止テスト"""
    # 最後の管理者が削除できないことを確認
```

## 運用考慮事項

### 監査・ログ

- 管理者権限の付与・剥奪は全てログ記録
- 定期的な管理者アクセス状況の監査
- 不正アクセス試行の検知・アラート

### バックアップ・復旧

- 管理者情報の定期バックアップ
- 初期管理者設定の復旧手順
- 管理者権限喪失時の復旧方法

### 設定変更

- `.env` の `ADMIN_EMAIL` 変更時の対応
- 管理者数上限の調整方法
- タイムゾーン設定変更時の影響

## 影響範囲

### 修正対象ファイル

- `app.py`: 権限チェック機能追加、初期化処理
- `database/models.py`: 管理者関連関数追加
- `templates/admin.html`: 管理者管理UI追加
- `static/js/admin.js`: 管理者管理機能追加
- `static/css/admin.css`: スタイル追加

### 新規作成ファイル

- `tests/test_admin_permission.py`: 管理者権限テスト
- `docs/admin-permission-system-design.md`: 本設計書