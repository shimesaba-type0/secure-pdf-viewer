# TASK-009: PDF配信セキュリティ強化（署名付きURL実装）

**フェーズ**: [Phase 3: セキュリティ・運用](../phases/phase3-security-operations.md)  
**優先度**: 🔴 高優先度  
**状況**: ⏳ 未着手  
**担当者**: 未割り当て  
**作成日**: 2025-07-23

## 概要
PDFファイルへの直接URLアクセスを防止し、署名付きURL（期限付き）による安全な配信システムを実装する。現在、`/static/pdfs/` 経由で認証をバイパスしたアクセスが可能な脆弱性を修正する。

## 現在の問題
- PDFファイルが `/static/pdfs/` で直接アクセス可能
- セッション認証をバイパスしてダウンロード可能
- `http://localhost:5000/static/pdfs/ファイル名.pdf` で誰でもアクセス可能

## 要件

### 1. 署名付きURL生成機能
- **URL署名**: HMACベースの改ざん検証
- **期限設定**: configurable expiration time（デフォルト30分）
- **セッション紐付け**: アクセス元セッションIDとの照合
- **ワンタイム制御**: 同一URLの再利用防止（オプション）

### 2. 専用配信エンドポイント
```
GET /secure/pdf/<signed_url_token>
```
- セッション認証必須
- URL署名検証
- 期限チェック
- アクセスログ記録

### 3. 静的ファイル保護
- `/static/pdfs/` への直接アクセス無効化
- Nginxリバースプロキシ設定対応
- Flask static files設定調整

### 4. セキュリティ強化
- **改ざん検知**: URL parameter tampering防止
- **リプレイ攻撃対策**: timestamp + nonce による重複防止
- **セッション整合性**: アクセス元認証状態確認
- **レート制限**: 同一セッションからの連続アクセス制限

## 実装対象

### バックエンド実装
1. **URL署名生成関数**
   ```python
   def generate_signed_pdf_url(filename, session_id, expires_in=1800):
       # HMAC署名付きURL生成
   ```

2. **配信エンドポイント実装**
   ```python
   @app.route('/secure/pdf/<signed_token>')
   def serve_secure_pdf(signed_token):
       # 署名検証 + 認証チェック + ファイル配信
   ```

3. **静的アクセス制御**
   - Flask static folder設定調整
   - PDFディレクトリのアクセス制御

### フロントエンド調整
4. **PDF.js連携更新**
   - 署名付きURL使用への変更
   - エラーハンドリング強化

### 設定・運用
5. **設定項目追加**
   - `pdf_url_expiry_hours`: URL有効期限（時間、デフォルト72時間）
   - `pdf_access_rate_limit`: アクセス制限設定
   - `signed_url_secret`: 署名用秘密鍵

6. **ログ・監視強化**
   - PDF アクセス詳細ログ
   - 不正アクセス試行の検知・通知

## PDF.js動作フローと署名付きURL統合

### 現在のPDF配信フロー
```mermaid
sequenceDiagram
    participant User as ブラウザ
    participant Server as Flaskサーバー
    participant DB as データベース
    participant Static as 静的ファイル

    User->>Server: GET / (閲覧画面リクエスト)
    Server->>DB: get_published_pdf() 実行
    DB-->>Server: file_path: "static/pdfs/xxxxx.pdf"
    Server-->>User: HTML + PDF path埋め込み
    User->>Static: pdfjsLib.getDocument(filePath) 実行
    Static-->>User: PDFファイル直接ダウンロード
    Note over User: PDF.jsがメモリ上でPDF処理
```

