FROM python:3.12-slim

WORKDIR /app

# システムパッケージのインストール
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 非rootユーザーの作成（デフォルトUID/GID: 1000）
ARG HOST_UID=1000
ARG HOST_GID=1000
RUN groupadd -g ${HOST_GID} appuser && \
    useradd -u ${HOST_UID} -g ${HOST_GID} -d /app -s /bin/bash appuser

# アプリケーションのコピー
COPY . .

# 必要なディレクトリの作成と権限設定
RUN mkdir -p instance logs static/pdfs && \
    chown -R appuser:appuser /app

# 非rootユーザーに切り替え
USER appuser

# ポート5000を公開
EXPOSE 5000

# アプリケーションの起動
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]

