// PDF Viewer using PDF.js
class PDFViewer {
    constructor() {
        this.pdfDoc = null;
        this.currentPage = 1;
        this.totalPages = 0;
        this.scale = 1.0;
        this.canvas = null;
        this.ctx = null;
        this.currentFileName = '';
        
        this.initializeElements();
        this.bindEvents();
    }
    
    initializeElements() {
        // Controls
        this.currentFileNameSpan = document.getElementById('currentFileName');
        this.prevPageBtn = document.getElementById('prevPage');
        this.nextPageBtn = document.getElementById('nextPage');
        this.pageInput = document.getElementById('pageInput');
        this.pageCount = document.getElementById('pageCount');
        this.zoomOutBtn = document.getElementById('zoomOut');
        this.zoomInBtn = document.getElementById('zoomIn');
        this.zoomSelect = document.getElementById('zoomSelect');
        this.fullscreenBtn = document.getElementById('fullscreenBtn');
        
        // Container
        this.pdfContainer = document.getElementById('pdfContainer');
        this.pdfViewerPanel = document.querySelector('.pdf-viewer-panel');
        
        // Fullscreen state
        this.isFullscreen = false;
        this.previousZoomValue = null;
    }
    
    bindEvents() {
        // Page navigation
        this.prevPageBtn?.addEventListener('click', () => this.previousPage());
        this.nextPageBtn?.addEventListener('click', () => this.nextPage());
        this.pageInput?.addEventListener('change', (e) => this.goToPage(parseInt(e.target.value)));
        
        // Zoom controls
        this.zoomOutBtn?.addEventListener('click', () => this.zoomOut());
        this.zoomInBtn?.addEventListener('click', () => this.zoomIn());
        this.zoomSelect?.addEventListener('change', (e) => this.setZoom(e.target.value));
        
        // Fullscreen control
        this.fullscreenBtn?.addEventListener('click', () => this.toggleFullscreen());
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyboard(e));
        
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
            
            // Calculate scale
            const viewport = page.getViewport({ scale: 1.0 });
            let scale = this.scale;
            
            if (this.zoomSelect.value === 'fit' || this.isFullscreen) {
                const containerWidth = this.pdfContainer.clientWidth - 40; // padding
                const containerHeight = this.pdfContainer.clientHeight - 40; // padding
                
                // Calculate scale to fit both width and height
                const scaleX = containerWidth / viewport.width;
                const scaleY = containerHeight / viewport.height;
                scale = Math.min(scaleX, scaleY); // Use smaller scale to fit completely
            } else {
                scale = parseFloat(this.zoomSelect.value) || 1.0;
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
                
                this.pdfContainer.innerHTML = '';
                this.pdfContainer.appendChild(canvasContainer);
            }
            
            // Set canvas dimensions
            this.canvas.height = scaledViewport.height;
            this.canvas.width = scaledViewport.width;
            
            // Render page
            const renderContext = {
                canvasContext: this.ctx,
                viewport: scaledViewport
            };
            
            await page.render(renderContext).promise;
            
            this.currentPage = pageNum;
            this.scale = scale;
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
    }
    
    enableControls() {
        this.prevPageBtn.disabled = false;
        this.nextPageBtn.disabled = false;
        this.pageInput.disabled = false;
        this.zoomOutBtn.disabled = false;
        this.zoomInBtn.disabled = false;
        this.zoomSelect.disabled = false;
        this.fullscreenBtn.disabled = false;
    }
    
    disableControls() {
        this.prevPageBtn.disabled = true;
        this.nextPageBtn.disabled = true;
        this.pageInput.disabled = true;
        this.zoomOutBtn.disabled = true;
        this.zoomInBtn.disabled = true;
        this.zoomSelect.disabled = true;
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
    
    async zoomIn() {
        const currentZoom = parseFloat(this.zoomSelect.value) || 1.0;
        const newZoom = Math.min(currentZoom + 0.25, 3.0);
        this.zoomSelect.value = newZoom;
        await this.setZoom(newZoom);
    }
    
    async zoomOut() {
        const currentZoom = parseFloat(this.zoomSelect.value) || 1.0;
        const newZoom = Math.max(currentZoom - 0.25, 0.25);
        this.zoomSelect.value = newZoom;
        await this.setZoom(newZoom);
    }
    
    async setZoom(zoomValue) {
        if (this.pdfDoc && this.currentPage) {
            await this.renderPage(this.currentPage);
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
            case '+':
            case '=':
                e.preventDefault();
                this.zoomIn();
                break;
            case '-':
                e.preventDefault();
                this.zoomOut();
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
        
        // Store current zoom setting and switch to fit mode for fullscreen
        this.previousZoomValue = this.zoomSelect.value;
        this.zoomSelect.value = 'fit';
        
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
        
        // Restore previous zoom setting
        if (this.previousZoomValue) {
            this.zoomSelect.value = this.previousZoomValue;
            this.previousZoomValue = null;
        }
        
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
            
            // Store current zoom setting and switch to fit mode for fullscreen
            this.previousZoomValue = this.zoomSelect.value;
            this.zoomSelect.value = 'fit';
            
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
        hint.textContent = 'ESC または F キーで全画面終了';
        hint.id = 'fullscreenHint';
        
        this.pdfViewerPanel.appendChild(hint);
        
        // Auto-hide after 3 seconds
        setTimeout(() => {
            this.hideFullscreenHint();
        }, 3000);
    }
    
    hideFullscreenHint() {
        const hint = document.getElementById('fullscreenHint');
        if (hint) {
            hint.remove();
        }
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