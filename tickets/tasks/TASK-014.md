# TASK-014: PDF.js Canvas競合エラー修正

## 🐛 問題の概要
PDF再読み込み時に大量のcanvas競合エラーが発生し、レンダリングが失敗している。

## 📋 エラー詳細
```
Page rendering failed: Error: Cannot use the same canvas during multiple render() operations. 
Use different canvas or ensure previous operations were cancelled or completed.
```

## 🔍 問題分析
1. **ウォーターマーク自動更新との競合**
   - `updateWatermarkOnly()` (pdf-viewer.js:164-168) が1分ごとに `renderPage()` を呼び出し
   - PDF再読み込み処理と同時実行されて競合が発生

2. **レンダリングタスクの重複**
   - 既存のレンダリング処理が完了前に新しいレンダリングが開始
   - PDF.jsの同一canvas制限に抵触

## 🎯 解決方針
1. **レンダリング排他制御の実装**
   - フラグによる重複実行防止
   - 既存タスクのキャンセル処理

2. **ウォーターマーク更新の適切化**
   - レンダリング中の更新停止
   - 完了後の再開制御

## ✅ 完了条件
- [x] canvas競合エラーの解消
- [x] PDF再読み込み処理の安定化
- [x] ウォーターマーク更新機能の正常動作

## 🔧 実装場所
- `static/js/pdf-viewer.js:15-17` (排他制御変数追加)
- `static/js/pdf-viewer.js:169-171` (ウォーターマーク更新競合回避)
- `static/js/pdf-viewer.js:299-310` (レンダリング排他制御)
- `static/js/pdf-viewer.js:417-418` (renderTask管理)
- `static/js/pdf-viewer.js:431-434` (リソースクリーンアップ)

## 🛠️ 実装内容
### レンダリング排他制御の実装
- `isRendering`フラグによる重複実行防止
- `renderTask`による既存レンダリングタスクの管理・キャンセル
- レンダリング中のウォーターマーク更新スキップ機能

### 技術仕様
- **排他制御**: `isRendering`フラグによる単一レンダリング保証
- **タスク管理**: `renderTask.cancel()`による既存処理のキャンセル  
- **リソース管理**: `finally`ブロックでのフラグ・タスクリセット

## 🚨 優先度
**HIGH** - ユーザビリティに直接影響

## 📅 ステータス
- **作成日**: 2025-07-24
- **完了日**: 2025-07-24
- **状態**: Completed