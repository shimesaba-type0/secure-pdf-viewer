# PTA PDF閲覧システム 仕様書

## 1. システム概要

PTA資料の限定公開・閲覧システム。特定の人のみが指定期間内にPDF資料を閲覧可能。

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
1. **事前共有パスワード認証**
   - 全ユーザー共通パスワード
   - 管理画面で変更可能

### 3.2 セッション管理
- **セッション有効期限**: 72時間（3日間）
- **自動延長**: なし（シンプルな実装）
- **強制ログアウト条件**:
  - 事前共有パスワード変更時
  - 管理者による全ユーザー強制ログアウト実行時
  - 異常なアクセスパターン検知時

**72時間設定の理由:**
- PTA資料の典型的利用パターン（月曜配布→木曜議論→金曜決定）に適合
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

2. **レスポンシブデザイン対応**
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

3. **ウォーターマーク仕様**
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
   - 著作者名: 設定で指定された著作者名（例：「PTA執行部」「資料作成者」等）
   - 閲覧者メールアドレス: 認証時のメールアドレス
   - 日時: リアルタイムの閲覧時刻（YYYY-MM-DD HH:mm:ss形式）
   - セッションID: 一意のセッション識別子

4. **セキュリティ**
   - 署名付きURL（期限付き）
   - 直接URLアクセス防止

### 3.5 管理機能
1. **アクセス解析**
   - リアルタイムアクセス数表示
   - 詳細ログ（IP、UA、メールアドレス、滞在時間、デバイス情報）
   - アクセス端末数監視（100台超過時警告）

2. **設定管理**
   - 事前共有パスワード変更
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
- `GET /auth/login` - 事前共有パスワード入力画面
- `POST /auth/login` - 事前共有パスワード確認
- `GET /auth/send-otp` - メールアドレス入力画面
- `POST /auth/send-otp` - OTP送信処理
- `GET /auth/verify-otp` - OTP入力画面
- `POST /auth/verify-otp` - OTP確認・認証完了
- `POST /auth/logout` - ログアウト

### 管理者系（/admin/）
- `GET /admin` - 管理者ダッシュボード（管理者権限必須）
- `GET /admin/settings` - 設定変更画面（事前共有パスワード、公開期間等）
- `POST /admin/settings` - 設定変更処理
- `GET /admin/analytics` - アクセス統計・分析画面（デバイス別分析含む）
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
('shared_password', 'default_password_123', 'string', '事前共有パスワード', 'auth', TRUE),
('publish_start', NULL, 'datetime', '公開開始日時', 'publish', FALSE),
('publish_end', NULL, 'datetime', '公開終了日時', 'publish', FALSE),
('system_status', 'active', 'string', 'システム状態（active/unpublished）', 'system', FALSE),
('session_timeout', '259200', 'integer', 'セッション有効期限（秒）', 'auth', FALSE),
('max_login_attempts', '5', 'integer', '最大ログイン試行回数', 'security', FALSE),
('lockout_duration', '1800', 'integer', 'ロックアウト時間（秒）', 'security', FALSE),
('force_logout_after', '0', 'integer', '強制ログアウト実行時刻', 'system', FALSE),
('mail_otp_expiry', '600', 'integer', 'OTP有効期限（秒）', 'mail', FALSE),
('analytics_retention_days', '90', 'integer', 'ログ保持期間（日）', 'system', FALSE),
('author_name', 'PTA執行部', 'string', 'ウォーターマーク表示用著作者名', 'watermark', FALSE),
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
    device_type TEXT,
    orientation_changes INTEGER,  -- 画面回転回数
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 7. ディレクトリ構成

```
pta-pdf-viewer/
|-- docker-compose.yml
|-- Dockerfile
|-- requirements.txt
|-- app.py                 # メインアプリケーション
|-- config.py              # 設定管理
|-- auth/
|   |-- __init__.py
|   |-- password.py        # パスワード認証
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
|   |   |-- main.css      # 基本スタイル
|   |   +-- responsive.css # レスポンシブ専用CSS
|   |-- js/
|   |   |-- watermark.js  # ウォーターマーク生成・管理
|   |   |-- responsive.js # レスポンシブ制御
|   |   +-- device-detect.js # デバイス検知
|   +-- pdfs/             # PDFファイル格納
|-- templates/
|   |-- index.html        # 認証画面
|   |-- viewer.html       # PDF閲覧画面
|   |-- admin.html        # 管理画面
|   |-- layout.html       # 共通レイアウト
|   +-- responsive/       # デバイス別テンプレート
|       |-- mobile.html
|       |-- tablet.html
|       +-- desktop.html
|-- instance/
|   +-- database.db       # SQLiteファイル
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
cd pta-pdf-viewer
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

# 注意: 事前共有パスワードはデータベースで管理（環境変数使用しない）
```

## 10. 開発フェーズ

### Phase 1: 基本機能（1-2週間）
1. Flask アプリケーション基盤
2. 事前共有パスワード認証
3. PDF.js によるPDF表示
4. 基本的なログ機能

### Phase 2: 認証強化（1週間）
5. OTP機能実装
6. セッション管理
7. 簡単な管理画面

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
3. **設定変更**: 管理画面で期間・パスワード変更

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
- **ユーザビリティ**: デバイス横断での一貫した操作性確保
- **アクセシビリティ**: 全デバイスでの快適な閲覧体験提供

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
  "watermark_content": "著作者: [著作者名], 閲覧者: user@example.com",
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

