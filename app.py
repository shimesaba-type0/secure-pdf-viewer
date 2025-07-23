from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
import os
import uuid
from datetime import datetime, timedelta
import pytz
from werkzeug.utils import secure_filename
import sqlite3
import hashlib
from database.models import get_setting, set_setting
from auth.passphrase import PassphraseManager
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import json
import time
import threading
from queue import Queue, Empty

# JST timezone
JST = pytz.timezone('Asia/Tokyo')

def get_consistent_hash(text):
    """
    一貫したハッシュ値を生成する関数
    """
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]

def detect_device_type(user_agent):
    """
    User-Agentからデバイスタイプを判定する
    Returns: 'mobile', 'tablet', 'desktop', 'other'
    """
    if not user_agent:
        return 'other'
    
    user_agent = user_agent.lower()
    
    # モバイルデバイスの判定
    mobile_keywords = [
        'mobile', 'android', 'iphone', 'ipod', 'blackberry', 
        'windows phone', 'opera mini', 'fennec'
    ]
    
    # タブレットの判定（iPadは特別扱い）
    tablet_keywords = ['ipad', 'tablet', 'kindle', 'silk', 'playbook']
    
    # デスクトップブラウザの判定
    desktop_keywords = ['windows nt', 'macintosh', 'linux', 'x11']
    
    # タブレット判定（モバイルより先に判定）
    if any(keyword in user_agent for keyword in tablet_keywords):
        return 'tablet'
    
    # Android タブレットの特別判定（Androidでmobileが含まれていない場合はタブレット）
    if 'android' in user_agent and 'mobile' not in user_agent:
        return 'tablet'
    
    # モバイル判定
    if any(keyword in user_agent for keyword in mobile_keywords):
        return 'mobile'
    
    # デスクトップ判定
    if any(keyword in user_agent for keyword in desktop_keywords):
        return 'desktop'
    
    return 'other'

def is_session_expired():
    """
    セッションが有効期限切れかどうかをチェックする
    Returns:
        bool: True if expired, False if valid
    """
    if not session.get('authenticated'):
        return True
    
    auth_time_str = session.get('auth_completed_at')
    if not auth_time_str:
        return True
    
    try:
        # ISO形式の日時文字列をパース
        auth_time = datetime.fromisoformat(auth_time_str)
        now = datetime.now()
        
        # 72時間（259200秒）の有効期限をチェック
        try:
            session_timeout = get_setting('session_timeout', 259200)  # デフォルト72時間
        except:
            session_timeout = 259200  # エラー時のフォールバック
        time_diff = (now - auth_time).total_seconds()
        
        return time_diff > session_timeout
    except (ValueError, TypeError):
        # 日時パースエラーの場合は期限切れとみなす
        return True

def clear_expired_session():
    """
    期限切れセッションをクリアする
    """
    session.clear()
    flash('セッションの有効期限が切れました。再度ログインしてください。', 'warning')

def check_session_integrity():
    """
    セッションの整合性をチェックする
    Returns:
        bool: True if valid, False if invalid
    """
    if not session.get('authenticated'):
        print("DEBUG: Session integrity check failed - not authenticated")
        return False
    
    # 両方の認証ステップが完了しているかチェック
    if not session.get('passphrase_verified') or not session.get('email'):
        print(f"DEBUG: Session integrity check failed - passphrase_verified: {session.get('passphrase_verified')}, email: {session.get('email')}")
        return False
    
    session_id = session.get('session_id')
    if not session_id:
        print("DEBUG: Session integrity check failed - no session_id")
        return False
    
    # データベースのセッション統計と照合
    try:
        conn = sqlite3.connect('instance/database.db')
        cursor = conn.cursor()
        
        # セッションIDがデータベースに存在するかチェック
        cursor.execute('SELECT start_time, email_hash FROM session_stats WHERE session_id = ?', (session_id,))
        db_session = cursor.fetchone()
        
        conn.close()
        
        if not db_session:
            # データベースにセッション記録がない場合は無効
            print(f"DEBUG: Session integrity check failed - no database record for session_id: {session_id}")
            return False
        
        # 認証完了時刻とデータベース記録の整合性チェック
        auth_time_str = session.get('auth_completed_at')
        if auth_time_str:
            try:
                auth_time = datetime.fromisoformat(auth_time_str)
                db_start_time = datetime.fromtimestamp(db_session[0])
                
                # 時刻の差が5分以上の場合は異常とみなす
                time_diff = abs((auth_time - db_start_time).total_seconds())
                if time_diff > 300:  # 5分
                    print(f"DEBUG: Session integrity check failed - time mismatch: {time_diff} seconds")
                    return False
            except (ValueError, TypeError) as e:
                print(f"DEBUG: Session integrity check failed - time parsing error: {e}")
                return False
        
        # メールアドレスのハッシュ値をチェック
        email = session.get('email')
        if email:
            expected_hash = get_consistent_hash(email)
            if expected_hash != db_session[1]:
                print(f"DEBUG: Session integrity check failed - email hash mismatch: expected {expected_hash}, got {db_session[1]}")
                return False
        
        print("DEBUG: Session integrity check passed")
        return True
    except Exception as e:
        print(f"DEBUG: Session integrity check failed - exception: {e}")
        return False

def require_valid_session():
    """
    有効なセッションを要求するデコレーター用の関数
    """
    if is_session_expired():
        clear_expired_session()
        return redirect(url_for('login'))
    
    # セッション整合性チェック
    if not check_session_integrity():
        session.clear()
        flash('セッションの整合性に問題があります。再度ログインしてください。', 'warning')
        return redirect(url_for('login'))
    
    return None

def invalidate_all_sessions():
    """
    全てのセッションを無効化する独立関数
    Returns:
        dict: 実行結果の詳細情報
    """
    print(f"*** SCHEDULED SESSION INVALIDATION EXECUTED AT {get_jst_datetime_string()} ***")
    deleted_sessions = 0
    deleted_otps = 0
    
    try:
        import sqlite3
        conn = sqlite3.connect('instance/database.db')
        cursor = conn.cursor()
        
        # 全てのセッション統計データを削除
        cursor.execute('SELECT COUNT(*) FROM session_stats')
        total_sessions = cursor.fetchone()[0]
        
        cursor.execute('DELETE FROM session_stats')
        deleted_sessions = cursor.rowcount
        
        # 全てのOTPトークンも削除
        cursor.execute('SELECT COUNT(*) FROM otp_tokens')
        total_otps = cursor.fetchone()[0]
        
        cursor.execute('DELETE FROM otp_tokens')
        deleted_otps = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        print(f"Database cleanup completed: Removed {deleted_sessions} sessions and {deleted_otps} OTP tokens")
        
    except Exception as e:
        error_msg = f"データベースクリーンアップエラー: {e}"
        print(error_msg)
    
    # リクエストコンテキスト内でのみFlaskセッションをクリア
    try:
        from flask import has_request_context
        if has_request_context():
            session.clear()
            print("Flask session cleared (in request context)")
        else:
            print("Flask session clear skipped (not in request context)")
    except Exception as e:
        print(f"Flask session clear error: {e}")
    
    # SSE通知は必ず送信（データベースエラーがあっても）
    try:
        # 全クライアントにセッション無効化を通知
        broadcast_sse_event('session_invalidated', {
            'message': '予定された時刻になったため、システムからログアウトされました。再度ログインしてください。',
            'deleted_sessions': deleted_sessions,
            'deleted_otps': deleted_otps,
            'redirect_url': '/auth/login',
            'clear_session': True  # クライアント側でもセッションストレージをクリア
        })
        print(f"SSE session invalidation notification sent to clients")
    except Exception as e:
        print(f"SSE notification error: {e}")
    
    result = {
        'success': True,
        'deleted_sessions': deleted_sessions,
        'deleted_otps': deleted_otps,
        'timestamp': get_jst_datetime_string(),
        'message': f'全セッション無効化完了: {deleted_sessions}セッション、{deleted_otps}OTPトークンを削除'
    }
    
    print(f"Session invalidation completed: {result['message']}")
    return result

