# セッション管理機能詳細仕様書

## 概要
TASK-003-3で実装されたセッション管理機能の詳細仕様書。管理者がアクティブセッションを効率的に監視・管理するための包括的な機能を提供する。

## 主要機能

### 1. セッション一覧表示機能

#### 表示項目
- **セッションID**: 一意識別子（先頭16文字のみ表示、ホバーで全体表示）
- **メールアドレス**: 認証時のメールアドレス（ハッシュではなく実際のアドレス）
- **デバイス種別**: モバイル/タブレット/PC/その他（アイコン付き）
- **開始時刻**: セッション開始日時（YYYY-MM-DD HH:MM:SS形式）
- **残り時間**: 72時間からの残り時間（期限切れ2時間前に警告表示）
- **経過時間**: セッション開始からの経過時間（時間単位）
- **管理者メモ**: セッションごとのメモ（インライン編集可能）
- **操作**: 詳細表示ボタン

#### 統計情報表示
- **総セッション数**: 現在アクティブなセッション数
- **デバイス別集計**: スマホ/タブレット/PC別のセッション数

### 2. デバイス種別自動判定機能

#### 判定ロジック
```python
def detect_device_type(user_agent):
    ua_lower = user_agent.lower()
    
    if any(mobile in ua_lower for mobile in [
        'mobile', 'android', 'iphone', 'ipod', 'blackberry'
    ]):
        return 'mobile'
    elif any(tablet in ua_lower for tablet in [
        'tablet', 'ipad', 'kindle', 'silk'
    ]):
        return 'tablet'
    elif any(desktop in ua_lower for desktop in [
        'windows', 'macintosh', 'linux', 'x11'
    ]):
        return 'desktop'
    else:
        return 'other'
```

#### デバイス別アイコン・ラベル
- **モバイル**: 📱 スマホ
- **タブレット**: 📱 タブレット  
- **デスクトップ**: 💻 PC
- **その他**: ❓ その他

### 3. 高度なフィルター機能

#### フィルター項目
1. **セッションID**: 部分一致検索
2. **メールアドレス**: 部分一致検索
3. **デバイス種別**: ドロップダウン選択（全て/スマホ/タブレット/PC/その他）
4. **開始日**: 日付選択（YYYY-MM-DD形式）
5. **メモ**: 部分一致検索

#### フィルター実装
- **リアルタイム検索**: 入力・選択と同時に結果を更新
- **クライアントサイド処理**: JavaScriptによる高速フィルタリング
- **複数条件組み合わせ**: AND条件でのフィルタリング
- **フィルタークリア**: 一括クリア機能

### 4. ソート機能

#### ソート対象カラム
- セッションID（文字列）
- メールアドレス（文字列）
- デバイス種別（文字列）
- 開始時刻（日時）
- 残り時間（数値）
- 経過時間（数値）

#### ソート実装
- **クリック切り替え**: ヘッダークリックで昇順・降順切り替え
- **視覚的インジケーター**: ↑（昇順）・↓（降順）表示
- **デフォルトソート**: 開始時刻降順（新しいセッションが上位）

### 5. 管理者メモ機能

#### メモ編集
- **インライン編集**: セル内クリックで編集モード開始
- **最大文字数**: 500文字
- **保存・キャンセル**: 専用ボタンでの操作
- **リアルタイム反映**: 保存後即座に表示更新

#### API仕様
```javascript
// メモ更新API
POST /admin/api/update-session-memo
Content-Type: application/json

{
    "session_id": "session_id_here",
    "memo": "メモ内容"
}

// レスポンス
{
    "success": true,
    "message": "メモを更新しました"
}
```

### 6. リアルタイム更新機能

#### 自動更新
- **更新間隔**: 30秒
- **チェックボックス**: オン/オフ切り替え可能
- **最終更新時刻表示**: ヘッダーエリアに表示

#### 手動更新
- **更新ボタン**: ヘッダーエリアに配置
- **即座反映**: クリック時に最新データ取得

### 7. 専用管理ページ

#### ページ構成
- **URL**: `/admin/sessions`
- **アクセス**: 管理画面からの「📋 詳細管理」リンク
- **戻りリンク**: 管理画面への戻りボタン

#### ヘッダーエリア
- **ページタイトル**: アクティブセッション一覧
- **自動更新設定**: チェックボックス
- **最終更新時刻**: リアルタイム表示
- **手動更新ボタン**: 🔄 更新
- **戻りボタン**: ← 管理画面に戻る

### 8. ダッシュボード統合

#### メイン管理画面への統合
- **アクセス状況カード**: デバイス別セッション数表示
- **詳細管理リンク**: セッション一覧ページへの遷移
- **リアルタイム更新**: 30秒間隔でカウント更新

