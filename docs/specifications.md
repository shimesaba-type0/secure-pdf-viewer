# セキュアPDF閲覧システム 仕様書

## 1. システム概要

セキュアなPDF資料の限定公開・閲覧システム。特定の人のみが指定期間内にPDF資料を閲覧可能。

### 対象ユーザー
- 閲覧権限者：約30人
- 想定同時アクセス：10人程度
- 想定端末数：45?90台（複数端末利用考慮）

## 2. アーキテクチャ

### インフラ構成
```
インターネット → Cloudflare → localhost（あなたのホスト）
```

| コンポーネント | 役割 | 技術 |
|---------------|------|------|
| **Cloudflare** | DNS、CDN、DDoS対策、地理的制限 | DNS Proxy, Security Rules |
| **localhost** | メインアプリケーション（モノシリック） | Flask |
| **さくらメール** | OTP送信 | SMTP (port 465) |
| **データベース** | ユーザー認証、ログ管理 | SQLite3 |

## 3. 機能要件

### 3.1 認証機能

1. **2段階認証システム**
   - **必須要件**: 全ユーザーが必ず2段階認証を経る必要がある
   - **第1段階**: 事前共有パスフレーズ認証
   - **第2段階**: メールアドレス経由OTP認証
   - **セキュリティ強化**: どちらか一方のみでのアクセスは不可

2. **事前共有パスフレーズ認証（第1段階）**
   - 全ユーザー共通パスフレーズ
   - 長さ: 32文字以上128文字以下
   - 許可文字: ASCII文字 (0-9, a-z, A-Z, _, -)
   - 管理画面で変更可能
   - **認証完了時の動作**: 既存セッション情報を完全クリア、第2段階認証へ移行

3. **OTP認証（第2段階）**
   - メールアドレス入力によるOTP送信
   - OTP有効期限: 10分間
   - 認証成功時のみ `session['authenticated'] = True` 設定
   - **完全認証完了**: 両段階の認証が完了した時点でコンテンツアクセス権限付与

### 3.2 セッション管理

- **セッション有効期限**: 72時間（3日間）
- **自動延長**: なし（シンプルな実装）
- **強制ログアウト条件**:
  - 設定時刻での定時全セッション無効化（管理画面で時刻設定可能）
  - 管理者による手動全ユーザー強制ログアウト実行時
  - 異常なアクセスパターン検知時
- **パスフレーズ変更時の動作**: 管理者セッションは継続、変更完了メッセージ表示

**セキュリティ強化 (2段階認証保護 - TASK-003-8対応完了)**
- **認証状態分離**: `session['passphrase_verified']` と `session['authenticated']` を分離管理
- **再認証時の挙動**: パスフレーズ認証成功時に既存の全セッション情報を完全クリア (`session.clear()`)
- **アクセス制御**: `session['authenticated'] = True` が設定されている場合のみコンテンツアクセス許可
- **セッション整合性チェック**: データベース記録との照合による2段階認証バイパス防止
  - セッションID、認証完了時刻、メールアドレスハッシュの整合性確認
  - 不整合検出時の自動セッションクリア・強制再認証
- **一貫したハッシュ関数**: SHA256ベースの `get_consistent_hash()` によるメールアドレスハッシュ管理
- **SSE接続管理**: SSE統一管理システムによる効率的なリアルタイム通知

**セッション制限監視機能 (TASK-003-5対応完了)**
- **同時接続数制限**: 管理画面で設定可能（1-1000セッション、デフォルト100）
- **制限チェック**: OTP認証完了前に実行、制限到達時は認証拒否
- **警告システム**: 80%以上で警告、90%以上でアラート（SSE経由通知）
- **リアルタイム監視**: 30秒間隔での自動更新、使用率表示
- **設定管理**: データベース設定 `max_concurrent_sessions`, `session_limit_enabled`

**72時間設定の理由:**
- 資料の典型的利用パターン（配布→議論→決定）に適合
- ユーザーフレンドリー（週2-3回のログインで済む）
- セキュリティ確保（3日で自動切断、緊急時即座対応可能）
- 実装がシンプル（自動延長ロジック不要）

### 3.3 アクセス制限
1. **地理的制限**
   - 日本国内からのみアクセス許可
   - 海外IPを自動拒否

