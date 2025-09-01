# PDF直接ダウンロード防止機能 - 技術仕様書

## 概要
既存の`secure_pdf_delivery`エンドポイントにReferrerチェック・User-Agentチェック機能を追加し、ブラウザからの直接PDF URLアクセスによるダウンロードを防止する。

## 実装状況 ✅ **完了済み** (2025-07-26)
- **実装済み**: セッション認証、トークン検証、アクセスログ
- **✅ 新規実装**: Referrerチェック、User-Agentチェック、強化されたセキュリティヘッダー
- **✅ 新規実装**: 3層設定管理システム（環境変数→DB→管理画面）
- **✅ 新規実装**: IP範囲・CIDR対応の柔軟なドメイン設定
- **✅ 新規実装**: 包括的テストスイート（11テストケース）

## 機能要件

### 1. Referrerチェック機能
#### 目的
PDF.jsを使用したアプリケーション内での表示のみを許可し、ブラウザでの直接アクセスを防止

#### 実装方針
- `Referer`ヘッダーが存在しない場合はアクセス拒否
- 許可されたドメインリストとの照合
- 設定ファイルでの許可ドメイン管理

#### 許可条件
```python
allowed_referrer_patterns = [
    request.host,           # 同一ホスト
    'localhost',           # 開発環境
    '127.0.0.1',          # ローカル開発
    # 設定ファイルで追加可能
]
```

### 2. User-Agentチェック機能
#### 目的
一般的なブラウザからの直接アクセスを制限し、PDF.js経由のアクセスを識別

#### 実装方針
- 基本的なUser-Agentの存在確認
- 疑わしいパターンの検出（wget, curl等）
- 設定による厳格モードのON/OFF

#### 制限対象
```python
blocked_user_agents = [
    '',                    # 空のUser-Agent
    'wget',               # コマンドラインツール
    'curl',               # コマンドラインツール
    'python-requests',    # スクリプト
    # その他の自動化ツール
]
```

### 3. 設定機能
#### 設定項目
```python
PDF_DOWNLOAD_PREVENTION = {
    'enabled': True,                    # 機能有効/無効
    'allowed_referrer_domains': [       # 許可ドメイン
        'localhost',
        '127.0.0.1'
    ],
    'strict_mode': False,               # 厳格モード
    'log_blocked_attempts': True,       # 拒否ログ出力
    'custom_error_message': None        # カスタムエラーメッセージ
}
```

## 技術仕様

### 1. アクセス制御フロー
```
1. 既存のセッション認証チェック（変更なし）
2. 既存のトークン検証（変更なし）
3. [新規] Referrerヘッダー検証
4. [新規] User-Agentヘッダー検証
5. 既存のファイル配信処理（ヘッダー強化）
```

### 2. 実装箇所
- **ファイル**: `app.py`
- **関数**: `secure_pdf_delivery` (line 1974-2093)
- **挿入位置**: トークン検証後、ファイル存在確認前

### 3. セキュリティヘッダー強化
既存のヘッダーに追加：
```python
headers = {
    # 既存のヘッダー（変更なし）
    'Content-Disposition': f'inline; filename="{filename}"',
    'Cache-Control': 'no-cache, no-store, must-revalidate',
    'Pragma': 'no-cache',
    'Expires': '0',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
    
    # 新規追加
    'Content-Security-Policy': "frame-ancestors 'self'",
    'X-Robots-Tag': 'noindex, nofollow, nosnippet, noarchive'
}
```

### 4. ログ機能強化
既存の`pdf_security.log_pdf_access`にフィールド追加：
```python
# 拒否時のログ項目追加
{
    "referer": request.headers.get('Referer', 'NONE'),
    "user_agent": request.headers.get('User-Agent', 'NONE'),
    "denial_reason": "invalid_referrer" | "blocked_user_agent"
}
```

## エラーハンドリング

### 1. Referrer検証失敗
- **HTTPステータス**: 403 Forbidden
- **レスポンス**: `{"error": "Access denied: Invalid referrer"}`
- **ログ**: `denial_reason: "invalid_referrer"`

### 2. User-Agent検証失敗
- **HTTPステータス**: 403 Forbidden
- **レスポンス**: `{"error": "Access denied: Invalid client"}`
- **ログ**: `denial_reason: "blocked_user_agent"`

## 下位互換性

### 1. 既存機能への影響
- **影響なし**: セッション認証、トークン検証、基本的なPDF配信
- **拡張のみ**: ログ機能、ヘッダー設定

### 2. 段階的導入
- **Phase 1**: 警告モードでログ出力のみ
- **Phase 2**: 実際のアクセス制御有効化

## テスト戦略

### 1. 単体テスト
- Referrerヘッダーの各パターンテスト
- User-Agentヘッダーの各パターンテスト
- 設定値による動作変更テスト

### 2. 統合テスト
- PDF.js経由の正常アクセステスト
- ブラウザ直接アクセスの拒否テスト
- 各種ブラウザでの動作確認

### 3. セキュリティテスト
- Referrer偽装攻撃テスト
- User-Agent偽装攻撃テスト
- 設定無効化での迂回テスト

## パフォーマンス考慮

### 1. 処理オーバーヘッド
- ヘッダー確認処理: ~1ms
- ドメイン照合処理: ~1ms
- 全体への影響: 無視できるレベル

### 2. メモリ使用量
- 設定値保持: ~1KB
- ログ機能拡張: ログ項目2つ追加

## 運用考慮事項

### 1. 設定管理
- 本番環境での適切なドメイン設定
- 開発環境での設定調整

### 2. モニタリング
- 拒否されたアクセスの監視
- 正常アクセスへの影響確認

### 3. 緊急時対応
- 設定による機能無効化オプション
- ログでの問題切り分け

## 実装順序

1. **設定機能の実装**
2. **Referrerチェック機能の実装**
3. **User-Agentチェック機能の実装**
4. **ログ機能の拡張**
5. **セキュリティヘッダーの強化**
6. **テストの実装と実行**

## 成功条件 ✅ **全て達成済み**

- [x] ブラウザからの直接PDFアクセスが403で拒否される
- [x] PDF.js経由のアクセスは正常に動作する
- [x] 拒否されたアクセスが適切にログに記録される
- [x] 既存機能に影響がない
- [x] パフォーマンスへの影響が最小限である
- [x] 管理画面での設定管理が可能
- [x] IP範囲・CIDR記法での柔軟な設定対応