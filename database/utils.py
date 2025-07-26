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
        WHERE ip_address = ? AND datetime(blocked_until) > datetime('now')
    ''', (ip_address,)).fetchone()
    
    return row is not None

def block_ip(db, ip_address, duration_seconds, reason="Rate limit exceeded"):
    """IPアドレスをブロック"""
    blocked_until = datetime.utcnow() + timedelta(seconds=duration_seconds)
    
    db.execute('''
        INSERT OR REPLACE INTO ip_blocks (ip_address, blocked_until, reason)
        VALUES (?, ?, ?)
    ''', (ip_address, blocked_until, reason))

def unblock_ip(db, ip_address):
    """IPアドレスのブロックを解除"""
    db.execute('DELETE FROM ip_blocks WHERE ip_address = ?', (ip_address,))

def check_auth_failures(db, ip_address, time_window_minutes=10):
    """指定時間内の認証失敗回数をチェック"""
    since_time = datetime.utcnow() - timedelta(minutes=time_window_minutes)
    
    row = db.execute('''
        SELECT COUNT(*) as count FROM auth_failures 
        WHERE ip_address = ? AND attempt_time > ?
    ''', (ip_address, since_time.strftime('%Y-%m-%d %H:%M:%S'))).fetchone()
    
    return row['count']

def cleanup_old_logs(db, retention_days=90):
    """古いログを削除"""
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    
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
    today = datetime.utcnow().strftime('%Y-%m-%d')
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


class RateLimitManager:
    """レート制限管理クラス"""
    
    def __init__(self, db_connection):
        """
        初期化
        Args:
            db_connection: データベース接続オブジェクト
        """
        self.db = db_connection
        self.failure_threshold = 5  # 10分間での失敗回数制限
        self.time_window_minutes = 10  # 制限判定の時間窓
        self.block_duration_minutes = 30  # 制限時間
    
    def record_auth_failure(self, ip_address, failure_type, email_attempted=None, device_type=None):
        """
        認証失敗を記録
        Args:
            ip_address: 失敗したIPアドレス
            failure_type: 失敗タイプ（'passphrase', 'otp', etc.）
            email_attempted: 試行されたメールアドレス
            device_type: デバイスタイプ
        Returns:
            bool: 制限に達した場合True
        """
        # 認証失敗ログを記録
        log_auth_failure(self.db, ip_address, failure_type, email_attempted, device_type)
        
        # 制限チェック
        return self.check_and_apply_rate_limit(ip_address)
    
    def check_and_apply_rate_limit(self, ip_address):
        """
        レート制限チェックと適用
        Args:
            ip_address: チェック対象のIPアドレス
        Returns:
            bool: 制限を適用した場合True
        """
        # 現在の失敗回数を取得
        failure_count = check_auth_failures(self.db, ip_address, self.time_window_minutes)
        
        # 制限閾値に達した場合
        if failure_count >= self.failure_threshold:
            self.apply_ip_block(
                ip_address, 
                f"Rate limit exceeded: {failure_count} failures in {self.time_window_minutes} minutes",
                self.block_duration_minutes
            )
            return True
        
        return False
    
    def apply_ip_block(self, ip_address, reason, duration_minutes=30):
        """
        IP制限を適用
        Args:
            ip_address: 制限対象のIPアドレス
            reason: 制限理由
            duration_minutes: 制限時間（分）
        """
        duration_seconds = duration_minutes * 60
        block_ip(self.db, ip_address, duration_seconds, reason)
        
        # ブロックインシデント作成
        incident_manager = BlockIncidentManager(self.db)
        incident_id = incident_manager.create_incident(ip_address, reason)
        
        # 制限適用ログを記録
        log_event(
            self.db,
            session_id=None,
            email_hash=None,
            event_type="ip_blocked",
            event_data={
                "ip_address": ip_address,
                "reason": reason,
                "duration_minutes": duration_minutes,
                "failure_count": check_auth_failures(self.db, ip_address, self.time_window_minutes),
                "incident_id": incident_id
            },
            ip_address=ip_address
        )
        
        return incident_id
    
    def get_blocked_ips(self):
        """
        現在制限中のIPアドレス一覧を取得
        Returns:
            List[Dict]: 制限IP情報のリスト
        """
        rows = self.db.execute('''
            SELECT 
                ip_address,
                blocked_until,
                reason,
                created_at,
                (blocked_until > CURRENT_TIMESTAMP) as is_active
            FROM ip_blocks 
            ORDER BY created_at DESC
        ''').fetchall()
        
        result = []
        for row in rows:
            # 最近の認証失敗回数も取得
            failure_count = check_auth_failures(self.db, row['ip_address'], self.time_window_minutes)
            
            result.append({
                'ip_address': row['ip_address'],
                'blocked_until': row['blocked_until'],
                'reason': row['reason'],
                'created_at': row['created_at'],
                'is_active': bool(row['is_active']),
                'recent_failures': failure_count
            })
        
        return result
    
    def unblock_ip_manual(self, ip_address, admin_user):
        """
        管理者による手動IP制限解除
        Args:
            ip_address: 解除対象のIPアドレス
            admin_user: 解除を実行した管理者
        Returns:
            bool: 解除成功時True
        """
        # 制限状況を確認
        blocked_info = self.db.execute('''
            SELECT blocked_until, reason FROM ip_blocks 
            WHERE ip_address = ?
        ''', (ip_address,)).fetchone()
        
        if not blocked_info:
            return False  # 制限されていない
        
        # 制限解除
        unblock_ip(self.db, ip_address)
        
        # 解除ログを記録
        log_event(
            self.db,
            session_id=None,
            email_hash=None,
            event_type="ip_unblocked_manual",
            event_data={
                "ip_address": ip_address,
                "admin_user": admin_user,
                "original_reason": blocked_info['reason'],
                "original_blocked_until": blocked_info['blocked_until']
            },
            ip_address=ip_address
        )
        
        return True
    
    def cleanup_expired_blocks(self):
        """
        期限切れのIP制限を自動削除
        Returns:
            int: 削除された制限数
        """
        result = self.db.execute('''
            DELETE FROM ip_blocks 
            WHERE blocked_until <= CURRENT_TIMESTAMP
        ''')
        
        deleted_count = result.rowcount
        
        if deleted_count > 0:
            log_event(
                self.db,
                session_id=None,
                email_hash=None,
                event_type="ip_blocks_auto_cleanup",
                event_data={
                    "deleted_count": deleted_count
                },
                ip_address=None
            )
        
        return deleted_count
    
    def get_rate_limit_stats(self):
        """
        レート制限統計情報を取得
        Returns:
            Dict: 統計情報
        """
        # 現在の制限IP数
        active_blocks = self.db.execute('''
            SELECT COUNT(*) as count FROM ip_blocks 
            WHERE blocked_until > CURRENT_TIMESTAMP
        ''').fetchone()
        
        # 今日の認証失敗数
        today = datetime.utcnow().strftime('%Y-%m-%d')
        today_failures = self.db.execute('''
            SELECT COUNT(*) as count FROM auth_failures 
            WHERE DATE(attempt_time) = ?
        ''', (today,)).fetchone()
        
        # 今日のIP制限数（UTC基準）
        today_blocks = self.db.execute('''
            SELECT COUNT(*) as count FROM ip_blocks 
            WHERE DATE(created_at) = ?
        ''', (today,)).fetchone()
        
        # 最も多い失敗理由
        top_failure_types = self.db.execute('''
            SELECT failure_type, COUNT(*) as count 
            FROM auth_failures 
            WHERE attempt_time > datetime('now', '-24 hours')
            GROUP BY failure_type 
            ORDER BY count DESC 
            LIMIT 5
        ''').fetchall()
        
        return {
            'active_blocks_count': active_blocks['count'],
            'today_failures_count': today_failures['count'],
            'today_blocks_count': today_blocks['count'],
            'top_failure_types': [dict(row) for row in top_failure_types],
            'current_settings': {
                'failure_threshold': self.failure_threshold,
                'time_window_minutes': self.time_window_minutes,
                'block_duration_minutes': self.block_duration_minutes
            }
        }


class BlockIncidentManager:
    """ブロックインシデント管理クラス"""
    
    def __init__(self, db_connection):
        """
        初期化
        Args:
            db_connection: データベース接続オブジェクト
        """
        self.db = db_connection
        self._ensure_table_exists()
    
    def _ensure_table_exists(self):
        """ブロックインシデントテーブルの存在確認・作成"""
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS block_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT UNIQUE NOT NULL,
                ip_address TEXT NOT NULL,
                block_reason TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved BOOLEAN DEFAULT FALSE,
                resolved_at TIMESTAMP NULL,
                resolved_by TEXT NULL,
                admin_notes TEXT NULL
            )
        ''')
        
        # インデックス作成
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_block_incidents_incident_id ON block_incidents(incident_id)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_block_incidents_ip ON block_incidents(ip_address)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_block_incidents_resolved ON block_incidents(resolved)')
    
    def generate_block_incident_id(self, ip_address):
        """
        ブロックインシデントIDを生成
        Args:
            ip_address: 対象IPアドレス
        Returns:
            str: ブロックインシデントID（例: BLOCK-20250726153045-A4B2）
        """
        # マイクロ秒も含めて一意性を確保
        now = datetime.utcnow()
        timestamp = now.strftime('%Y%m%d%H%M%S')
        microsec = now.microsecond
        
        # IPアドレス、時刻、マイクロ秒からハッシュを生成
        hash_input = f"{timestamp}{microsec}{ip_address}"
        ip_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:4].upper()
        
        return f"BLOCK-{timestamp}-{ip_hash}"
    
    def create_incident(self, ip_address, block_reason):
        """
        ブロックインシデントを作成
        Args:
            ip_address: 制限対象のIPアドレス
            block_reason: 制限理由
        Returns:
            str: 作成されたインシデントID
        """
        incident_id = self.generate_block_incident_id(ip_address)
        
        self.db.execute('''
            INSERT INTO block_incidents (incident_id, ip_address, block_reason)
            VALUES (?, ?, ?)
        ''', (incident_id, ip_address, block_reason))
        
        return incident_id
    
    def resolve_incident(self, incident_id, admin_user, admin_notes=None):
        """
        インシデントを解除
        Args:
            incident_id: インシデントID
            admin_user: 解除を実行した管理者
            admin_notes: 管理者メモ
        Returns:
            bool: 解除成功時True
        """
        # インシデントの存在確認
        incident = self.db.execute('''
            SELECT id FROM block_incidents 
            WHERE incident_id = ? AND resolved = FALSE
        ''', (incident_id,)).fetchone()
        
        if not incident:
            return False
        
        # インシデント解除
        self.db.execute('''
            UPDATE block_incidents 
            SET resolved = TRUE, 
                resolved_at = CURRENT_TIMESTAMP,
                resolved_by = ?,
                admin_notes = ?
            WHERE incident_id = ?
        ''', (admin_user, admin_notes, incident_id))
        
        return True
    
    def get_incident_by_id(self, incident_id):
        """
        インシデントIDでインシデント情報を取得
        Args:
            incident_id: インシデントID
        Returns:
            Dict: インシデント情報、存在しない場合はNone
        """
        row = self.db.execute('''
            SELECT * FROM block_incidents WHERE incident_id = ?
        ''', (incident_id,)).fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_pending_incidents(self, limit=50):
        """
        未解決のインシデント一覧を取得
        Args:
            limit: 取得件数の上限
        Returns:
            List[Dict]: 未解決インシデントのリスト
        """
        rows = self.db.execute('''
            SELECT * FROM block_incidents 
            WHERE resolved = FALSE 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,)).fetchall()
        
        return [dict(row) for row in rows]
    
    def get_all_incidents(self, limit=100):
        """
        全インシデント一覧を取得（管理者用）
        Args:
            limit: 取得件数の上限
        Returns:
            List[Dict]: インシデントのリスト
        """
        rows = self.db.execute('''
            SELECT * FROM block_incidents 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,)).fetchall()
        
        return [dict(row) for row in rows]
    
    def get_incidents_by_ip(self, ip_address):
        """
        特定IPアドレスのインシデント履歴を取得
        Args:
            ip_address: IPアドレス
        Returns:
            List[Dict]: インシデント履歴
        """
        rows = self.db.execute('''
            SELECT * FROM block_incidents 
            WHERE ip_address = ? 
            ORDER BY created_at DESC
        ''', (ip_address,)).fetchall()
        
        return [dict(row) for row in rows]
    
    def cleanup_old_incidents(self, retention_days=90):
        """
        古いインシデントを削除
        Args:
            retention_days: 保持期間（日）
        Returns:
            int: 削除されたインシデント数
        """
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        result = self.db.execute('''
            DELETE FROM block_incidents 
            WHERE created_at < ? AND resolved = TRUE
        ''', (cutoff_date.strftime('%Y-%m-%d %H:%M:%S'),))
        
        return result.rowcount
    
    def get_incident_stats(self):
        """
        インシデント統計情報を取得
        Returns:
            Dict: 統計情報
        """
        # 未解決インシデント数
        pending_count = self.db.execute('''
            SELECT COUNT(*) as count FROM block_incidents 
            WHERE resolved = FALSE
        ''').fetchone()
        
        # 今日のインシデント数
        today = datetime.utcnow().strftime('%Y-%m-%d')
        today_count = self.db.execute('''
            SELECT COUNT(*) as count FROM block_incidents 
            WHERE DATE(created_at) = ?
        ''', (today,)).fetchone()
        
        # 解決済みインシデント数（今日）
        today_resolved = self.db.execute('''
            SELECT COUNT(*) as count FROM block_incidents 
            WHERE DATE(resolved_at) = ? AND resolved = TRUE
        ''', (today,)).fetchone()
        
        # 平均解決時間（分）
        avg_resolution_time = self.db.execute('''
            SELECT AVG((julianday(resolved_at) - julianday(created_at)) * 1440) as avg_minutes
            FROM block_incidents 
            WHERE resolved = TRUE AND resolved_at IS NOT NULL
            AND created_at > datetime('now', '-30 days')
        ''').fetchone()
        
        return {
            'pending_incidents': pending_count['count'],
            'today_incidents': today_count['count'],
            'today_resolved': today_resolved['count'],
            'avg_resolution_minutes': round(avg_resolution_time['avg_minutes'] or 0, 1)
        }