#### 表示項目
- **現在のアクセス数**: 総セッション数
- **📱 スマホ**: モバイルセッション数
- **📱 タブレット**: タブレットセッション数  
- **💻 PC**: デスクトップセッション数

### 9. セッション詳細専用URL機能

#### 専用URL設計
- **URL形式**: `/admin/sessions/<session_id>`
- **直接アクセス**: URLを直接入力してアクセス可能
- **ブックマーク対応**: 特定セッションの詳細をブックマーク
- **複数タブ**: 複数セッションの同時比較が可能

#### 詳細ページ機能
- **完全なセッション情報**: 全項目の詳細表示
- **メモ編集機能**: クリックして編集、リアルタイム保存
- **レスポンシブ対応**: デスクトップ・タブレット・モバイル最適化
- **ナビゲーション**: セッション一覧・管理画面への戻りリンク

#### テキスト表示改善
- **適切な折り返し**: 長いメモテキストの枠内表示
- **文字制御**: `word-wrap`, `word-break`, `overflow-wrap`による制御
- **視覚的一貫性**: 全要素が枠内に適切に収まる表示

## レスポンシブ対応

### デザイン方針
- **Mobile First**: モバイル優先設計
- **Progressive Enhancement**: 画面サイズに応じた機能拡張
- **横スクロール対応**: 小画面でも全カラム表示

### ブレークポイント設計

#### デスクトップ（769px以上）
- **レイアウト**: 横並び表示
- **フィルター**: 2行配置（3項目 + 2項目 + クリアボタン）
- **テーブル**: フル表示、適切なパディング

#### タブレット（480px-768px）
- **ヘッダー**: 縦並び配置
- **フィルター**: 縦並び配置
- **テーブル**: パディング・フォントサイズ調整
- **自動更新/最終更新**: フォントサイズ縮小

#### スマートフォン（480px以下）
- **ヘッダーアクション**: 縦並び、全幅表示
- **ボタン**: 中央揃え、適切なタッチターゲット
- **横スクロール**: テーブル全体の横スクロール対応
- **最小幅**: 800px（全カラム表示保証）

### CSS実装詳細

#### フィルタークリアボタン調整
```css
/* フィルタークリアボタンの位置調整 */
.filter-group .btn {
    margin-top: 2.0rem; /* ラベル高さ + gap を調整してボトムを揃える */
    align-self: flex-start;
    width: 100%; /* 他の入力フィールドと同じ幅 */
    padding: 0.5rem; /* 他の入力フィールドと同じパディング */
    font-size: 0.9rem; /* 他の入力フィールドと同じフォントサイズ */
    height: auto; /* 自動高さ調整 */
}
```

#### 横スクロール対応
```css
.sessions-table-container {
    background: white;
    border: 1px solid #e1e5e9;
    border-radius: 8px;
    overflow-x: auto; /* 横スクロール有効 */
    margin-bottom: 2rem;
}

.sessions-table {
    width: 100%;
    min-width: 800px; /* 小さい画面でも全カラム表示のための最小幅 */
    border-collapse: collapse;
    font-size: 0.9rem;
}
```

#### スマホヘッダー最適化
```css
@media (max-width: 480px) {
    .header-actions {
        flex-direction: column;
        align-items: stretch;
        gap: 0.5rem;
    }
    
    .header-actions .auto-refresh-setting,
    .header-actions .sessions-info {
        text-align: center;
        font-size: 0.75rem;
    }
    
    .header-actions .auto-refresh-setting label {
        justify-content: center; /* チェックボックスとテキストを中央配置 */
    }
    
    .header-actions .btn {
        width: 100%;
        text-align: center;
        justify-content: center;
        display: flex;
        align-items: center;
    }
}
```

## API仕様

### セッション情報取得
```http
GET /admin/api/active-sessions

Response:
{
    "sessions": [
        {
            "session_id": "abc123...",
            "email_address": "user@example.com",
            "device_type": "mobile",
            "start_time": "2025-07-23 10:30:25",
            "remaining_time": "71時間29分",
            "elapsed_hours": 0.5,
            "memo": "ユーザー名: 田中太郎"
        }
    ],
    "total_count": 1,
    "mobile_count": 1,
    "tablet_count": 0,
    "desktop_count": 0
}
```

### メモ更新
```http
POST /admin/api/update-session-memo
Content-Type: application/json

{
    "session_id": "abc123...",
    "memo": "新しいメモ内容"
}

Response:
{
    "success": true,
    "message": "メモを更新しました"
}
```

## データベース仕様

