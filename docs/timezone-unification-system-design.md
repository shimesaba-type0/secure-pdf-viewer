# タイムゾーン統一管理システム - 技術設計仕様書

## 概要

アプリケーション全体のタイムゾーン不整合を解決し、環境変数による統一管理システムを実装する。

## 現状の問題点

### 1. タイムゾーンの不整合
- **app.py**: `JST = pytz.timezone('Asia/Tokyo')` - JST固定
- **database/utils.py**: `datetime.utcnow()` - UTC基準
- **database/models.py**: `CURRENT_TIMESTAMP` - SQLiteデフォルト（UTC）

### 2. 混在する時刻処理
- `datetime.now(JST)` vs `datetime.now()` の混在
- データベース保存時とアプリケーション処理での不整合
- レート制限など時刻比較機能でのバグ発生

## 解決アプローチ

### アーキテクチャ設計

```
config/timezone.py (新規作成)
├── 環境変数TIMEZONE読み込み
├── アプリケーション統一時刻関数
├── データベース保存用標準化処理
└── タイムゾーン変換ユーティリティ

修正対象:
├── app.py: JST固定→統一タイムゾーン
├── database/utils.py: UTC固定→統一タイムゾーン
└── database/models.py: 標準化処理の追加
```

## タイムゾーン指定仕様

### 指定形式
- **IANA Time Zone Database形式**: `timedatectl set-timezone`と同じ指定方法を使用
- システムタイムゾーンの自動取得は行わず、**必ず明示的に指定**

### 対応タイムゾーン例
```bash
# 主要タイムゾーン（IANA Time Zone Database形式）
Asia/Tokyo          # 日本標準時（JST）
UTC                 # 協定世界時（推奨：本番環境）
America/New_York    # 東部標準時（EST/EDT）
Europe/London       # グリニッジ標準時（GMT/BST）
Asia/Shanghai       # 中国標準時（CST）
Australia/Sydney    # オーストラリア東部標準時（AEST/AEDT）
```

### 設定方法

#### 開発環境
```bash
# .env ファイル
TIMEZONE=Asia/Tokyo  # デフォルト値
```

#### Docker Compose環境
```yaml
# docker-compose.yml
services:
  app:
    environment:
      - TIMEZONE=Asia/Tokyo
    # 注意: /etc/localtime のマウントは行わない（予期しない動作防止）
```

#### 本番環境（推奨設定）
```bash
# 本番環境では UTC を推奨
TIMEZONE=UTC
```

### 設定検証
```bash
# 指定可能なタイムゾーン一覧確認（Linux）
timedatectl list-timezones | grep Asia/Tokyo
timedatectl list-timezones | grep UTC
```

## 技術仕様

### 1. 統一タイムゾーンモジュール（config/timezone.py）

```python
import os
import pytz
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# 環境変数からタイムゾーンを取得（明示的指定必須）
TIMEZONE = os.getenv('TIMEZONE', 'Asia/Tokyo')

# タイムゾーン妥当性チェック
try:
    APP_TZ = pytz.timezone(TIMEZONE)
    logger.info(f"Application timezone set to: {TIMEZONE}")
except pytz.exceptions.UnknownTimeZoneError:
    logger.error(f"Invalid timezone specified: {TIMEZONE}. Falling back to Asia/Tokyo")
    APP_TZ = pytz.timezone('Asia/Tokyo')
    TIMEZONE = 'Asia/Tokyo'

def get_app_timezone():
    """アプリケーション統一タイムゾーンを取得"""
    return APP_TZ

def get_app_now():
    """アプリケーション統一タイムゾーンでの現在時刻"""
    return datetime.now(APP_TZ)

def get_app_datetime_string():
    """データベース保存用統一時刻文字列"""
    return get_app_now().strftime('%Y-%m-%d %H:%M:%S')

def localize_datetime(dt):
    """naive datetime をアプリタイムゾーンとして解釈"""
    if dt.tzinfo is None:
        return APP_TZ.localize(dt)
    return dt.astimezone(APP_TZ)

def to_app_timezone(dt):
    """任意のタイムゾーンの datetime をアプリタイムゾーンに変換"""
    if dt.tzinfo is None:
        logger.warning("naive datetime passed to to_app_timezone, treating as APP_TZ")
        return APP_TZ.localize(dt)
    return dt.astimezone(APP_TZ)

def create_app_datetime(year, month, day, hour=0, minute=0, second=0):
    """アプリタイムゾーンでの datetime 作成"""
    return APP_TZ.localize(datetime(year, month, day, hour, minute, second))

def parse_datetime_local(datetime_str):
    """datetime-local 形式の文字列をアプリタイムゾーンで解析"""
    dt_naive = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M')
    return APP_TZ.localize(dt_naive)

def format_for_display(dt):
    """表示用に時刻をフォーマット"""
    if dt.tzinfo is None:
        dt = APP_TZ.localize(dt)
    else:
        dt = dt.astimezone(APP_TZ)
    return dt.strftime('%Y年%m月%d日 %H:%M:%S')

def get_timezone_info():
    """現在のタイムゾーン設定情報を取得"""
    return {
        'timezone': TIMEZONE,
        'current_time': get_app_now().isoformat(),
        'current_offset': get_app_now().strftime('%z')
    }
```