def cleanup_expired_sessions():
    """
    期限切れセッションの定期クリーンアップ処理
    """
    try:
        import sqlite3
        conn = sqlite3.connect('instance/database.db')
        cursor = conn.cursor()
        
        # 72時間以上古いセッション統計データを削除
        try:
            session_timeout = get_setting('session_timeout', 259200)  # デフォルト72時間
        except:
            session_timeout = 259200  # エラー時のフォールバック
        cutoff_time = datetime.now() - timedelta(seconds=session_timeout)
        cutoff_timestamp = int(cutoff_time.timestamp())
        
        # 古いセッション統計を削除
        cursor.execute('''
            DELETE FROM session_stats 
            WHERE start_time < ?
        ''', (cutoff_timestamp,))
        
        deleted_sessions = cursor.rowcount
        
        # 古いOTPトークンも一緒にクリーンアップ（24時間以上古いもの）
        old_otp_cutoff = datetime.now() - timedelta(hours=24)
        cursor.execute('''
            DELETE FROM otp_tokens 
            WHERE created_at < ?
        ''', (old_otp_cutoff.isoformat(),))
        
        deleted_otps = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        if deleted_sessions > 0 or deleted_otps > 0:
            print(f"Session cleanup: Removed {deleted_sessions} expired sessions and {deleted_otps} old OTP tokens")
            
    except Exception as e:
        print(f"Session cleanup error: {e}")

def setup_session_invalidation_scheduler(datetime_str):
    """
    設定時刻セッション無効化のスケジューラーを設定
    Args:
        datetime_str (str): 日時文字列（YYYY-MM-DDTHH:MM形式）
    """
    try:
        # 既存のスケジュールをクリア
        try:
            scheduler.remove_job('session_invalidation')
        except:
            pass  # ジョブが存在しない場合は無視
        
        # 日時文字列をdatetimeオブジェクトに変換
        target_datetime = datetime.fromisoformat(datetime_str)
        
        # JSTタイムゾーンに変換
        if target_datetime.tzinfo is None:
            target_datetime = JST.localize(target_datetime)
        else:
            target_datetime = target_datetime.astimezone(JST)
        
        # 現在時刻（JST）と比較して過去の日時でないかチェック（5分の猶予を追加）
        now_jst = datetime.now(JST)
        grace_period = timedelta(minutes=5)
        if target_datetime <= (now_jst - grace_period):
            raise ValueError("過去の日時は設定できません")
        
        # 指定日時に一度だけ実行するスケジュールを追加
        scheduler.add_job(
            func=invalidate_all_sessions,
            trigger="date",
            run_date=target_datetime,
            id='session_invalidation',
            replace_existing=True
        )
        
        print(f"Session invalidation scheduled for {target_datetime}")
        
    except Exception as e:
        print(f"Failed to schedule session invalidation: {e}")
        raise

def get_jst_now():
    """現在のJST時刻を取得"""
    return datetime.now(JST)

def get_jst_datetime_string():
    """現在のJST時刻を文字列で取得（データベース保存用）"""
    return get_jst_now().strftime('%Y-%m-%d %H:%M:%S')

# SSE用のクライアント管理
sse_clients = set()
sse_lock = threading.Lock()

def add_sse_client(client_queue):
    """SSEクライアントを追加"""
    with sse_lock:
        sse_clients.add(client_queue)
        print(f"SSE client connected. Total clients: {len(sse_clients)}")

def remove_sse_client(client_queue):
    """SSEクライアントを削除"""
    with sse_lock:
        sse_clients.discard(client_queue)
        print(f"SSE client disconnected. Total clients: {len(sse_clients)}")

def broadcast_sse_event(event_type, data):
    """全SSEクライアントにイベントを送信"""
    print(f"Broadcasting SSE event '{event_type}' to {len(sse_clients)} clients")
    with sse_lock:
        dead_clients = set()
        for client_queue in sse_clients.copy():
            try:
                client_queue.put({
                    'event': event_type,
                    'data': data,
                    'timestamp': get_jst_datetime_string()
                }, timeout=1)
                print(f"  -> Event sent to client")
            except Exception as e:
                print(f"  -> Failed to send to client: {e}")
                dead_clients.add(client_queue)
        
        # 切断されたクライアントを削除
        for dead_client in dead_clients:
            sse_clients.discard(dead_client)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-this')
app.config['UPLOAD_FOLDER'] = 'static/pdfs'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize scheduler for auto-unpublish functionality
scheduler = BackgroundScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# セッションクリーンアップを毎時間実行するようにスケジュール
scheduler.add_job(
    func=cleanup_expired_sessions,
    trigger="interval",
    hours=1,
    id='session_cleanup',
    replace_existing=True
)

def auto_unpublish_all_pdfs():
    """指定時刻に全てのPDFの公開を停止する"""
    try:
        conn = sqlite3.connect('instance/database.db')
        cursor = conn.cursor()
        
        # 全てのPDFを非公開にする
        cursor.execute('''
            UPDATE pdf_files 
            SET is_published = FALSE, unpublished_date = ? 
            WHERE is_published = TRUE
        ''', (get_jst_datetime_string(),))
        
        # publish_end設定をクリア
        cursor.execute('''
            UPDATE settings 
            SET value = NULL, updated_at = CURRENT_TIMESTAMP, updated_by = 'scheduler'
            WHERE key = 'publish_end'
        ''')
        
        conn.commit()
        conn.close()
        
        print(f"Auto-unpublish completed at {datetime.now()}")
        
        # SSEで全クライアントに通知
        broadcast_sse_event('pdf_unpublished', {
            'message': '公開が自動的に停止されました',
            'reason': 'scheduled',
            'timestamp': get_jst_datetime_string()
        })
        
    except Exception as e:
        print(f"Auto-unpublish failed: {e}")

def schedule_auto_unpublish(end_datetime):
    """公開終了日時にスケジュールを設定"""
    # 既存のスケジュールをクリア
    try:
        scheduler.remove_job('auto_unpublish')
    except:
        pass  # ジョブが存在しない場合は無視
    
    # 新しいスケジュールを追加
    scheduler.add_job(
        func=auto_unpublish_all_pdfs,
        trigger="date",
        run_date=end_datetime,
        id='auto_unpublish'
    )
    print(f"Scheduled auto-unpublish for {end_datetime}")

