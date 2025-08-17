# アプリケーション内バックアップ・復旧システム設計書

## 概要
管理画面からワンクリックでシステム全体のバックアップ・復旧を実行できる機能の設計

## アーキテクチャ設計

### システム構成
```
Backup System Architecture:
┌─────────────────────────────────────────────────────────────┐
│                    管理画面 UI                                │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ バックアップ実行  │  │ バックアップ一覧  │                   │
│  │     ボタン       │  │   ・ダウンロード  │                   │
│  └─────────────────┘  │   ・削除         │                   │
│           │           └─────────────────┘                   │
└───────────┼─────────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────────────┐
│                    Flask API                                │
│  POST /admin/backup/create     GET /admin/backup/list       │
│  GET  /admin/backup/download   DELETE /admin/backup/delete  │
│  GET  /admin/backup/status                                  │
└───────────┼─────────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────────────┐
│                BackupManager                                │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ Database Backup │  │  File Backup    │                   │
│  │  (SQLite Safe)  │  │  (PDFs, Logs)   │                   │
│  └─────────────────┘  └─────────────────┘                   │
│            │                    │                           │
│  ┌─────────▼────────────────────▼─────────┐                 │
│  │        Archive Creation               │                 │
│  │         (tar.gz)                      │                 │
│  └───────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### データフロー
```
1. バックアップ実行フロー:
   UI操作 → API呼び出し → BackupManager
   → SQLite安全バックアップ → ファイル収集 → アーカイブ化
   → メタデータ保存 → 完了通知

2. 進行状況表示フロー:
   BackupManager → SSE送信 → フロントエンド更新

3. 一覧表示フロー:
   API呼び出し → メタデータ読み込み → JSON返却 → UI表示
```

## 技術仕様

### バックアップ対象データ
1. **SQLiteデータベース** (`instance/database.db`)
   - SQLite `.backup` コマンドによる安全バックアップ
   - スキーマ情報も併せてエクスポート

2. **設定ファイル** (`.env`)
   - 機密情報（パスワード、秘密鍵）のマスク処理
   - バックアップ用の安全な形式で保存

3. **PDFファイル** (`static/pdfs/`)
   - アップロード済み全PDFファイル
   - ファイル整合性チェック付き

4. **重要ログ** (`logs/app.log`, `instance/emergency_log.txt`)
   - 運用履歴の保存

### セキュリティ設計

#### アクセス制御
- 管理者権限必須
- バックアップファイルのアクセス権限: 600（所有者のみ）
- バックアップディレクトリのアクセス権限: 700

#### 機密情報保護
```python
# .envファイル内の機密情報マスク
sensitive_keys = ['SECRET_KEY', 'PASSWORD', 'API_KEY', 'TOKEN', 'PRIVATE']
# 例: SECRET_KEY=abc123 → SECRET_KEY=***MASKED***
```

#### パス・トラバーサル対策
- ファイル名のサニタイズ
- 許可されたディレクトリ内のみアクセス
- バックアップファイルの検証

### ファイル構造設計

#### バックアップディレクトリ構造
```
backups/
├── manual/                    # 手動バックアップ
│   ├── backup_20250730_143025.tar.gz
│   └── backup_20250730_120000.tar.gz
├── auto/                      # 自動バックアップ（将来実装）
│   ├── daily_20250730.tar.gz
│   └── daily_20250729.tar.gz
└── metadata/                  # メタデータ
    ├── backup_20250730_143025.json
    └── daily_20250730.json