2. **レート制限**
   - 10分間で5回認証失敗 → 30分間IP制限
   - 管理画面で制限解除可能

3. **公開期間制限**
   - 開始日時・終了日時設定
   - 期間外は自動アクセス拒否

### 3.4 PDF閲覧機能
1. **PDF表示**
   - PDF.js による埋め込み表示
   - 印刷・ダウンロード無効化
   - 右クリック無効化
   - **全画面表示機能**（F11キー、専用ボタン対応）

2. **ナビゲーション機能**
   - **最初のページボタン**（⏮アイコン、1ページ目で無効化、TASK-012対応）
   - ページ送り（前/次）ボタン
   - ページ番号入力によるジャンプ
   - キーボードショートカット（矢印キー、Home/Endキー）

3. **レスポンシブデザイン対応**
   - **マルチデバイス対応**: スマートフォン、タブレット、PCなど、デバイスを選ばずに表示が整うように設計
   - **ブレークポイント設計**:
     - デスクトップ: 769px以上（フル機能表示）
     - タブレット: 480px?768px（中間レイアウト）
     - スマートフォン: 480px以下（コンパクト表示）
   - **動的レイアウト調整**:
     - ツールバー：デバイスサイズに応じて改行・縦積み対応
     - PDF表示：画面幅に応じた自動スケーリング
     - ウォーターマーク：デバイスサイズに応じた位置・文字サイズ調整
   - **操作性最適化**:
     - タッチ操作対応（スマホ・タブレット）
     - 画面回転対応（orientationchange検知）
     - リアルタイム画面サイズ変更対応

4. **ウォーターマーク仕様**
   - **配置**: 各ページ右上（デバイスに応じて調整）
     - デスクトップ: 上から20px、右から20px
     - タブレット: 上から10px、右から10px  
     - スマートフォン: 上から5px、右から5px
   - **フォントサイズ**: デバイス対応
     - デスクトップ: 10px
     - タブレット: 9px
     - スマートフォン: 8px
   - **フォント**: Courier New（等幅フォント）
   - **透明度**: 0.3（控えめで文書の可読性を確保）
   - **背景**: 半透明白背景（rgba(255, 255, 255, 0.8)）
   - **境界線**: 1px 薄いグレー境界線
   - **角丸**: 4px border-radius
   - **パディング**: デバイスに応じて調整
   - **改行制御**: 小画面でも読みやすい表示
   
   **表示内容（4行構成）:**
   ```
   著作者: [著作者名]
   閲覧者: [ユーザーメールアドレス]
   日時: YYYY-MM-DD HH:mm:ss
   SID: [セッションID]
   ```
   
   **動的要素:**
   - 著作者名: 設定で指定された著作者名（例：「資料作成者」「組織名」等）
   - 閲覧者メールアドレス: 認証時のメールアドレス
   - 日時: リアルタイムの閲覧時刻（YYYY-MM-DD HH:mm:ss形式）
   - セッションID: 一意のセッション識別子

5. **セキュリティ**
   - 署名付きURL（期限付き）
   - 直接URLアクセス防止

### 3.5 管理機能
1. **アクセス解析**
   - リアルタイムアクセス数表示
   - 詳細ログ（IP、UA、メールアドレス、滞在時間、デバイス情報）
   - アクセス端末数監視（100台超過時警告）

2. **セッション管理機能 (TASK-003-3完了)**
   - **アクティブセッション一覧表示**: セッションID、メールアドレス、デバイス種別、開始時刻、残り時間、経過時間
   - **高度なフィルター機能**: SID、メールアドレス、デバイス、開始日、メモによる絞り込み
   - **ソート機能**: 全カラムでの昇順・降順ソート
   - **デバイス種別自動判定**: User-Agentからモバイル/タブレット/PC/その他を判定
   - **管理者メモ機能**: セッションごとのメモ編集・保存機能
   - **専用セッション管理ページ**: `/admin/sessions` での詳細管理
   - **セッション詳細専用URL**: `/admin/sessions/<session_id>` での個別詳細表示
   - **詳細ページメモ編集**: 専用URLページでのリアルタイムメモ編集機能
   - **ダッシュボード統合**: メイン管理画面にデバイス別セッション数表示
   - **リアルタイム更新**: 30秒間隔自動更新、手動更新ボタン
   - **レスポンシブ対応**: 横スクロール対応で全カラム表示、モバイル最適化
   - **テキスト折り返し対応**: 長いメモテキストの適切な表示制御