def restore_scheduled_unpublish():
    """アプリ起動時に既存の公開終了設定を復元"""
    try:
        conn = sqlite3.connect('instance/database.db')
        publish_end_str = get_setting(conn, 'publish_end', None)
        conn.close()
        
        if publish_end_str:
            publish_end_dt = datetime.fromisoformat(publish_end_str)
            # データベースからの値がoffset-awareでない場合はJSTとして扱う
            if publish_end_dt.tzinfo is None:
                publish_end_dt = JST.localize(publish_end_dt)
            
            # 設定時刻がまだ未来の場合のみスケジュールを復元
            if publish_end_dt > get_jst_now():
                schedule_auto_unpublish(publish_end_dt)
            else:
                # 設定時刻が過去の場合は自動停止を実行
                print("Publish end time is in the past, executing auto-unpublish now")
                auto_unpublish_all_pdfs()
                
    except Exception as e:
        print(f"Failed to restore scheduled unpublish: {e}")

# アプリ起動時にスケジュールを復元
restore_scheduled_unpublish()

def check_and_handle_expired_publish():
    """フォールバック: アクセス時に公開終了時刻をチェック"""
    try:
        conn = sqlite3.connect('instance/database.db')
        publish_end_str = get_setting(conn, 'publish_end', None)
        conn.close()
        
        if publish_end_str:
            publish_end_dt = datetime.fromisoformat(publish_end_str)
            # データベースからの値がoffset-awareでない場合はJSTとして扱う
            if publish_end_dt.tzinfo is None:
                publish_end_dt = JST.localize(publish_end_dt)
            
            # 公開終了時刻が過去の場合は自動停止を実行
            if publish_end_dt <= get_jst_now():
                print(f"Detected expired publish end time: {publish_end_dt}, executing auto-unpublish")
                auto_unpublish_all_pdfs()
                return True  # 停止処理を実行した
                
    except Exception as e:
        print(f"Failed to check expired publish: {e}")
    
    return False  # 停止処理は実行されなかった

@app.route('/')
def index():
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check
    
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    # フォールバック: 公開終了時刻をチェック
    check_and_handle_expired_publish()
    
    # Get list of uploaded PDF files for viewer
    pdf_files = get_pdf_files()
    
    # Get published PDF for auto-load
    published_pdf = get_published_pdf()
    
    # Get current author name setting for watermark and publish end time
    conn = sqlite3.connect('instance/database.db')
    author_name = get_setting(conn, 'author_name', 'Default_Author')
    
    # Get publish end datetime setting
    publish_end_str = get_setting(conn, 'publish_end', None)
    publish_end_datetime_formatted = None
    
    if publish_end_str:
        try:
            publish_end_dt = datetime.fromisoformat(publish_end_str)
            # Handle timezone if not present
            if publish_end_dt.tzinfo is None:
                publish_end_dt = JST.localize(publish_end_dt)
            
            # Convert to JST and format for display
            publish_end_jst = publish_end_dt.astimezone(JST)
            publish_end_datetime_formatted = publish_end_jst.strftime('%Y年%m月%d日 %H:%M')
        except ValueError:
            publish_end_datetime_formatted = None
    
    conn.close()
    
    return render_template('viewer.html', 
                         pdf_files=pdf_files, 
                         published_pdf=published_pdf, 
                         author_name=author_name,
                         publish_end_datetime_formatted=publish_end_datetime_formatted)