### 署名付きURL実装後のフロー
```mermaid
sequenceDiagram
    participant User as ブラウザ
    participant Server as Flaskサーバー
    participant DB as データベース
    participant Secure as 署名付きエンドポイント

    User->>Server: GET / (閲覧画面リクエスト)
    Server->>DB: get_published_pdf() 実行
    Server->>Server: generate_signed_pdf_url() 実行
    Server-->>User: HTML + 署名付きURL埋め込み
    User->>Secure: pdfjsLib.getDocument(signed_url) 実行
    Secure->>Secure: 署名検証 + セッション認証
    Secure-->>User: 認証済みPDFファイル配信
    Note over User: PDF.jsがメモリ上でPDF処理
```

### 重要な技術的ポイント

1. **PDF.jsのアクセスパターン**
   - **初回ロード時のみアクセス**: `pdfjsLib.getDocument()` は最初の1回だけ実行
   - **全データダウンロード**: PDFファイル全体をブラウザにダウンロード
   - **メモリ上処理**: ページめくりは既ダウンロードデータを使用
   - **再アクセスなし**: セッション中にPDF URLへの追加リクエストは発生しない

2. **署名付きURL期限設計**
   - **72時間有効**: セッション有効期限と同期（30分は短すぎる）
   - **1回限りアクセス**: 初回PDF取得時専用の設計
   - **セッション連動**: セッション無効化時にURL期限も即座無効

3. **JavaScript側の変更点**
   ```javascript
   // 現在の実装
   const loadingTask = pdfjsLib.getDocument('/static/pdfs/xxxxx.pdf');
   
   // 署名付きURL実装後
   const loadingTask = pdfjsLib.getDocument('/secure/pdf/signed-token-here');
   ```

### データフロー詳細

| 段階 | 処理内容 | 実行場所 | 技術要素 |
|------|----------|----------|----------|
| 1. ページ生成 | 署名付きURL生成 | サーバー側 | HMAC署名、期限設定 |
| 2. HTML配信 | 署名付きURL埋め込み | テンプレート | Jinja2変数展開 |
| 3. PDF取得 | 署名付きURLアクセス | ブラウザ側 | PDF.js, XMLHttpRequest |
| 4. 認証・配信 | 署名検証→ファイル送信 | サーバー側 | 認証チェック、ファイルI/O |

## 技術仕様

### URL構造
```
/secure/pdf/<base64(signature)>?f=<filename>&exp=<expiry>&sid=<session_id>
```

### 署名アルゴリズム
```python
signature = hmac.new(
    SECRET_KEY, 
    f"{filename}:{expiry}:{session_id}".encode(), 
    hashlib.sha256
).hexdigest()
```

### データベース設計
```sql
-- PDF アクセスログテーブル拡張
ALTER TABLE access_logs ADD COLUMN pdf_access_method TEXT; -- 'direct', 'signed_url'
ALTER TABLE access_logs ADD COLUMN url_signature TEXT;
ALTER TABLE access_logs ADD COLUMN signature_valid BOOLEAN;
```

## 成功基準
1. ✅ `/static/pdfs/` 直接アクセスが完全に無効化される
2. ✅ 署名付きURLからのみPDFアクセス可能
3. ✅ URL期限切れ・改ざんが適切に検知される
4. ✅ セッション認証との統合が正常動作
5. ✅ 既存のPDF.js表示機能が維持される

## セキュリティテスト項目
- [ ] 直接URL攻撃テスト
- [ ] URL署名改ざんテスト  
- [ ] 期限切れURL使用テスト
- [ ] セッション詐称テスト
- [ ] レート制限動作テスト

## 関連ドキュメント
- [specifications.md](../../docs/specifications.md) Lines 148-151, 287-294
- [Phase 3 Security Requirements](../phases/phase3-security-operations.md)

## 依存関係
- ✅ TASK-003: セッション管理システム（認証基盤）
- 🔄 TASK-004: レート制限システム（組み合わせ強化）

## 注意事項
- 本番環境では必ずHTTPS必須
- 署名用秘密鍵の安全な管理が必要
- 既存PDF閲覧機能への影響最小化
- パフォーマンスへの影響考慮（キャッシュ戦略）