3. **設定管理**
   - 事前共有パスワード変更
   - 公開期間変更
   - IP制限解除
   - 緊急公開停止
   - 全セッション無効化実行時刻設定（時:分形式）
   - 手動全ユーザー強制ログアウト

4. **通知機能**
   - 異常アクセス時メール通知
   - アクセス数閾値超過通知

## 4. 非機能要件

### 4.1 セキュリティ

**認証・アクセス制御 (TASK-003-8セキュリティ強化完了)**
- **強制2段階認証**: 全ユーザーが必ずパスフレーズ+OTPの2段階を経る
- **認証状態分離管理**: `session['passphrase_verified']` と `session['authenticated']` の分離
- **セッションクリア**: パスフレーズ認証成功時の既存セッション情報完全消去 (`session.clear()`)
- **2段階認証バイパス防止**: 中間段階でのコンテンツアクセス不可
- **セッション整合性チェック**: データベース記録との照合によるセッション検証
  - セッションID存在確認
  - 認証時刻整合性確認（5分以内許容）
  - メールアドレスハッシュ照合（SHA256ベース）
- **強制再認証**: セッション無効化後の確実な2段階認証実施
- **一貫したハッシュ管理**: `get_consistent_hash()`による実行間一貫性保証

**通信・データ保護**
- SSL/TLS暗号化（Cloudflare管理）
- メールアドレスハッシュ化保存
- セッション管理（Flask-Session）
- CSRF対策
- ウォーターマークによる著作権保護・不正利用追跡

**リアルタイム通知 (SSE統一管理システム強化)**
- **SSE統一管理システム**: ページ遷移を跨ったSSE接続管理
- セッション無効化イベントの即座通知・自動リダイレクト
  - **クライアント側セッションストレージクリア**: `clear_session: true` による完全クリア
  - **3秒後自動リダイレクト**: ユーザーに通知後、ログイン画面へ誘導
  - **エラー分離処理**: データベースエラーが発生してもSSE通知は確実に送信
- PDF公開/停止イベントのリアルタイム配信
- **接続品質管理**: デッドクライアント自動削除、ハートビート機能

### 4.2 パフォーマンス
- 静的ファイルCDNキャッシュ（Cloudflare）
- PDF初回読み込み後キャッシュ
- 同時30ユーザー対応
- **レスポンシブ画像最適化**: デバイスに応じた適切なレンダリングサイズ

### 4.3 可用性
- DDoS攻撃防御（Cloudflare）
- 自動バックアップ（SQLiteファイル）

### 4.4 ユーザビリティ
- **デバイス横断対応**: 同一ユーザーが複数デバイスで一貫した体験
- **アクセシビリティ**: 最小タッチターゲットサイズ確保（44px以上）
- **パフォーマンス**: モバイル環境での快適な動作速度

## 5. エンドポイント設計

### メインコンテンツ
- `GET /` - PDF閲覧画面（認証必須、未認証時は /auth/login へリダイレクト）

### 認証系（/auth/）

**2段階認証フロー (TASK-003-8セキュリティ強化対応)**
- `GET /auth/login` - 事前共有パスフレーズ入力画面
- `POST /auth/login` - 事前共有パスフレーズ確認・**全セッション情報クリア**・第2段階へ移行
- `GET /auth/email` - メールアドレス入力画面（第1段階認証完了者のみアクセス可能）
  - **セッション整合性チェック**: 完全認証済み状態の場合、データベースとの整合性確認
- `POST /auth/email` - OTP送信処理・**一貫したハッシュでメールアドレス管理**
- `GET /auth/verify-otp` - OTP入力画面
  - **セッション整合性チェック**: 完全認証済み状態の場合、データベースとの整合性確認
- `POST /auth/verify-otp` - OTP確認・完全認証完了 (`session['authenticated'] = True` 設定)
  - **セッション統計記録**: データベースにセッション情報を記録
- `POST /auth/logout` - ログアウト

