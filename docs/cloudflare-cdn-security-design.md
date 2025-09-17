# Cloudflare CDN対応セキュリティ機能設計書

## 概要

GitHub Issue #6に基づき、secure-pdf-viewerアプリケーションをCloudflare CDN環境に対応させるためのセキュリティ機能強化を実装する。本設計書では、CDN環境での実IP取得、適切なリファラー検証、セキュリティヘッダー設定、ログ・監視機能の強化について定義する。

## システム要件

### 機能要件

1. **Real IP Address取得**: Cloudflareの`CF-Connecting-IP`ヘッダーから実IPを正確に取得
2. **Cloudflare Referrer検証**: CDN環境での適切なリファラー検証
3. **CDNセキュリティヘッダー**: Cloudflare環境に最適化されたセキュリティヘッダー設定
4. **強化されたログ・監視**: CDN環境での詳細なアクセスログとセキュリティ監視

### 非機能要件

1. **互換性**: 既存のローカル環境での動作を維持
2. **セキュリティ**: 既存のセキュリティレベルを低下させない
3. **パフォーマンス**: 新機能による応答時間への影響を最小限に抑制
4. **運用性**: 設定の柔軟性と運用の容易さを確保

## アーキテクチャ設計

### システム構成

```
[Client] -> [Cloudflare CDN] -> [secure-pdf-viewer]
                                      |
                         [security/cdn_security.py]
                                      |
                         [既存セキュリティ機能群]
```

### モジュール構成

```
security/
├── cdn_security.py          # 新規: CDN セキュリティ機能
├── api_security.py          # 拡張: CDN対応セキュリティヘッダー
└── ...

config/
├── pdf_security_settings.py # 拡張: CDN対応リファラー検証
└── ...
```

## 詳細設計

### 1. Real IP Address取得機能

#### モジュール: `security/cdn_security.py`

```python
def get_real_ip() -> str:
    """
    CDN環境での実IPアドレス取得
    
    IPアドレス取得優先順位:
    1. CF-Connecting-IP (Cloudflare提供の実IP)
    2. X-Forwarded-For (プロキシチェーンの最初のIP)
    3. request.remote_addr (直接接続時のIP)
    
    環境変数による制御:
    - TRUST_CF_CONNECTING_IP: CF-Connecting-IPの信頼設定
    - STRICT_IP_VALIDATION: IP形式の厳密検証
    
    Returns:
        str: 検証済み実IPアドレス
    """
```

**実装ポイント**:
- 環境変数による柔軟な設定制御
- IP形式の厳密な検証（IPv4/IPv6対応）
- セキュリティログによる不正IP検知
- 既存`client_ip`取得箇所の統一的置換

### 2. Cloudflare Referrer検証機能

#### モジュール: `config/pdf_security_settings.py` (拡張)

```python
def is_cloudflare_referrer_valid(referer_url: str) -> bool:
    """
    Cloudflare CDN環境でのリファラー検証
    
    検証ロジック:
    1. CLOUDFLARE_DOMAIN環境変数との照合
    2. 既存のreferrer許可リストとの照合
    3. URLパース結果の検証
    
    Args:
        referer_url: 検証対象のリファラーURL
        
    Returns:
        bool: 検証結果（True: 許可, False: 拒否）
    """

def get_enhanced_referrer_validation(referer_url: str) -> dict:
    """
    リファラー検証の詳細情報取得（ログ・監視用）
    
    Returns:
        dict: 検証結果の詳細情報
        {
            'is_valid': bool,
            'validation_type': str,  # 'cloudflare_cdn' | 'traditional' | 'invalid'
            'cloudflare_domain': str,
            'original_referrer': str
        }
    """
```

### 3. CDNセキュリティヘッダー設定

#### モジュール: `security/api_security.py` (拡張)

```python
def add_cdn_security_headers(response: Response) -> Response:
    """
    CDN環境向けセキュリティヘッダー追加
    
    追加ヘッダー:
    - X-Real-IP-Source: IP取得方法の明示
    - X-CDN-Environment: CDN環境識別子
    - Content-Security-Policy: Cloudflareドメイン対応CSP
    - CF-Cache-Status: キャッシュ制御指示
    
    Args:
        response: 対象Flaskレスポンス
        
    Returns:
        Response: セキュリティヘッダー追加済みレスポンス
    """
```

### 4. 強化されたログ・監視機能

#### データベーススキーマ

```sql
CREATE TABLE IF NOT EXISTS cdn_access_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL,
    action TEXT NOT NULL,
    real_ip TEXT NOT NULL,
    cf_connecting_ip TEXT,
    x_forwarded_for TEXT,
    user_agent TEXT,
    referrer TEXT,
    referrer_validation JSON,
    cloudflare_domain TEXT,
    session_id TEXT,
    additional_info JSON,
    created_at TEXT NOT NULL
);

-- パフォーマンス最適化用インデックス
CREATE INDEX IF NOT EXISTS idx_cdn_logs_real_ip ON cdn_access_logs(real_ip);
CREATE INDEX IF NOT EXISTS idx_cdn_logs_endpoint ON cdn_access_logs(endpoint);
CREATE INDEX IF NOT EXISTS idx_cdn_logs_created_at ON cdn_access_logs(created_at);
```

#### ログ記録機能

```python
def log_cdn_access(endpoint: str, action: str, additional_info: dict = None):
    """
    CDN環境でのアクセスログ記録
    
    記録情報:
    - 基本アクセス情報（endpoint, action, timestamp）
    - IP情報（real_ip, cf_connecting_ip, x_forwarded_for）
    - HTTPヘッダー情報（user_agent, referrer）
    - セキュリティ検証結果（referrer_validation）
    - セッション情報（session_id）
    """

def get_cdn_security_status() -> dict:
    """
    CDNセキュリティ状態の取得
    
    Returns:
        dict: 現在のCDNセキュリティ状態
        {
            'cloudflare_domain': str,
            'ip_detection_method': str,
            'real_ip': str,
            'cdn_headers_present': bool,
            'referrer_validation_active': bool
        }
    """
```

