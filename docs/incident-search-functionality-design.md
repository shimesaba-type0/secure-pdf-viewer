# インシデント検索機能設計書

**文書バージョン**: 1.0  
**作成日**: 2025-07-27  
**関連チケット**: TASK-004拡張機能  

## 概要

レート制限システムで生成される大量のブロックインシデントレコードに対して、管理者が効率的にインシデント対応を行うための検索機能を実装する。

## 現状の問題

### 問題点
1. **大量レコード生成**: 攻撃時に数百〜数千件のインシデントレコードが作成される
2. **表示の非効率性**: 管理画面で全件表示されるため実用的でない
3. **検索機能の欠如**: 特定インシデントの検索手段がない
4. **運用効率の低下**: 正当ユーザーの誤ブロック解除に時間がかかる

### 現在の実装状況
- ~~インシデント一覧表示のみ（全件表示）~~ → **削除済み**
- ~~インシデントID検索フォームなし~~ → **実装済み**
- 統計情報表示のみ → **維持**

## 設計方針

### 基本コンセプト
- **検索前**: 0件表示（デフォルト状態）
- **検索後**: 1件表示（インシデントIDは一意のため）
- **用途特化**: 正当ユーザーの誤ブロック解除が主目的

### 運用想定
1. ユーザーからブロック解除依頼（インシデントID提供）
2. 管理者がインシデントID検索
3. 該当インシデントの詳細確認と解除処理

## 機能仕様

### 検索機能
- **検索対象**: インシデントID（完全一致）
- **入力形式**: `BLOCK-YYYYMMDDHHMMSS-XXXX`
- **検索結果**: 0件または1件
- **レスポンス**: リアルタイム検索（非同期）

### UI設計
```
┌─────────────────────────────────────┐
│ インシデント検索                      │
├─────────────────────────────────────┤
│ インシデントID: [________________] [検索] │
│                                     │
│ ┌─── 検索結果 ────────────────────┐   │
│ │ （検索前は空、検索後は1件表示）      │   │
│ │                                 │   │
│ │ [インシデント詳細テーブル]           │   │
│ │ [解除ボタン]                     │   │
│ └─────────────────────────────────┘   │
└─────────────────────────────────────┘
```

### API設計
```
GET /admin/api/incident-search?incident_id={ID}

Response:
{
  "success": true,
  "incident": {
    "incident_id": "BLOCK-20250727140530-A4B2",
    "ip_address": "192.168.1.100", 
    "block_reason": "認証失敗回数制限(5回/10分)",
    "created_at": "2025-07-27 14:05:30",
    "resolved": false,
    "resolved_at": null,
    "resolved_by": null,
    "admin_notes": null
  }
}

Error Response:
{
  "success": false,
  "error": "インシデントが見つかりません"
}
```

## 実装仕様

### バックエンド実装

#### 新規APIエンドポイント
```python
@app.route('/admin/api/incident-search', methods=['GET'])
@admin_required
def api_incident_search():
    """インシデントID検索API"""
    incident_id = request.args.get('incident_id', '').strip()
    
    if not incident_id:
        return jsonify({'success': False, 'error': 'インシデントIDが指定されていません'})
    
    # インシデントID形式検証
    if not re.match(r'^BLOCK-\d{14}-[A-Z0-9]{4}$', incident_id):
        return jsonify({'success': False, 'error': '無効なインシデントID形式です'})
    
    # インシデント検索
    incident = incident_manager.get_incident_by_id(incident_id)
    
    if not incident:
        return jsonify({'success': False, 'error': 'インシデントが見つかりません'})
    
    return jsonify({'success': True, 'incident': dict(incident)})
```

#### 入力検証
- インシデントID形式チェック（正規表現）
- SQLインジェクション防止（既存実装使用）
- 管理者権限チェック（既存実装使用）

### フロントエンド実装

