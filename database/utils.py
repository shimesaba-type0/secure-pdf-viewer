"""
データベースユーティリティ関数
"""

import hashlib
import time
from datetime import datetime, timedelta
from .models import get_setting, set_setting, log_access, log_event, log_auth_failure

def hash_email(email):
    """メールアドレスをハッシュ化（プライバシー保護）"""
    return hashlib.sha256(email.encode()).hexdigest()[:16]

def is_ip_blocked(db, ip_address):
    """IPアドレスがブロックされているかチェック"""
    row = db.execute('''
        SELECT blocked_until FROM ip_blocks 
        WHERE ip_address = ? AND blocked_until > CURRENT_TIMESTAMP
    ''', (ip_address,)).fetchone()
    
    return row is not None

def block_ip(db, ip_address, duration_seconds, reason="Rate limit exceeded"):
    """IPアドレスをブロック"""
    blocked_until = datetime.now() + timedelta(seconds=duration_seconds)
    
    db.execute('''
        INSERT OR REPLACE INTO ip_blocks (ip_address, blocked_until, reason)
        VALUES (?, ?, ?)
    ''', (ip_address, blocked_until, reason))

def unblock_ip(db, ip_address):
    """IPアドレスのブロックを解除"""
    db.execute('DELETE FROM ip_blocks WHERE ip_address = ?', (ip_address,))

def check_auth_failures(db, ip_address, time_window_minutes=10):
    """指定時間内の認証失敗回数をチェック"""
    since_time = datetime.now() - timedelta(minutes=time_window_minutes)
    
    row = db.execute('''
        SELECT COUNT(*) as count FROM auth_failures 
        WHERE ip_address = ? AND attempt_time > ?
    ''', (ip_address, since_time)).fetchone()
    
    return row['count']

def cleanup_old_logs(db, retention_days=90):
    """古いログを削除"""
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    
    # 古いアクセスログを削除
    access_deleted = db.execute('''
        DELETE FROM access_logs WHERE access_time < ?
    ''', (cutoff_date,)).rowcount
    
    # 古いイベントログを削除
    event_deleted = db.execute('''
        DELETE FROM event_logs WHERE created_at < ?
    ''', (cutoff_date,)).rowcount
    
    # 古い認証失敗ログを削除
    auth_deleted = db.execute('''
        DELETE FROM auth_failures WHERE attempt_time < ?
    ''', (cutoff_date,)).rowcount
    
    return {
        'access_logs': access_deleted,
        'event_logs': event_deleted,
        'auth_failures': auth_deleted
    }

def get_current_active_sessions(db):
    """現在のアクティブセッション数を取得"""
    session_timeout = get_setting(db, 'session_timeout', 259200)  # 72時間
    cutoff_time = int(time.time()) - session_timeout
    
    row = db.execute('''
        SELECT COUNT(DISTINCT session_id) as count 
        FROM access_logs 
        WHERE access_time > datetime(?, 'unixepoch')
    ''', (cutoff_time,)).fetchone()
    
    return row['count']

def get_recent_access_logs(db, limit=50):
    """最近のアクセスログを取得"""
    return db.execute('''
        SELECT 
            access_time,
            ip_address,
            endpoint,
            method,
            status_code,
            device_type,
            user_agent
        FROM access_logs 
        ORDER BY access_time DESC 
        LIMIT ?
    ''', (limit,)).fetchall()

def get_system_stats(db):
    """システム統計情報を取得"""
    # 今日のアクセス数
    today = datetime.now().strftime('%Y-%m-%d')
    today_access = db.execute('''
        SELECT COUNT(*) as count FROM access_logs 
        WHERE DATE(access_time) = ?
    ''', (today,)).fetchone()
    
    # 総ユーザー数（ユニークなemail_hash）
    total_users = db.execute('''
        SELECT COUNT(DISTINCT email_hash) as count FROM access_logs
        WHERE email_hash IS NOT NULL
    ''').fetchone()
    
    # 現在のアクティブセッション数
    active_sessions = get_current_active_sessions(db)
    
    # 最後のアクセス時刻
    last_access = db.execute('''
        SELECT MAX(access_time) as last_time FROM access_logs
    ''').fetchone()
    
    return {
        'today_access': today_access['count'],
        'total_users': total_users['count'],
        'active_sessions': active_sessions,
        'last_access': last_access['last_time']
    }

def is_admin_user(db, email):
    """管理者ユーザーかチェック"""
    row = db.execute('''
        SELECT is_active FROM admin_users 
        WHERE email = ? AND is_active = TRUE
    ''', (email,)).fetchone()
    
    return row is not None

def add_admin_user(db, email, added_by='system'):
    """管理者ユーザーを追加"""
    try:
        db.execute('''
            INSERT INTO admin_users (email, added_by)
            VALUES (?, ?)
        ''', (email, added_by))
        return True
    except Exception:
        return False

def remove_admin_user(db, email):
    """管理者ユーザーを削除"""
    db.execute('''
        UPDATE admin_users SET is_active = FALSE 
        WHERE email = ?
    ''', (email,))

def validate_session_timeout():
    """セッションタイムアウトの妥当性チェック"""
    # 実装は後で追加
    pass