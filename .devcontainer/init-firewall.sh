#!/bin/bash
# Claude Code用のファイアウォール設定

# 基本的に必要なドメイン（Claude Code動作用）
ALLOWED_DOMAINS=(
    "api.anthropic.com"      # Claude Code API
    "registry.npmjs.org"     # npm パッケージ
    "github.com"             # Git操作、リポジトリアクセス
    "api.github.com"         # GitHub API
    "pypi.org"               # Python パッケージインデックス
    "files.pythonhosted.org" # Python パッケージダウンロード
)

# ========================================
# ?? 必要に応じて以下にドメインを追加してください
# ========================================
#
# メールサーバー例:
# - Gmail: "smtp.gmail.com"
# - Outlook: "smtp-mail.outlook.com"
# - さくらメール: "mail.sakura.ne.jp"
# - 独自SMTPサーバー: "mail.yourcompany.com"
#
# その他の外部サービス例:
# - CDN: "cdn.jsdelivr.net", "unpkg.com"
# - 認証サービス: "auth0.com", "okta.com"
# - 監視サービス: "api.datadoghq.com"
# - ファイルストレージ: "s3.amazonaws.com"
#
# サブドメインについて:
# - "example.com" を許可すると "api.example.com", "cdn.example.com" 等も自動許可
# - 特定のサブドメインのみ許可したい場合は完全なドメイン名を指定
#
# 追加例:
# ALLOWED_DOMAINS+=(
#     "your-additional-domain.com"
#     "another-service.example.org"
# )

# 環境変数からメールサーバーを追加（.envで設定）
if [ ! -z "$MAIL_SERVER" ]; then
    ALLOWED_DOMAINS+=("$MAIL_SERVER")
    echo "Added mail server: $MAIL_SERVER"
fi

# ファイアウォール設定（必要に応じて実装）
echo "Firewall configured for Claude Code development"

