from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
import os
import uuid
from datetime import datetime, timedelta
import pytz
from werkzeug.utils import secure_filename
import sqlite3
from database.models import get_setting, set_setting
from auth.passphrase import PassphraseManager
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import json
import time
import threading
from queue import Queue

# JST timezone
JST = pytz.timezone('Asia/Tokyo')

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

def require_valid_session():
    """
    有効なセッションを要求するデコレーター用の関数
    """
    if is_session_expired():
        clear_expired_session()
        return redirect(url_for('login'))
    return None

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

def remove_sse_client(client_queue):
    """SSEクライアントを削除"""
    with sse_lock:
        sse_clients.discard(client_queue)

def broadcast_sse_event(event_type, data):
    """全SSEクライアントにイベントを送信"""
    with sse_lock:
        dead_clients = set()
        for client_queue in sse_clients.copy():
            try:
                client_queue.put({
                    'event': event_type,
                    'data': data,
                    'timestamp': get_jst_datetime_string()
                }, timeout=1)
            except:
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
                session['passphrase_verified'] = True
                session['login_time'] = datetime.now().isoformat()
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
    
    # 既に完全認証済みの場合はメイン画面へ
    if session.get('authenticated'):
        return redirect(url_for('index'))
    
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
    
    # 既に完全認証済みの場合はメイン画面へ
    if session.get('authenticated'):
        return redirect(url_for('index'))
    
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
            
            conn.execute('''
                INSERT OR REPLACE INTO session_stats 
                (session_id, email_hash, start_time, ip_address, device_type, last_updated)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (session_id, hash(email), int(now.timestamp()), request.remote_addr, 'web'))
            
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
    
    conn.close()
    
    return render_template('admin.html', 
                         pdf_files=pdf_files, 
                         author_name=author_name,
                         publish_end_datetime=publish_end_datetime,
                         publish_end_datetime_formatted=publish_end_datetime_formatted,
                         publish_start_formatted=publish_start_formatted,
                         last_unpublish_formatted=last_unpublish_formatted,
                         current_published_pdf=current_published_pdf)

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
        
        # 全ユーザーを強制ログアウト
        session.clear()
        flash('パスフレーズが更新されました。再度ログインしてください。')
        return redirect(url_for('login'))
        
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
                except:
                    # タイムアウト時はハートビートを送信
                    yield f"data: {json.dumps({'event': 'heartbeat', 'timestamp': get_jst_datetime_string()})}\n\n"
                    
        except GeneratorExit:
            # クライアント切断時
            pass
        finally:
            remove_sse_client(client_queue)
    
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