**セキュリティ制御 (バイパス攻撃防止)**
- 各段階で前段階の認証状態確認を実施
- **完全認証状態での整合性チェック**: OTP認証完了時のみ実行（`session_id`と`auth_completed_at`存在時）
- **時刻整合性確認**: 認証完了時刻とDB記録の差が5分以内であることを確認
- **メールハッシュ整合性確認**: SHA256ベースの一貫したハッシュで照合
- 不正なフロー（段階スキップ等）を検知してログイン画面へリダイレクト
- セッション無効化後の再認証時は必ず全2段階を経る必要がある
- **デバッグ機能**: 整合性チェック失敗時の詳細ログ出力

### 管理者系（/admin/）
- `GET /admin` - 管理者ダッシュボード（管理者権限必須）
- `GET /admin/settings` - 設定変更画面（事前共有パスフレーズ、公開期間等）
- `POST /admin/settings` - 設定変更処理
- `GET /admin/analytics` - アクセス統計・分析画面（デバイス別分析含む）
- `GET /admin/managers` - 管理者一覧表示
- `POST /admin/managers/add` - 管理者追加（メールアドレス入力）
- `POST /admin/managers/remove` - 管理者削除
- `POST /admin/unblock-ip` - IP制限解除
- `POST /admin/unpublish` - 緊急公開停止
- `POST /admin/invalidate-all-sessions` - 手動全セッション無効化実行
- `POST /admin/emergency-stop` - 緊急停止実行（全PDF公開停止 + 全セッション無効化）
- `POST /admin/schedule-session-invalidation` - 定時全セッション無効化スケジュール設定
- `POST /admin/clear-session-invalidation-schedule` - スケジュール解除
- `POST /admin/upload-pdf` - PDFファイルアップロード

**セッション管理機能 (TASK-003-3実装)**
- `GET /admin/sessions` - 専用セッション管理ページ（フィルター・ソート機能付き）
- `GET /admin/sessions/<session_id>` - セッション詳細ページ（専用URL、メモ編集機能付き）
- `GET /admin/api/active-sessions` - アクティブセッション情報取得API
- `POST /admin/api/update-session-memo` - セッションメモ更新API

**セッション無効化機能強化 (TASK-003-8対応)**
- **手動実行**: 管理画面から即座に全セッション無効化
- **スケジュール実行**: 指定時刻での自動セッション無効化
- **完全クリア**: データベース記録・OTPトークン・Flaskセッション・クライアント側ストレージの全削除
- **SSE即座通知**: 全接続クライアントへのリアルタイム通知とリダイレクト

### PDF配信
- `GET /static/pdfs/<filename>` - PDFファイル配信（セッション認証必須）

**セキュリティ方式:**
- セッション認証による直接アクセス防止
- 非認証ユーザーは自動的に /auth/login へリダイレクト
- PDF.js による埋め込み表示（印刷・ダウンロード制御）

## 6. データベース設計