```

#### アーカイブ内部構造
```
backup_20250730_143025/
├── database/
│   ├── database.db            # 安全バックアップ
│   └── database_schema.sql    # スキーマ情報
├── config/
│   └── .env                   # マスク済み設定
├── files/
│   └── pdfs/                  # PDFファイル群
├── logs/
│   ├── app.log
│   └── emergency_log.txt
└── metadata.json              # バックアップ詳細情報
```

### API設計

#### エンドポイント一覧
```python
POST   /admin/backup/create     # バックアップ実行
GET    /admin/backup/list       # バックアップ一覧取得
GET    /admin/backup/download   # バックアップダウンロード
DELETE /admin/backup/delete     # バックアップ削除
POST   /admin/backup/restore    # 復旧実行（明示的文字列認証）
GET    /admin/backup/status     # 実行状況取得（SSE）
```

#### APIレスポンス形式
```json
{
  "status": "success|error|in_progress",
  "message": "実行結果メッセージ",
  "data": {
    "backup_name": "backup_20250730_143025",
    "timestamp": "20250730_143025",
    "size": 1048576,
    "files_count": 15,
    "checksum": "sha256:abc123..."
  }
}
```

### UI設計

#### 管理画面追加セクション
```html
<!-- バックアップセクション -->
<div class="backup-section">
  <h3>システムバックアップ</h3>
  
  <!-- 実行コントロール -->
  <div class="backup-controls">
    <button id="create-backup-btn">バックアップ実行</button>
    <div id="backup-progress" class="hidden">
      <div class="progress-bar">
        <div class="progress-fill"></div>
      </div>
      <div class="progress-text">準備中...</div>
    </div>
  </div>
  
  <!-- バックアップ一覧 -->
  <div class="backup-list">
    <table id="backup-table">
      <thead>
        <tr>
          <th>作成日時</th>
          <th>タイプ</th>
          <th>サイズ</th>
          <th>状態</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody id="backup-list-body">
        <!-- 動的に生成 -->
      </tbody>
    </table>
  </div>
</div>
```

## 実装コンポーネント

### 1. バックアップコア機能 (`database/backup.py`)
```python
class BackupManager:
    def create_backup()          # メインバックアップ処理
    def _backup_database()       # SQLite安全バックアップ
    def _backup_config_files()   # 設定ファイルバックアップ
    def _backup_pdf_files()      # PDFファイルバックアップ
    def _backup_log_files()      # ログファイルバックアップ
    def _create_archive()        # tar.gz アーカイブ作成
    def list_backups()           # バックアップ一覧
    def delete_backup()          # バックアップ削除
    def get_backup_path()        # ダウンロード用パス取得
```

### 2. API エンドポイント (`app.py`)
```python
@app.route('/admin/backup/create', methods=['POST'])
@requires_admin
def create_backup():
    # 非同期バックアップ実行
    # SSEで進行状況送信

@app.route('/admin/backup/list', methods=['GET'])
@requires_admin  
def list_backups():
    # バックアップ一覧JSON返却

@app.route('/admin/backup/download/<backup_name>')
@requires_admin
def download_backup(backup_name):
    # セキュアファイルダウンロード

@app.route('/admin/backup/delete/<backup_name>', methods=['DELETE'])
@requires_admin
def delete_backup(backup_name):
    # バックアップファイル削除

@app.route('/admin/backup/status')
@requires_admin
def backup_status():
    # SSE進行状況ストリーム