### 2. データベース処理の統一

#### 既存の問題
- `CURRENT_TIMESTAMP` はSQLiteではUTC
- `datetime.utcnow()` の直接使用
- タイムゾーンを考慮しない時刻比較

#### 解決策
- すべてのタイムスタンプ処理で統一関数を使用
- 比較処理前の適切なタイムゾーン変換
- データベース保存時の標準化

## 実装計画

### Phase 1: 基盤実装
1. `config/timezone.py` モジュール作成
2. `.env.example` へタイムゾーン設定追加
3. 基本テストケース作成

### Phase 2: 段階的移行
1. `app.py` のタイムゾーン処理移行
   - JST固定定義の削除
   - 統一関数への置き換え
2. `database/utils.py` の修正
   - UTC固定処理の統一化
   - 時刻比較ロジックの修正
3. `database/models.py` の修正
   - タイムスタンプ処理の標準化

### Phase 3: テスト・検証
1. 単体テストの実行
2. 統合テストの実行
3. 異なるタイムゾーン設定での動作確認
4. レート制限機能のテスト

## 影響範囲

### 修正対象ファイル（推定）
- `config/timezone.py` (新規)
- `.env.example` (追加)
- `app.py` (約30箇所の時刻処理)
- `database/utils.py` (約15箇所)
- `database/models.py` (約5箇所)
- テストファイル群 (約20ファイル)

### リスク要因
1. 既存データのタイムゾーン解釈変更
2. 時刻依存機能での予期しない動作
3. 本番環境でのタイムゾーン設定誤り

### 軽減策
1. 段階的な実装とテスト
2. 本番適用前の十分な検証
3. ロールバック手順の準備
4. 設定変更時の動作確認テスト

## 品質保証

### テスト戦略
1. **単体テスト**: 各時刻処理関数の正確性
2. **統合テスト**: アプリケーション全体の一貫性
3. **設定テスト**: 異なるタイムゾーン設定での動作
4. **回帰テスト**: 既存機能の正常動作確認
5. **タイムゾーン妥当性テスト**: 不正なタイムゾーン指定時の動作

### 成功条件
- [ ] 環境変数によるタイムゾーン設定
- [ ] システム全体でのタイムゾーン統一
- [ ] 既存機能の正常動作維持
- [ ] レート制限機能の正確な動作
- [ ] タイムゾーン変更テストの成功
- [ ] 不正タイムゾーン指定時の適切なフォールバック

## 運用・保守

### 設定時の注意事項
- **必ず明示的にタイムゾーンを指定してください**
- システムタイムゾーンに依存する設定は行いません
- 未指定の場合は`Asia/Tokyo`がデフォルト値として使用されます
- 本番環境では`UTC`の使用を強く推奨します

### 設定例
```bash
# 開発環境（JST）
TIMEZONE=Asia/Tokyo

# 本番環境（UTC推奨）
TIMEZONE=UTC

# その他の地域
TIMEZONE=America/New_York  # ニューヨーク
TIMEZONE=Europe/London     # ロンドン
```

### ログ・監視
- タイムゾーン設定の起動時ログ出力
- 不正なタイムゾーン指定時の警告ログ
- 時刻処理エラーの適切なログ記録
- 設定変更時の影響確認

### 後方互換性
- 既存のデータベースデータは変更なし
- 表示層での適切なタイムゾーン変換
- 段階的な移行による影響最小化

## Docker Compose での運用

### 推奨設定
```yaml
# docker-compose.yml
version: '3.8'
services:
  app:
    build: .
    environment:
      # 明示的なタイムゾーン指定
      - TIMEZONE=Asia/Tokyo
      # または
      - TIMEZONE=${TIMEZONE:-Asia/Tokyo}
    # 注意: 以下の設定は使用しない（予期しない動作防止）
    # volumes:
    #   - /etc/localtime:/etc/localtime:ro  # 使用禁止
    #   - /etc/timezone:/etc/timezone:ro    # 使用禁止
```

### .env ファイル例
```bash
# プロジェクトルートの .env
TIMEZONE=Asia/Tokyo

# 本番環境用
# TIMEZONE=UTC
```

## 参考情報
- [IANA Time Zone Database](https://www.iana.org/time-zones)
- [Python pytz ドキュメント](https://pytz.sourceforge.net/)
- [SQLite タイムゾーン処理](https://www.sqlite.org/lang_datefunc.html)
- [timedatectl コマンド](https://man7.org/linux/man-pages/man1/timedatectl.1.html)