## 設定管理

### 環境変数設定

`.env.example`に以下を追加済み:

```bash
# Cloudflare CDN セキュリティ設定
ENABLE_CDN_SECURITY=true
CDN_ENVIRONMENT=cloudflare
# CDN環境でのIPヘッダー信頼設定（本番環境でのみ有効化）
TRUST_CF_CONNECTING_IP=true
# リアルIP検証の厳密モード（不正なIPフォーマットを拒否）
STRICT_IP_VALIDATION=true
```

### 既存環境変数の活用

```bash
# 既存設定（そのまま利用）
CLOUDFLARE_DOMAIN=your-domain.com
PDF_ALLOWED_REFERRER_DOMAINS=localhost,127.0.0.1,yourdomain.com,10.0.0.0/24
```

## セキュリティ考慮事項

### 脅威モデル

1. **IPスプーフィング攻撃**
   - 対策: 複数ヘッダーソースからの検証、IP形式の厳密検証
   
2. **リファラー偽装攻撃**
   - 対策: 多重検証機構、環境変数による動的設定

3. **CDNバイパス攻撃**
   - 対策: オリジンサーバーへの直接アクセス制限、セキュリティヘッダー強化

### セキュリティ強化策

1. **監視・検知**
   - 異常IPパターンの検知
   - 不正リファラーアクセスの記録
   - CDNヘッダー不整合の監視

2. **アクセス制御**
   - 環境変数による段階的セキュリティ制御
   - IP信頼レベルの調整可能性
   - リファラー検証の柔軟性

## データベース設計

### 新規テーブル

**cdn_access_logs**: CDN環境専用アクセスログ
- 既存`access_logs`との分離によるパフォーマンス確保
- CDN固有情報の詳細記録
- セキュリティ分析用の構造化データ

### 既存テーブルとの関係

- `access_logs`: 従来のアクセスログ（継続利用）
- `security_violations`: セキュリティ違反記録（拡張利用）
- `csrf_tokens`: CSRF保護（既存機能活用）

## パフォーマンス設計

### 最適化策

1. **キャッシュ戦略**
   - IP検証結果のセッション内キャッシュ
   - リファラー検証結果の一時保存

2. **データベース最適化**
   - 適切なインデックス設計
   - ログローテーション機構

3. **非同期処理**
   - 重要でないログ処理の非同期化
   - バックグラウンドでのデータクリーンアップ

## テスト戦略

### 単体テスト

1. **IP取得機能**
   - 各種ヘッダーパターンでのテスト
   - 不正IP形式の検証テスト

2. **リファラー検証**
   - Cloudflareドメインでの検証テスト
   - 既存許可リストとの整合性テスト

### 統合テスト

1. **CDN環境シミュレーション**
   - CloudflareヘッダーでのE2Eテスト
   - 既存機能との互換性テスト

2. **セキュリティテスト**
   - 攻撃パターンでの防御テスト
   - ログ記録の完全性テスト

## 実装フェーズ計画

### Phase 1: 基盤機能実装 (1日)
- `security/cdn_security.py`の基本機能実装
- 環境変数による設定制御
- 既存コードでのIP取得統一化

### Phase 2: セキュリティ機能強化 (1日)
- リファラー検証機能の拡張
- セキュリティヘッダーのCDN対応
- ログ・監視機能の実装

### Phase 3: テスト・検証 (1日)
- 単体テスト・統合テストの実装
- CDN環境での動作検証
- 既存環境での互換性確認

## 成功基準

### 機能要件達成基準

1. **IP取得精度**: CF-Connecting-IPからの実IP取得成功率 > 95%
2. **リファラー検証**: Cloudflare経由アクセスの適切な許可
3. **セキュリティヘッダー**: CDN環境での適切なセキュリティヘッダー設定
4. **ログ完全性**: アクセス情報の完全な記録と検索可能性

### セキュリティ要件達成基準

1. **攻撃防御**: IPスプーフィング・リファラー偽装攻撃の検知・防止
2. **監視機能**: セキュリティ違反の適切な記録と通知
3. **アクセス制御**: 不正アクセスの効果的なブロック

### 運用要件達成基準

1. **互換性**: 既存環境での100%の機能継続
2. **設定柔軟性**: 環境変数による段階的セキュリティ制御
3. **運用効率**: ログ分析・監視業務の効率化

## 運用・保守

### 監視ポイント

1. **CDNヘッダー監視**: CF-Connecting-IPヘッダーの存在確認
2. **IP検証エラー**: 不正IP形式の検知頻度
3. **リファラー違反**: 不正リファラーアクセスの発生頻度

### メンテナンス項目

1. **ログローテーション**: CDNアクセスログの定期的なローテーション
2. **設定見直し**: 環境変数設定の定期的な見直し
3. **セキュリティ更新**: Cloudflare仕様変更への対応

## 関連ドキュメント

- GitHub Issue #6: Cloudflare CDN対応のためのセキュリティ機能強化
- GitHub Issue #4: PDF表示問題（本実装により解決予定）
- 既存設計書: `docs/security-design-philosophy.md`
- 既存設計書: `docs/api-security-phase2-design.md`

---

**文書作成日**: 2025-09-06  
**対象Issue**: #6  
**設計者**: Claude Code  
**承認者**: (TBD)  
**版数**: 1.0