```

### 3. フロントエンド処理 (`static/js/backup.js`)
```javascript
class BackupManager {
    createBackup()           // バックアップ実行
    loadBackupList()         // 一覧更新
    downloadBackup()         // ダウンロード
    deleteBackup()           // 削除
    showProgress()           // 進行状況表示
    connectSSE()             // Server-Sent Events接続
}
```

### 4. スタイル (`static/css/main.css`)
- バックアップセクションのレスポンシブデザイン
- 進行状況バー
- バックアップ一覧テーブル

## パフォーマンス考慮事項

### 非同期処理
- バックアップ処理は別スレッドで実行
- メインアプリケーションの動作に影響なし
- SSEによるリアルタイム進行状況表示

### 大容量ファイル対応
- チャンク単位でのファイル処理
- メモリ使用量の最適化
- 進行状況の細かい更新

### エラーハンドリング
- 各段階でのエラー捕捉
- 部分バックアップの継続実行
- 詳細なエラーログ記録

## セキュリティ検証項目

### 入力検証
- [ ] ファイル名のサニタイズ
- [ ] パス・トラバーサル防止
- [ ] ファイルサイズ制限

### アクセス制御
- [ ] 管理者権限確認
- [ ] セッション検証
- [ ] CSRF対策

### ファイル保護
- [ ] バックアップファイルの暗号化（オプション）
- [ ] アクセス権限設定
- [ ] 機密情報マスク

## テスト戦略

### 単体テスト
- BackupManager各メソッド
- API エンドポイント
- フロントエンド関数

### 統合テスト
- エンドツーエンドバックアップ
- UI操作テスト
- エラーシナリオテスト

### セキュリティテスト
- 権限チェック
- パストラバーサル攻撃
- 機密情報漏洩防止

## 運用考慮事項

### 監視項目
- バックアップ実行状況
- ディスク使用量
- エラー発生率

### アラート条件
- バックアップ失敗
- ディスク容量不足
- 権限エラー

### メンテナンス
- 古いバックアップの自動削除
- 定期的な整合性チェック
- ログローテーション

## 復旧機能設計（Phase 3）

### 復旧機能アーキテクチャ

#### システム構成
```
Restore System Architecture:
┌─────────────────────────────────────────────────────────────┐
│                    管理画面 UI                                │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ バックアップ一覧  │  │   復旧モーダル    │                   │
│  │   「復旧」ボタン  │  │ ・警告メッセージ   │                   │
│  └─────────────────┘  │ ・文字列入力確認   │                   │
│           │           └─────────────────┘                   │
└───────────┼─────────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────────────┐
│                 復旧確認システム                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 明示的文字列認証: 「復旧を実行します」完全一致入力        │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────┼─────────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────────────┐
│                  RestoreManager                             │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ 復旧前セーフティ  │  │   復旧実行処理   │                   │
│  │   ネット作成     │  │ ・tar.gz展開    │                   │
│  │（自動バックアップ）│  │ ・ファイル配置   │                   │
│  └─────────────────┘  └─────────────────┘                   │
│            │                    │                           │
│  ┌─────────▼────────────────────▼─────────┐                 │
│  │       整合性チェック・ログ記録           │                 │
│  └───────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### 復旧フロー設計

#### 1. 復旧操作の本質
**tar.gz展開 → ファイル配置**（SQLiteも単純なファイル操作）

#### 2. 権限設計
- **バックアップ閲覧・作成・ダウンロード** → 通常管理者 ✅
- **バックアップ復旧・削除** → 管理者 + 明示的確認入力 ⚠️

#### 3. 安全確認システム
```
復旧ボタン → モーダル表示 → 明示的文字列入力 → 最終確認 → 実行
    ↑              ↑                ↑              ↑         ↑
  衝動的        一時停止         熟考時間        最終確認    実行
```

#### 4. 復旧フロー詳細
```
1. 管理画面でバックアップ一覧表示
2. 復旧対象の「復旧」ボタンクリック
3. 復旧確認モーダル表示
   - 復旧対象情報表示（名前・日時・サイズ）
   - 警告メッセージ表示
   - 明示的文字列入力欄（「復旧を実行します」）
4. 文字列完全一致確認後に実行ボタン有効化
5. 復旧実行開始
   a. 現在データの自動バックアップ作成（復旧前セーフティネット）
   b. tar.gz展開・ファイル配置
   c. 整合性チェック
   d. 復旧完了ログ記録
6. 復旧結果通知・画面更新
```

### 復旧API設計

#### 復旧エンドポイント
```python
@app.route('/admin/backup/restore', methods=['POST'])
@requires_admin
def restore_backup():
    """
    復旧実行API
    
    Request Body:
    {
        "backup_name": "backup_20250730_143025",
        "confirmation_text": "復旧を実行します"
    }
    
    Response:
    {
        "status": "success|error|in_progress",
        "message": "復旧実行開始",
        "data": {
            "restore_id": "restore_20250817_190000",
            "pre_restore_backup": "pre_restore_20250817_190000",
            "estimated_time": 60
        }
    }
    """
```

### 復旧コンポーネント設計

#### BackupManager拡張 (`database/backup.py`)
```python
class BackupManager:
    # 既存機能
    def create_backup()
    def list_backups()
    def delete_backup()
    
    # Phase 3追加機能
    def restore_from_backup(backup_name):
        """
        バックアップからの復旧実行
        1. 復旧前自動バックアップ作成
        2. tar.gz展開
        3. ファイル配置
        4. 整合性チェック
        5. ログ記録
        """
    
    def _create_pre_restore_backup():
        """復旧前セーフティネット作成"""
    
    def _extract_and_restore_files(backup_path):
        """アーカイブ展開・ファイル配置"""
    
    def _verify_restore_integrity():
        """復旧後整合性チェック"""
    
    def _log_restore_operation():
        """復旧操作ログ記録"""
```

