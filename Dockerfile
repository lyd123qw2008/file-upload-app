FROM python:3.9-slim

WORKDIR /app

# 安装字体支持
RUN apt-get update && apt-get install -y \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# 先复制requirements.txt并安装依赖，这样可以利用Docker缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 将应用代码复制到容器中
COPY src/ .

EXPOSE 5000

# 设置默认环境变量
ENV FLASK_ENV=production
ENV FLASK_DEBUG=False
# 注意：不要在Dockerfile中硬编码凭据，应通过环境变量或密钥管理器提供
# ENV ADMIN_USERNAME=your_admin_username
# ENV ADMIN_PASSWORD=your_secure_password

# 使用Gunicorn作为生产服务器，优化适配单核CPU
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "--max-requests", "1000", "--max-requests-jitter", "50", "app:app"]