# セキュアPDF閲覧システム

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
1. **事前共有パスフレーズ認証**
   - 全ユーザー共通パスフレーズ
   - 長さ: 32文字以上128文字以下
   - 許可文字: ASCII文字 (0-9, a-z, A-Z, _, -)
   - 管理画面で変更可能

### 3.2 セッション管理
- **セッション有効期限**: 72時間（3日間）
- **自動延長**: なし（シンプルな実装）
- **強制ログアウト条件**:
  - 事前共有パスフレーズ変更時
  - 管理者による全ユーザー強制ログアウト実行時
  - 異常なアクセスパターン検知時

**72時間設定の理由:**
- 資料の典型的利用パターン（配布→議論→決定）に適合
- ユーザーフレンドリー（週2-3回のログインで済む）
- セキュリティ確保（3日で自動切断、緊急時即座対応可能）
- 実装がシンプル（自動延長ロジック不要）

### 3.2 アクセス制限
1. **地理的制限**
   - 日本国内からのみアクセス許可
   - 海外IPを自動拒否

2. **レート制限**
   - 10分間で5回認証失敗 → 30分間IP制限
   - 管理画面で制限解除可能

3. **公開期間制限**
   - 開始日時・終了日時設定
   - 期間外は自動アクセス拒否

### 3.3 PDF閲覧機能
1. **PDF表示**
   - PDF.js による埋め込み表示
   - 印刷・ダウンロード無効化
   - 右クリック無効化

2. **ウォーターマーク仕様**
   - **配置**: 各ページ右上（上から20px、右から20px）
   - **フォントサイズ**: 10px
   - **フォント**: Courier New（等幅フォント）
   - **透明度**: 0.3（控えめで文書の可読性を確保）
   - **背景**: 半透明白背景（rgba(255, 255, 255, 0.8)）
   - **境界線**: 1px 薄いグレー境界線
   - **角丸**: 4px border-radius
   - **パディング**: 4px（上下） × 8px（左右）
   
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

3. **セキュリティ**
   - 署名付きURL（期限付き）
   - 直接URLアクセス防止

### 3.4 管理機能
1. **アクセス解析**
   - リアルタイムアクセス数表示
   - 詳細ログ（IP、UA、メールアドレス、滞在時間）
   - アクセス端末数監視（100台超過時警告）

2. **設定管理**
   - 事前共有パスフレーズ変更
   - 公開期間変更
   - IP制限解除
   - 緊急公開停止

3. **通知機能**
   - 異常アクセス時メール通知
   - アクセス数閾値超過通知

## 4. 非機能要件

### 4.1 セキュリティ
- SSL/TLS暗号化（Cloudflare管理）
- メールアドレスハッシュ化保存
- セッション管理（Flask-Session）
- CSRF対策
- ウォーターマークによる著作権保護・不正利用追跡

### 4.2 パフォーマンス
- 静的ファイルCDNキャッシュ（Cloudflare）
- PDF初回読み込み後キャッシュ
- 同時30ユーザー対応

### 4.3 可用性
- DDoS攻撃防御（Cloudflare）
- 自動バックアップ（SQLiteファイル）

## 5. エンドポイント設計

### メインコンテンツ
- `GET /` - PDF閲覧画面（認証必須、未認証時は /auth/login へリダイレクト）

### 認証系（/auth/）
- `GET /auth/login` - 事前共有パスフレーズ入力画面
- `POST /auth/login` - 事前共有パスフレーズ確認
- `GET /auth/send-otp` - メールアドレス入力画面
- `POST /auth/send-otp` - OTP送信処理
- `GET /auth/verify-otp` - OTP入力画面
- `POST /auth/verify-otp` - OTP確認・認証完了
- `POST /auth/logout` - ログアウト

### 管理者系（/admin/）
- `GET /admin` - 管理者ダッシュボード（管理者権限必須）
- `GET /admin/settings` - 設定変更画面（事前共有パスフレーズ、公開期間等）
- `POST /admin/settings` - 設定変更処理
- `GET /admin/analytics` - アクセス統計・分析画面
- `GET /admin/managers` - 管理者一覧表示
- `POST /admin/managers/add` - 管理者追加（メールアドレス入力）
- `POST /admin/managers/remove` - 管理者削除
- `POST /admin/unblock-ip` - IP制限解除
- `POST /admin/unpublish` - 緊急公開停止
- `POST /admin/force-logout-all` - 全ユーザー強制ログアウト
- `POST /admin/upload-pdf` - PDFファイルアップロード

### PDF配信
- `GET /static/pdfs/<filename>` - PDFファイル配信（セッション認証必須）

**セキュリティ方式:**
- セッション認証による直接アクセス防止
- 非認証ユーザーは自動的に /auth/login へリダイレクト
- PDF.js による埋め込み表示（印刷・ダウンロード制御）

## 6. 初期セットアップ

### 6.1 パスフレーズの初期設定

システムを初回起動する前に、以下の手順でパスフレーズを設定してください：

#### 方法1: 自動生成（推奨）
```bash
# 32文字のランダムパスフレーズを自動生成
python scripts/setup/setup_initial_passphrase.py
```

#### 方法2: カスタムパスフレーズ設定
```bash
# 独自のパスフレーズを設定
python scripts/setup/setup_initial_passphrase.py --custom
```