### session_statsテーブル拡張
```sql
-- memo カラム追加（TASK-003-3対応）
ALTER TABLE session_stats ADD COLUMN memo TEXT DEFAULT '';

-- device_type 利用拡張
-- 'mobile', 'tablet', 'desktop', 'other' の値を格納
-- User-Agent解析による自動判定結果
```

## JavaScript機能

### sessions.js主要機能
- **フィルタリング**: `applyFilters()` - リアルタイム検索
- **ソート**: `applySorting()` - カラムクリック対応
- **メモ編集**: `editMemo()`, `saveMemo()` - インライン編集
- **自動更新**: `startAutoRefresh()` - 30秒間隔更新
- **デバイス情報**: `getDeviceInfo()` - アイコン・ラベル取得

### admin.js統合機能
- **ダッシュボード更新**: デバイス別カウント表示
- **SSE連携**: リアルタイム通知対応
- **セッション管理**: 基本的なセッション表示機能

## セキュリティ考慮事項

### アクセス制御
- **管理者権限必須**: 全セッション管理機能へのアクセス
- **CSRF対策**: メモ更新API等でのトークン確認
- **入力検証**: メモ文字数制限、SQLインジェクション対策

### データ保護
- **メールアドレス表示**: 管理者のみ閲覧可能
- **セッションID部分表示**: 機密性とユーザビリティのバランス
- **監査ログ**: メモ更新履歴の記録

## セッション制限監視機能（TASK-003-5実装済み）

### 5. セッション制限設定機能 ✅ 2025-07-23完了

#### 管理画面設定UI
- **制限数設定**: 1-1000セッションの範囲で設定可能（デフォルト100）
- **監視有効/無効**: セッション制限機能のオン/オフ切り替え
- **リアルタイム状況表示**: 現在のセッション数と使用率の表示
- **警告表示**: 制限の80%以上で警告、90%以上でアラート

#### セッション制限チェック機能
```python
def check_session_limit():
    """
    セッション数制限をチェックする
    Returns:
        dict: {'allowed': bool, 'current_count': int, 'max_limit': int, 'warning': str}
    """
```

#### 制限実行タイミング
- **OTP認証完了前**: 制限到達時は認証を拒否
- **エラーメッセージ表示**: ユーザーに制限状況を通知
- **管理者警告**: SSE経由でリアルタイム警告配信

### 6. リアルタイム監視ダッシュボード ✅ 2025-07-23完了

#### 自動更新機能
- **更新間隔**: 30秒間隔での状況更新
- **使用率表示**: パーセンテージと分数形式での表示
- **警告レベル表示**: 視覚的な警告インジケーター

#### API エンドポイント
```javascript
// セッション制限状況取得
GET /admin/api/session-limit-status
Response: {
    "success": true,
    "current_sessions": 15,
    "max_sessions": 100,
    "usage_percentage": 15.0,
    "is_warning": false,
    "is_critical": false
}

// セッション制限設定更新
POST /admin/update-session-limits
Data: {
    "max_concurrent_sessions": "50",
    "session_limit_enabled": "on"
}
```

### 7. SSE警告通知システム ✅ 2025-07-23完了

#### 通知イベント
- **session_limit_warning**: 制限の80%以上で発生
- **session_limit_updated**: 設定変更時に発生

#### JavaScript処理
```javascript
function handleSessionLimitWarning(data) {
    // 警告メッセージ表示
    showSSENotification('⚠️ ' + data.message, 'warning');
    
    // 90%以上でアラートダイアログ表示
    if (data.usage_percentage >= 90) {
        alert(`🚨 セッション数制限に近づいています\n現在: ${data.current_count}/${data.max_limit}`);
    }
}
```

## データベース拡張

### settings テーブル追加設定
```sql
-- セッション制限関連設定
INSERT INTO settings (key, value, value_type, description, category, is_sensitive) VALUES
('max_concurrent_sessions', '100', 'integer', '同時接続数制限（警告閾値）', 'security', FALSE),
('session_limit_enabled', 'true', 'boolean', 'セッション数制限有効化', 'security', FALSE);
```

## 今後の拡張予定

### 機能追加候補
- **セッション詳細ページ**: 個別セッションの詳細情報表示
- **CSVエクスポート**: セッション一覧のデータ出力
- **アクセス履歴**: セッション内のページ遷移履歴
- **メールアラート機能**: セッション制限達成時の管理者メール通知 🔄 検討中

### パフォーマンス改善
- **ページネーション**: 大量セッション対応
- **サーバーサイドフィルタリング**: 重い処理の最適化
- **キャッシュ機能**: 頻繁なデータ取得の最適化