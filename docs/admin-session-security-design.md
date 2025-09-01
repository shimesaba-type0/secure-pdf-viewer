# 管理者セッション強化設計書

## 概要

管理者セッションの特別管理、セッションハイジャック対策、完全なセッション無効化機能の設計。

## 現在の実装状況

### 既存機能
- `require_valid_session()`: セッション有効性検証
- `@require_admin_permission`: 管理者権限デコレータ  
- `session_stats`: セッション統計テーブル
- `invalidate_all_sessions()`: 全セッション無効化

### 課題
- 管理者セッションと一般セッションが同じ管理方法
- セッションハイジャック対策が不十分
- ログアウト時のセッション削除が不完全

## 機能設計

### 1. 管理者セッション特別管理

#### admin_sessionsテーブル
```sql
CREATE TABLE admin_sessions (
    session_id TEXT PRIMARY KEY,
    admin_email TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_verified_at TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    security_flags JSON,
    verification_token TEXT
);
```

#### 管理者専用セッション関数
```python
def create_admin_session(admin_email, session_id, ip_address, user_agent):
    """管理者セッション作成"""
    
def verify_admin_session(session_id, ip_address, user_agent):
    """管理者セッション検証"""
    
def update_admin_session_verification(session_id):
    """管理者セッション検証時刻更新"""
```

#### 設定項目
- `admin_session_timeout`: 管理者セッション有効期限（秒）
- `admin_session_verification_interval`: セッション再検証間隔（秒）
- `admin_session_ip_binding`: IPアドレス固定有効化

### 2. セッションハイジャック対策

#### セッション固定攻撃対策
```python
def regenerate_admin_session_id():
    """管理者ログイン時のセッションID再生成"""
    
def generate_session_verification_token():
    """セッション検証トークン生成"""
```

#### セッション盗用対策  
```python
def verify_session_environment(session_id, current_ip, current_ua):
    """セッション環境の検証"""
    # IPアドレス検証
    # ユーザーエージェント検証
    # 異常パターン検出
```

### 3. 完全セッション無効化

#### 管理者専用ログアウト
```python
def admin_complete_logout(admin_email, session_id):
    """管理者の完全ログアウト処理"""
    # 1. admin_sessionsからの削除
    # 2. session_statsからの削除  
    # 3. 関連OTPトークンの削除
    # 4. Flaskセッション削除
    # 5. セキュリティログ記録
    # 6. クライアント通知
```

#### 多層削除機能
```python
def invalidate_admin_session_completely(session_id):
    """管理者セッションの完全無効化"""
    
def cleanup_related_tokens(session_id):
    """セッション関連トークンのクリーンアップ"""
```

### 4. 強化されたデコレータ

#### 管理者専用デコレータ
```python
def require_admin_session(f):
    """管理者セッション必須デコレータ（強化版）"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. 基本認証確認
        # 2. 管理者権限確認
        # 3. admin_sessionsテーブル確認
        # 4. セッション環境検証
        # 5. 検証時刻更新
```

## データベース設計

### テーブル追加
- `admin_sessions`: 管理者専用セッション管理
- `admin_actions`: 管理者操作ログ（TASK-021で追加予定）

### 設定追加
```sql
INSERT INTO settings (key, value, value_type, description, category) VALUES
('admin_session_timeout', '1800', 'integer', '管理者セッション有効期限（秒）', 'security'),
('admin_session_verification_interval', '300', 'integer', 'セッション再検証間隔（秒）', 'security'),
('admin_session_ip_binding', 'true', 'boolean', 'IPアドレス固定有効化', 'security');
```

## API設計

### 内部API
- `create_admin_session()`: 管理者セッション作成
- `verify_admin_session()`: セッション検証
- `admin_complete_logout()`: 完全ログアウト
- `verify_session_environment()`: 環境検証

### エンドポイント変更
- `/auth/logout`: 管理者の場合は特別処理
- 全管理者ルート: `@require_admin_session` デコレータ適用

## セキュリティ要件

### 認証強化
- セッション固定攻撃の防止
- セッション盗用の検出・防止
- IPアドレスバインディング（オプション）

### ログ・監査
- 管理者セッション操作の全記録
- セッション異常の検出・記録
- セキュリティイベントログとの連携

### パフォーマンス
- セッション検証の効率化
- データベースクエリ最適化
- キャッシュ機能の活用

## 成功基準

- 管理者セッションが独立して管理される
- セッション固定攻撃が防止される
- セッションハイジャック試行が検出される
- ログアウト時にセッションが完全無効化される
- 異常セッションパターンが検出される
- セキュリティイベントが適切に記録される