# Secure PDF Viewer

セキュアなPDF閲覧システム - 限定公開・期間制限・認証機能付き

## 概要

特定のユーザーのみが指定期間内にPDF資料を安全に閲覧できるシステムです。企業の機密資料、教育機関の試験問題、医療文書、法的文書など、セキュアな文書配布が必要な場面で活用できます。

## 主な機能

### ?? セキュリティ機能
- **二段階認証**: 事前共有パスワード + OTP（メール認証）
- **セッション管理**: 72時間の期限付きセッション
- **地理的制限**: 日本国内からのみアクセス許可
- **レート制限**: 認証失敗時の自動IP制限
- **ウォーターマーク**: 閲覧者情報の透かし表示

### ?? PDF機能
- **PDF.js表示**: ブラウザ内での安全なPDF表示
- **印刷・ダウンロード制限**: 右クリック・印刷機能の無効化
- **直接アクセス防止**: 署名付きURLによる保護

### ?? 管理機能
- **リアルタイム監視**: アクセス数・端末数の即時確認
- **詳細ログ**: IP、UA、滞在時間の記録
- **緊急対応**: 即座の公開停止・IP制限解除
- **期間管理**: 公開開始・終了時刻の設定

## 対象ユーザー

- **閲覧権限者**: 約30人（**参考値**）
- **想定同時アクセス**: 10人程度
- **想定端末数**: 45?90台（複数端末利用考慮）

?? **重要**: 上記の数値は参考値です。実際の対応可能ユーザー数は**ホストするサーバーのスペック**（CPU、メモリ、ネットワーク帯域）により大きく変わります。本番運用前に**十分な負荷テストを実施**し、ご利用環境に適した構成を検証してください。

## 技術スタック

- **Backend**: Flask (Python 3.12)
- **Database**: SQLite3
- **PDF表示**: PDF.js
- **Mail**: SMTP (さくらメール等)
- **Infrastructure**: Docker + **Cloudflare（必須）**
- **Development**: Claude Code + VS Code Dev Container

## 依存関係

### ?? Cloudflare（必須）
このアプリケーションは以下のCloudflare機能に依存しており、**Cloudflare契約が必要**です：

- **SSL/TLS暗号化**: Cloudflareが証明書を管理・提供
- **DDoS攻撃防御**: Cloudflareのセキュリティ層で保護
- **地理的制限**: 日本国内のみアクセス許可（Cloudflare Security Rules）
- **CDNキャッシュ**: 静的ファイルの高速配信
- **DNS管理**: ドメイン名とIPアドレスの紐付け

### ?? Cloudflareなしでの制限事項
Cloudflareを使用しない場合、以下の機能が利用できません：
- 地理的アクセス制限
- DDoS攻撃からの保護
- 自動SSL証明書
- CDNによる高速化

## クイックスタート

### 1. リポジトリのクローン
```bash
git clone https://github.com/your-username/secure-pdf-viewer.git
cd secure-pdf-viewer
```

### 2. 環境設定
```bash
# 環境変数ファイルの作成
cp .env.example .env

# シークレットキーの自動生成
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
sed -i "s/your-secret-key-here/$SECRET_KEY/" .env

# .envファイルを編集（メール設定等）
nano .env
```

### 3. Docker環境での起動
```bash
# コンテナのビルドと起動
docker-compose up --build -d

# ログの確認
docker-compose logs -f app

# アクセス確認
curl http://0.0.0.0:5000/
```

### 4. 開発環境（VS Code Dev Container）
```bash
# VS Codeで開く
code .

# Command Palette (Ctrl+Shift+P) で実行:
# "Remote-Containers: Reopen in Container"

# Claude Codeで開発開始
claude --dangerously-skip-permissions
```

## 設定

### 環境変数（.env）
```bash
# Flask設定
FLASK_SECRET_KEY=生成された64文字のキー
FLASK_ENV=development

# メール設定
MAIL_SERVER=your-mail-server.com
MAIL_PORT=465
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-email-password

# 管理者設定
ADMIN_EMAIL=admin@example.com

# システム設定
CLOUDFLARE_DOMAIN=your-domain.com
```

