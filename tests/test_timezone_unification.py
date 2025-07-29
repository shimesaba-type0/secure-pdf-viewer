"""
タイムゾーン統一管理システムのテストケース
"""

import unittest
import os
import pytz
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import sys

# テスト対象モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

class TestTimezoneUnification(unittest.TestCase):
    """タイムゾーン統一管理システムのテスト"""
    
    def setUp(self):
        """テスト前の準備"""
        # 既存のconfig.timezoneモジュールをリセット
        if 'config.timezone' in sys.modules:
            del sys.modules['config.timezone']
    
    @patch.dict(os.environ, {'TIMEZONE': 'Asia/Tokyo'})
    def test_timezone_module_with_jst(self):
        """JST設定でのモジュール動作テスト"""
        from config.timezone import APP_TZ, TIMEZONE, get_app_timezone, get_app_now
        
        self.assertEqual(TIMEZONE, 'Asia/Tokyo')
        self.assertEqual(APP_TZ.zone, 'Asia/Tokyo')
        self.assertEqual(get_app_timezone().zone, 'Asia/Tokyo')
        
        # 現在時刻がJSTで取得されることを確認
        now = get_app_now()
        self.assertEqual(now.tzinfo.zone, 'Asia/Tokyo')
    
    @patch.dict(os.environ, {'TIMEZONE': 'UTC'})
    def test_timezone_module_with_utc(self):
        """UTC設定でのモジュール動作テスト"""
        # モジュールを再インポート
        if 'config.timezone' in sys.modules:
            del sys.modules['config.timezone']
        
        from config.timezone import APP_TZ, TIMEZONE, get_app_timezone, get_app_now
        
        self.assertEqual(TIMEZONE, 'UTC')
        self.assertEqual(APP_TZ.zone, 'UTC')
        
        now = get_app_now()
        self.assertEqual(now.tzinfo.zone, 'UTC')
    
    @patch.dict(os.environ, {'TIMEZONE': 'Invalid/Timezone'})
    def test_invalid_timezone_fallback(self):
        """不正なタイムゾーン指定時のフォールバック動作テスト"""
        # モジュールを再インポート
        if 'config.timezone' in sys.modules:
            del sys.modules['config.timezone']
        
        from config.timezone import APP_TZ, TIMEZONE
        
        # フォールバック先がAsia/Tokyoになることを確認
        self.assertEqual(TIMEZONE, 'Asia/Tokyo')
        self.assertEqual(APP_TZ.zone, 'Asia/Tokyo')
    
    @patch.dict(os.environ, {}, clear=True)
    def test_default_timezone(self):
        """環境変数未設定時のデフォルトタイムゾーンテスト"""
        if 'config.timezone' in sys.modules:
            del sys.modules['config.timezone']
        
        from config.timezone import TIMEZONE, APP_TZ
        
        self.assertEqual(TIMEZONE, 'Asia/Tokyo')
        self.assertEqual(APP_TZ.zone, 'Asia/Tokyo')
    
    @patch.dict(os.environ, {'TIMEZONE': 'Asia/Tokyo'})
    def test_datetime_functions(self):
        """時刻関数の動作テスト"""
        if 'config.timezone' in sys.modules:
            del sys.modules['config.timezone']
        
        from config.timezone import (
            get_app_now, get_app_datetime_string, localize_datetime,
            to_app_timezone, create_app_datetime, parse_datetime_local,
            format_for_display, get_timezone_info
        )
        
        # get_app_now テスト
        now = get_app_now()
        self.assertIsNotNone(now.tzinfo)
        self.assertEqual(now.tzinfo.zone, 'Asia/Tokyo')
        
        # get_app_datetime_string テスト
        dt_str = get_app_datetime_string()
        self.assertIsInstance(dt_str, str)
        self.assertEqual(len(dt_str), 19)  # YYYY-MM-DD HH:MM:SS
        
        # localize_datetime テスト
        naive_dt = datetime(2025, 1, 1, 12, 0, 0)
        localized = localize_datetime(naive_dt)
        self.assertEqual(localized.tzinfo.zone, 'Asia/Tokyo')
        self.assertEqual(localized.year, 2025)
        
        # to_app_timezone テスト
        utc_dt = pytz.UTC.localize(datetime(2025, 1, 1, 3, 0, 0))  # UTC 3:00
        jst_dt = to_app_timezone(utc_dt)
        self.assertEqual(jst_dt.tzinfo.zone, 'Asia/Tokyo')
        self.assertEqual(jst_dt.hour, 12)  # JST 12:00
        
        # create_app_datetime テスト
        created_dt = create_app_datetime(2025, 6, 15, 14, 30, 45)
        self.assertEqual(created_dt.tzinfo.zone, 'Asia/Tokyo')
        self.assertEqual(created_dt.month, 6)
        self.assertEqual(created_dt.hour, 14)
        
        # parse_datetime_local テスト
        parsed_dt = parse_datetime_local('2025-07-29T10:30')
        self.assertEqual(parsed_dt.tzinfo.zone, 'Asia/Tokyo')
        self.assertEqual(parsed_dt.day, 29)
        self.assertEqual(parsed_dt.hour, 10)
        
        # format_for_display テスト
        test_dt = create_app_datetime(2025, 3, 15, 9, 30, 0)
        formatted = format_for_display(test_dt)
        self.assertIn('2025年03月15日', formatted)
        self.assertIn('09:30:00', formatted)
        
        # get_timezone_info テスト
        tz_info = get_timezone_info()
        self.assertIn('timezone', tz_info)
        self.assertIn('current_time', tz_info)
        self.assertIn('current_offset', tz_info)
        self.assertEqual(tz_info['timezone'], 'Asia/Tokyo')
    
    @patch.dict(os.environ, {'TIMEZONE': 'America/New_York'})
    def test_timezone_conversion_accuracy(self):
        """タイムゾーン変換の精度テスト"""
        if 'config.timezone' in sys.modules:
            del sys.modules['config.timezone']
        
        from config.timezone import to_app_timezone, create_app_datetime
        
        # UTC → EST/EDT 変換テスト
        utc_winter = pytz.UTC.localize(datetime(2025, 1, 15, 15, 0, 0))  # UTC 15:00 (冬時間)
        est_winter = to_app_timezone(utc_winter)
        self.assertEqual(est_winter.hour, 10)  # EST = UTC-5
        
        utc_summer = pytz.UTC.localize(datetime(2025, 7, 15, 15, 0, 0))  # UTC 15:00 (夏時間)
        edt_summer = to_app_timezone(utc_summer)
        self.assertEqual(edt_summer.hour, 11)  # EDT = UTC-4
    
    @patch.dict(os.environ, {'TIMEZONE': 'Asia/Tokyo'})
    def test_naive_datetime_handling(self):
        """naive datetime の処理テスト"""
        if 'config.timezone' in sys.modules:
            del sys.modules['config.timezone']
        
        from config.timezone import localize_datetime, to_app_timezone
        
        # naive datetime のローカライズテスト
        naive_dt = datetime(2025, 4, 1, 10, 0, 0)
        localized = localize_datetime(naive_dt)
        self.assertEqual(localized.tzinfo.zone, 'Asia/Tokyo')
        
        # naive datetime の変換テスト（警告ログも確認すべきだが、ここでは動作確認のみ）
        with patch('config.timezone.logger') as mock_logger:
            converted = to_app_timezone(naive_dt)
            self.assertEqual(converted.tzinfo.zone, 'Asia/Tokyo')
            mock_logger.warning.assert_called_once()
    
    @patch.dict(os.environ, {'TIMEZONE': 'Europe/London'})
    def test_summer_time_handling(self):
        """サマータイム処理テスト"""
        if 'config.timezone' in sys.modules:
            del sys.modules['config.timezone']
        
        from config.timezone import create_app_datetime, to_app_timezone
        
        # GMT期間（冬時間）
        winter_dt = create_app_datetime(2025, 1, 15, 12, 0, 0)
        utc_winter = winter_dt.astimezone(pytz.UTC)
        self.assertEqual(utc_winter.hour, 12)  # GMT = UTC+0
        
        # BST期間（夏時間）
        summer_dt = create_app_datetime(2025, 7, 15, 12, 0, 0)
        utc_summer = summer_dt.astimezone(pytz.UTC)
        self.assertEqual(utc_summer.hour, 11)  # BST = UTC+1
    
    def test_multiple_timezone_modules(self):
        """複数の異なるタイムゾーン設定でのモジュール動作テスト"""
        test_timezones = [
            'Asia/Tokyo',
            'UTC', 
            'America/New_York',
            'Europe/London',
            'Australia/Sydney'
        ]
        
        for tz in test_timezones:
            with self.subTest(timezone=tz):
                with patch.dict(os.environ, {'TIMEZONE': tz}):
                    # モジュールを再インポート
                    if 'config.timezone' in sys.modules:
                        del sys.modules['config.timezone']
                    
                    from config.timezone import APP_TZ, TIMEZONE, get_app_now
                    
                    self.assertEqual(TIMEZONE, tz)
                    self.assertEqual(APP_TZ.zone, tz)
                    
                    now = get_app_now()
                    self.assertEqual(now.tzinfo.zone, tz)


