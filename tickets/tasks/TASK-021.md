# TASK-021: 権限制御とセキュリティ強化

## 概要
TASK-019で実装した管理者権限システムを基盤として、セキュリティを強化します。監査ログ、セッション管理、API保護などの高度なセキュリティ機能を追加実装します。

## 背景・目的
TASK-019で基本的な管理者権限システムが完成したため、セキュリティをさらに強化します：
- 管理者操作の詳細監査ログ実装
- セッションセキュリティの強化
- API セキュリティの向上
- 多層防御システムの構築

## 要件

### セキュリティ要件
1. **アクセス制御** *(TASK-019で基本実装済み)*
   - ~~管理画面は管理者のみアクセス可能~~ ✅ 完了
   - API エンドポイントの権限チェック強化
   - ~~設定変更は管理者のみ可能~~ ✅ 完了

2. **セッション管理強化**
   - 管理者セッションの特別な管理
   - セッションハイジャック対策
   - 管理者ログアウト時の完全なセッション無効化

3. **監査ログ**
   - 管理者のすべての操作をログ記録
   - 権限変更の詳細ログ
   - 不正アクセス試行の記録

4. **多層防御**
   - IPアドレス制限（オプション）
   - 時間ベースのアクセス制御（オプション）
   - 管理者用の強化認証（将来拡張）

### 技術仕様

#### 権限チェック機能 *(TASK-019で実装済み)*
```python
# ✅ 既存実装済み (database/models.py)
def is_admin(email):
    """メールアドレスが管理者かチェック"""
    
# ✅ 既存実装済み (app.py: @require_admin_permission)
# def require_admin(f):  # 名前が異なる
    
# 新規実装予定
def check_admin_session(session_id):
    """管理者セッションの有効性チェック"""
```

#### セキュリティログ強化
```python
def log_admin_action(admin_email, action, details, ip_address):
    """管理者操作のログ記録"""
    
def log_unauthorized_access(email, endpoint, ip_address):
    """不正アクセス試行のログ記録"""
```

#### 権限制御対象エンドポイント
1. **管理画面系**
   - `/admin/*` - 全ての管理画面
   - `/admin/api/*` - 管理API

2. **設定変更系**
   - 設定値の変更
   - システム状態の変更
   - ユーザー管理操作

3. **ログ閲覧系**
   - アクセスログ閲覧
   - セキュリティログ閲覧
   - セッション管理

### 実装項目

#### Phase 1: セッション管理強化 *(基本権限制御はTASK-019で完了)*

**設計書**: `docs/admin-session-security-design.md`

**実装フェーズ分割**:

1. **Sub-Phase 1A: データベース基盤整備** ✅ **完了**
   - ✅ `admin_sessions` テーブル作成（9カラム、インデックス付き）
   - ✅ セキュリティ設定3項目の追加（admin_session_timeout, admin_session_verification_interval, admin_session_ip_binding）
   - ✅ 基本的なCRUD関数実装（create_admin_session, verify_admin_session, update_admin_session_verification, delete_admin_session, get_admin_session_info, cleanup_expired_admin_sessions）
   - ✅ テスト実装・実行完了（12テスト全パス）
   - ✅ lint・フォーマッター実行完了  
   - ✅ ブラウザ動作確認完了（セキュリティフラグ、IPアドレス検証など全機能動作確認済み）

2. **Sub-Phase 1B: 管理者セッション作成・検証** ✅ **完了**
   - ✅ `create_admin_session()` 関数実装（Sub-Phase 1Aで完了）
   - ✅ `verify_admin_session()` 関数実装（Sub-Phase 1Aで完了）
   - ✅ 管理者ログイン時のセッション作成処理（app.py:1615-1622に`create_admin_session()`統合完了）
   - ✅ 管理者権限チェック時のセッション検証処理（`@require_admin_permission`デコレータに`verify_admin_session()`統合完了）
   - ✅ データベースロック問題解決（既存接続再利用による同期化）
   - ✅ ブラウザ動作確認完了（管理画面アクセス200 OK、セッション検証成功）

3. **Sub-Phase 1C: 強化デコレータ** ✅ **完了**
   - ✅ `@require_admin_session` デコレータ実装（5段階セキュリティチェック）
   - ✅ 既存の `@require_admin_permission` との統合（別名として定義）
   - ✅ 全管理画面への適用（リダイレクト先修正含む）
   - ✅ 包括的テストコード追加（8テストケース）
   - ✅ ブラウザ動作確認完了（認証フロー・管理画面アクセス・セッション検証ログ確認済み）

4. **Sub-Phase 1D: セッションハイジャック対策**
   - セッションID再生成機能
   - IP/ユーザーエージェント検証
   - 異常パターン検出

5. **Sub-Phase 1E: 完全ログアウト機能**
   - `admin_complete_logout()` 関数実装
   - 多層削除処理（admin_sessions, session_stats, OTP削除）
   - ログアウトエンドポイント拡張

6. **Sub-Phase 1F: 統合・動作確認**
   - エンドツーエンドテスト
   - ブラウザ動作確認
   - セキュリティ検証

#### Phase 2: API セキュリティ
1. **管理API の保護**
   - 全管理APIに権限チェック
   - CSRF トークンの検証
   - レート制限の適用

