document.addEventListener('DOMContentLoaded', function() {
    const otpInput = document.getElementById('otp_code');
    const verifyBtn = document.getElementById('verify-btn');
    const resendBtn = document.getElementById('resend-btn');
    const form = document.querySelector('.otp-form');
    
    // OTP入力フィールドのバリデーション
    otpInput.addEventListener('input', function() {
        let value = this.value.replace(/[^0-9]/g, ''); // 数字以外を除去
        this.value = value;
        
        // 6桁入力時にボタンを有効化
        if (value.length === 6) {
            verifyBtn.disabled = false;
            verifyBtn.classList.remove('btn-disabled');
        } else {
            verifyBtn.disabled = true;
            verifyBtn.classList.add('btn-disabled');
        }
    });
    
    // 初期状態でボタンを無効化
    verifyBtn.disabled = true;
    verifyBtn.classList.add('btn-disabled');
    
    // フォーム送信処理
    form.addEventListener('submit', function(e) {
        const otpValue = otpInput.value.trim();
        
        if (otpValue.length !== 6) {
            e.preventDefault();
            alert('6桁のOTPコードを入力してください');
            return;
        }
        
        // 送信中状態に変更
        verifyBtn.disabled = true;
        verifyBtn.textContent = '認証中...';
        
        // エラー時のリセット（3秒後）
        setTimeout(function() {
            verifyBtn.disabled = false;
            verifyBtn.textContent = '認証';
        }, 3000);
    });
    
    // 再送信ボタンの処理
    resendBtn.addEventListener('click', function() {
        this.disabled = true;
        this.textContent = '送信中...';
        
        // メールアドレス入力画面に戻る
        window.location.href = '/auth/email';
    });
    
    // 自動フォーカス
    otpInput.focus();
    
    // ペースト時の自動整形
    otpInput.addEventListener('paste', function(e) {
        setTimeout(() => {
            let value = this.value.replace(/[^0-9]/g, '');
            if (value.length > 6) {
                value = value.substring(0, 6);
            }
            this.value = value;
            
            // バリデーションイベントを発火
            this.dispatchEvent(new Event('input'));
        }, 0);
    });
    
    // 残り時間のカウントダウン（簡易版）
    const remainingTimeElement = document.getElementById('remaining-time');
    if (remainingTimeElement) {
        let minutes = 10;
        let seconds = 0;
        
        const updateTimer = () => {
            if (minutes === 0 && seconds === 0) {
                remainingTimeElement.textContent = '期限切れ';
                remainingTimeElement.style.color = '#dc3545';
                verifyBtn.disabled = true;
                verifyBtn.textContent = '期限切れ';
                return;
            }
            
            if (seconds === 0) {
                minutes--;
                seconds = 59;
            } else {
                seconds--;
            }
            
            const timeString = `${minutes}分${seconds.toString().padStart(2, '0')}秒`;
            remainingTimeElement.textContent = timeString;
            
            // 残り時間が少なくなったら色を変更
            if (minutes < 2) {
                remainingTimeElement.style.color = '#dc3545';
            } else if (minutes < 5) {
                remainingTimeElement.style.color = '#ffc107';
            }
        };
        
        // 1秒ごとに更新
        setInterval(updateTimer, 1000);
    }
});