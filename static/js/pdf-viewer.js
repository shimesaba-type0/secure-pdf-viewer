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
        // File list
        this.fileList = document.getElementById('pdfFileList');
        
        // Controls
        this.currentFileNameSpan = document.getElementById('currentFileName');
        this.prevPageBtn = document.getElementById('prevPage');
        this.nextPageBtn = document.getElementById('nextPage');
        this.pageInput = document.getElementById('pageInput');
        this.pageCount = document.getElementById('pageCount');
        this.zoomOutBtn = document.getElementById('zoomOut');
        this.zoomInBtn = document.getElementById('zoomIn');
        this.zoomSelect = document.getElementById('zoomSelect');
        
        // Container
        this.pdfContainer = document.getElementById('pdfContainer');
    }
    
    bindEvents() {
        // File selection
        if (this.fileList) {
            this.fileList.addEventListener('click', (e) => {
                const pdfItem = e.target.closest('.pdf-item');
                if (pdfItem) {
                    this.selectFile(pdfItem);
                }
            });
        }
        
        // Page navigation
        this.prevPageBtn?.addEventListener('click', () => this.previousPage());
        this.nextPageBtn?.addEventListener('click', () => this.nextPage());
        this.pageInput?.addEventListener('change', (e) => this.goToPage(parseInt(e.target.value)));
        
        // Zoom controls
        this.zoomOutBtn?.addEventListener('click', () => this.zoomOut());
        this.zoomInBtn?.addEventListener('click', () => this.zoomIn());
        this.zoomSelect?.addEventListener('change', (e) => this.setZoom(e.target.value));
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyboard(e));
    }
    
    async selectFile(pdfItem) {
        // Remove active class from all items
        document.querySelectorAll('.pdf-item').forEach(item => {
            item.classList.remove('active');
        });
        
        // Add active class to selected item
        pdfItem.classList.add('active');
        
        const filePath = pdfItem.dataset.filePath;
        const fileName = pdfItem.querySelector('.pdf-item-name').textContent;
        
        try {
            await this.loadPDF(filePath, fileName);
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
            
            if (this.zoomSelect.value === 'fit') {
                const containerWidth = this.pdfContainer.clientWidth - 40; // padding
                scale = containerWidth / viewport.width;
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
    }
    
    disableControls() {
        this.prevPageBtn.disabled = true;
        this.nextPageBtn.disabled = true;
        this.pageInput.disabled = true;
        this.zoomOutBtn.disabled = true;
        this.zoomInBtn.disabled = true;
        this.zoomSelect.disabled = true;
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
        }
    }
    
    showLoading() {
        this.pdfContainer.innerHTML = '<div class="no-pdf-selected">📄 PDFを読み込み中...</div>';
    }
    
    showError(message) {
        this.pdfContainer.innerHTML = `<div class="no-pdf-selected">❌ ${message}</div>`;
        this.disableControls();
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
            // Find the PDF item and select it
            const pdfItem = document.querySelector(`[data-file-id="${publishedPdf.id}"]`);
            if (pdfItem) {
                setTimeout(() => {
                    viewer.selectFile(pdfItem);
                }, 100); // Small delay to ensure everything is initialized
            }
        }
    }
});