2. **エラーレスポンスの統一**
   - 401 Unauthorized の適切な返却
   - 403 Forbidden の適切な返却
   - セキュリティ情報の非開示

#### Phase 3: 監査とログ
1. **操作ログの強化**
   - 管理者の全操作を記録
   - ログのタイムスタンプ統一
   - ログレベルの分類

2. **セキュリティイベント検知**
   - 不正アクセス試行の検知
   - 異常なパターンの検知
   - アラート機能（将来拡張）

### データベース拡張

#### Phase 1 関連テーブル

##### admin_sessions テーブル追加 *(Sub-Phase 1A)*
```sql
CREATE TABLE admin_sessions (
    session_id TEXT PRIMARY KEY,
    admin_email TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_verified_at TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    security_flags JSON,
    verification_token TEXT
);
```

#### admin_actions テーブル追加 *(Phase 3)*
```sql
CREATE TABLE admin_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_email TEXT NOT NULL,
    action_type TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    details JSON,
    ip_address TEXT,
    user_agent TEXT,
    session_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    risk_level TEXT DEFAULT 'low'
);
```

#### セキュリティ設定追加
```sql
-- settings テーブルに追加
INSERT INTO settings (key, value, value_type, description, category) VALUES
('admin_session_timeout', '3600', 'integer', '管理者セッション有効期限（秒）', 'security'),
('admin_ip_restriction', '', 'string', '管理者アクセス許可IP（カンマ区切り）', 'security'),
('admin_audit_retention', '365', 'integer', '管理者監査ログ保持期間（日）', 'security');
```

### 成功基準
- [x] 管理者のみが管理画面にアクセスできる *(TASK-019で完了)*
- [x] 一般ユーザーは管理機能にアクセスできない *(TASK-019で完了)*
- [ ] 全ての管理者操作がログに記録される **← Phase 3で実装**
- [ ] 不正アクセス試行が検知・記録される **← Phase 3で実装**
- [x] 管理者セッションが強化管理される **← Sub-Phase 1Aで完了**
- [x] エラーハンドリングが適切に動作する *(TASK-019で基本完了)*
- [ ] 権限昇格攻撃が防止される **← Sub-Phase 1C/1Dで強化実装**

### セキュリティテスト項目
1. **権限制御テスト**
   - [ ] 管理者権限なしでの管理画面アクセス拒否
   - [ ] 権限昇格攻撃の防止
   - [ ] セッション固定攻撃の防止

2. **認証テスト**
   - [x] 無効なセッションでのアクセス拒否 *(Sub-Phase 1Aで確認済み)*
   - [x] セッション有効期限の確認 *(Sub-Phase 1Aで確認済み)*
   - [ ] 管理者ログアウト後のセッション無効化 **← Sub-Phase 1Eで実装**

3. **ログテスト**
   - [ ] 管理者操作のログ記録
   - [ ] 不正アクセス試行のログ記録
   - [ ] ログの改ざん防止

### パフォーマンス考慮事項
- 権限チェックのキャッシュ化
- データベースクエリの最適化
- ログ書き込みの非同期処理

## 実装ファイル
1. ~~**auth/admin_auth.py** (新規)~~ → **database/models.py** *(TASK-019で実装済み)*
   - ~~管理者権限チェック機能~~ ✅ 完了

2. **database/models.py** ✅ **Sub-Phase 1A完了**
   - 管理者関連のデータベース操作
   - ✅ **admin_sessions テーブル作成・CRUD関数実装完了**
   - **admin_actions テーブル操作関数 (Phase 3で追加)**

3. **app.py** ✅ **Sub-Phase 1C完了**
   - ~~ルートへの権限チェック適用~~ ✅ 完了（TASK-019）
   - ✅ **セッション管理強化実装完了（Sub-Phase 1B/1C）**
   - ✅ **require_admin_session デコレータ実装（Sub-Phase 1C）**
   - ✅ **強化セキュリティチェック機能統合（Sub-Phase 1C）**

4. **tests/test_enhanced_admin_decorator.py** ✅ **Sub-Phase 1C追加**
   - ✅ **強化デコレータの包括的テストコード（8テストケース）**
   - ✅ **セッション環境検証・統合テスト・エラーハンドリング確認**

5. **security/audit_logger.py** (新規)
   - 監査ログ機能 (Phase 3で実装予定)

## 関連チケット
- TASK-019: 管理者権限システムの実装
- TASK-020: 管理者権限フロントエンド実装

## 完了予定日
2025-07-30

## ステータス
- [x] 要件定義完了
- [x] セキュリティ設計完了 (`docs/admin-session-security-design.md`)
- [x] 実装開始（Sub-Phase 1A完了）
- [x] セキュリティテスト（Sub-Phase 1A/1B/1C分完了）
- [ ] 完了（Sub-Phase 1D〜1F残り）

### 進捗状況
- **Phase 1 セッション管理強化**: 3/6フェーズ完了（50.0%）
  - ✅ Sub-Phase 1A: データベース基盤整備
  - ✅ Sub-Phase 1B: 管理者セッション作成・検証（データベースロック問題解決、ブラウザ動作確認済み）
  - ✅ Sub-Phase 1C: 強化デコレータ（実装完了、ブラウザ動作確認済み）
  - ⏳ Sub-Phase 1D: セッションハイジャック対策（次回実装）