### テーブル構成
```sql
-- アクセスログ（基本的なアクセス記録）
CREATE TABLE access_logs (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    email_hash TEXT,
    ip_address TEXT,
    user_agent TEXT,
    device_type TEXT,  -- 'desktop', 'tablet', 'mobile'
    screen_resolution TEXT,  -- 'WxH' format
    access_time TIMESTAMP,
    endpoint TEXT,
    method TEXT,
    status_code INTEGER
);

-- イベントログ（詳細なユーザー行動記録）
CREATE TABLE event_logs (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    email_hash TEXT,
    event_type TEXT,  -- 'pdf_open', 'inactive_timeout', 'reactivated', 'page_scroll', 'tab_switch', 'orientation_change'
    event_data JSON,  -- 詳細データ（ページ番号、スクロール位置、デバイス情報等）
    timestamp INTEGER,
    ip_address TEXT,
    device_info JSON,  -- デバイス詳細情報
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 認証失敗ログ
CREATE TABLE auth_failures (
    id INTEGER PRIMARY KEY,
    ip_address TEXT,
    attempt_time TIMESTAMP,
    failure_type TEXT,
    email_attempted TEXT,
    device_type TEXT
);

-- IP制限
CREATE TABLE ip_blocks (
    ip_address TEXT PRIMARY KEY,
    blocked_until TIMESTAMP,
    reason TEXT
);

-- システム設定テーブル
CREATE TABLE settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value TEXT,
    value_type TEXT DEFAULT 'string',  -- 'string', 'integer', 'boolean', 'datetime', 'json'
    description TEXT,
    category TEXT DEFAULT 'general',   -- 'auth', 'publish', 'system', 'mail', 'security', 'responsive'
    is_sensitive BOOLEAN DEFAULT FALSE, -- パスワード等の機密情報フラグ
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT  -- 更新者（管理者メールアドレス）
);

-- 初期データ  
INSERT INTO settings (key, value, value_type, description, category, is_sensitive) VALUES
('shared_passphrase', 'default_passphrase_32chars_minimum_length_example', 'string', '事前共有パスフレーズ（32-128文字、0-9a-zA-Z_-のみ）', 'auth', TRUE),
('publish_start', NULL, 'datetime', '公開開始日時', 'publish', FALSE),
('publish_end', NULL, 'datetime', '公開終了日時', 'publish', FALSE),
('system_status', 'active', 'string', 'システム状態（active/unpublished）', 'system', FALSE),
('session_timeout', '259200', 'integer', 'セッション有効期限（秒）', 'auth', FALSE),
('max_login_attempts', '5', 'integer', '最大ログイン試行回数', 'security', FALSE),
('lockout_duration', '1800', 'integer', 'ロックアウト時間（秒）', 'security', FALSE),
('force_logout_time', '02:00', 'string', '定時全セッション無効化実行時刻（HH:MM形式）', 'system', FALSE),
('mail_otp_expiry', '600', 'integer', 'OTP有効期限（秒）', 'mail', FALSE),
('analytics_retention_days', '90', 'integer', 'ログ保持期間（日）', 'system', FALSE),
('author_name', 'Default_Author', 'string', 'ウォーターマーク表示用著作者名', 'watermark', FALSE),
('mobile_breakpoint', '480', 'integer', 'モバイル判定ブレークポイント（px）', 'responsive', FALSE),
('tablet_breakpoint', '768', 'integer', 'タブレット判定ブレークポイント（px）', 'responsive', FALSE),
('enable_touch_optimizations', 'true', 'boolean', 'タッチ操作最適化有効', 'responsive', FALSE);

-- 設定変更履歴テーブル
CREATE TABLE settings_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by TEXT NOT NULL,  -- 変更者メールアドレス
    change_reason TEXT,        -- 変更理由
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address TEXT
);

-- システム設定のインデックス
CREATE INDEX idx_settings_key ON settings(key);
CREATE INDEX idx_settings_category ON settings(category);
CREATE INDEX idx_settings_history_key ON settings_history(setting_key);
CREATE INDEX idx_settings_history_changed_at ON settings_history(changed_at);

-- 管理者権限
CREATE TABLE admin_users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE,
    added_by TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- セッション統計（集計用・整合性チェック用・管理機能用）
CREATE TABLE session_stats (
    session_id TEXT PRIMARY KEY,
    email_hash TEXT,              -- SHA256ベース一貫したハッシュ
    start_time INTEGER,           -- 認証完了時刻（UNIX timestamp）
    end_time INTEGER,
    total_active_time INTEGER,
    total_inactive_time INTEGER,
    page_views INTEGER,
    reactivation_count INTEGER,
    ip_address TEXT,
    device_type TEXT,             -- 'mobile', 'tablet', 'desktop', 'other'（User-Agent判定）
    memo TEXT DEFAULT '',         -- 管理者メモ機能（TASK-003-3）
    orientation_changes INTEGER,  -- 画面回転回数
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- OTPトークン管理（セッション無効化対応）
CREATE TABLE otp_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    otp_code TEXT NOT NULL,
    session_id TEXT,               -- 関連セッションID
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    used_at TIMESTAMP
);
```

## 7. ディレクトリ構成

