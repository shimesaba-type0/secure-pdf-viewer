"""
タイムゾーン統一管理モジュール

アプリケーション全体で使用するタイムゾーンを統一管理し、
時刻処理の一貫性を保証する。

環境変数TIMEZONEで指定されたIANA Time Zone Database形式の
タイムゾーンを使用する。未指定の場合はAsia/Tokyoがデフォルト。
"""

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
    """
    アプリケーション統一タイムゾーンを取得
    
    Returns:
        pytz.timezone: アプリケーション統一タイムゾーン
    """
    return APP_TZ

def get_app_now():
    """
    アプリケーション統一タイムゾーンでの現在時刻を取得
    
    Returns:
        datetime: タイムゾーン付きの現在時刻
    """
    return datetime.now(APP_TZ)

def get_app_datetime_string():
    """
    データベース保存用統一時刻文字列を取得
    
    Returns:
        str: YYYY-MM-DD HH:MM:SS 形式の時刻文字列
    """
    return get_app_now().strftime('%Y-%m-%d %H:%M:%S')

def localize_datetime(dt):
    """
    naive datetime をアプリタイムゾーンとして解釈
    
    Args:
        dt (datetime): naive datetime または aware datetime
        
    Returns:
        datetime: アプリタイムゾーンに変換されたdatetime
    """
    if dt.tzinfo is None:
        return APP_TZ.localize(dt)
    return dt.astimezone(APP_TZ)

def to_app_timezone(dt):
    """
    任意のタイムゾーンの datetime をアプリタイムゾーンに変換
    
    Args:
        dt (datetime): 変換対象のdatetime
        
    Returns:
        datetime: アプリタイムゾーンに変換されたdatetime
    """
    if dt.tzinfo is None:
        logger.warning("naive datetime passed to to_app_timezone, treating as APP_TZ")
        return APP_TZ.localize(dt)
    return dt.astimezone(APP_TZ)

def create_app_datetime(year, month, day, hour=0, minute=0, second=0):
    """
    アプリタイムゾーンでの datetime を作成
    
    Args:
        year (int): 年
        month (int): 月
        day (int): 日
        hour (int): 時（デフォルト: 0）
        minute (int): 分（デフォルト: 0）
        second (int): 秒（デフォルト: 0）
        
    Returns:
        datetime: アプリタイムゾーンのdatetime
    """
    return APP_TZ.localize(datetime(year, month, day, hour, minute, second))

def parse_datetime_local(datetime_str):
    """
    datetime-local 形式の文字列をアプリタイムゾーンで解析
    
    Args:
        datetime_str (str): YYYY-MM-DDTHH:MM 形式の文字列
        
    Returns:
        datetime: アプリタイムゾーンのdatetime
    """
    dt_naive = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M')
    return APP_TZ.localize(dt_naive)

def format_for_display(dt):
    """
    表示用に時刻をフォーマット
    
    Args:
        dt (datetime): フォーマット対象のdatetime
        
    Returns:
        str: 日本語形式の時刻文字列（YYYY年MM月DD日 HH:MM:SS）
    """
    if dt.tzinfo is None:
        dt = APP_TZ.localize(dt)
    else:
        dt = dt.astimezone(APP_TZ)
    return dt.strftime('%Y年%m月%d日 %H:%M:%S')

def get_timezone_info():
    """
    現在のタイムゾーン設定情報を取得
    
    Returns:
        dict: タイムゾーン情報
            - timezone: タイムゾーン名
            - current_time: 現在時刻のISO形式
            - current_offset: UTCからのオフセット
    """
    now = get_app_now()
    return {
        'timezone': TIMEZONE,
        'current_time': now.isoformat(),
        'current_offset': now.strftime('%z')
    }

def compare_app_datetimes(dt1, dt2):
    """
    2つのdatetimeをアプリタイムゾーンで比較
    
    Args:
        dt1 (datetime): 比較対象1
        dt2 (datetime): 比較対象2
        
    Returns:
        int: dt1 < dt2なら-1, dt1 == dt2なら0, dt1 > dt2なら1
    """
    app_dt1 = to_app_timezone(dt1)
    app_dt2 = to_app_timezone(dt2)
    
    if app_dt1 < app_dt2:
        return -1
    elif app_dt1 > app_dt2:
        return 1
    else:
        return 0

def add_app_timedelta(dt, **kwargs):
    """
    アプリタイムゾーンでのtimedelta加算
    
    Args:
        dt (datetime): 基準時刻
        **kwargs: timedelta のパラメータ
        
    Returns:
        datetime: 加算結果のdatetime
    """
    app_dt = to_app_timezone(dt)
    return app_dt + timedelta(**kwargs)

def get_app_date_range(start_date, end_date):
    """
    アプリタイムゾーンでの日付範囲を生成
    
    Args:
        start_date (datetime or date): 開始日
        end_date (datetime or date): 終了日
        
    Returns:
        list: 日付のリスト
    """
    if hasattr(start_date, 'date'):
        start_date = start_date.date()
    if hasattr(end_date, 'date'):
        end_date = end_date.date()
    
    dates = []
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date)
        current_date += timedelta(days=1)
    
    return dates

# 互換性のための関数（既存コードとの移行用）
def get_jst_now():
    """
    既存のJST取得コードとの互換性を保つための関数
    
    注意: この関数は移行期間中のみ使用し、将来的にはget_app_now()を使用すること
    
    Returns:
        datetime: アプリタイムゾーンの現在時刻
    """
    logger.warning("get_jst_now() is deprecated. Use get_app_now() instead.")
    return get_app_now()

def get_jst_datetime_string():
    """
    既存のJST文字列取得コードとの互換性を保つための関数
    
    注意: この関数は移行期間中のみ使用し、将来的にはget_app_datetime_string()を使用すること
    
    Returns:
        str: アプリタイムゾーンの時刻文字列
    """
    logger.warning("get_jst_datetime_string() is deprecated. Use get_app_datetime_string() instead.")
    return get_app_datetime_string()

# モジュール初期化時のログ出力
logger.info(f"Timezone module initialized with timezone: {TIMEZONE}")
logger.info(f"Current application time: {get_app_now().isoformat()}")
logger.info(f"UTC offset: {get_app_now().strftime('%z')}")