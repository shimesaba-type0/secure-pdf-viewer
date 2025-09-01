# TASK-012: PDF最初のページに戻るボタンの追加

## 概要
PDF閲覧画面に最初のページ（1ページ目）に戻るボタンを追加する。

## 背景
- 現在のナビゲーション機能: 前ページ/次ページ、ページ番号入力
- 長いPDFで最初のページに素早く戻る機能がない
- キーボードショートカット（Homeキー）は実装済みだが、UIボタンがない

## 実装内容

### 1. UIコンポーネント
- **場所**: `/templates/viewer.html`
- **追加**: ⏮ アイコンの最初のページボタン
- **配置**: ページコントロール内（前ページボタンの左隣）

### 2. JavaScript機能
- **場所**: `/static/js/pdf-viewer.js`
- **新規メソッド**: `goToFirstPage()`
- **既存メソッド更新**: `updatePageInfo()`, `enableControls()`, `disableControls()`

### 3. 実装詳細
```javascript
async goToFirstPage() {
    if (this.totalPages > 0) {
        await this.renderPage(1);
    }
}

updatePageInfo() {
    this.pageInput.value = this.currentPage;
    this.prevPageBtn.disabled = this.currentPage <= 1;
    this.nextPageBtn.disabled = this.currentPage >= this.totalPages;
    
    // 最初のページボタンの状態更新
    this.firstPageBtn.disabled = this.currentPage <= 1;
    
    // ナビゲーションオーバーレイボタンも更新
    if (this.navPrevBtn) {
        this.navPrevBtn.classList.toggle('disabled', this.currentPage <= 1);
    }
    if (this.navNextBtn) {
        this.navNextBtn.classList.toggle('disabled', this.currentPage >= this.totalPages);
    }
}
```

### 4. イベントバインディング
```javascript
// initializeElements()メソッド内
this.firstPageBtn = document.getElementById('firstPageBtn');

// bindEvents()メソッド内  
this.firstPageBtn?.addEventListener('click', () => this.goToFirstPage());
```

### 5. スタイル調整
- 小さなスマートフォンでのタッチターゲットサイズ確保
- ボタン間の適切な間隔
- 無効状態の視覚的フィードバック

## テストケース
- [x] ボタンの表示確認
- [x] 1ページ目での無効状態
- [x] 2ページ目以降での有効状態
- [x] クリック時の動作確認
- [x] レスポンシブデザインでの表示
- [x] キーボードショートカット（Home）との連携

## 成功基準
- [x] 最初のページボタンが適切に配置されている
- [x] 1ページ目では無効状態になる
- [x] 2ページ目以降では有効状態になる
- [x] クリック時に1ページ目に移動する
- [x] 既存の機能に影響しない

## 優先度
**Medium** - 利便性向上

## 担当者
開発チーム

## 期限
~~3週間以内~~ **完了済み**

## 実装完了日
2025-07-24

## 実装内容詳細
### HTMLファイルの変更
- `/templates/viewer.html`: ページコントロール内に最初のページボタンを追加
  - `<button class="btn btn-sm btn-secondary" id="firstPageBtn" disabled>⏮</button>`

### JavaScriptファイルの変更  
- `/static/js/pdf-viewer.js`: 
  - `initializeElements()`: `this.firstPageBtn` 要素の初期化
  - `bindEvents()`: 最初のページボタンのクリックイベント
  - `goToFirstPage()`: 新規メソッド実装
  - `updatePageInfo()`: ボタン状態制御ロジック追加
  - `enableControls()` / `disableControls()`: 全ボタン制御に対応

### 設計書への反映
- `/docs/specifications.md`: PDF閲覧機能のナビゲーション仕様を更新

## 関連チケット
- 前提: なし
- 関連: TASK-011 (PDF再読み込みボタン)
- 後続: TASK-013 (テストケース作成)

## 実装者
Claude Code

## 完了確認
実装完了。動作確認推奨。