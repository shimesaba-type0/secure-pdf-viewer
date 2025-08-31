# Phase 2: API セキュリティ強化設計書

## 概要
TASK-021 Phase 2では、管理者APIとユーザーAPIのセキュリティを強化し、統一されたセキュリティレスポンスを実装します。

## 現状分析

### 管理者API（要保護）
1. `/admin/api/session-limit-status` - セッション制限状況取得（保護済み：session認証）
2. `/admin/api/active-sessions` - アクティブセッション一覧（保護要：管理者権限）
3. `/admin/api/update-session-memo` - セッションメモ更新（保護要：管理者権限）
4. `/admin/api/pdf-security-settings` (GET/POST) - PDF設定取得・更新（保護要：管理者権限）
5. `/admin/api/pdf-security-validate` - PDF設定検証（保護要：管理者権限）
6. `/admin/api/block-incidents` - ブロック事案一覧（保護要：管理者権限）
7. `/admin/api/incident-stats` - 事案統計（保護要：管理者権限）
8. `/admin/api/incident-search` - 事案検索（保護要：管理者権限）
9. `/admin/api/resolve-incident` - 事案解決（保護要：管理者権限）

### ユーザーAPI（現状維持）
1. `/api/generate-pdf-url` - PDF URL生成（ユーザー認証必要）
2. `/api/session-info` - セッション情報取得（ユーザー認証必要）
3. `/api/events` - イベントストリーム（ユーザー認証必要）
4. `/api/security-event` - セキュリティイベント記録（内部API）
5. `/api/logs/*` - ログAPI群（管理者権限必要）

## セキュリティ要件

### 1. 管理者API保護
- **権限チェック**: 全管理者APIに `@require_admin_session` デコレータ適用
- **CSRF対策**: POSTリクエストにCSRFトークン検証追加
- **レート制限**: 管理者APIの呼び出し頻度制限（基本設定）

### 2. エラーレスポンス統一
```python
# 標準化されたエラーレスポンス
{
    "error": "Unauthorized",          # 401: 認証なし
    "message": "Access denied",       # 403: 権限なし  
    "timestamp": "2025-08-31T10:30:00Z"
}
```

### 3. セキュリティヘッダー
```python
# セキュリティヘッダー追加
"X-Content-Type-Options": "nosniff",
"X-Frame-Options": "DENY",
"X-XSS-Protection": "1; mode=block",
"Strict-Transport-Security": "max-age=31536000"
```

## 実装方針

### Phase 2A: 管理者API保護強化
1. **権限チェック強化**
   - 未保護の管理者APIに `@require_admin_session` デコレータ追加
   - 既存保護APIのデコレータ統一

2. **CSRF保護実装**
   - `generate_csrf_token()` 関数実装
   - `validate_csrf_token()` 関数実装
   - POST系管理者APIにCSRF検証追加

### Phase 2B: エラーレスポンス統一
1. **統一エラーハンドラー**
   - `create_error_response()` 関数実装
   - タイムスタンプ統一（アプリケーション設定準拠）
   - セキュリティ情報の非開示

2. **レスポンスヘッダー強化**
   - セキュリティヘッダー自動付与
   - API専用レスポンス処理

## 実装ファイル

### 新規作成
1. **security/api_security.py**
   ```python
   def generate_csrf_token(session_id: str) -> str
   def validate_csrf_token(token: str, session_id: str) -> bool
   def create_error_response(error_type: str, message: str = None) -> tuple
   def add_security_headers(response) -> Response
   def apply_rate_limit(endpoint: str, user_id: str) -> bool
   ```

### 修正ファイル
1. **app.py**
   - 管理者API群への `@require_admin_session` デコレータ追加
   - CSRF保護の統合
   - エラーレスポンス統一

2. **database/models.py**
   - CSRFトークン管理機能追加（必要に応じて）

## テスト項目

### セキュリティテスト
1. **権限テスト**
   - 非管理者による管理者API呼び出し拒否
   - 未認証による管理者API呼び出し拒否
   - 有効な管理者による正常アクセス

2. **CSRF保護テスト**
   - 無効なCSRFトークンでの拒否
   - 有効なCSRFトークンでの受理
   - トークン未送信での拒否

3. **エラーレスポンステスト**
   - 401/403エラーの適切な返却
   - エラーメッセージの統一性
   - セキュリティ情報の非漏洩

### パフォーマンステスト
1. **レート制限テスト**
   - 正常範囲内のリクエスト処理
   - 制限値超過時の適切な拒否

## 成功基準
- [ ] 全管理者APIが適切に保護される
- [ ] CSRF攻撃が防止される  
- [ ] エラーレスポンスが統一される
- [ ] セキュリティヘッダーが適用される
- [ ] 既存機能に影響しない
- [ ] パフォーマンスが維持される

## セキュリティ向上効果
- **権限昇格攻撃防止**: 未保護API経由の権限昇格を阻止
- **CSRF攻撃防止**: 管理者操作の不正実行を阻止
- **情報漏洩防止**: エラーメッセージからの情報漏洩を阻止
- **攻撃面の縮小**: 統一されたセキュリティ境界の確立