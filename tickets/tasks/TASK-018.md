# TASK-018: アプリケーション内バックアップ・復旧システム

## 概要
管理画面からワンクリックでシステム全体のバックアップ・復旧を実行できる機能の実装

## 背景
現在のシステムは手動でのファイルコピーによるバックアップに依存しており、以下の課題があります：
- 管理者が手動でコマンド実行する必要がある
- SQLite実行中の安全でないファイルコピーのリスク
- バックアップファイルの管理が煩雑
- 定期バックアップの仕組みがない
- 復旧手順が明確でない

## 要件

### 機能要件

#### 1. バックアップ機能
**対象データ:**
- SQLiteデータベース (`instance/database.db`) - SQLite安全コマンド使用
- 設定ファイル (`.env`)
- アップロード済みPDFファイル (`static/pdfs/`)
- 重要ログファイル (`logs/app.log`, `instance/emergency_log.txt`)

**バックアップ方式:**
```python
# SQLite安全バックアップ
sqlite3 database.db ".backup backup_file.db"

# アーカイブ作成
tar.gz形式でまとめて圧縮
```

#### 2. 管理画面UI
**バックアップセクション:**
- 手動バックアップ実行ボタン
- バックアップ進行状況表示
- バックアップファイル一覧（作成日時、サイズ）
- ダウンロード機能
- 削除機能（世代管理）

**設定項目:**
- 自動バックアップ有効/無効
- バックアップ実行間隔（日次/週次）
- 保持世代数（デフォルト30日）
- バックアップ保存先パス

#### 3. 復旧機能（慎重実装）
- バックアップファイルからの復旧
- 復旧前の現在データ自動バックアップ
- 復旧実行確認（管理者認証）
- 復旧ログの記録

### 非機能要件

#### セキュリティ
- バックアップファイルの暗号化（オプション）
- アクセス制御（管理者のみ）
- バックアップファイルのパス traversal 対策
- 復旧時の整合性チェック

#### パフォーマンス
- バックアップ実行中のアプリケーション動作継続
- 大容量PDFファイル対応
- 非同期実行（進行状況表示）

#### 運用性
- バックアップ失敗時のアラート
- ディスク容量監視
- ログ出力（実行履歴）

## 実装方針

### 設計ドキュメント
詳細な技術設計は `docs/backup-system-design.md` を参照

### 実装フェーズ分割

#### Phase 1A: コア機能基盤（1-2時間）
**目標**: バックアップコア機能の実装と基本テスト
- `database/backup.py` の BackupManager クラス実装
- SQLite安全バックアップ、ファイル収集、アーカイブ化
- 単体テスト作成・実行
- lint・formatter実行

**成果物**:
- 動作する BackupManager クラス
- 単体テストの成功
- SQLite、PDFファイル、ログのバックアップ確認

#### Phase 1B: API実装（1-2時間）  
**目標**: Flask APIエンドポイントの実装とテスト
- `app.py` にバックアップAPIエンドポイント追加
  - POST /admin/backup/create
  - GET /admin/backup/list  
  - GET /admin/backup/download
  - DELETE /admin/backup/delete
  - GET /admin/backup/status（SSE）
- APIテスト作成・実行
- エラーハンドリング・セキュリティ検証

**成果物**:
- 動作するAPIエンドポイント
- APIテストの成功
- セキュリティチェック完了

#### Phase 1C: UI実装（1-2時間）
**目標**: 管理画面UIとフロントエンド処理の実装
- `templates/admin.html` にバックアップセクション追加
- `static/js/backup.js` フロントエンド処理実装
- `static/css/main.css` レスポンシブスタイル追加
- UI操作テスト

**成果物**:
- バックアップセクション付き管理画面
- 動作するフロントエンド機能
- レスポンシブデザイン確認

#### Phase 1D: 統合・動作確認（1時間）
**目標**: エンドツーエンド動作確認と最終検証
- 統合テスト実行
- ブラウザでの動作確認
- セキュリティ検証
- パフォーマンステスト

**成果物**:
- 完全に動作するバックアップシステム
- 全テスト成功
- 本番レディ状態

### Phase 2以降: スケジューリング・復旧機能
Phase 1完了後、別セッションで実装予定

## 技術詳細

### ディレクトリ構造
```
backups/
├── manual/
│   ├── backup_20250730_143025.tar.gz
│   └── backup_20250730_120000.tar.gz
├── auto/
│   ├── daily_20250730.tar.gz
│   └── daily_20250729.tar.gz
└── metadata/
    ├── backup_20250730_143025.json
    └── daily_20250730.json
```

### バックアップアーカイブ構造
```
backup_20250730_143025/
├── database/
│   ├── database.db          # SQLite安全バックアップ
│   └── database_schema.sql  # スキーマ情報
├── config/
│   └── .env                 # 設定ファイル（秘匿情報マスク版）
├── files/
│   └── pdfs/                # PDFファイル
├── logs/
│   ├── app.log
│   └── emergency_log.txt
└── metadata.json            # バックアップ情報
```

### APIエンドポイント
```python
# 管理者用API
POST /admin/backup/create     # バックアップ実行
GET  /admin/backup/list       # バックアップ一覧
GET  /admin/backup/download   # ダウンロード
DELETE /admin/backup/delete   # 削除
POST /admin/backup/restore    # 復旧実行（Phase 3）
GET  /admin/backup/status     # 実行状況取得
```

## 実装対象ファイル

### 新規作成
- `database/backup.py` - バックアップコア機能
- `static/js/backup.js` - フロントエンド処理
- `templates/admin_backup.html` - 管理画面UI（または admin.html 拡張）

### 修正対象
- `app.py` - APIエンドポイント追加
- `templates/admin.html` - バックアップセクション追加
- `static/css/main.css` - スタイル追加

