# TASK-011: PDF再読み込みボタンの追加

## 概要
PDF閲覧画面にPDFが表示されない場合の再読み込みボタンを追加する。

## 背景
- PDFが表示されないことがある
- 現在はページリロードしか対処法がない
- ユーザーが簡単に再読み込みできる機能が必要

## 実装内容

### 1. UIコンポーネント ✅ 完了
- **場所**: `/templates/viewer.html`
- **追加**: 「再読み込み」ボタン（絵文字なし、明確なテキスト表示）
- **配置**: display-controls内（全画面ボタンと同じ行）
- **レスポンシブ対応**: スマホ表示でページ操作とディスプレイ操作の2段レイアウト

### 2. JavaScript機能 ✅ 完了
- **場所**: `/static/js/pdf-viewer.js`
- **新規メソッド**: `reloadCurrentPDF()`
- **処理内容**:
  - 現在のPDFファイル名とページ位置を保持
  - 既存PDF.jsドキュメントとCanvasをクリア
  - 署名付きURLを再取得（`getSignedPdfUrl()`）
  - PDFを直接再読み込み（競合回避のためloadPDF()を使用せず）
  - 元のページ位置を復元（範囲チェック付き）
  - 包括的エラーハンドリング

### 3. 実装詳細 ✅ 完了
実装された最終コード:
```javascript
async reloadCurrentPDF() {
    if (!this.currentFileName) {
        this.showError('再読み込みするPDFがありません');
        return;
    }
    
    try {
        this.showLoading();
        console.log('PDF再読み込み開始:', this.currentFileName);
        
        // 現在のページ位置を保持
        const targetPage = this.currentPage;
        const fileName = this.currentFileName;
        
        // PDFを再読み込み
        const signedUrl = await this.getSignedPdfUrl();
        console.log('署名付きURL取得結果:', signedUrl);
        
        if (signedUrl) {
            // 既存のPDFをクリア
            this.pdfDoc = null;
            this.canvas = null;
            
            // Load PDF document directly without using loadPDF to avoid conflicts
            const loadingTask = pdfjsLib.getDocument(signedUrl);
            this.pdfDoc = await loadingTask.promise;
            
            this.currentFileName = fileName;
            this.totalPages = this.pdfDoc.numPages;
            
            // Update UI
            this.updateUI();
            this.enableControls();
            this.showNavigationHelp();
            
            // Ensure container has proper dimensions before rendering
            await this.waitForContainerReady();
            
            // 元のページに戻る（範囲チェック）
            const pageToRender = Math.min(targetPage, this.totalPages);
            await this.renderPage(pageToRender);
            
            console.log('PDF再読み込み完了, ページ:', pageToRender);
        } else {
            throw new Error('署名付きURLの取得に失敗しました');
        }
    } catch (error) {
        console.error('PDF再読み込みエラー:', error);
        this.showError('PDF再読み込みに失敗しました: ' + error.message);
    }
}
```

## テストケース ✅ 完了
- [x] ボタンの表示確認（HTMLテンプレート構造テスト）
- [x] JavaScript関数の存在確認（reloadCurrentPDF、getSignedPdfUrl）
- [x] 未認証ユーザーのアクセス拒否確認
- [x] 実装されたエラーハンドリング機能確認
- [x] レスポンシブ対応確認

## 成功基準 ✅ 達成
- [x] 再読み込みボタンが適切に配置されている（display-controls内、レスポンシブ対応）
- [x] PDFが正常に再読み込みされる（署名付きURL再取得による確実な処理）
- [x] 現在のページ位置が保持される（範囲チェック付きページ復元）
- [x] エラー時に適切なメッセージが表示される（包括的エラーハンドリング）

## 実装完了情報

### 完了日時
2025-07-24

### 実装ファイル
- `templates/viewer.html`: 再読み込みボタンUI追加
- `static/js/pdf-viewer.js`: reloadCurrentPDF()メソッド実装
- `docs/specifications.md`: 仕様書更新
- `tests/test_pdf_reload_feature.py`: テストケース作成

### Git情報
- **コミット**: `493d4bc - feat: TASK-011 PDF再読み込みボタンの実装`
- **ブランチ**: `issue1`
- **プッシュ済み**: ✅

### 技術的解決ポイント
1. **期限切れURL対応**: 再読み込み時に常に新しい署名付きURLを取得
2. **競合回避**: loadPDF()を使わず直接PDF.js APIを使用
3. **レスポンシブ対応**: デスクトップとスマホでの適切な表示
4. **ページ位置保持**: 元のページに確実に戻る機能

## 優先度
**High** - ユーザビリティに直結 ✅ **完了**

## 担当者
開発チーム ✅ **完了**

## 期限
2週間以内 ✅ **期限内完了**

## 関連チケット
- 前提: なし
- 関連: TASK-012 (最初のページに戻るボタン) ✅ 完了済み
- 後続: ✅ テストケース作成完了（TASK-013は統合）

---

## ✅ TASK-011 完了
**ステータス**: 🟢 **COMPLETED**  
**完了日**: 2025-07-24  
**品質**: 全成功基準達成、テスト完了、ドキュメント更新済み