```
secure-pdf-viewer/
|-- docker-compose.yml
|-- Dockerfile
|-- requirements.txt
|-- app.py                 # メインアプリケーション
|-- config.py              # 設定管理
|-- auth/
|   |-- __init__.py
|   |-- passphrase.py      # パスフレーズ認証
|   |-- otp.py            # OTP機能
|   +-- session.py        # セッション管理
|-- mail/
|   |-- __init__.py
|   +-- sender.py         # メール送信
|-- database/
|   |-- __init__.py
|   |-- models.py         # データベースモデル
|   +-- migrations.py     # マイグレーション
|-- static/
|   |-- css/
|   |   |-- main.css      # 基本スタイル（レスポンシブ対応含む）
|   |   +-- responsive.css # レスポンシブ専用CSS
|   |-- js/
|   |   |-- admin.js      # 管理画面用JavaScript
|   |   |-- sessions.js   # セッション管理ページ用JavaScript
|   |   |-- sse-manager.js # SSE統一管理システム
|   |   |-- watermark.js  # ウォーターマーク生成・管理
|   |   |-- responsive.js # レスポンシブ制御
|   |   +-- device-detect.js # デバイス検知
|   +-- pdfs/             # PDFファイル格納
|-- templates/
|   |-- index.html        # 認証画面
|   |-- viewer.html       # PDF閲覧画面
|   |-- admin.html        # 管理画面
|   |-- sessions.html     # セッション管理専用ページ
|   |-- session_detail.html # セッション詳細専用ページ
|   |-- layout.html       # 共通レイアウト
|   +-- responsive/       # デバイス別テンプレート
|       |-- mobile.html
|       |-- tablet.html
|       +-- desktop.html
|-- instance/
|   +-- database.db       # SQLiteファイル
|-- tests/                # テストコード
|   |-- test_auth_flow.py # 認証フロー統合テスト
|   |-- test_session_invalidation.py # セッション無効化機能テスト
|   |-- test_session_invalidation_auth_flow.py # セッション無効化後認証フロー統合テスト
|   |-- test_task_003_8_regression.py # TASK-003-8リグレッションテスト
|   +-- test_sse_*.py     # SSE統一管理システムテスト
+-- logs/                 # アプリケーションログ
```

## 8. 開発・デプロイ方針

### コンテナ化
- **Docker Compose** 使用
- 開発環境と本番環境の統一
- ポータビリティ確保

### バージョン管理
- **Git** 管理
- ブランチ戦略：main（本番）、develop（開発）
- PDFファイルは .gitignore 対象

### デプロイ
```bash
# 初回セットアップ
git clone <repository>
cd secure-pdf-viewer
cp .env.example .env    # 環境変数設定
docker-compose up -d

# PDF更新
docker-compose exec app python manage.py upload-pdf <file>
```

## 9. 環境変数

```bash
# .env ファイル
FLASK_SECRET_KEY=<ランダム文字列>
MAIL_SERVER=mail.sakura.ne.jp
MAIL_PORT=465
MAIL_USERNAME=<さくらメールアカウント>
MAIL_PASSWORD=<さくらメールパスワード>
ADMIN_EMAIL=<管理者メールアドレス>
CLOUDFLARE_DOMAIN=<ドメイン名>

# 注意: 事前共有パスフレーズはデータベースで管理（環境変数使用しない）
```

## 10. 開発フェーズ

### Phase 1: 認証システム完成 ✅ 完了（2025-07-21）
1. ✅ Flask アプリケーション基盤
2. ✅ 事前共有パスフレーズ認証（セッションクリア機能含む）
3. ✅ PDF.js によるPDF表示
4. ✅ 基本的なログ機能
5. ✅ OTP機能実装（メール2段階認証）
6. ✅ セッション管理強化（72時間有効期限・整合性チェック）
7. ✅ 全セッション無効化機能（手動・スケジュール実行）
8. ✅ SSE統一管理システム（リアルタイム通知）
9. ✅ 2段階認証バイパス脆弱性修正（TASK-003-8）
10. ✅ 包括的テストカバレッジ（リグレッションテスト含む）

### Phase 2: 認証強化 ✅ 完了（Phase 1に統合）
~~5. OTP機能実装~~ ✅ Phase 1で完了
~~6. セッション管理~~ ✅ Phase 1で完了  
~~7. 簡単な管理画面~~ ✅ Phase 1で完了

### Phase 3: セキュリティ・運用（1週間）
8. IP制限・レート制限
9. **ウォーターマーク実装**（レスポンシブ対応）
10. 詳細分析・通知機能

