document.addEventListener('DOMContentLoaded', function() {
    const emailInput = document.getElementById('email');
    const form = document.querySelector('.login-form');
    
    // メールアドレスのバリデーション
    emailInput.addEventListener('input', function() {
        const email = this.value;
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        
        if (email && !emailRegex.test(email)) {
            this.setCustomValidity('有効なメールアドレスを入力してください');
        } else {
            this.setCustomValidity('');
        }
    });
    
    // フォーム送信時の処理
    form.addEventListener('submit', function(e) {
        const submitButton = this.querySelector('button[type="submit"]');
        
        // 重複送信防止
        submitButton.disabled = true;
        submitButton.textContent = '送信中...';
        
        // 3秒後に再度有効化（エラー時のため）
        setTimeout(function() {
            submitButton.disabled = false;
            submitButton.textContent = '送信';
        }, 3000);
    });
    
});