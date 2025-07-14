// PDF Viewer using PDF.js
class PDFViewer {
    constructor() {
        this.pdfDoc = null;
        this.currentPage = 1;
        this.totalPages = 0;
        this.canvas = null;
        this.ctx = null;
        this.currentFileName = '';
        this.authorName = 'Default_Author'; // デフォルト値
        this.sessionInfo = null; // セッション情報
        this.eventSource = null; // SSE接続
        
        this.initializeElements();
        this.loadAuthorName();
        this.loadSessionInfo();
        this.initializeSSE();
        this.bindEvents();
    }
    
    initializeElements() {
        // Controls
        this.currentFileNameSpan = document.getElementById('currentFileName');
        this.prevPageBtn = document.getElementById('prevPage');
        this.nextPageBtn = document.getElementById('nextPage');
        this.pageInput = document.getElementById('pageInput');
        this.pageCount = document.getElementById('pageCount');
        this.fullscreenBtn = document.getElementById('fullscreenBtn');
        
        // Container
        this.pdfContainer = document.getElementById('pdfContainer');
        this.pdfViewerPanel = document.querySelector('.pdf-viewer-panel');
        
        // Fullscreen state
        this.isFullscreen = false;
        
        // Navigation overlay buttons
        this.navPrevBtn = null;
        this.navNextBtn = null;
        
        // Resize handling
        this.resizeTimeout = null;
    }
    
    loadAuthorName() {
        // Load author name from template data
        const authorNameData = document.getElementById('authorNameData');
        if (authorNameData) {
            try {
                this.authorName = JSON.parse(authorNameData.textContent) || 'Default_Author';
            } catch (e) {
                console.warn('Failed to load author name, using default');
                this.authorName = 'Default_Author';
            }
        }
    }
    
    async loadSessionInfo() {
        // Load session info from API for watermark
        try {
            const response = await fetch('/api/session-info');
            if (response.ok) {
                this.sessionInfo = await response.json();
            } else {
                console.warn('Failed to load session info, using fallback');
                this.sessionInfo = {
                    session_id: 'SID-FALLBACK',
                    email: 'anonymous@example.com'
                };
            }
        } catch (e) {
            console.warn('Failed to load session info:', e);
            this.sessionInfo = {
                session_id: 'SID-FALLBACK',
                email: 'anonymous@example.com'
            };
        }
    }
    
    initializeSSE() {
        // Server-Sent Events接続を初期化
        try {
            this.eventSource = new EventSource('/api/events');
            
            this.eventSource.onopen = () => {
                console.log('SSE接続が確立されました');
            };
            
            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleSSEEvent(data);
                } catch (e) {
                    console.warn('SSEメッセージの解析に失敗:', e);
                }
            };
            
