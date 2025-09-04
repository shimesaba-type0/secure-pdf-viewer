# セキュアPDF閲覧システム

## 概要

セキュアなPDF資料の限定公開・閲覧システムです。特定の人のみが指定期間内にPDF資料を閲覧可能な、企業や組織向けの機密資料管理ソリューションです。

### 主な機能
- **2段階認証**: 共有パスフレーズ + メールOTP認証
- **セキュアPDF配信**: 直接ダウンロード防止・ウォーターマーク付与
- **アクセス管理**: セッション管理・IP制限・地理的制限
- **管理機能**: リアルタイム監視・統計・緊急停止機能

## 想定利用シーン

### 対象ユーザー
- **閲覧権限者**: 約30人（一般利用者）
- **管理者**: 1-3名（システム管理・監視）
- **想定同時アクセス**: 10人程度
- **対応端末数**: 45-90台（複数端末利用考慮）

### 利用想定
- 重要な企業資料の限定公開
- 役員会議資料の事前配布
- 機密情報を含む文書の安全な共有
- 期間限定の資料配布（会議前後の短期間公開）

## システム構成

### インフラ構成
```
インターネット → Cloudflare → localhost（Docker）
                     ↓
                   メール（OTP送信）
```

### 技術スタック
- **アプリケーション**: Flask (Python)
- **コンテナ化**: Docker + Docker Compose
- **データベース**: SQLite3
- **フロントエンド**: PDF.js + 独自JavaScript
- **CDN/セキュリティ**: Cloudflare
- **メール配信**: SMTP対応メールサーバー

### セキュリティ特徴
- **多層防御アーキテクチャ**: CDN・アプリ・セッション・ファイルレベル
- **直接ダウンロード防止**: Referrer・User-Agent・認証チェック
- **ウォーターマーク**: 動的生成・不正利用追跡
- **リアルタイム監視**: 異常アクセス検知・自動ブロック

## デプロイ方法

### 前提条件
- Docker及びDocker Composeがインストール済み
- Git が使用可能な環境
- OpenSSL または Python3 が使用可能
- SQLite3 がインストール済み（データベース管理・トラブルシューティング用）

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y sqlite3

# CentOS/RHEL/Rocky Linux
sudo yum install -y sqlite3
# または dnf を使用
sudo dnf install -y sqlite3

# インストール確認
sqlite3 --version
```

### 開発環境セットアップ

```bash
# リポジトリクローン
git clone <repository-url>
cd secure-pdf-viewer

# 環境変数設定
cp .env.example .env
# [重要] .env ファイルを必ず編集してください
# 特にPDF_ALLOWED_REFERRER_DOMAINSにアクセス元のIPアドレス/ネットワークを追加
# 例: PDF_ALLOWED_REFERRER_DOMAINS=localhost,127.0.0.1,192.168.1.0/24

# データベース初期化・マイグレーション実行
docker-compose run --rm db-init

# 開発環境起動
docker-compose up -d

# 初期パスフレーズ設定
docker-compose exec app python scripts/setup/setup_initial_passphrase.py

# セットアップ完了確認
echo "=== セットアップ完了確認 ==="
docker-compose ps
docker-compose exec app python -c "
import sqlite3
conn = sqlite3.connect('instance/database.db')
migrations = conn.execute('SELECT name FROM migrations ORDER BY id').fetchall()
print('適用済みマイグレーション:', [m[0] for m in migrations])
conn.close()
"

# ログ確認
docker-compose logs -f app
```

### 本番環境デプロイ

```bash
# リポジトリクローン
git clone <repository-url>
cd secure-pdf-viewer

# 本番環境用設定
cp .env.example .env
# .env を本番環境用に編集（詳細は環境変数設定を参照）

# 本番用Docker設定
sed -i 's/FLASK_ENV=development/FLASK_ENV=production/' docker-compose.yml
sed -i 's/FLASK_DEBUG=1/FLASK_DEBUG=0/' docker-compose.yml

# 必要なディレクトリ作成
mkdir -p instance logs static/pdfs backups
chmod 700 backups

# データベース初期化・マイグレーション実行
docker-compose run --rm db-init

# 本番環境起動
docker-compose up -d

# 動作確認
curl -I http://localhost:5000
docker-compose ps
```

### 環境変数設定

`.env` ファイルの主要設定項目：

```bash
# Flask設定（必須）
FLASK_SECRET_KEY=$(openssl rand -hex 32)
FLASK_ENV=production  # 本番環境

# メール設定（必須）
MAIL_SERVER=your-mail-server.com
MAIL_PORT=465
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-email-password

# 管理者設定（必須）
ADMIN_EMAIL=admin@example.com