class TestTimezoneCompatibility(unittest.TestCase):
    """既存コードとの互換性テスト"""
    
    @patch.dict(os.environ, {'TIMEZONE': 'Asia/Tokyo'})
    def test_compatibility_with_existing_jst_usage(self):
        """既存のJST使用コードとの互換性テスト"""
        if 'config.timezone' in sys.modules:
            del sys.modules['config.timezone']
        
        from config.timezone import get_app_timezone, get_app_now
        
        # 既存のJST = pytz.timezone('Asia/Tokyo') と同等の動作確認
        app_tz = get_app_timezone()
        jst_reference = pytz.timezone('Asia/Tokyo')
        
        test_dt = datetime(2025, 6, 15, 10, 30, 0)
        app_localized = app_tz.localize(test_dt)
        jst_localized = jst_reference.localize(test_dt)
        
        self.assertEqual(app_localized, jst_localized)
    
    @patch.dict(os.environ, {'TIMEZONE': 'Asia/Tokyo'})
    def test_database_timestamp_compatibility(self):
        """データベースタイムスタンプとの互換性テスト"""
        if 'config.timezone' in sys.modules:
            del sys.modules['config.timezone']
        
        from config.timezone import get_app_datetime_string, localize_datetime
        
        # データベース保存形式のテスト
        timestamp_str = get_app_datetime_string()
        
        # 文字列からdatetimeに戻す処理のテスト
        dt_parsed = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        localized_dt = localize_datetime(dt_parsed)
        
        self.assertIsNotNone(localized_dt.tzinfo)
        self.assertEqual(localized_dt.tzinfo.zone, 'Asia/Tokyo')


if __name__ == '__main__':
    unittest.main()