**パスフレーズ要件:**
- 32文字以上128文字以下
- 使用可能文字: 0-9, a-z, A-Z, _, -
- 例: `MySecurePassphrase123_for_PDF_Viewer`

### 6.2 アプリケーション起動
```bash
# Flask アプリケーション起動
python app.py
```

### 6.3 初回ログイン
1. ブラウザで `http://localhost:5000` にアクセス
2. 設定したパスフレーズでログイン
3. 管理画面で必要に応じてパスフレーズを変更

**注意:** 初回セットアップ時に表示されるパスフレーズは必ず安全に保存してください。

## 7. データベース設計

### テーブル構成
```sql
-- アクセスログ（基本的なアクセス記録）
CREATE TABLE access_logs (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    email_hash TEXT,
    ip_address TEXT,
    user_agent TEXT,
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
    event_type TEXT,  -- 'pdf_open', 'inactive_timeout', 'reactivated', 'page_scroll', 'tab_switch'
    event_data JSON,  -- 詳細データ（ページ番号、スクロール位置等）
    timestamp INTEGER,
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 認証失敗ログ
CREATE TABLE auth_failures (
    id INTEGER PRIMARY KEY,
    ip_address TEXT,
    attempt_time TIMESTAMP,
    failure_type TEXT,
    email_attempted TEXT
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
    category TEXT DEFAULT 'general',   -- 'auth', 'publish', 'system', 'mail', 'security'
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
('force_logout_after', '0', 'integer', '強制ログアウト実行時刻', 'system', FALSE),
('mail_otp_expiry', '600', 'integer', 'OTP有効期限（秒）', 'mail', FALSE),
('analytics_retention_days', '90', 'integer', 'ログ保持期間（日）', 'system', FALSE),
('author_name', 'Default_Author', 'string', 'ウォーターマーク表示用著作者名', 'watermark', FALSE);

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

-- セッション統計（集計用）
CREATE TABLE session_stats (
    session_id TEXT PRIMARY KEY,
    email_hash TEXT,
    start_time INTEGER,
    end_time INTEGER,
    total_active_time INTEGER,
    total_inactive_time INTEGER,
    page_views INTEGER,
    reactivation_count INTEGER,
    ip_address TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 7. ディレクトリ構成

```
secure-pdf-viewer/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── app.py                 # メインアプリケーション
├── config.py              # 設定管理
├── auth/
│   ├── __init__.py
│   ├── passphrase.py      # パスフレーズ認証
│   ├── otp.py            # OTP機能
│   └── session.py        # セッション管理
├── mail/
│   ├── __init__.py
│   └── sender.py         # メール送信
├── database/
│   ├── __init__.py
│   ├── models.py         # データベースモデル
│   └── migrations.py     # マイグレーション
├── static/
│   ├── css/
│   ├── js/
│   │   └── watermark.js  # ウォーターマーク生成・管理
│   └── pdfs/             # PDFファイル格納
├── templates/
│   ├── index.html        # 認証画面
│   ├── viewer.html       # PDF閲覧画面
│   ├── admin.html        # 管理画面
│   └── layout.html       # 共通レイアウト
├── instance/
│   └── database.db       # SQLiteファイル
└── logs/                 # アプリケーションログ
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

### Phase 1: 基本機能（1-2週間）
1. Flask アプリケーション基盤
2. 事前共有パスフレーズ認証
3. PDF.js によるPDF表示
4. 基本的なログ機能

### Phase 2: 認証強化（1週間）
5. OTP機能実装
6. セッション管理
7. 簡単な管理画面

### Phase 3: セキュリティ・運用（1週間）
8. IP制限・レート制限
9. **ウォーターマーク実装**（パターン1仕様）
10. 詳細分析・通知機能

### Phase 4: 本番運用準備
11. Docker化
12. Cloudflare設定
13. 監視・バックアップ体制

## 11. 運用手順

### 日常運用
1. **PDF更新**: 管理画面またはCLIでアップロード
2. **アクセス監視**: 管理画面でリアルタイム確認
3. **設定変更**: 管理画面で期間・パスフレーズ変更

### 緊急対応
1. **即時停止**: 管理画面の緊急停止ボタン
2. **IP制限解除**: LINEで連絡受付→管理画面で解除
3. **異常検知**: メール通知→状況確認→対応

## 12. 成功指標

- **セキュリティ**: 不正アクセス0件
- **可用性**: 99%以上のアップタイム
- **監視**: アクセス範囲の把握（100台以下維持）
- **運用**: 管理作業の自動化により手間を最小化
- **著作権保護**: ウォーターマークによる適切な著作者表示と追跡機能

## 13. ウォーターマーク技術仕様

### フロントエンド実装
- **ライブラリ**: PDF.js標準機能を使用
- **レンダリング**: Canvas上でPDF描画後、DOM要素でウォーターマーク重複配置
- **更新頻度**: ページ表示時およびページ切り替え時に動的生成

### セキュリティ考慮事項
- **改ざん防止**: JavaScript難読化、DOM操作検知
- **スクリーンショット対応**: 透かし情報により撮影者特定可能
- **印刷制御**: CSS media queries により印刷時も透かし表示

### ログ記録
ウォーターマーク表示時に以下の情報をevent_logsテーブルに記録：
```json
{
  "event_type": "watermark_displayed",
  "page_number": 1,
  "watermark_content": "著作者: Default_Author, 閲覧者: user@example.com",
  "display_time": "2025-07-13 15:30:25"
}
```