### シークレットキーの生成方法（Linux）
```bash
# Python使用（推奨）
python3 -c "import secrets; print(secrets.token_hex(32))"

# OpenSSL使用
openssl rand -hex 32
```

## 開発

### ローカル開発環境
```bash
# 仮想環境の作成
python3 -m venv venv
source venv/bin/activate

# 依存関係のインストール
pip install -r requirements.txt

# 開発サーバーの起動
export FLASK_ENV=development
export FLASK_DEBUG=1
python app.py
```

### Claude Codeでの開発
```bash
# 機能実装の例
claude "Implement Flask basic authentication with shared password"
claude "Create PDF viewer with PDF.js integration"
claude "Add OTP email authentication system"
```

## アーキテクチャ

```
インターネット → Cloudflare（必須） → nginx（リバースプロキシ） → localhost:5000（Docker）
```

| コンポーネント | 役割 | 技術 | 依存度 |
|---------------|------|------|--------|
| **Cloudflare** | DNS、CDN、DDoS対策、地理的制限 | DNS Proxy, Security Rules | **必須** |
| **nginx** | リバースプロキシ、SSL終端、静的ファイル配信 | HTTP Server/Proxy | **推奨** |
| **Docker** | アプリケーション実行環境 | Flask + gunicorn | 必須 |
| **SQLite3** | ユーザー認証、ログ管理 | データベース | 必須 |
| **SMTP** | OTP送信 | メール配信 | 必須 |

### 推奨構成の理由
- **nginx**: 静的ファイル配信の高速化、SSL終端処理
- **Cloudflare**: 外部脅威からの保護、地理的制限
- **Docker**: アプリケーションの分離、デプロイの簡素化

### Cloudflare設定要件
- **ドメイン契約**: 独自ドメインが必要
- **プランレベル**: Free プラン以上（Security Rules使用のため）
- **DNS設定**: A レコードでサーバーIPを指定
- **SSL設定**: "Full (strict)" モード推奨

## API エンドポイント

### 認証系
- `GET /auth/login` - 事前共有パスワード入力
- `POST /auth/login` - パスワード確認
- `GET /auth/send-otp` - OTP送信画面
- `POST /auth/send-otp` - OTP送信処理
- `GET /auth/verify-otp` - OTP入力画面
- `POST /auth/verify-otp` - OTP確認・認証完了

### 管理者系
- `GET /admin` - 管理者ダッシュボード
- `GET /admin/analytics` - アクセス統計
- `POST /admin/settings` - 設定変更
- `POST /admin/force-logout-all` - 全ユーザー強制ログアウト

### PDF配信
- `GET /` - PDF閲覧画面（認証必須）
- `GET /static/pdfs/<filename>` - PDFファイル配信

## セキュリティ機能

### 認証
- 事前共有パスワード（管理画面で変更可能）
- OTPメール認証（10分間有効）
- セッション管理（72時間有効期限）

### アクセス制限
- 地理的制限（日本国内のみ）
- レート制限（10分間で5回失敗 → 30分間IP制限）
- 公開期間制限（開始・終了日時設定）

### PDF保護
- PDF.js埋め込み表示
- 印刷・ダウンロード無効化
- 右クリック無効化
- ウォーターマーク表示
- 署名付きURL

## 本番デプロイ

### 前提条件
- **Cloudflareアカウント**: 必須（無料プランでも可）
- **独自ドメイン**: Cloudflareで管理するドメインが必要
- **Ubuntu Server**: 22.04 LTS以上推奨
- **十分なサーバースペック**: 想定ユーザー数に応じた負荷テスト必須

