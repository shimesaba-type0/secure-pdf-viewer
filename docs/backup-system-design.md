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

この設計により、セキュアで信頼性の高いバックアップシステムを実装できます。