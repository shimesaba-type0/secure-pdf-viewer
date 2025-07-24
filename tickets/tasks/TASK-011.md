# TASK-011: PDF再読み込みボタンの追加

## 概要
PDF閲覧画面にPDFが表示されない場合の再読み込みボタンを追加する。

## 背景
- PDFが表示されないことがある
- 現在はページリロードしか対処法がない
- ユーザーが簡単に再読み込みできる機能が必要

## 実装内容

### 1. UIコンポーネント
- **場所**: `/templates/viewer.html`
- **追加**: 🔄 アイコンの再読み込みボタン
- **配置**: ページコントロール内（次ページボタンの隣）

### 2. JavaScript機能
- **場所**: `/static/js/pdf-viewer.js`
- **新規メソッド**: `reloadCurrentPDF()`
- **処理内容**:
  - 現在のPDFファイルパスを保持
  - PDF.jsドキュメントを破棄
  - 署名付きURLを再取得
  - PDFを再読み込み
  - エラーハンドリング

### 3. 実装詳細
```javascript
async reloadCurrentPDF() {
    if (!this.currentFileName) {
        this.showError('再読み込みするPDFがありません');
        return;
    }
    
    try {
        this.showLoading();
        // 現在のページ位置を保持
        const currentPage = this.currentPage;
        
        // PDFを再読み込み
        const signedUrl = await this.getSignedPdfUrl();
        if (signedUrl) {
            await this.loadPDF(signedUrl, this.currentFileName);
            // 元のページに戻る
            if (currentPage <= this.totalPages) {
                await this.renderPage(currentPage);
            }
        }
    } catch (error) {
        this.showError('PDF再読み込みに失敗しました: ' + error.message);
    }
}
```

## テストケース
- [ ] ボタンの表示確認
- [ ] PDF読み込み成功時の動作
- [ ] PDF読み込み失敗時のエラーハンドリング
- [ ] ページ位置の復元
- [ ] ボタンの有効/無効状態

## 成功基準
- [ ] 再読み込みボタンが適切に配置されている
- [ ] PDFが正常に再読み込みされる
- [ ] 現在のページ位置が保持される
- [ ] エラー時に適切なメッセージが表示される

## 優先度
**High** - ユーザビリティに直結

## 担当者
開発チーム

## 期限
2週間以内

## 関連チケット
- 前提: なし
- 関連: TASK-012 (最初のページに戻るボタン)
- 後続: TASK-013 (テストケース作成)