### Phase 4: レスポンシブ対応・UI/UX強化（1週間）
11. **マルチデバイス対応実装**
12. **レスポンシブデザイン適用**
13. **全画面表示機能**
14. **タッチ操作最適化**

### Phase 5: 本番運用準備
15. Docker化
16. Cloudflare設定
17. 監視・バックアップ体制
18. **デバイス別動作テスト**

## 11. 運用手順

### 日常運用
1. **PDF更新**: 管理画面またはCLIでアップロード
2. **アクセス監視**: 管理画面でリアルタイム確認（デバイス別分析含む）
3. **設定変更**: 管理画面で期間・パスフレーズ変更

### 緊急対応
1. **即時停止**: 管理画面の緊急停止ボタン（2段階確認付き）
   - 全PDF公開停止 + 全セッション無効化を一括実行
   - 誤操作防止のための「緊急停止」テキスト入力確認
   - SSE通知による即座な状態変更通知
   - 実行ログの自動記録（`instance/emergency_log.txt`）
2. **IP制限解除**: LINEで連絡受付→管理画面で解除
3. **異常検知**: メール通知→状況確認→対応

## 12. 成功指標

- **セキュリティ**: 不正アクセス0件
  - ✅ **2段階認証バイパス脆弱性修正**: TASK-003-8対応完了
  - ✅ **セッション整合性チェック**: データベース記録との照合による堅牢化
  - ✅ **完全セッションクリア**: 再認証時の古い認証情報完全削除
- **可用性**: 99%以上のアップタイム
- **監視**: アクセス範囲の把握（100台以下維持）
- **運用**: 管理作業の自動化により手間を最小化
  - ✅ **セッション無効化**: 手動・スケジュール実行による柔軟な制御
  - ✅ **リアルタイム通知**: SSE統一管理システムによる即座な状態変更通知
- **著作権保護**: ウォーターマークによる適切な著作者表示と追跡機能
- **ユーザビリティ**: デバイス横断での一貫した操作性確保
- **アクセシビリティ**: 全デバイスでの快適な閲覧体験提供
- **品質保証**: 包括的テストカバレッジによる継続的品質維持
  - ✅ **リグレッションテスト**: TASK-003-8問題の再発防止
  - ✅ **統合テストスイート**: 認証フロー全体の動作保証

## 13. ウォーターマーク技術仕様

### フロントエンド実装
- **ライブラリ**: PDF.js標準機能を使用
- **レンダリング**: Canvas上でPDF描画後、DOM要素でウォーターマーク重複配置
- **更新頻度**: ページ表示時およびページ切り替え時に動的生成
- **レスポンシブ対応**: デバイスサイズに応じた動的サイズ・位置調整

### セキュリティ考慮事項
- **改ざん防止**: JavaScript難読化、DOM操作検知
- **スクリーンショット対応**: 透かし情報により撮影者特定可能
- **印刷制御**: CSS media queries により印刷時も透かし表示
- **デバイス追跡**: アクセス元デバイス情報の記録

### ログ記録
ウォーターマーク表示時に以下の情報をevent_logsテーブルに記録：
```json
{
  "event_type": "watermark_displayed",
  "page_number": 1,
  "watermark_content": "著作者: Default_Author, 閲覧者: user@example.com",
  "display_time": "2025-07-13 15:30:25",
  "device_info": {
    "type": "mobile",
    "screen_size": "390x844",
    "user_agent": "Mozilla/5.0...",
    "orientation": "portrait"
  }
}
```

## 14. レスポンシブデザイン技術仕様

### CSS設計方針
- **Mobile First**: モバイルを基準とした設計
- **Progressive Enhancement**: 画面サイズに応じた機能拡張
- **Flexible Grid**: CSS Grid/Flexboxによる柔軟なレイアウト

### JavaScript制御
- **デバイス検知**: User-Agent + 画面サイズによる判定
- **動的レンダリング**: PDF.jsスケール調整
- **イベント管理**: orientationchange、resize対応

### パフォーマンス最適化
- **画像最適化**: デバイス解像度に応じたCanvasサイズ調整
- **メモリ管理**: 不要なDOM要素の自動削除
- **ネットワーク効率**: デバイス別リソース読み込み

