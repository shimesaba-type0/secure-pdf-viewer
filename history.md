# 事前共有パスフレーズ認証実装プロジェクト履歴

## プロジェクト概要
Secure PDF Viewerアプリケーションに事前共有パスフレーズ認証システムを実装する。現在のハードコードされたパスワード「demo123」を動的なパスフレーズ管理システムに置き換える。

**パスフレーズ仕様**:
- 長さ: 32文字以上128文字以下
- 許可文字: ASCII文字 (0-9, a-z, A-Z, _, -)
- 管理画面で動的変更可能

## 現在の技術スタック
- **フレームワーク**: Flask 2.3.3
- **データベース**: SQLite3
- **認証**: Flask-Session (セッションベース)
- **フロントエンド**: HTML/CSS/JavaScript
- **パスフレーズハッシュ**: cryptography 41.0.7

## 既存システムの分析結果

### 認証システム（app.py）
```python
# 現在のハードコードされた認証（line 222）
if password == "demo123":
    session['authenticated'] = True
```

### データベース構造（database/models.py）
- `admin_users`: 管理者情報
- `access_logs`: アクセスログ
- `auth_failures`: 認証失敗記録
- `ip_blocks`: IP制限
- `settings`: システム設定

### セキュリティ機能（database/utils.py）
- `hash_email()`: メールハッシュ化
- `is_ip_blocked()`: IP制限チェック
- `check_auth_failures()`: 認証失敗監視

## 完了タスク ✅

### 1. 既存コードベース調査
- app.py の認証ロジック分析
- database/models.py のテーブル構造確認
- database/utils.py のセキュリティ機能確認
- templates/login.html のUI構造確認

### 2. 事前共有パスフレーズ認証設計
- データベース拡張案：shared_passphrases テーブル
- API エンドポイント設計：/api/auth/verify-passphrase, /api/auth/set-passphrase
- フロントエンド改修計画：ログイン画面とパスフレーズ設定画面
- バリデーション機能：32-128文字、ASCII制限 (0-9a-zA-Z_-)

### 4a. ログイン画面改修
**ファイル**: `/home/ope/secure-pdf-viewer/templates/login.html`
**変更内容**:
```html
<!-- 変更前 -->
<p>デモ用パスワード: demo123</p>

<!-- 変更後 -->
<p>事前共有パスフレーズを入力してください（32-128文字、0-9a-zA-Z_-のみ）</p>
```

## 未完了タスク

### 高優先度
- **3a**: shared_passphrases テーブル追加
- **3b**: パスフレーズハッシュ化関数追加（32-128文字バリデーション含む）
- **3c**: パスフレーズ検証API実装
- **3d**: パスフレーズ設定API実装

### 中優先度
- **4b**: 管理者用パスフレーズ設定画面実装
- **5a**: セッション管理ロジック更新
- **5b**: ハードコードパスワード移行
- **6**: データベースマイグレーション（shared_passwords→shared_passphrases）

### 低優先度
- **7a-7c**: 各種テスト実装

## 技術的な実装メモ

### 推奨する shared_passphrases テーブル構造
```sql
CREATE TABLE shared_passphrases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    passphrase_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    created_by TEXT,
    -- バリデーション用メタデータ
    char_count INTEGER NOT NULL,  -- 32-128の範囲チェック
    char_set_valid BOOLEAN DEFAULT TRUE  -- ASCII制限チェック
);
```

### 重要なファイル
- `app.py`: メイン認証ロジック（line 222でハードコードパスワード）
- `database/models.py`: データベーススキーマ
- `database/utils.py`: セキュリティユーティリティ
- `templates/login.html`: ログイン画面（改修済み）
- `static/css/main.css`: スタイリング（.login-* クラス）
- `auth/passphrase.py`: パスフレーズ認証モジュール（新規作成予定）

### セキュリティ考慮事項
- パスフレーズハッシュ化必須
- 文字数制限強制（32-128文字）
- 文字種制限強制（ASCII: 0-9a-zA-Z_-のみ）
- レート制限実装済み（IP制限機能あり）
- 認証失敗ログ記録機能あり
- セッション管理はFlask-Sessionで実装済み

## 次の推奨作業順序
1. 3a: データベースモデル拡張（shared_passphrases）
2. 3b: パスフレーズハッシュ化関数（バリデーション含む）
3. 3c: パスフレーズ検証API
4. 5a: セッション管理更新
5. 5b: ハードコード移行
6. UI/UX改修（パスフレーズ用表示）

## 注意事項
- Git コミットサイズに適したタスク分割済み
- 既存のセキュリティ機能を活用
- Flask のセッションベース認証を継続利用
- UI/UX は既存デザインに準拠