@app.route('/auth/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        
        # パスフレーズ認証を実行
        conn = sqlite3.connect('instance/database.db')
        passphrase_manager = PassphraseManager(conn)
        
        try:
            if passphrase_manager.verify_passphrase(password):
                # パスフレーズ認証成功時に古いセッション情報を完全にクリア
                session.clear()
                session['passphrase_verified'] = True
                session['login_time'] = datetime.now().isoformat()
                print(f"DEBUG: login - passphrase verified, session cleared and reset")
                conn.close()
                return redirect(url_for('email_input'))
            else:
                conn.close()
                return render_template('login.html', error='パスフレーズが正しくありません')
        except Exception as e:
            conn.close()
            return render_template('login.html', error='認証エラーが発生しました')
    
    return render_template('login.html')

@app.route('/auth/email', methods=['GET', 'POST'])
def email_input():
    # パスフレーズ認証が完了しているかチェック
    if not session.get('passphrase_verified'):
        return redirect(url_for('login'))
    
    # 既に完全認証済みの場合は整合性をチェック
    # ただし、OTP認証が完了している場合のみ（session_idとauth_completed_atが存在）
    if session.get('authenticated') and session.get('session_id') and session.get('auth_completed_at'):
        print(f"DEBUG: email_input - checking session integrity for session_id: {session.get('session_id')}")
        if check_session_integrity():
            return redirect(url_for('index'))
        else:
            # 整合性に問題がある場合はセッションをクリア
            print(f"DEBUG: email_input - clearing session due to integrity failure")
            session.clear()
            flash('セッションの整合性に問題があります。再度ログインしてください。', 'warning')
            return redirect(url_for('login'))
    else:
        print(f"DEBUG: email_input - skipping integrity check: authenticated={session.get('authenticated')}, session_id={session.get('session_id')}, auth_completed_at={session.get('auth_completed_at')}")
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        # バリデーション
        if not email:
            return render_template('email_input.html', error='メールアドレスを入力してください')
        
        # 簡単なメールアドレス形式チェック
        import re
        email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_pattern, email):
            return render_template('email_input.html', error='有効なメールアドレスを入力してください', email=email)
        
        try:
            # データベース接続
            conn = sqlite3.connect('instance/database.db')
            conn.row_factory = sqlite3.Row
            
            # OTP生成（6桁）
            import secrets
            otp_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            
            # 有効期限設定（10分後）
            import datetime
            expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
            
            # 古いOTPを無効化（同じメールアドレスの未使用OTP）
            conn.execute('''
                UPDATE otp_tokens 
                SET used = TRUE, used_at = CURRENT_TIMESTAMP 
                WHERE email = ? AND used = FALSE
            ''', (email,))
            
            # 新しいOTPをデータベースに保存
            conn.execute('''
                INSERT INTO otp_tokens (email, otp_code, session_id, ip_address, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (email, otp_code, session.get('session_id', ''), request.remote_addr, expires_at.isoformat()))
            
            conn.commit()
            
            # メール送信
            from mail.email_service import EmailService
            email_service = EmailService()
            
            if email_service.send_otp_email(email, otp_code):
                # セッションにメールアドレスを保存
                session['email'] = email
                conn.close()
                return redirect(url_for('verify_otp'))
            else:
                conn.close()
                return render_template('email_input.html', 
                                     error='メール送信に失敗しました。しばらく時間をおいて再試行してください。', 
                                     email=email)
                                     
        except Exception as e:
            if 'conn' in locals():
                conn.close()
            return render_template('email_input.html', 
                                 error='システムエラーが発生しました。しばらく時間をおいて再試行してください。', 
                                 email=email)
    
    return render_template('email_input.html')

@app.route('/auth/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    # パスフレーズ認証とメールアドレスが設定されているかチェック
    if not session.get('passphrase_verified') or not session.get('email'):
        return redirect(url_for('login'))
    
    # 既に完全認証済みの場合は整合性をチェック
    # ただし、OTP認証が完了している場合のみ（session_idとauth_completed_atが存在）
    if session.get('authenticated') and session.get('session_id') and session.get('auth_completed_at'):
        if check_session_integrity():
            return redirect(url_for('index'))
        else:
            # 整合性に問題がある場合はセッションをクリア
            session.clear()
            flash('セッションの整合性に問題があります。再度ログインしてください。', 'warning')
            return redirect(url_for('login'))
    
    email = session.get('email')
    
    if request.method == 'POST':
        otp_code = request.form.get('otp_code', '').strip()
        
        # バリデーション
        if not otp_code:
            return render_template('verify_otp.html', email=email, error='OTPコードを入力してください')
        
        if len(otp_code) != 6 or not otp_code.isdigit():
            return render_template('verify_otp.html', email=email, error='6桁の数字を入力してください')
        
        try:
            # データベース接続
            conn = sqlite3.connect('instance/database.db')
            conn.row_factory = sqlite3.Row
            
            # 有効なOTPを検索
            otp_record = conn.execute('''
                SELECT id, otp_code, expires_at, used 
                FROM otp_tokens 
                WHERE email = ? AND otp_code = ? AND used = FALSE
                ORDER BY created_at DESC
                LIMIT 1
            ''', (email, otp_code)).fetchone()
            
            if not otp_record:
                conn.close()
                return render_template('verify_otp.html', email=email, 
                                     error='無効なOTPコードです。正しいコードを入力してください。')
            
            # 有効期限チェック
            import datetime
            expires_at = datetime.datetime.fromisoformat(otp_record['expires_at'])
            now = datetime.datetime.now()
            
            if now > expires_at:
                # 期限切れOTPを無効化
                conn.execute('''
                    UPDATE otp_tokens 
                    SET used = TRUE, used_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (otp_record['id'],))
                conn.commit()
                conn.close()
                return render_template('verify_otp.html', email=email, 
                                     error='OTPコードの有効期限が切れています。再送信してください。')
            
            # OTPを使用済みにマーク
            conn.execute('''
                UPDATE otp_tokens 
                SET used = TRUE, used_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (otp_record['id'],))
            conn.commit()
            
            # 認証完了
            session['authenticated'] = True
            session['email'] = email
            session['auth_completed_at'] = datetime.datetime.now().isoformat()
            
            # セッション統計を更新
            session_id = session.get('session_id', str(uuid.uuid4()))
            session['session_id'] = session_id
            
            # User-Agentからデバイスタイプを判定
            user_agent = request.headers.get('User-Agent', '')
            device_type = detect_device_type(user_agent)
            
            conn.execute('''
                INSERT OR REPLACE INTO session_stats 
                (session_id, email_hash, email_address, start_time, ip_address, device_type, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (session_id, get_consistent_hash(email), email, int(now.timestamp()), request.remote_addr, device_type))
            
            conn.commit()
            conn.close()
            
            return redirect(url_for('index'))
            
        except Exception as e:
            if 'conn' in locals():
                conn.close()
            return render_template('verify_otp.html', email=email, 
                                 error='システムエラーが発生しました。しばらく時間をおいて再試行してください。')
    
    return render_template('verify_otp.html', email=email)

@app.route('/auth/resend-otp', methods=['POST'])
def resend_otp():
    # パスフレーズ認証とメールアドレスが設定されているかチェック
    if not session.get('passphrase_verified') or not session.get('email'):
        return {'success': False, 'error': '認証セッションが無効です'}, 400
    
    email = session.get('email')
    
    try:
        # データベース接続
        conn = sqlite3.connect('instance/database.db')
        conn.row_factory = sqlite3.Row
        
        # OTP生成（6桁）
        import secrets
        otp_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        
        # 有効期限設定（10分後）
        import datetime
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
        
        # 古いOTPを無効化（同じメールアドレスの未使用OTP）
        conn.execute('''
            UPDATE otp_tokens 
            SET used = TRUE, used_at = CURRENT_TIMESTAMP 
            WHERE email = ? AND used = FALSE
        ''', (email,))
        
        # 新しいOTPをデータベースに保存
        conn.execute('''
            INSERT INTO otp_tokens (email, otp_code, session_id, ip_address, expires_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (email, otp_code, session.get('session_id', ''), request.remote_addr, expires_at.isoformat()))
        
        conn.commit()
        
        # メール送信
        from mail.email_service import EmailService
        email_service = EmailService()
        
        if email_service.send_otp_email(email, otp_code):
            conn.close()
            return {'success': True, 'message': '認証コードを再送信しました'}
        else:
            conn.close()
            return {'success': False, 'error': 'メール送信に失敗しました'}, 500
                                 
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return {'success': False, 'error': 'システムエラーが発生しました'}, 500

@app.route('/auth/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin')
def admin():
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check
    
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    # フォールバック: 公開終了時刻をチェック
    check_and_handle_expired_publish()
    
    # Get list of uploaded PDF files
    pdf_files = get_pdf_files()
    
    # Get current author name setting
    conn = sqlite3.connect('instance/database.db')
    author_name = get_setting(conn, 'author_name', 'Default_Author')
    
    # Get current publish end datetime setting
    publish_end_str = get_setting(conn, 'publish_end', None)
    publish_end_datetime = None
    publish_end_datetime_formatted = None
    
    if publish_end_str:
        try:
            publish_end_dt = datetime.fromisoformat(publish_end_str)
            # データベースからの値がoffset-awareでない場合はJSTとして扱う
            if publish_end_dt.tzinfo is None:
                publish_end_dt = JST.localize(publish_end_dt)
            
            # JSTに変換してからフォーマット
            publish_end_jst = publish_end_dt.astimezone(JST)
            # datetime-local input format: YYYY-MM-DDTHH:MM
            publish_end_datetime = publish_end_jst.strftime('%Y-%m-%dT%H:%M')
            # Display format
            publish_end_datetime_formatted = publish_end_jst.strftime('%Y年%m月%d日 %H:%M')
        except ValueError:
            publish_end_datetime = None
            publish_end_datetime_formatted = None
    
    # Get current published PDF's publish date and recent publication info
    current_published_pdf = None
    publish_start_formatted = None
    last_unpublish_formatted = None
    
    # 現在公開中のPDFを探す
    for pdf in pdf_files:
        if pdf.get('is_published'):
            current_published_pdf = pdf
            break
    
    # 現在公開中のPDFの開始日時
    if current_published_pdf and current_published_pdf.get('published_date'):
        try:
            published_dt = datetime.fromisoformat(current_published_pdf['published_date'])
            if published_dt.tzinfo is None:
                published_dt = JST.localize(published_dt)
            published_jst = published_dt.astimezone(JST)
            publish_start_formatted = published_jst.strftime('%Y年%m月%d日 %H:%M')
        except (ValueError, TypeError):
            publish_start_formatted = None
    
    # 最近停止したPDFの停止日時を取得（現在公開中でない場合）
    if not current_published_pdf:
        for pdf in pdf_files:
            if pdf.get('unpublished_date'):
                try:
                    unpublished_dt = datetime.fromisoformat(pdf['unpublished_date'])
                    if unpublished_dt.tzinfo is None:
                        unpublished_dt = JST.localize(unpublished_dt)
                    unpublished_jst = unpublished_dt.astimezone(JST)
                    last_unpublish_formatted = unpublished_jst.strftime('%Y年%m月%d日 %H:%M')
                    break  # 最初に見つかった（最新の）停止日時を使用
                except (ValueError, TypeError):
                    continue
    
    # Get session invalidation schedule setting
    conn = sqlite3.connect('instance/database.db')
    scheduled_invalidation_datetime_str = get_setting(conn, 'scheduled_invalidation_datetime', None)
    conn.close()
    
    scheduled_invalidation_datetime = None
    scheduled_invalidation_datetime_formatted = None
    scheduled_invalidation_seconds = '00'  # デフォルト秒
    
    if scheduled_invalidation_datetime_str:
        try:
            target_dt = datetime.fromisoformat(scheduled_invalidation_datetime_str)
            
            # JSTタイムゾーンに変換
            if target_dt.tzinfo is None:
                target_jst = JST.localize(target_dt)
            else:
                target_jst = target_dt.astimezone(JST)
            
            # 現在時刻（JST）と比較して過去の設定かチェック
            now_jst = datetime.now(JST)
            if target_jst <= now_jst:
                # 過去の設定なので削除
                conn_cleanup = sqlite3.connect('instance/database.db')
                cursor_cleanup = conn_cleanup.cursor()
                cursor_cleanup.execute("DELETE FROM settings WHERE key = ?", ('scheduled_invalidation_datetime',))
                conn_cleanup.commit()
                conn_cleanup.close()
                print(f"Removed expired session invalidation schedule: {target_jst}")
                
                # 表示用変数をリセット
                scheduled_invalidation_datetime = None
                scheduled_invalidation_datetime_formatted = None
                scheduled_invalidation_seconds = '00'
            else:
                # 未来の設定なので表示
                # datetime-local input format: YYYY-MM-DDTHH:MM (秒は除く)
                scheduled_invalidation_datetime = target_dt.strftime('%Y-%m-%dT%H:%M')
                # 秒の値を抽出
                scheduled_invalidation_seconds = f"{target_dt.second:02d}"
                # Display format
                scheduled_invalidation_datetime_formatted = target_jst.strftime('%Y年%m月%d日 %H:%M:%S')
                
        except ValueError:
            scheduled_invalidation_datetime = None
            scheduled_invalidation_datetime_formatted = None
            scheduled_invalidation_seconds = '00'
    
    return render_template('admin.html', 
                         pdf_files=pdf_files, 
                         author_name=author_name,
                         publish_end_datetime=publish_end_datetime,
                         publish_end_datetime_formatted=publish_end_datetime_formatted,
                         publish_start_formatted=publish_start_formatted,
                         last_unpublish_formatted=last_unpublish_formatted,
                         current_published_pdf=current_published_pdf,
                         scheduled_invalidation_datetime=scheduled_invalidation_datetime,
                         scheduled_invalidation_datetime_formatted=scheduled_invalidation_datetime_formatted,
                         scheduled_invalidation_seconds=scheduled_invalidation_seconds)

@app.route('/admin/sessions')
def sessions():
    """セッション一覧ページ"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check
    
    return render_template('sessions.html')

@app.route('/admin/sessions/<session_id>')
def session_detail(session_id):
    """セッション詳細ページ"""
    session_check = require_valid_session()
    if session_check:
        return session_check
    
    try:
        conn = sqlite3.connect('instance/database.db')
        cursor = conn.cursor()
        
        # セッション情報を取得
        cursor.execute('''
            SELECT 
                session_id,
                email_hash,
                email_address,
                start_time,
                ip_address,
                device_type,
                last_updated,
                memo
            FROM session_stats 
            WHERE session_id = ?
        ''', (session_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return "セッションが見つかりません", 404
        
        session_id, email_hash, stored_email_address, start_time, ip_address, device_type, last_updated, memo = row
        
        # フォールバック用のメールアドレス取得
        if not stored_email_address:
            conn = sqlite3.connect('instance/database.db')
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT email FROM otp_tokens ORDER BY created_at DESC')
            emails = cursor.fetchall()
            
            email_hash_map = {}
            for email_row in emails:
                email = email_row[0]
                email_hash_calc = get_consistent_hash(email)
                email_hash_map[email_hash_calc] = email
            
            email_address = email_hash_map.get(email_hash, f"不明({email_hash[:8]})")
            conn.close()
        else:
            email_address = stored_email_address
        
        # 開始時刻を日本時間に変換
        start_dt = datetime.fromtimestamp(start_time)
        start_jst = start_dt.astimezone(JST)
        
        # 残り時間と経過時間を計算
        now = datetime.now(JST)
        elapsed = now - start_jst
        elapsed_hours = round(elapsed.total_seconds() / 3600, 1)
        
        # 72時間から経過時間を引いて残り時間を計算
        session_timeout = 72 * 3600  # 72時間を秒に変換
        remaining_seconds = session_timeout - elapsed.total_seconds()
        
        if remaining_seconds > 0:
            remaining_hours = int(remaining_seconds // 3600)
            remaining_minutes = int((remaining_seconds % 3600) // 60)
            remaining_time = f"{remaining_hours}時間{remaining_minutes}分"
        else:
            remaining_time = "期限切れ"
        
        session_data = {
            'session_id': session_id,
            'email_address': email_address,
            'device_type': device_type,
            'start_time': start_jst.strftime('%Y-%m-%d %H:%M:%S'),
            'remaining_time': remaining_time,
            'elapsed_hours': elapsed_hours,
            'memo': memo or ''
        }
        
        return render_template('session_detail.html', session=session_data)
        
    except Exception as e:
        print(f"セッション詳細取得エラー: {e}")
        return "エラーが発生しました", 500

@app.route('/admin/upload-pdf', methods=['POST'])
def upload_pdf():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    if 'pdf_file' not in request.files:
        flash('ファイルが選択されていません')
        return redirect(url_for('admin'))
    
    file = request.files['pdf_file']
    if file.filename == '':
        flash('ファイルが選択されていません')
        return redirect(url_for('admin'))
    
    if file and allowed_file(file.filename):
        original_filename = file.filename
        
        # Generate unique filename using UUID
        file_extension = original_filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        try:
            file.save(filepath)
            
            # Get actual file size
            file_size = os.path.getsize(filepath)
            
            # Add to database with both original and stored filename
            add_pdf_to_db(original_filename, unique_filename, filepath, file_size)
            
            flash(f'ファイル "{original_filename}" がアップロードされました')
        except Exception as e:
            flash(f'アップロードに失敗しました: {str(e)}')
    else:
        flash('PDFファイルのみアップロード可能です')
    
    return redirect(url_for('admin'))

@app.route('/admin/delete-pdf/<int:pdf_id>', methods=['POST'])
def delete_pdf(pdf_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get file info from database
        conn = sqlite3.connect('instance/database.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        pdf_info = cursor.execute(
            'SELECT * FROM pdf_files WHERE id = ?', (pdf_id,)
        ).fetchone()
        
        if not pdf_info:
            return jsonify({'error': 'ファイルが見つかりません'}), 404
        
        # Delete file from filesystem
        if os.path.exists(pdf_info['file_path']):
            os.remove(pdf_info['file_path'])
        
        # Delete from database
        cursor.execute('DELETE FROM pdf_files WHERE id = ?', (pdf_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/publish-pdf/<int:pdf_id>', methods=['POST'])
def publish_pdf(pdf_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = sqlite3.connect('instance/database.db')
        cursor = conn.cursor()
        
        # Check if PDF exists
        pdf_info = cursor.execute(
            'SELECT id FROM pdf_files WHERE id = ?', (pdf_id,)
        ).fetchone()
        
        if not pdf_info:
            return jsonify({'error': 'ファイルが見つかりません'}), 404
        
        # Unpublish all other PDFs (only one can be published at a time)
        cursor.execute('''
            UPDATE pdf_files 
            SET is_published = FALSE, unpublished_date = ? 
            WHERE is_published = TRUE
        ''', (get_jst_datetime_string(),))
        
        # Publish the selected PDF
        cursor.execute('''
            UPDATE pdf_files 
            SET is_published = TRUE, published_date = ?, unpublished_date = NULL 
            WHERE id = ?
        ''', (get_jst_datetime_string(), pdf_id))
        
        conn.commit()
        conn.close()
        
        # SSEで全クライアントに通知（公開開始）
        broadcast_sse_event('pdf_published', {
            'message': 'PDFが公開されました',
            'reason': 'manual',
            'timestamp': get_jst_datetime_string()
        })
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/unpublish-pdf/<int:pdf_id>', methods=['POST'])
def unpublish_pdf(pdf_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = sqlite3.connect('instance/database.db')
        cursor = conn.cursor()
        
        # Unpublish the PDF
        cursor.execute('''
            UPDATE pdf_files 
            SET is_published = FALSE, unpublished_date = ? 
            WHERE id = ?
        ''', (get_jst_datetime_string(), pdf_id))
        
        conn.commit()
        conn.close()
        
        # SSEで全クライアントに通知（手動停止）
        broadcast_sse_event('pdf_unpublished', {
            'message': '公開が手動で停止されました',
            'reason': 'manual',
            'timestamp': get_jst_datetime_string()
        })
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/update-passphrase', methods=['POST'])
def update_passphrase():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    new_passphrase = request.form.get('new_passphrase', '').strip()
    confirm_passphrase = request.form.get('confirm_passphrase', '').strip()
    
    if not new_passphrase:
        flash('新しいパスフレーズを入力してください')
        return redirect(url_for('admin'))
    
    if new_passphrase != confirm_passphrase:
        flash('パスフレーズが一致しません')
        return redirect(url_for('admin'))
    
    try:
        conn = sqlite3.connect('instance/database.db')
        passphrase_manager = PassphraseManager(conn)
        
        # パスフレーズを更新
        passphrase_manager.update_passphrase(new_passphrase)
        conn.commit()
        conn.close()
        
        # パスフレーズ変更後もセッションを維持
        flash('パスフレーズが更新されました。既存のセッションは維持されます。', 'success')
        return redirect(url_for('admin'))
        
    except ValueError as e:
        flash(f'パスフレーズの更新に失敗しました: {str(e)}')
    except Exception as e:
        flash(f'システムエラーが発生しました: {str(e)}')
    
    return redirect(url_for('admin'))

@app.route('/admin/update-author', methods=['POST'])
def update_author():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    author_name = request.form.get('author_name', '').strip()
    
    if not author_name:
        flash('著作者名を入力してください')
        return redirect(url_for('admin'))
    
    if len(author_name) > 100:
        flash('著作者名は100文字以内で入力してください')
        return redirect(url_for('admin'))
    
    try:
        conn = sqlite3.connect('instance/database.db')
        set_setting(conn, 'author_name', author_name, 'admin')
        conn.commit()
        conn.close()
        
        flash(f'著作者名を "{author_name}" に更新しました')
    except Exception as e:
        flash(f'更新に失敗しました: {str(e)}')
    
    return redirect(url_for('admin'))

@app.route('/admin/update-publish-end', methods=['POST'])
def update_publish_end():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    publish_end_datetime = request.form.get('publish_end_datetime', '').strip()
    
    try:
        conn = sqlite3.connect('instance/database.db')
        
        if publish_end_datetime:
            # Convert datetime-local format to JST aware datetime
            # datetime-localはタイムゾーン情報なしなので、JSTとして扱う
            publish_end_naive = datetime.fromisoformat(publish_end_datetime)
            publish_end_dt = JST.localize(publish_end_naive)
            
            # Validate that the datetime is in the future
            if publish_end_dt <= get_jst_now():
                flash('公開終了日時は現在時刻より後の時刻を設定してください')
                return redirect(url_for('admin'))
            
            # Save to database as ISO format string
            set_setting(conn, 'publish_end', publish_end_dt.isoformat(), 'admin')
            conn.commit()
            
            # Schedule auto-unpublish
            schedule_auto_unpublish(publish_end_dt)
            
            formatted_time = publish_end_dt.strftime('%Y年%m月%d日 %H:%M')
            flash(f'公開終了日時を {formatted_time} に設定しました（自動停止スケジュール済み）')
        else:
            # Clear the setting
            set_setting(conn, 'publish_end', None, 'admin')
            conn.commit()
            
            # Remove scheduled auto-unpublish
            try:
                scheduler.remove_job('auto_unpublish')
            except:
                pass  # ジョブが存在しない場合は無視
            
            flash('公開終了日時設定をクリアしました（無制限公開、自動停止解除済み）')
        
        conn.close()
        
    except ValueError:
        flash('日時の形式が正しくありません')
    except Exception as e:
        flash(f'設定の更新に失敗しました: {str(e)}')
    
    return redirect(url_for('admin'))

@app.route('/admin/invalidate-all-sessions', methods=['POST'])
def manual_invalidate_all_sessions():
    """手動で全セッション無効化を実行"""
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        result = invalidate_all_sessions()
        if result['success']:
            flash(result['message'], 'success')
            return jsonify(result)
        else:
            flash(result['message'], 'error')
            return jsonify(result), 500
    except Exception as e:
        error_msg = f'全セッション無効化の実行に失敗しました: {str(e)}'
        flash(error_msg, 'error')
        return jsonify({'error': error_msg}), 500

@app.route('/admin/schedule-session-invalidation', methods=['POST'])
def schedule_session_invalidation():
    """設定時刻セッション無効化のスケジュール設定"""
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    try:
        invalidation_datetime = request.form.get('invalidation_datetime', '').strip()
        invalidation_seconds = request.form.get('invalidation_seconds', '00').strip()
        
        if invalidation_datetime:
            # 秒を追加して完全な日時文字列を作成（YYYY-MM-DDTHH:MM:SS）
            complete_datetime_str = f"{invalidation_datetime}:{invalidation_seconds}"
            
            # 日時の形式チェック（YYYY-MM-DDTHH:MM:SS）
            target_datetime = datetime.fromisoformat(complete_datetime_str)
            
            # 過去の日時チェック
            now = datetime.now()
            if target_datetime <= now:
                flash('過去の日時は設定できません。未来の日時を指定してください。', 'error')
                return redirect(url_for('admin'))
            
            # データベースに設定を保存（秒まで含む完全な日時文字列）
            conn = sqlite3.connect('instance/database.db')
            set_setting(conn, 'scheduled_invalidation_datetime', complete_datetime_str, 'admin')
            conn.commit()
            conn.close()
            
            # スケジューラーを設定
            setup_session_invalidation_scheduler(complete_datetime_str)
            
            # 表示用に日時をフォーマット
            if target_datetime.tzinfo is None:
                target_jst = JST.localize(target_datetime)
            else:
                target_jst = target_datetime.astimezone(JST)
            formatted_datetime = target_jst.strftime('%Y年%m月%d日 %H:%M:%S')
            
            flash(f'設定時刻セッション無効化を {formatted_datetime} に設定しました', 'success')
        else:
            flash('無効化日時を入力してください', 'error')
    
    except ValueError as e:
        if "過去の日時" in str(e):
            flash('過去の日時は設定できません。未来の日時を指定してください。', 'error')
        else:
            flash('日時の形式が正しくありません（YYYY-MM-DDTHH:MM形式で入力してください）', 'error')
    except Exception as e:
        flash(f'スケジュール設定に失敗しました: {str(e)}', 'error')
    
    return redirect(url_for('admin'))

@app.route('/admin/clear-session-invalidation-schedule', methods=['POST'])
def clear_session_invalidation_schedule():
    """設定時刻セッション無効化のスケジュール解除"""
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # データベースから設定を削除
        conn = sqlite3.connect('instance/database.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM settings WHERE key = ?", ('scheduled_invalidation_datetime',))
        deleted_rows = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"Schedule cleared: deleted {deleted_rows} settings")
        
        # スケジューラーのジョブを削除
        try:
            scheduler.remove_job('session_invalidation')
            print("Scheduler job 'session_invalidation' removed successfully")
        except Exception as e:
            print(f"Scheduler job removal: {e} (job may not exist)")
        
        flash('設定時刻セッション無効化のスケジュールを解除しました', 'success')
        return jsonify({'success': True, 'message': 'スケジュールを解除しました'})
    
    except Exception as e:
        error_msg = f'スケジュール解除に失敗しました: {str(e)}'
        flash(error_msg, 'error')
        return jsonify({'error': error_msg}), 500

@app.route('/api/session-info')
def get_session_info():
    """ウォーターマーク用のセッション情報を取得"""
    # セッション有効期限チェック
    if is_session_expired():
        return jsonify({'error': 'Session expired'}), 401
    
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # セッションから直接メールアドレスとセッションIDを取得
        email = session.get('email', 'unknown@example.com')
        session_id = session.get('session_id', 'SID-FALLBACK')
        
        return jsonify({
            'session_id': session_id,
            'email': email,
            'success': True
        })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/active-sessions')
def get_active_sessions():
    """管理画面用：アクティブセッション一覧を取得"""
    # セッション有効期限チェック
    session_check = require_valid_session()
    if session_check:
        return session_check
    
    try:
        conn = sqlite3.connect('instance/database.db')
        cursor = conn.cursor()
        
        # session_timeout設定値を取得
        try:
            session_timeout = get_setting('session_timeout', 259200)  # デフォルト72時間
        except:
            session_timeout = 259200  # エラー時のフォールバック
        
        # 有効期限内のセッションのみ取得
        cutoff_timestamp = int((datetime.now() - timedelta(seconds=session_timeout)).timestamp())
        
        cursor.execute('''
            SELECT 
                session_id,
                email_hash,
                email_address,
                start_time,
                ip_address,
                device_type,
                last_updated,
                memo
            FROM session_stats 
            WHERE start_time > ?
            ORDER BY start_time DESC
        ''', (cutoff_timestamp,))
        
        rows = cursor.fetchall()
        
        # 全てのOTPトークンからメールアドレスを取得してハッシュマッピングを作成
        cursor.execute('SELECT DISTINCT email FROM otp_tokens ORDER BY created_at DESC')
        emails = cursor.fetchall()
        
        email_hash_map = {}
        for email_row in emails:
            email = email_row[0]
            email_hash = get_consistent_hash(email)
            email_hash_map[email_hash] = email
        
        conn.close()
        
        sessions = []
        for row in rows:
            session_id, email_hash, stored_email_address, start_time, ip_address, device_type, last_updated, memo = row
            
            # 保存されたemail_addressを使用、なければハッシュマップから取得
            email_address = stored_email_address or email_hash_map.get(email_hash, f"不明({email_hash[:8]})")
            
            # 開始時刻を日本時間に変換
            start_dt = datetime.fromtimestamp(start_time)
            start_jst = start_dt.astimezone(JST)
            
            # 最終更新時刻がある場合は変換（文字列形式での格納を想定）
            last_updated_formatted = None
            if last_updated:
                try:
                    last_updated_dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                    last_updated_jst = last_updated_dt.astimezone(JST)
                    last_updated_formatted = last_updated_jst.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    last_updated_formatted = last_updated
            
            # セッション経過時間を計算
            elapsed_seconds = (datetime.now() - start_dt).total_seconds()
            remaining_seconds = session_timeout - elapsed_seconds
            
            # 残り時間を時分秒形式で表示
            if remaining_seconds > 0:
                hours = int(remaining_seconds // 3600)
                minutes = int((remaining_seconds % 3600) // 60)
                remaining_time = f"{hours}時間{minutes}分"
            else:
                remaining_time = "期限切れ"
            
            sessions.append({
                'session_id': session_id,
                'email_address': email_address,
                'email_hash': email_hash,
                'start_time': start_jst.strftime('%Y-%m-%d %H:%M:%S'),
                'ip_address': ip_address,
                'device_type': device_type,
                'last_updated': last_updated_formatted,
                'remaining_time': remaining_time,
                'elapsed_hours': round(elapsed_seconds / 3600, 1),
                'memo': memo or ''
            })
        
        return jsonify({
            'sessions': sessions,
            'total_count': len(sessions),
            'session_timeout_hours': round(session_timeout / 3600, 1)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/update-session-memo', methods=['POST'])
def update_session_memo():
    """セッションのメモを更新"""
    session_check = require_valid_session()
    if session_check:
        return session_check
    
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        memo = data.get('memo', '').strip()
        
        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400
        
        # メモの長さ制限
        if len(memo) > 500:
            return jsonify({'error': 'メモは500文字以内で入力してください'}), 400
        
        conn = sqlite3.connect('instance/database.db')
        cursor = conn.cursor()
        
        # セッションが存在するかチェック
        cursor.execute('SELECT session_id FROM session_stats WHERE session_id = ?', (session_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': 'セッションが見つかりません'}), 404
        
        # メモを更新
        cursor.execute('''
            UPDATE session_stats 
            SET memo = ?, last_updated = CURRENT_TIMESTAMP 
            WHERE session_id = ?
        ''', (memo, session_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'メモを更新しました',
            'session_id': session_id,
            'memo': memo
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/events')
def sse_stream():
    """Server-Sent Events ストリーム"""
    # セッション有効期限チェック
    if is_session_expired():
        return jsonify({'error': 'Session expired'}), 401
    
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    def event_stream():
        client_queue = Queue()
        add_sse_client(client_queue)
        
        try:
            # 接続確立時のハートビート
            yield f"data: {json.dumps({'event': 'connected', 'message': 'SSE接続が確立されました'})}\n\n"
            
            while True:
                try:
                    # キューからイベントを取得（30秒タイムアウト）
                    event_data = client_queue.get(timeout=30)
                    yield f"event: {event_data['event']}\n"
                    yield f"data: {json.dumps(event_data['data'])}\n\n"
                except Empty:
                    # タイムアウト時はハートビートを送信
                    yield f"data: {json.dumps({'event': 'heartbeat', 'timestamp': get_jst_datetime_string()})}\n\n"
                except Exception:
                    # その他のエラーは無視して継続
                    break
                    
        except (GeneratorExit, ConnectionError, BrokenPipeError):
            # クライアント切断時は静かに終了
            pass
        except Exception:
            # その他のエラーも静かに終了
            pass
        finally:
            # クライアントを確実に削除
            try:
                remove_sse_client(client_queue)
            except:
                pass
    
    return Response(
        event_stream(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'  # nginx用
        }
    )

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

def get_pdf_files():
    try:
        conn = sqlite3.connect('instance/database.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        files = cursor.execute('''
            SELECT id, original_filename, stored_filename, file_path, file_size, 
                   upload_date, is_published, published_date, unpublished_date
            FROM pdf_files 
            ORDER BY upload_date DESC
        ''').fetchall()
        
        conn.close()
        
        result = []
        for file in files:
            # フォーマット済み日時を作成
            published_formatted = None
            unpublished_formatted = None
            
            if file['published_date']:
                try:
                    published_dt = datetime.fromisoformat(file['published_date'])
                    if published_dt.tzinfo is None:
                        published_dt = JST.localize(published_dt)
                    published_jst = published_dt.astimezone(JST)
                    published_formatted = published_jst.strftime('%Y年%m月%d日 %H:%M')
                except (ValueError, TypeError):
                    published_formatted = None
            
            if file['unpublished_date']:
                try:
                    unpublished_dt = datetime.fromisoformat(file['unpublished_date'])
                    if unpublished_dt.tzinfo is None:
                        unpublished_dt = JST.localize(unpublished_dt)
                    unpublished_jst = unpublished_dt.astimezone(JST)
                    unpublished_formatted = unpublished_jst.strftime('%Y年%m月%d日 %H:%M')
                except (ValueError, TypeError):
                    unpublished_formatted = None
            
            result.append({
                'id': file['id'],
                'name': file['original_filename'],
                'stored_name': file['stored_filename'],
                'path': file['file_path'],
                'size': format_file_size(file['file_size']),
                'upload_date': file['upload_date'],
                'is_published': bool(file['is_published']) if file['is_published'] is not None else False,
                'published_date': file['published_date'],
                'unpublished_date': file['unpublished_date'],
                'published_formatted': published_formatted,
                'unpublished_formatted': unpublished_formatted
            })
        
        return result
    except Exception as e:
        print(f"Error getting PDF files: {e}")
        return []

def add_pdf_to_db(original_filename, stored_filename, filepath, file_size):
    conn = sqlite3.connect('instance/database.db')
    cursor = conn.cursor()
    
    # Create table if it doesn't exist - updated schema
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pdf_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            is_published BOOLEAN DEFAULT FALSE,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Check if we need to migrate old data
    try:
        cursor.execute("SELECT filename FROM pdf_files LIMIT 1")
        # Old schema exists, need to migrate
        try:
            cursor.execute("ALTER TABLE pdf_files ADD COLUMN original_filename TEXT")
            cursor.execute("ALTER TABLE pdf_files ADD COLUMN stored_filename TEXT")
            cursor.execute("ALTER TABLE pdf_files ADD COLUMN is_published BOOLEAN DEFAULT FALSE")
            # Update existing records
            cursor.execute('''
                UPDATE pdf_files 
                SET original_filename = filename, stored_filename = filename, is_published = FALSE
                WHERE original_filename IS NULL
            ''')
        except sqlite3.OperationalError:
            # Columns already exist
            pass
    except sqlite3.OperationalError:
        # New schema or migration already done
        pass
    
    cursor.execute('''
        INSERT INTO pdf_files (original_filename, stored_filename, file_path, file_size)
        VALUES (?, ?, ?, ?)
    ''', (original_filename, stored_filename, filepath, file_size))
    
    conn.commit()
    conn.close()

def format_file_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    return f"{size:.1f} {size_names[i]}"

def get_published_pdf():
    """Get the currently published PDF file"""
    try:
        conn = sqlite3.connect('instance/database.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        published_file = cursor.execute('''
            SELECT id, original_filename, stored_filename, file_path, file_size, upload_date
            FROM pdf_files 
            WHERE is_published = TRUE
            LIMIT 1
        ''').fetchone()
        
        conn.close()
        
        if published_file:
            return {
                'id': published_file['id'],
                'name': published_file['original_filename'],
                'stored_name': published_file['stored_filename'],
                'path': published_file['file_path'],
                'size': format_file_size(published_file['file_size']),
                'upload_date': published_file['upload_date']
            }
        return None
    except Exception as e:
        print(f"Error getting published PDF: {e}")
        return None

def initialize_scheduled_tasks():
    """
    アプリ起動時に設定済みのスケジュールタスクを復元
    """
    try:
        conn = sqlite3.connect('instance/database.db')
        
        # セッション無効化スケジュールの復元（新形式）
        scheduled_datetime = get_setting(conn, 'session_invalidation_datetime', None)
        if scheduled_datetime:
            # 過去の日時でないかチェック
            try:
                target_dt = datetime.fromisoformat(scheduled_datetime)
                now = datetime.now()
                # 5分以上前の場合のみ期限切れとして削除
                time_diff = (target_dt - now).total_seconds()
                if time_diff > -300:  # 5分前まではまだ有効とみなす
                    if time_diff > 0:
                        setup_session_invalidation_scheduler(scheduled_datetime)
                        print(f"Restored session invalidation schedule: {target_dt}")
                    else:
                        print(f"Session invalidation schedule recently expired: {target_dt} (keeping for safety)")
                else:
                    # 5分以上前の場合は設定を削除
                    set_setting(conn, 'session_invalidation_datetime', None, 'system')
                    conn.commit()
                    print(f"Removed expired session invalidation schedule: {target_dt}")
            except ValueError:
                # 不正な形式の場合は設定を削除
                set_setting(conn, 'session_invalidation_datetime', None, 'system')
                conn.commit()
                print("Removed invalid session invalidation schedule")
        
        # 旧形式の設定があれば削除（migration）
        old_schedule = get_setting(conn, 'session_invalidation_time', None)
        if old_schedule:
            set_setting(conn, 'session_invalidation_time', None, 'system')
            conn.commit()
            print("Migrated old session invalidation schedule format")
        
        conn.close()
        
    except Exception as e:
        print(f"Failed to initialize scheduled tasks: {e}")

# 起動時にスケジュールタスクを初期化
initialize_scheduled_tasks()

def cleanup_expired_schedules():
    """期限切れのスケジュール設定をクリーンアップ"""
    try:
        conn = sqlite3.connect('instance/database.db')
        cursor = conn.cursor()
        
        # 期限切れの設定を取得
        cursor.execute('SELECT value FROM settings WHERE key = ?', ('scheduled_invalidation_datetime',))
        result = cursor.fetchone()
        
        if result:
            try:
                target_dt = datetime.fromisoformat(result[0])
                if target_dt.tzinfo is None:
                    target_jst = JST.localize(target_dt)
                else:
                    target_jst = target_dt.astimezone(JST)
                
                now_jst = datetime.now(JST)
                if target_jst <= now_jst:
                    # 期限切れなので削除
                    cursor.execute("DELETE FROM settings WHERE key = ?", ('scheduled_invalidation_datetime',))
                    conn.commit()
                    print(f"Removed expired session invalidation schedule on startup: {target_jst}")
            except ValueError:
                # 無効な日時形式の設定も削除
                cursor.execute("DELETE FROM settings WHERE key = ?", ('scheduled_invalidation_datetime',))
                conn.commit()
                print("Removed invalid session invalidation schedule on startup")
        
        conn.close()
    except Exception as e:
        print(f"Error during schedule cleanup: {e}")

if __name__ == '__main__':
    # 起動時に期限切れ設定をクリーンアップ
    cleanup_expired_schedules()
    app.run(debug=True, host='0.0.0.0', port=5000)