### 1. Cloudflare設定（必須手順）
```bash
# 1. Cloudflareでドメインを追加
# 2. ネームサーバーをCloudflareに変更
# 3. DNS設定
A レコード: your-domain.com → サーバーのIPアドレス

# 4. SSL/TLS設定
暗号化モード: "Full (strict)"

# 5. セキュリティルール（地理的制限）
国: 日本のみ許可
アクション: 許可

# 6. その他のセキュリティ設定
ブラウザ整合性チェック: 有効
チャレンジ通過: 有効
```

### 2. nginx設定（推奨）
```bash
# nginxのインストール
sudo apt update
sudo apt install nginx

# 設定ファイルの作成
sudo nano /etc/nginx/sites-available/secure-pdf-viewer
```

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # HTTPからHTTPSにリダイレクト
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL証明書（Cloudflareから自動取得）
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # セキュリティヘッダー
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    
    # 静的ファイルの直接配信
    location /static/ {
        alias /path/to/secure-pdf-viewer/static/;
        expires 1h;
        add_header Cache-Control "public, immutable";
    }
    
    # アプリケーションへのプロキシ
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# 設定の有効化
sudo ln -s /etc/nginx/sites-available/secure-pdf-viewer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. アプリケーション設定
```bash
# 本番用docker-compose
docker-compose -f docker-compose.prod.yml up -d

# 自動起動設定
sudo systemctl enable docker
sudo systemctl enable nginx
```

### 4. 負荷テスト（必須）
```bash
# Apache Benchでの基本テスト
ab -n 1000 -c 10 https://your-domain.com/

# より詳細な負荷テスト
# - 想定同時ユーザー数での接続テスト
# - PDF表示の応答時間測定
# - メモリ・CPU使用率の監視
```

### 5. 監視・バックアップ
- SQLiteファイルの定期バックアップ
- ログローテーション設定
- アクセス監視アラート
- サーバーリソース監視

### 6. nginx代替案（開発環境用）
開発環境ではnginxなしでも動作可能：
```bash
# 直接アクセス（本番非推奨）
docker-compose up -d  # http://0.0.0.0:5000 でアクセス
```

## トラブルシューティング

### よくある問題

**1. コンテナが起動しない**
```bash
# ログの確認
docker-compose logs app

# ポート競合の確認
netstat -tlnp | grep 5000
```

**2. メール送信エラー**
```bash
# SMTP設定の確認
docker-compose exec app python -c "
import smtplib
smtp = smtplib.SMTP('mail.sakura.ne.jp', 465)
print('Connection successful')
"
```

**3. PDF表示エラー**
```bash
# PDFファイルの存在確認
ls -la static/pdfs/

# ファイル権限の確認
chmod 644 static/pdfs/*.pdf
```

**4. Cloudflare関連の問題**
```bash
# DNS設定の確認
dig your-domain.com

# SSL証明書の確認
curl -I https://your-domain.com

# 地理的制限のテスト
curl -H "CF-IPCountry: US" https://your-domain.com  # アクセス拒否を確認
curl -H "CF-IPCountry: JP" https://your-domain.com  # アクセス許可を確認
```

**5. ローカル開発でCloudflare機能をテストできない場合**
```bash
# 地理的制限の代替テスト
# IPアドレス範囲での制限をnginxで実装
```

## ライセンス

MIT License

## コントリビューション

1. このリポジトリをフォーク
2. フィーチャーブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. プルリクエストを作成

## サポート

問題や質問がある場合は、GitHubのIssuesページをご利用ください。

---

**?? 重要**: このシステムは機密文書の配布を目的としており、**Cloudflareの契約が前提**となっています。また、記載のユーザー数は参考値であり、**実際の処理能力はサーバースペック**（CPU、メモリ、ネットワーク）に大きく依存します。

**本番運用前の必須事項**: 
- 想定負荷での十分な負荷テスト実施
- セキュリティ設定の適切な構成
- 定期的なシステムアップデート

**Cloudflare要件**: 
- 独自ドメインの契約
- Cloudflareアカウント（無料プランでも可）
- DNS設定権限

**推奨インフラ構成**:
- nginx リバースプロキシ
- 十分なサーバーリソース
- 監視・バックアップ体制