            this.eventSource.addEventListener('pdf_unpublished', (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handlePDFUnpublished(data);
                } catch (e) {
                    console.warn('PDF停止イベントの処理に失敗:', e);
                }
            });
            
            this.eventSource.addEventListener('pdf_published', (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handlePDFPublished(data);
                } catch (e) {
                    console.warn('PDF公開イベントの処理に失敗:', e);
                }
            });
            
            this.eventSource.onerror = (error) => {
                console.warn('SSE接続エラー:', error);
                // 自動再接続は EventSource が行う
            };
            
        } catch (e) {
            console.warn('SSE初期化に失敗:', e);
        }
    }
    
    handleSSEEvent(data) {
        // 一般的なSSEイベント処理
        if (data.event === 'connected') {
            console.log('SSE:', data.message);
        } else if (data.event === 'heartbeat') {
            // ハートビートは特に何もしない
        }
    }
    
    handlePDFUnpublished(data) {
        // PDF公開停止時の処理
        console.log('PDF公開停止:', data.message);
        
        // PDFを非表示にして終了メッセージを表示
        this.showPublicationEndedMessage(data);
        
        // PDFコントロールを無効化
        this.disableControls();
    }
    
    handlePDFPublished(data) {
        // PDF公開開始時の処理
        console.log('PDF公開開始:', data.message);
        
        // ページをリロードして新しいPDFを表示
        // 既に何かが表示されている場合のみリロード
        if (this.pdfDoc) {
            window.location.reload();
        }
    }
    
    showPublicationEndedMessage(data) {
        // 公開終了メッセージを表示
        const endMessage = document.createElement('div');
        endMessage.className = 'publication-ended-message';
        endMessage.innerHTML = `
            <div class="end-message-content">
                <h2>📄 公開終了</h2>
                <p>${data.message}</p>
                <p class="end-time">終了時刻: ${data.timestamp}</p>
                <small>このページを閉じてください</small>
            </div>
        `;
        
        // 既存のPDFコンテナを置き換え
        this.pdfContainer.innerHTML = '';
        this.pdfContainer.appendChild(endMessage);
        
        // ナビゲーションヘルプも非表示
        this.hideNavigationHelp();
    }
    
    bindEvents() {
        // Page navigation
        this.prevPageBtn?.addEventListener('click', () => this.previousPage());
        this.nextPageBtn?.addEventListener('click', () => this.nextPage());
        this.pageInput?.addEventListener('change', (e) => this.goToPage(parseInt(e.target.value)));
        
        // Fullscreen control
        this.fullscreenBtn?.addEventListener('click', () => this.toggleFullscreen());
        
        // Mobile fullscreen exit - double tap
        let lastTap = 0;
        this.pdfContainer?.addEventListener('touchend', (e) => {
            const currentTime = new Date().getTime();
            const tapLength = currentTime - lastTap;
            if (tapLength < 500 && tapLength > 0 && this.isFullscreen) {
                // Double tap detected in fullscreen mode
                e.preventDefault();
                this.exitFullscreen();
            }
            lastTap = currentTime;
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyboard(e));
        
        // Window resize handling for responsive design
        window.addEventListener('resize', () => this.handleResize());
        
        // Orientation change handling for mobile
        window.addEventListener('orientationchange', () => {
            setTimeout(() => this.handleResize(), 300); // Delay for orientation change completion
        });
        
        // Fullscreen change events
        document.addEventListener('fullscreenchange', () => this.handleFullscreenChange());
        document.addEventListener('webkitfullscreenchange', () => this.handleFullscreenChange());
        document.addEventListener('mozfullscreenchange', () => this.handleFullscreenChange());
        document.addEventListener('MSFullscreenChange', () => this.handleFullscreenChange());
    }
    
    async loadPublishedPDF(publishedPdf) {
        try {
            await this.loadPDF(publishedPdf.path, publishedPdf.name);
        } catch (error) {
            console.error('PDF loading failed:', error);
            this.showError('PDFファイルの読み込みに失敗しました: ' + error.message);
        }
    }
    
    async loadPDF(filePath, fileName) {
        try {
            // Show loading indicator
            this.showLoading();
            
            // Load PDF document
            const loadingTask = pdfjsLib.getDocument(filePath);
            this.pdfDoc = await loadingTask.promise;
            
            this.currentFileName = fileName;
            this.totalPages = this.pdfDoc.numPages;
            this.currentPage = 1;
            
            // Update UI
            this.updateUI();
            this.enableControls();
            
            // Show navigation help
            this.showNavigationHelp();
            
            // Ensure container has proper dimensions before rendering
            await this.waitForContainerReady();
            
            // Render first page
            await this.renderPage(1);
            
        } catch (error) {
            throw new Error('PDF document loading failed: ' + error.message);
        }
    }
    
    async renderPage(pageNum) {
        if (!this.pdfDoc) return;
        
        try {
            // Get page
            const page = await this.pdfDoc.getPage(pageNum);
            
            // Calculate scale - always 1.0 (100%) for default display
            const viewport = page.getViewport({ scale: 1.0 });
            let scale;
            
            if (this.isFullscreen) {
                // For fullscreen: fit to screen with proper centering
                const isMobile = window.innerWidth <= 768;
                const containerWidth = this.pdfContainer.clientWidth;
                const containerHeight = this.pdfContainer.clientHeight;
                
                if (isMobile) {
                    // Mobile fullscreen: center PDF with black bars
                    const isPortrait = window.innerHeight > window.innerWidth;
                    
                    if (isPortrait) {
                        // Portrait: fit width, allow height to overflow (black bars top/bottom)
                        const availableWidth = containerWidth * 0.95; // 95% of screen width
                        scale = availableWidth / viewport.width;
                        
                        // Ensure it doesn't get too large vertically
                        const maxHeight = containerHeight * 0.9;
                        if (scale * viewport.height > maxHeight) {
                            scale = maxHeight / viewport.height;
                        }
                    } else {
                        // Landscape: fit height, allow width to overflow (black bars left/right) 
                        const availableHeight = containerHeight * 0.9; // 90% of screen height
                        scale = availableHeight / viewport.height;
                        
                        // Ensure it doesn't get too wide
                        const maxWidth = containerWidth * 0.95;
                        if (scale * viewport.width > maxWidth) {
                            scale = maxWidth / viewport.width;
                        }
                    }
                    
                    // Minimum scale for readability
                    scale = Math.max(scale, 0.4);
                } else {
                    // Desktop fullscreen: fit to screen
                    const paddingX = 40;
                    const paddingY = 40;
                    const availableWidth = containerWidth - paddingX;
                    const availableHeight = containerHeight - paddingY;
                    
                    const scaleX = availableWidth / viewport.width;
                    const scaleY = availableHeight / viewport.height;
                    scale = Math.min(scaleX, scaleY);
                }
            } else {
                // Default display: always 100%
                scale = 1.0;
            }
            
            const scaledViewport = page.getViewport({ scale: scale });
            
            // Create or update canvas
            if (!this.canvas) {
                this.canvas = document.createElement('canvas');
                this.canvas.id = 'pdfCanvas';
                this.ctx = this.canvas.getContext('2d');
                
                const canvasContainer = document.createElement('div');
                canvasContainer.className = 'pdf-canvas-container';
                canvasContainer.appendChild(this.canvas);
                
                // Add navigation overlay buttons
                const prevBtn = document.createElement('button');
                prevBtn.className = 'pdf-nav-overlay pdf-nav-prev';
                prevBtn.innerHTML = '◀';
                prevBtn.addEventListener('click', () => this.previousPage());
                
                const nextBtn = document.createElement('button');
                nextBtn.className = 'pdf-nav-overlay pdf-nav-next';
                nextBtn.innerHTML = '▶';
                nextBtn.addEventListener('click', () => this.nextPage());
                
                canvasContainer.appendChild(prevBtn);
                canvasContainer.appendChild(nextBtn);
                
                // Store references for updating state
                this.navPrevBtn = prevBtn;
                this.navNextBtn = nextBtn;
                
                this.pdfContainer.innerHTML = '';
                this.pdfContainer.appendChild(canvasContainer);
            }
            
            // Set canvas dimensions explicitly
            this.canvas.height = Math.floor(scaledViewport.height);
            this.canvas.width = Math.floor(scaledViewport.width);
            
            // Clear any previous content
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            
            // Render page
            const renderContext = {
                canvasContext: this.ctx,
                viewport: scaledViewport
            };
            
            await page.render(renderContext).promise;
            
            // Add watermark overlay
            this.addWatermark(this.ctx, scaledViewport.width, scaledViewport.height);
            
            this.currentPage = pageNum;
            // Don't store scale to avoid accumulation
            this.updatePageInfo();
            
        } catch (error) {
            console.error('Page rendering failed:', error);
            this.showError('ページの表示に失敗しました: ' + error.message);
        }
    }
    
    updateUI() {
        this.currentFileNameSpan.textContent = this.currentFileName;
        this.pageCount.textContent = `/ ${this.totalPages}`;
        this.pageInput.max = this.totalPages;
    }
    
    updatePageInfo() {
        this.pageInput.value = this.currentPage;
        this.prevPageBtn.disabled = this.currentPage <= 1;
        this.nextPageBtn.disabled = this.currentPage >= this.totalPages;
        
        // Update navigation overlay buttons
        if (this.navPrevBtn) {
            this.navPrevBtn.classList.toggle('disabled', this.currentPage <= 1);
        }
        if (this.navNextBtn) {
            this.navNextBtn.classList.toggle('disabled', this.currentPage >= this.totalPages);
        }
    }
    
    enableControls() {
        this.prevPageBtn.disabled = false;
        this.nextPageBtn.disabled = false;
        this.pageInput.disabled = false;
        this.fullscreenBtn.disabled = false;
    }
    
    disableControls() {
        this.prevPageBtn.disabled = true;
        this.nextPageBtn.disabled = true;
        this.pageInput.disabled = true;
        this.fullscreenBtn.disabled = true;
    }
    
    async previousPage() {
        if (this.currentPage > 1) {
            await this.renderPage(this.currentPage - 1);
        }
    }
    
    async nextPage() {
        if (this.currentPage < this.totalPages) {
            await this.renderPage(this.currentPage + 1);
        }
    }
    
    async goToPage(pageNum) {
        if (pageNum >= 1 && pageNum <= this.totalPages) {
            await this.renderPage(pageNum);
        } else {
            this.pageInput.value = this.currentPage; // Reset to current page
        }
    }
    
    
    handleKeyboard(e) {
        if (!this.pdfDoc) return;
        
        switch (e.key) {
            case 'ArrowLeft':
            case 'ArrowUp':
                e.preventDefault();
                this.previousPage();
                break;
            case 'ArrowRight':
            case 'ArrowDown':
                e.preventDefault();
                this.nextPage();
                break;
            case 'Home':
                e.preventDefault();
                this.goToPage(1);
                break;
            case 'End':
                e.preventDefault();
                this.goToPage(this.totalPages);
                break;
            case 'f':
            case 'F':
                if (this.pdfDoc) {
                    e.preventDefault();
                    this.toggleFullscreen();
                }
                break;
            case 'Escape':
                if (this.isFullscreen) {
                    e.preventDefault();
                    this.exitFullscreen();
                }
                break;
        }
    }
    
    showLoading() {
        this.pdfContainer.innerHTML = '<div class="no-pdf-selected">📄 PDFを読み込み中...</div>';
    }
    
    showError(message) {
        this.pdfContainer.innerHTML = `<div class="no-pdf-selected">❌ ${message}</div>`;
        this.disableControls();
    }
    
    toggleFullscreen() {
        if (this.isFullscreen) {
            this.exitFullscreen();
        } else {
            this.enterFullscreen();
        }
    }
    
    async enterFullscreen() {
        try {
            // Try to use browser's fullscreen API first
            if (this.pdfViewerPanel.requestFullscreen) {
                await this.pdfViewerPanel.requestFullscreen();
            } else if (this.pdfViewerPanel.webkitRequestFullscreen) {
                await this.pdfViewerPanel.webkitRequestFullscreen();
            } else if (this.pdfViewerPanel.mozRequestFullScreen) {
                await this.pdfViewerPanel.mozRequestFullScreen();
            } else if (this.pdfViewerPanel.msRequestFullscreen) {
                await this.pdfViewerPanel.msRequestFullscreen();
            } else {
                // Fallback to CSS fullscreen
                this.enterCSSFullscreen();
            }
        } catch (error) {
            // If browser fullscreen fails, use CSS fullscreen
            this.enterCSSFullscreen();
        }
    }
    
    enterCSSFullscreen() {
        this.pdfViewerPanel.classList.add('fullscreen');
        this.isFullscreen = true;
        this.updateFullscreenButton();
        this.showFullscreenHint();
        
        
        // Re-render current page to fit new size
        if (this.pdfDoc && this.currentPage) {
            setTimeout(() => {
                this.renderPage(this.currentPage);
            }, 100);
        }
    }
    
    exitFullscreen() {
        if (document.fullscreenElement || document.webkitFullscreenElement || 
            document.mozFullScreenElement || document.msFullscreenElement) {
            // Exit browser fullscreen
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.mozCancelFullScreen) {
                document.mozCancelFullScreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
        } else {
            // Exit CSS fullscreen
            this.exitCSSFullscreen();
        }
    }
    
    exitCSSFullscreen() {
        this.pdfViewerPanel.classList.remove('fullscreen');
        this.isFullscreen = false;
        this.updateFullscreenButton();
        this.hideFullscreenHint();
        
        // Re-render current page to fit new size
        if (this.pdfDoc && this.currentPage) {
            setTimeout(() => {
                this.renderPage(this.currentPage);
            }, 100);
        }
    }
    
    handleFullscreenChange() {
        const isInFullscreen = !!(document.fullscreenElement || document.webkitFullscreenElement || 
                                  document.mozFullScreenElement || document.msFullscreenElement);
        
        if (!isInFullscreen && this.isFullscreen) {
            // Exited browser fullscreen
            this.exitCSSFullscreen();
        } else if (isInFullscreen && !this.isFullscreen) {
            // Entered browser fullscreen
            this.isFullscreen = true;
            this.updateFullscreenButton();
            this.showFullscreenHint();
            
            // Re-render current page
            if (this.pdfDoc && this.currentPage) {
                setTimeout(() => {
                    this.renderPage(this.currentPage);
                }, 100);
            }
        }
    }
    
    updateFullscreenButton() {
        if (this.fullscreenBtn) {
            this.fullscreenBtn.textContent = this.isFullscreen ? '全画面終了' : '全画面表示';
        }
    }
    
    showFullscreenHint() {
        // Remove existing hint
        this.hideFullscreenHint();
        
        const hint = document.createElement('div');
        hint.className = 'fullscreen-exit-hint';
        
        // Different hint text for mobile vs desktop
        const isMobile = window.innerWidth <= 768;
        if (isMobile) {
            hint.textContent = 'ダブルタップで全画面終了';
        } else {
            hint.textContent = 'ESC または F キーで全画面終了';
        }
        
        hint.id = 'fullscreenHint';
        
        this.pdfViewerPanel.appendChild(hint);
        
        // Auto-hide after 4 seconds on mobile, 3 seconds on desktop
        setTimeout(() => {
            this.hideFullscreenHint();
        }, isMobile ? 4000 : 3000);
    }
    
    hideFullscreenHint() {
        const hint = document.getElementById('fullscreenHint');
        if (hint) {
            hint.remove();
        }
    }
    
    showNavigationHelp() {
        const helpElement = document.getElementById('pdfNavigationHelp');
        if (helpElement) {
            helpElement.style.display = 'block';
        }
    }
    
    hideNavigationHelp() {
        const helpElement = document.getElementById('pdfNavigationHelp');
        if (helpElement) {
            helpElement.style.display = 'none';
        }
    }
    
    handleResize() {
        // Re-render current page when window is resized for responsive layout
        if (this.pdfDoc && this.currentPage) {
            // Debounce resize events
            clearTimeout(this.resizeTimeout);
            this.resizeTimeout = setTimeout(() => {
                this.renderPage(this.currentPage);
            }, 250);
        }
    }
    
    async waitForContainerReady() {
        // Wait for container to have proper dimensions
        return new Promise((resolve) => {
            const checkContainer = () => {
                if (this.pdfContainer.clientWidth > 0 && this.pdfContainer.clientHeight > 0) {
                    resolve();
                } else {
                    setTimeout(checkContainer, 10);
                }
            };
            checkContainer();
        });
    }
    
    addWatermark(ctx, canvasWidth, canvasHeight) {
        // Save current context state
        ctx.save();
        
        // Watermark settings - 4 pieces of information as per specification
        const author = this.authorName; // 著作者（動的に取得）
        
        // 閲覧者メールアドレス（動的に取得）
        const viewerEmail = this.sessionInfo ? 
            this.sessionInfo.email : 'loading@example.com';
        
        // セッションID（動的に取得）
        const sessionId = this.sessionInfo ? 
            this.sessionInfo.session_id : 'SID-LOADING';
        const currentDateTime = new Date().toLocaleString('ja-JP', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        }).replace(/\//g, '/');
        
        // Calculate responsive font size based on canvas size
        const baseFontSize = Math.min(canvasWidth, canvasHeight) * 0.018;
        const fontSize = Math.max(10, Math.min(20, baseFontSize));
        
        // Watermark style - top-right corner
        ctx.globalAlpha = 0.4; // More visible
        ctx.fillStyle = '#FF0000'; // Red color for better visibility
        ctx.font = `bold ${fontSize}px Arial, sans-serif`;
        ctx.textAlign = 'right';
        ctx.textBaseline = 'top';
        
        // Position in top-right corner
        const padding = 15;
        const lineHeight = fontSize + 3;
        let yPosition = padding;
        
        // Display 4 pieces of information vertically
        ctx.fillText(`著作者: ${author}`, canvasWidth - padding, yPosition);
        yPosition += lineHeight;
        
        ctx.font = `${fontSize * 0.85}px Arial, sans-serif`;
        ctx.fillText(`閲覧者: ${viewerEmail}`, canvasWidth - padding, yPosition);
        yPosition += lineHeight;
        
        ctx.fillText(`日時: ${currentDateTime}`, canvasWidth - padding, yPosition);
        yPosition += lineHeight;
        
        ctx.fillText(`SID: ${sessionId}`, canvasWidth - padding, yPosition);
        
        // Add page number watermark at bottom center
        if (this.currentPage && this.totalPages) {
            ctx.globalAlpha = 0.3;
            ctx.fillStyle = '#666666';
            ctx.font = `${fontSize * 0.7}px Arial, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'bottom';
            ctx.fillText(`ページ ${this.currentPage}/${this.totalPages}`, canvasWidth / 2, canvasHeight - 10);
        }
        
        // Restore context state
        ctx.restore();
    }
}

// Initialize PDF viewer when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    const viewer = new PDFViewer();
    
    // Auto-load published PDF if available
    const publishedPdfData = document.getElementById('publishedPdfData');
    if (publishedPdfData) {
        const publishedPdf = JSON.parse(publishedPdfData.textContent);
        if (publishedPdf) {
            setTimeout(() => {
                viewer.loadPublishedPDF(publishedPdf);
            }, 100); // Small delay to ensure everything is initialized
        }
    }
});