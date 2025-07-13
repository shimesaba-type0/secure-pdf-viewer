from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
import sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-this')
app.config['UPLOAD_FOLDER'] = 'static/pdfs'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    return render_template('viewer.html')

@app.route('/auth/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == 'demo123':
            session['authenticated'] = True
            session['login_time'] = datetime.now().isoformat()
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='パスワードが正しくありません')
    return render_template('login.html')

@app.route('/auth/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin')
def admin():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    # Get list of uploaded PDF files
    pdf_files = get_pdf_files()
    return render_template('admin.html', pdf_files=pdf_files)

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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

def get_pdf_files():
    try:
        conn = sqlite3.connect('instance/database.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        files = cursor.execute('''
            SELECT id, original_filename, stored_filename, file_path, file_size, upload_date 
            FROM pdf_files 
            ORDER BY upload_date DESC
        ''').fetchall()
        
        conn.close()
        
        result = []
        for file in files:
            result.append({
                'id': file['id'],
                'name': file['original_filename'],
                'stored_name': file['stored_filename'],
                'path': file['file_path'],
                'size': format_file_size(file['file_size']),
                'upload_date': file['upload_date']
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
            # Update existing records
            cursor.execute('''
                UPDATE pdf_files 
                SET original_filename = filename, stored_filename = filename 
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

