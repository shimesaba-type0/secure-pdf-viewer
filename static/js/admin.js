// PDF Upload functionality
document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('pdfFile');
    const uploadArea = document.getElementById('uploadArea');
    const uploadInfo = document.getElementById('uploadInfo');
    const uploadBtn = document.getElementById('uploadBtn');
    const clearBtn = document.getElementById('clearBtn');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');

    if (fileInput) {
        // File input change event
        fileInput.addEventListener('change', function(e) {
            handleFileSelection(e.target.files[0]);
        });

        // Drag and drop functionality
        uploadArea.addEventListener('dragover', function(e) {
            e.preventDefault();
            uploadArea.classList.add('drag-over');
        });

        uploadArea.addEventListener('dragleave', function(e) {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
        });

        uploadArea.addEventListener('drop', function(e) {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                fileInput.files = files;
                handleFileSelection(files[0]);
            }
        });
    }

    function handleFileSelection(file) {
        if (file) {
            if (file.type !== 'application/pdf') {
                alert('PDFファイルのみアップロード可能です');
                clearSelection();
                return;
            }

            if (file.size > 16 * 1024 * 1024) { // 16MB
                alert('ファイルサイズが16MBを超えています');
                clearSelection();
                return;
            }

            fileName.textContent = file.name;
            fileSize.textContent = formatFileSize(file.size);
            uploadInfo.style.display = 'block';
            uploadBtn.disabled = false;
            clearBtn.disabled = false;
        }
    }

    function formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }
});

function clearSelection() {
    const fileInput = document.getElementById('pdfFile');
    const uploadInfo = document.getElementById('uploadInfo');
    const uploadBtn = document.getElementById('uploadBtn');
    const clearBtn = document.getElementById('clearBtn');

    fileInput.value = '';
    uploadInfo.style.display = 'none';
    uploadBtn.disabled = true;
    clearBtn.disabled = true;
}

function previewPDF(path) {
    // Open PDF in new window/tab
    window.open(path, '_blank');
}

function deletePDF(fileId) {
    if (confirm('このPDFファイルを削除しますか？')) {
        fetch(`/admin/delete-pdf/${fileId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload(); // Refresh page to update file list
            } else {
                alert('削除に失敗しました: ' + data.error);
            }
        })
        .catch(error => {
            alert('削除に失敗しました: ' + error);
        });
    }
}