# システム設定（必須）
CLOUDFLARE_DOMAIN=your-domain.com
TIMEZONE=UTC  # 本番環境推奨

# PDF配信セキュリティ（重要）
PDF_DOWNLOAD_PREVENTION_ENABLED=true
# [重要] PDF閲覧を許可するReferrer（必須設定）
# アクセス元のIPアドレス、ドメイン、ネットワークを指定
# 設定例: localhost,127.0.0.1,192.168.1.0/24,yourdomain.com
# 注意: この設定が正しくないとPDFが表示されません（403 Forbidden）
PDF_ALLOWED_REFERRER_DOMAINS=localhost,127.0.0.1,your-domain.com,192.168.1.0/24
PDF_USER_AGENT_CHECK_ENABLED=true
PDF_STRICT_MODE=false  # 開発環境では false 推奨
```

### 運用・メンテナンス

```bash
# システム停止・再起動
docker-compose down
docker-compose up -d

# ログローテーション
docker-compose exec app find /app/logs -name "*.log" -type f -mtime +7 -delete

# システム更新
docker-compose pull
docker-compose up -d --force-recreate

# バックアップ確認
ls -la backups/

# データベース状態確認
docker-compose exec app python -c "
from database.models import init_db
init_db()
print('Database initialized successfully')
"
```

## トラブルシューティング

### よくある問題

**PDFが表示されない（403 Forbidden エラー）** *** 最重要 ***
```bash
# 原因: PDF_ALLOWED_REFERRER_DOMAINSの設定不備
# 解決方法:
# 1. .envファイルでアクセス元IPアドレスを追加
echo "PDF_ALLOWED_REFERRER_DOMAINS=localhost,127.0.0.1,192.168.1.0/24" >> .env

# 2. 環境変数変更後は必ず再起動（restartでは不十分）
docker-compose down && docker-compose up -d

# 3. 設定確認
docker-compose exec app printenv | grep PDF_ALLOWED_REFERRER_DOMAINS
```

**管理画面でPDFファイルリストが表示されない**
```bash
# 原因: データベースマイグレーション未実行
# 解決方法:
docker-compose exec app python -c "
from database.migrations import run_all_migrations
import sqlite3
conn = sqlite3.connect('instance/database.db')
run_all_migrations(conn)
conn.close()
print('マイグレーション完了')
"

# アプリケーション再起動
docker-compose restart app
```

**ポート競合エラー**
```bash
netstat -tulpn | grep :5000
# 必要に応じてdocker-compose.ymlのポート設定変更
```

**データベースエラー**
```bash
docker-compose run --rm db-init
```

**環境変数が反映されない**
```bash
# .env変更後はrestartではなく down/up が必要
docker-compose down && docker-compose up -d
```

**メール送信エラー**
```bash
# .envのメール設定を確認
docker-compose logs app | grep -i mail
```

## ドキュメント

詳細な技術仕様・設計については、以下のドキュメントを参照してください：

### 主要設計書
- **[システム全体仕様](./docs/specifications.md)** - 全体アーキテクチャ・機能要件
- **[セキュリティ設計](./docs/security-design-philosophy.md)** - セキュリティアーキテクチャ・脅威対策
- **[PDF配信アーキテクチャ](./docs/pdf-delivery-architecture.md)** - PDF配信・保護機能

### 機能別設計書
- **[認証・セッション管理](./docs/session-management-features.md)** - 認証フロー・セッション設計
- **[管理者権限システム](./docs/admin-permission-system-design.md)** - 管理機能・権限管理
- **[バックアップシステム](./docs/backup-system-design.md)** - データバックアップ・復旧
- **[監視・アラート](./docs/monitoring-alert-system-design.md)** - 監視機能・通知システム
- **[レート制限](./docs/rate-limiting-system-design.md)** - アクセス制御・DoS対策
- **[ログ・監査](./docs/security-event-logging-design.md)** - セキュリティログ・監査機能

### 実装ガイド
- **[PDF直接ダウンロード防止](./docs/pdf-download-prevention-implementation.md)** - 実装詳細
- **[ウォーターマーク機能](./docs/watermark-enhancement-implementation.md)** - 実装・運用
- **[タイムゾーン統一](./docs/timezone-unification-system-design.md)** - 時刻管理統一
- **[レスポンシブUI](./docs/responsive-ui-improvement-design.md)** - UI/UX改善

### 運用ガイド
- **[緊急停止機能](./docs/emergency-stop-feature.md)** - 緊急対応手順
- **[インシデント検索](./docs/incident-search-functionality-design.md)** - ログ分析・調査

## ライセンス

[LICENSE](./LICENSE) を参照してください。

## サポート

技術的な問題や質問については、プロジェクト管理者にお問い合わせください。

