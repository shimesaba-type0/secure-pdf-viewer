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
- [ ] ボタンの表示確認
- [ ] 1ページ目での無効状態
- [ ] 2ページ目以降での有効状態
- [ ] クリック時の動作確認
- [ ] レスポンシブデザインでの表示
- [ ] キーボードショートカット（Home）との連携

## 成功基準
- [ ] 最初のページボタンが適切に配置されている
- [ ] 1ページ目では無効状態になる
- [ ] 2ページ目以降では有効状態になる
- [ ] クリック時に1ページ目に移動する
- [ ] 既存の機能に影響しない

## 優先度
**Medium** - 利便性向上

## 担当者
開発チーム

## 期限
3週間以内

## 関連チケット
- 前提: なし
- 関連: TASK-011 (PDF再読み込みボタン)
- 後続: TASK-013 (テストケース作成)