#### HTML構造
```html
<div class="incident-search-section">
    <h4>インシデント検索</h4>
    <div class="search-form">
        <label for="incidentIdSearch">インシデントID:</label>
        <div class="search-input-group">
            <input type="text" id="incidentIdSearch" 
                   placeholder="BLOCK-20250727140530-A4B2" 
                   maxlength="24">
            <button type="button" onclick="searchIncident()">検索</button>
            <button type="button" onclick="clearSearch()">クリア</button>
        </div>
    </div>
    
    <div id="searchResults" class="search-results">
        <!-- 検索結果表示エリア（初期状態は空） -->
    </div>
</div>
```

#### JavaScript実装
```javascript
async function searchIncident() {
    const incidentId = document.getElementById('incidentIdSearch').value.trim();
    const resultsDiv = document.getElementById('searchResults');
    
    if (!incidentId) {
        showMessage('インシデントIDを入力してください', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/admin/api/incident-search?incident_id=${encodeURIComponent(incidentId)}`);
        const data = await response.json();
        
        if (data.success) {
            displaySearchResult(data.incident);
        } else {
            showMessage(data.error, 'error');
            resultsDiv.innerHTML = '';
        }
    } catch (error) {
        showMessage('検索エラーが発生しました', 'error');
        resultsDiv.innerHTML = '';
    }
}
```

### セキュリティ考慮事項

1. **入力検証**: インシデントID形式の厳格チェック
2. **権限制御**: 管理者権限必須
3. **SQLインジェクション防止**: パラメータ化クエリ使用
4. **レート制限**: 既存システムに準拠
5. **ログ記録**: 検索操作のログ出力

## テスト仕様

### 単体テスト
1. **API正常系**: 有効なインシデントIDで検索成功
2. **API異常系**: 
   - 無効なインシデントID形式
   - 存在しないインシデントID
   - 空のインシデントID
3. **権限テスト**: 非管理者ユーザーのアクセス拒否
4. **入力検証テスト**: 各種不正入力パターン

### 統合テスト
1. **E2Eシナリオ**: インシデント作成→検索→解除の流れ
2. **UI操作テスト**: 検索フォームの動作確認
3. **エラーハンドリングテスト**: ネットワークエラー等の処理

### パフォーマンステスト
- **検索速度**: インシデントID検索の応答時間
- **同時接続**: 複数管理者による同時検索操作

## 実装スケジュール

1. **Phase 1**: バックエンドAPI実装（1-2時間） → ✅ **完了**
2. **Phase 2**: フロントエンド実装（1-2時間） → ✅ **完了**
3. **Phase 3**: テスト実装・実行（1時間） → ✅ **完了**
4. **Phase 4**: 統合・リファクタリング（30分） → ✅ **完了**
5. **Phase 5**: UI最適化（一覧削除・検索特化）→ ✅ **完了**

## 関連ドキュメント

- [TASK-004: 詳細レート制限システム実装](../tickets/tasks/TASK-004.md)
- [レート制限システム設計仕様書](rate-limiting-system-design.md)
- [セキュリティ設計理念](security-design-philosophy.md)

## 実装完了事項

### ✅ **Phase 5: UI最適化（2025-07-27完了）**
- **インシデント一覧テーブル削除**: 大量データ時の性能問題解決
- **制限IP一覧テーブル削除**: レート制限管理の統計特化
- **検索特化UI**: インシデントID検索→詳細表示→操作の効率的フロー
- **統計情報維持**: 概要把握用として未解決件数等の統計は継続表示
- **デモページ提供**: 包括的なテスト環境とドキュメント
- **UIクリーンアップ**: 不要なヘルプテキスト削除とシンプル化

### 📋 **最終的な運用フロー**
1. **デフォルト**: インシデント・制限IP表示0件（すっきりした画面）
2. **概要把握**: レート制限統計とインシデント統計で全体状況確認
3. **個別対応**: インシデントID入力→検索→詳細確認→解除操作
4. **IP制限解除**: インシデント解除により制限IPも自動解除

## 将来の拡張案

### Phase 2機能候補
- 部分検索機能（IPアドレス、日付範囲）
- エクスポート機能（CSV、JSON）
- インシデント統計レポート機能

### 運用改善案
- 古いインシデントの自動削除
- インシデント発生通知機能
- ダッシュボード統合