## 成功条件

### Phase 1A: コア機能基盤 ✅ **完了** (2025-01-31)
- [x] **BackupManagerクラス実装完了** - `database/backup.py`
- [x] **SQLiteデータベースが安全にバックアップされる** - `.backup`コマンド使用
- [x] **.env、PDFファイル、ログが含まれる** - 機密情報マスク処理付き
- [x] **tar.gz形式でアーカイブ化される** - セキュアな権限設定
- [x] **バックアップファイル一覧・削除・パス取得機能** - 実装済み
- [x] **包括的単体テスト完了** - 11テストケース全成功
- [x] **セキュリティ対策実装** - Path Traversal対策、チェックサム検証
- [x] **コード品質確認** - Black formatter、Flake8 linter通過

**コミット**: `7017619` - feat: TASK-018 Phase 1A完了 - BackupManagerコア機能実装

### Phase 1B: API実装 ✅ **完了** (2025-01-31)
- [x] **APIエンドポイント実装完了** - POST /admin/backup/create 等5つのエンドポイント
- [x] **認証・セキュリティ対策実装** - セッション検証、パストラバーサル対策
- [x] **非同期バックアップ実行** - 別スレッドでの実行、進行状況管理
- [x] **SSE対応** - Server-Sent Events による進行状況のリアルタイム通知
- [x] **APIテスト完了** - 15テストケース作成、セキュリティテスト含む
- [x] **統合テスト完了** - BackupManager 11テスト全成功
- [x] **動作確認完了** - 実際のアプリケーションでAPIレスポンス確認

### Phase 1C: UI実装 ✅ **完了** (2025-08-07)
- [x] **管理画面バックアップセクション実装完了** - `templates/admin.html`
- [x] **フロントエンド処理実装完了** - `static/js/backup.js` (BackupManagerクラス)
- [x] **レスポンシブスタイル追加** - `static/css/main.css` (330行追加)
- [x] **Server-Sent Events対応** - リアルタイム進行状況表示
- [x] **API統合完了** - Phase 1B APIエンドポイント完全連携
- [x] **UIテスト作成** - `tests/test_backup_ui.py` (Selenium統合テスト)
- [x] **品質保証完了** - Black formatter・Flake8 linter通過
- [x] **静的ファイル配信確認** - JavaScript・CSS正常配信
- [x] **レスポンシブ対応** - モバイル・タブレット・PC対応

**コミット**: `329d455` - feat: TASK-018 Phase 1C完了 - バックアップUI実装

### Phase 1D: 統合・動作確認（次回セッション予定）
- [ ] エンドツーエンドテスト実行
- [ ] 管理者認証でのフル動作確認
- [ ] ブラウザでの実バックアップ動作テスト

### Phase 2
- [ ] 定期バックアップが設定・実行される
- [ ] 世代管理（古いファイル自動削除）が動作する
- [ ] バックアップ設定が管理画面から変更できる

### Phase 3
- [ ] バックアップからの復旧が実行できる
- [ ] 復旧前の自動バックアップが作成される
- [ ] 復旧実行時の安全確認が動作する

## 優先度
**High** - 本番運用に必須の機能

## 見積もり工数
- **Phase 1A**: ✅ **完了** 2時間（コア機能基盤）
- **Phase 1B**: ✅ **完了** 2時間（API実装）
- **Phase 1C**: ✅ **完了** 2時間（UI実装）
- **Phase 1D**: 1時間（統合・動作確認）
- **Phase 2**: 2-3時間（スケジューリング・世代管理）
- **Phase 3**: 3-4時間（復旧機能）
- **合計**: 9-13時間（Phase 1A-1C: 6時間完了済み）

## 関連チケット
- TASK-001〜017: 全機能のデータ保護対象
- Phase 4 インフラ準備との連携

## セキュリティ考慮事項

### 機密情報の取り扱い
- `.env`ファイル内のパスワード・秘密鍵のマスク処理
- バックアップファイルのアクセス権限設定（600）
- バックアップディレクトリの外部アクセス防止

### 攻撃対策
- ファイル名のサニタイズ（Path Traversal対策）
- バックアップファイルサイズ制限
- 復旧時の整合性検証

## 進捗状況

### 完了済み
- **2025-01-31**: Phase 1A完了（BackupManagerコア機能）
  - コミット: `7017619`
  - 実装: `database/backup.py`
  - テスト: `tests/test_backup_manager.py` (11テスト成功)
  - 動作確認: `tests/test_backup_manual.py`

### 完了済み
- **2025-01-31**: Phase 1B完了（Flask APIエンドポイント実装）
  - 実装: `app.py` 行3611-3860 (バックアップAPI 5エンドポイント)
  - テスト: `tests/test_backup_api.py` (15テストケース)
  - セキュリティ: パストラバーサル対策、認証検証
  - 非同期: バックアップ実行、SSE進行状況通知

### 完了済み
- **2025-08-07**: Phase 1C完了（バックアップUI実装）
  - 実装: `templates/admin.html` バックアップセクション追加
  - 実装: `static/js/backup.js` BackupManagerクラス (400行)
  - 実装: `static/css/main.css` レスポンシブスタイル (330行)
  - テスト: `tests/test_backup_ui.py` Seleniumブラウザテスト
  - 機能: Server-Sent Events リアルタイム進行表示
  - 品質: Black・Flake8完全準拠、静的ファイル配信確認

### 次回セッション予定  
- Phase 1D: 統合・動作確認（エンドツーエンドテスト）

## 備考
- 本機能により運用時のデータ保護が大幅に向上
- 災害復旧・移行作業が簡素化される
- Phase 4（本番環境構築）での必須要件
- 外部ストレージ連携（AWS S3等）は将来拡張として検討