#### フロントエンド拡張 (`static/js/backup.js`)
```javascript
class BackupManager {
    // 既存機能
    createBackup()
    loadBackupList()
    
    // Phase 3追加機能
    showRestoreModal(backupName) {
        // 復旧確認モーダル表示
        // 警告メッセージ・文字列入力欄
    }
    
    validateConfirmationText() {
        // 「復旧を実行します」完全一致確認
        // 実行ボタン有効化制御
    }
    
    executeRestore(backupName, confirmationText) {
        // 復旧実行API呼び出し
        // 進行状況表示（SSE）
    }
    
    showRestoreProgress() {
        // 復旧進行状況表示
    }
}
```

### セキュリティ設計

#### 明示的文字列認証
- **入力文字列**: 「復旧を実行します」
- **認証方式**: 完全一致確認
- **選択理由**:
  - 実装簡潔性（Phase 3早期完成）
  - 緊急時の確実性（メール遅延リスク回避）
  - 十分な誤操作防止効果

#### 復旧セキュリティ考慮事項
- **復旧前セーフティネット**: 現在データの自動バックアップ
- **操作ログ記録**: 復旧実行者・日時・対象の完全記録
- **整合性チェック**: 復旧後のデータ検証
- **誤操作防止**: 明示的文字列入力による二重確認

#### 将来拡張検討事項
- **OTP認証**: メールOTPによるセキュリティ強化
- **段階的権限**: スーパー管理者権限の導入
- **復旧スケジューリング**: 指定時刻での復旧実行

### 復旧UI設計

#### 復旧確認モーダル
```html
<!-- 復旧確認モーダル -->
<div id="restore-modal" class="modal">
  <div class="modal-content">
    <h3>⚠️ データ復旧の実行</h3>
    
    <!-- 復旧対象情報 -->
    <div class="restore-info">
      <p><strong>復旧対象:</strong> <span id="restore-backup-name"></span></p>
      <p><strong>作成日時:</strong> <span id="restore-backup-date"></span></p>
      <p><strong>サイズ:</strong> <span id="restore-backup-size"></span></p>
    </div>
    
    <!-- 警告メッセージ -->
    <div class="warning-message">
      <p>⚠️ <strong>警告:</strong> 現在のデータが完全に置き換えられます</p>
      <p>✅ 復旧前に自動バックアップを作成します</p>
      <p>❌ この操作は取り消せません</p>
    </div>
    
    <!-- 明示的文字列入力 -->
    <div class="confirmation-input">
      <label>確認のため、以下を正確に入力してください:</label>
      <input type="text" id="confirmation-text" placeholder="復旧を実行します">
      <small>完全一致しないと実行ボタンが有効化されません</small>
    </div>
    
    <!-- 実行ボタン -->
    <div class="modal-actions">
      <button id="execute-restore-btn" disabled>復旧実行</button>
      <button id="cancel-restore-btn">キャンセル</button>
    </div>
  </div>
</div>
```

### パフォーマンス考慮事項

#### 復旧処理最適化
- **非同期実行**: メインアプリケーションへの影響最小化
- **進行状況表示**: SSEによるリアルタイム更新
- **ファイル処理**: 大容量対応のチャンク処理

#### 復旧時間見積もり
- **小規模環境** (< 100MB): 30-60秒
- **中規模環境** (100MB-1GB): 1-3分
- **大規模環境** (> 1GB): 3-10分

### テスト戦略

#### 復旧機能テスト
```python
# tests/test_backup_restore.py
class TestBackupRestore:
    def test_restore_with_confirmation()
    def test_restore_without_confirmation()
    def test_pre_restore_backup_creation()
    def test_restore_integrity_check()
    def test_restore_logging()
    def test_restore_ui_flow()
```

#### セキュリティテスト
- 不正復旧実行防止
- 明示的文字列認証バイパス試行
- 復旧権限チェック

この復旧機能設計により、セキュアで信頼性の高いバックアップ・復旧システムが完成します。