"""
PDF直接ダウンロード防止機能のテストケース
"""
import pytest
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from flask import Flask
from app import app, pdf_security


class TestPDFDownloadPrevention:
    """PDF直接ダウンロード防止機能のテストクラス"""
    
    @pytest.fixture
    def client(self):
        """Flaskテストクライアントのフィクスチャ"""
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key'
        app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
        
        with app.test_client() as client:
            yield client
    
    @pytest.fixture
    def sample_pdf(self):
        """テスト用PDFファイルの作成"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'%PDF-1.4\n%fake pdf content\n%%EOF')
            yield f.name
        os.unlink(f.name)
    
    @pytest.fixture
    def mock_session(self):
        """モックセッションの設定"""
        session_data = {
            'authenticated': True,
            'session_id': 'test-session-123',
            'user_id': 'test-user'
        }
        return session_data
    
    @pytest.fixture
    def valid_token(self, sample_pdf):
        """有効なPDFトークンの生成"""
        filename = os.path.basename(sample_pdf)
        token_data = {
            'valid': True,
            'filename': filename,
            'session_id': 'test-session-123',
            'one_time': False
        }
        return 'valid-test-token', token_data
    
    def test_referrer_check_missing_header(self, client, mock_session, valid_token, sample_pdf):
        """Referrerヘッダーが存在しない場合のテスト"""
        token, token_data = valid_token
        filename = token_data['filename']
        
        # PDFファイルを配置
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(pdf_path, 'wb') as f:
            with open(sample_pdf, 'rb') as src:
                f.write(src.read())
        
        with patch('app.session', mock_session), \
             patch('app.pdf_security.verify_signed_url', return_value=token_data), \
             patch('app.require_valid_session', return_value=None):
            
            # Referrerヘッダーなしでアクセス
            response = client.get(f'/secure/pdf/{token}')
            
            # 403エラーが返されることを確認
            assert response.status_code == 403
            data = json.loads(response.data)
            assert 'Invalid referrer' in data['error']
    
    def test_referrer_check_invalid_domain(self, client, mock_session, valid_token, sample_pdf):
        """無効なReferrerドメインからのアクセステスト"""
        token, token_data = valid_token
        filename = token_data['filename']
        
        # PDFファイルを配置
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(pdf_path, 'wb') as f:
            with open(sample_pdf, 'rb') as src:
                f.write(src.read())
        
        with patch('app.session', mock_session), \
             patch('app.pdf_security.verify_signed_url', return_value=token_data), \
             patch('app.require_valid_session', return_value=None):
            
            # 無効なReferrerヘッダーでアクセス
            response = client.get(f'/secure/pdf/{token}', 
                                headers={'Referer': 'https://malicious-site.com/page'})
            
            # 403エラーが返されることを確認
            assert response.status_code == 403
            data = json.loads(response.data)
            assert 'Invalid referrer' in data['error']
    
    def test_referrer_check_valid_domain(self, client, mock_session, valid_token, sample_pdf):
        """有効なReferrerドメインからのアクセステスト"""
        token, token_data = valid_token
        filename = token_data['filename']
        
        # PDFファイルを配置
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(pdf_path, 'wb') as f:
            with open(sample_pdf, 'rb') as src:
                f.write(src.read())
        
        # テスト用の設定をモック
        mock_config = {
            'enabled': True,
            'allowed_referrer_domains': ['localhost'],
            'blocked_user_agents': ['wget', 'curl'],
            'user_agent_check_enabled': True,
            'log_blocked_attempts': True
        }
        
        with patch('app.session', mock_session), \
             patch('app.pdf_security.verify_signed_url', return_value=token_data), \
             patch('app.require_valid_session', return_value=None), \
             patch('app.pdf_security.log_pdf_access'), \
             patch('app.get_pdf_security_config', return_value=mock_config):
            
            # 有効なReferrerヘッダーでアクセス
            response = client.get(f'/secure/pdf/{token}', 
                                headers={'Referer': 'http://localhost/app'})
            
            # 正常にPDFが返されることを確認
            assert response.status_code == 200
            assert response.content_type == 'application/pdf'
    
    def test_user_agent_check_empty(self, client, mock_session, valid_token, sample_pdf):
        """空のUser-Agentのテスト"""
        token, token_data = valid_token
        filename = token_data['filename']
        
        # PDFファイルを配置
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(pdf_path, 'wb') as f:
            with open(sample_pdf, 'rb') as src:
                f.write(src.read())
        
        # テスト用の設定をモック
        mock_config = {
            'enabled': True,
            'allowed_referrer_domains': ['localhost'],
            'blocked_user_agents': ['wget', 'curl'],
            'user_agent_check_enabled': True,
            'log_blocked_attempts': True
        }
        
        with patch('app.session', mock_session), \
             patch('app.pdf_security.verify_signed_url', return_value=token_data), \
             patch('app.require_valid_session', return_value=None), \
             patch('app.get_pdf_security_config', return_value=mock_config):
            
            # 空のUser-Agentでアクセス
            response = client.get(f'/secure/pdf/{token}', 
                                headers={
                                    'Referer': 'http://localhost/app',
                                    'User-Agent': ''
                                })
            
            # 403エラーが返されることを確認
            assert response.status_code == 403
            data = json.loads(response.data)
            assert 'Invalid client' in data['error']
    
    def test_user_agent_check_blocked_agents(self, client, mock_session, valid_token, sample_pdf):
        """ブロックされるUser-Agentのテスト"""
        token, token_data = valid_token
        filename = token_data['filename']
        
        # PDFファイルを配置
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(pdf_path, 'wb') as f:
            with open(sample_pdf, 'rb') as src:
                f.write(src.read())
        
        # テスト用の設定をモック
        mock_config = {
            'enabled': True,
            'allowed_referrer_domains': ['localhost'],
            'blocked_user_agents': ['wget', 'curl', 'python-requests', 'Go-http-client', 'Java/', 'node-fetch'],
            'user_agent_check_enabled': True,
            'log_blocked_attempts': True
        }
        
        # 新しい充実したブラックリストの一部をテスト
        blocked_agents = ['wget', 'curl', 'python-requests', 'Go-http-client', 'Java/', 'node-fetch']
        
        for agent in blocked_agents:
            with patch('app.session', mock_session), \
                 patch('app.pdf_security.verify_signed_url', return_value=token_data), \
                 patch('app.require_valid_session', return_value=None), \
                 patch('app.get_pdf_security_config', return_value=mock_config):
                
                # ブロックされるUser-Agentでアクセス
                response = client.get(f'/secure/pdf/{token}', 
                                    headers={
                                        'Referer': 'http://localhost/app',
                                        'User-Agent': agent
                                    })
                
                # 403エラーが返されることを確認
                assert response.status_code == 403
                data = json.loads(response.data)
                assert 'Invalid client' in data['error']
    
    def test_user_agent_check_valid_browser(self, client, mock_session, valid_token, sample_pdf):
        """有効なブラウザUser-Agentのテスト"""
        token, token_data = valid_token
        filename = token_data['filename']
        
        # PDFファイルを配置
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(pdf_path, 'wb') as f:
            with open(sample_pdf, 'rb') as src:
                f.write(src.read())
        
        # テスト用の設定をモック
        mock_config = {
            'enabled': True,
            'allowed_referrer_domains': ['localhost'],
            'blocked_user_agents': ['wget', 'curl'],
            'user_agent_check_enabled': True,
            'log_blocked_attempts': True
        }
        
        with patch('app.session', mock_session), \
             patch('app.pdf_security.verify_signed_url', return_value=token_data), \
             patch('app.require_valid_session', return_value=None), \
             patch('app.pdf_security.log_pdf_access'), \
             patch('app.get_pdf_security_config', return_value=mock_config):
            
            # 有効なブラウザUser-Agentでアクセス
            response = client.get(f'/secure/pdf/{token}', 
                                headers={
                                    'Referer': 'http://localhost/app',
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                                })
            
            # 正常にPDFが返されることを確認
            assert response.status_code == 200
            assert response.content_type == 'application/pdf'
    
    def test_security_headers(self, client, mock_session, valid_token, sample_pdf):
        """強化されたセキュリティヘッダーのテスト"""
        token, token_data = valid_token
        filename = token_data['filename']
        
        # PDFファイルを配置
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(pdf_path, 'wb') as f:
            with open(sample_pdf, 'rb') as src:
                f.write(src.read())
        
        # テスト用の設定をモック
        mock_config = {
            'enabled': True,
            'allowed_referrer_domains': ['localhost'],
            'blocked_user_agents': ['wget', 'curl'],
            'user_agent_check_enabled': True,
            'log_blocked_attempts': True
        }
        
        with patch('app.session', mock_session), \
             patch('app.pdf_security.verify_signed_url', return_value=token_data), \
             patch('app.require_valid_session', return_value=None), \
             patch('app.pdf_security.log_pdf_access'), \
             patch('app.get_pdf_security_config', return_value=mock_config):
            
            response = client.get(f'/secure/pdf/{token}', 
                                headers={
                                    'Referer': 'http://localhost/app',
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                                })
            
            # セキュリティヘッダーの確認
            assert response.headers.get('Content-Security-Policy') == "frame-ancestors 'self'"
            assert response.headers.get('X-Robots-Tag') == 'noindex, nofollow, nosnippet, noarchive'
            assert response.headers.get('X-Content-Type-Options') == 'nosniff'
            assert response.headers.get('X-Frame-Options') == 'DENY'
    
    def test_logging_blocked_access(self, client, mock_session, valid_token, sample_pdf):
        """ブロックされたアクセスのログ記録テスト"""
        token, token_data = valid_token
        filename = token_data['filename']
        
        # PDFファイルを配置
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(pdf_path, 'wb') as f:
            with open(sample_pdf, 'rb') as src:
                f.write(src.read())
        
        with patch('app.session', mock_session), \
             patch('app.pdf_security.verify_signed_url', return_value=token_data), \
             patch('app.require_valid_session', return_value=None), \
             patch('app.pdf_security.log_pdf_access') as mock_log:
            
            # Referrerなしでアクセス
            response = client.get(f'/secure/pdf/{token}')
            
            # ログが呼ばれたことを確認
            mock_log.assert_called_once()
            args, kwargs = mock_log.call_args
            
            # ログの内容を確認
            assert kwargs['success'] == False
            assert 'invalid_referrer' in kwargs['error_message']
    
    def test_configuration_disabled(self, client, mock_session, valid_token, sample_pdf):
        """機能無効化設定のテスト"""
        token, token_data = valid_token
        filename = token_data['filename']
        
        # PDFファイルを配置
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(pdf_path, 'wb') as f:
            with open(sample_pdf, 'rb') as src:
                f.write(src.read())
        
        # PDF防止機能全体を無効化
        mock_config = {
            'enabled': False,
            'allowed_referrer_domains': ['localhost'],
            'blocked_user_agents': ['wget'],
            'user_agent_check_enabled': True,
            'log_blocked_attempts': True
        }
        
        with patch('app.session', mock_session), \
             patch('app.pdf_security.verify_signed_url', return_value=token_data), \
             patch('app.require_valid_session', return_value=None), \
             patch('app.pdf_security.log_pdf_access'), \
             patch('app.get_pdf_security_config', return_value=mock_config):
            
            # 機能無効時はReferrerなしでもアクセス可能
            response = client.get(f'/secure/pdf/{token}')
            assert response.status_code == 200
    
    def test_user_agent_check_disabled(self, client, mock_session, valid_token, sample_pdf):
        """User-Agentチェック無効化のテスト"""
        token, token_data = valid_token
        filename = token_data['filename']
        
        # PDFファイルを配置
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(pdf_path, 'wb') as f:
            with open(sample_pdf, 'rb') as src:
                f.write(src.read())
        
        # User-Agentチェックのみ無効化
        mock_config = {
            'enabled': True,
            'allowed_referrer_domains': ['localhost'],
            'blocked_user_agents': ['wget', 'curl', 'python-requests'],
            'user_agent_check_enabled': False,  # User-Agentチェック無効
            'log_blocked_attempts': True
        }
        
        with patch('app.session', mock_session), \
             patch('app.pdf_security.verify_signed_url', return_value=token_data), \
             patch('app.require_valid_session', return_value=None), \
             patch('app.pdf_security.log_pdf_access'), \
             patch('app.get_pdf_security_config', return_value=mock_config):
            
            # User-Agentチェック無効時はwgetでもアクセス可能（Referrerは必要）
            response = client.get(f'/secure/pdf/{token}', 
                                headers={
                                    'Referer': 'http://localhost/app',
                                    'User-Agent': 'wget'  # 通常ならブロックされる
                                })
            assert response.status_code == 200
    
    def test_backwards_compatibility(self, client, mock_session, valid_token, sample_pdf):
        """既存機能との互換性テスト"""
        token, token_data = valid_token
        filename = token_data['filename']
        
        # PDFファイルを配置
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(pdf_path, 'wb') as f:
            with open(sample_pdf, 'rb') as src:
                f.write(src.read())
        
        # テスト用の設定をモック
        mock_config = {
            'enabled': True,
            'allowed_referrer_domains': ['localhost'],
            'blocked_user_agents': ['wget', 'curl'],
            'user_agent_check_enabled': True,
            'log_blocked_attempts': True
        }
        
        with patch('app.session', mock_session), \
             patch('app.pdf_security.verify_signed_url', return_value=token_data), \
             patch('app.require_valid_session', return_value=None), \
             patch('app.pdf_security.log_pdf_access'), \
             patch('app.get_pdf_security_config', return_value=mock_config):
            
            # 正常なアクセスでは既存機能が動作することを確認
            response = client.get(f'/secure/pdf/{token}', 
                                headers={
                                    'Referer': 'http://localhost/app',
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                                })
            
            assert response.status_code == 200
            assert response.content_type == 'application/pdf'
            
            # 既存のヘッダーが維持されていることを確認
            assert 'inline' in response.headers.get('Content-Disposition', '')
            assert response.headers.get('Cache-Control') == 'no-cache, no-store, must-revalidate'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])