# 使用官方Python镜像，支持多平台架构
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.10.4-slim

# 设置维护者信息
LABEL maintainer="ddcat666@88.com"
LABEL description="AI Goofish - 智能闲鱼商品监控系统"
LABEL version="1.2.2"

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    # 基础工具
    curl \
    wget \
    git \
    # Playwright浏览器依赖
    libnss3 \
    libnspr4 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libxss1 \
    libasound2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    # 字体支持
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-noto-cjk \
    # 清理缓存
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements.txt并安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装Playwright浏览器
RUN playwright install chromium
RUN playwright install-deps chromium

# 创建必要的目录
RUN mkdir -p /app/data \
    /app/logs \
    /app/prompts \
    /app/static \
    /app/templates

# 复制项目文件（包括.env、*.db、prompts等）
COPY . .

# 确保重要文件和目录的权限正确
RUN if [ -f ".env" ]; then chmod 600 .env; fi
RUN if [ -f "*.db" ]; then chmod 644 *.db 2>/dev/null || true; fi
RUN if [ -d "prompts" ]; then chmod -R 755 prompts/; fi

# 调试：列出复制的文件
RUN ls -la /app/

# 确保关键文件存在
RUN test -f web_server.py || (echo "ERROR: web_server.py not found!" && exit 1)
RUN test -f spider_v2.py || (echo "ERROR: spider_v2.py not found!" && exit 1)

# 设置文件权限
RUN chmod +x *.py

# 创建非root用户（安全最佳实践）
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["python", "web_server.py"]
