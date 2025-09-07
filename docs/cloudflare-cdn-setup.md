# Cloudflare CDN セットアップガイド

## 概要

このガイドでは、secure-pdf-viewerアプリケーションでCloudflare CDNを使用するための設定手順について説明します。

## 前提条件

- Cloudflareアカウントが作成済みであること
- ドメインがCloudflareに登録済みであること
- アプリケーションが既にデプロイされていること

## 環境変数設定

`.env`ファイルに以下の設定を追加してください：

```bash
# Cloudflare CDN セキュリティ設定
ENABLE_CDN_SECURITY=true
CDN_ENVIRONMENT=cloudflare
TRUST_CF_CONNECTING_IP=true
STRICT_IP_VALIDATION=true

# CloudflareドメインでPDFダウンロード防止を許可
CLOUDFLARE_DOMAIN=your-domain.com
```

## Cloudflare設定手順

### 1. SSL/TLS設定

1. Cloudflareダッシュボードにログイン
2. 対象ドメインを選択
3. **SSL/TLS** → **概要** で暗号化モードを「フル（厳密）」に設定

### 2. DNS設定

1. **DNS** セクションで、オリジンサーバーのIPアドレスを設定
2. プロキシステータス（🧡の雲マーク）を**有効**に設定

### 3. Real IP復元の設定

Cloudflare経由でアクセスされた際に実IPアドレスを正しく取得するため、以下のヘッダーが自動的に付与されます：

- `CF-Connecting-IP`: 実際のクライアントIPアドレス
- `X-Forwarded-For`: プロキシチェーンのIPアドレス

### 4. セキュリティ設定

**Security** → **Settings** で以下を設定：

- **Security Level**: Medium（推奨）
- **Challenge Passage**: 30 minutes
- **Browser Integrity Check**: ON

## nginx設定（オプション）

リバースプロキシとしてnginxを使用している場合、以下の設定を追加：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Cloudflareの実IP復元
        real_ip_header CF-Connecting-IP;
        set_real_ip_from 103.21.244.0/22;
        set_real_ip_from 103.22.200.0/22;
        set_real_ip_from 103.31.4.0/22;
        # ... 他のCloudflare IP範囲
    }
}
```

## セキュリティ機能の確認

### 1. Real IP取得の確認

アプリケーション起動後、以下のログでIP取得方法を確認：

```
Real IP detected from CF-Connecting-IP: xxx.xxx.xxx.xxx
```

### 2. CDNセキュリティヘッダーの確認

ブラウザの開発者ツールで以下のヘッダーが付与されているか確認：

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000
X-CDN-Environment: cloudflare
Cache-Control: private, no-cache, no-store, must-revalidate
```

### 3. テストページでの動作確認

`/admin`ページにアクセスし、以下のデバッグヘッダーを確認：

```
X-TEST-CDN: test-working
X-DEBUG-ENV: CDN=true
```

## トラブルシューティング

### ヘッダーが表示されない場合

1. アプリケーションが再起動されているか確認
2. `.env`ファイルの設定値が正しいか確認
3. `ENABLE_CDN_SECURITY=true`が設定されているか確認

### Real IPが正しく取得されない場合

1. `TRUST_CF_CONNECTING_IP=true`が設定されているか確認
2. CloudflareのプロキシステータスがONになっているか確認
3. nginxのreal_ip設定が正しいか確認（nginx使用時）

### リファラー検証エラーの場合

1. `CLOUDFLARE_DOMAIN`が正しく設定されているか確認
2. PDF URLへの直接アクセスがCloudflare経由になっているか確認

## ログ監視

CDNアクセスログは`cdn_access_logs`テーブルに記録されます。以下の情報が記録されます：

- リアルIP（CF-Connecting-IP）
- リファラー検証結果
- セッション情報
- CDN固有のヘッダー情報

定期的なログ監視により、CDN経由のアクセス状況を把握できます。