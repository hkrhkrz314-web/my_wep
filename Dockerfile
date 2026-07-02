#===================================================================
# Project: Wolf Host - Private Bot Hosting Dashboard
# Author: White Wolf
# Telegram: https://t.me/j49_c
# Year: 2026
# License: MIT
# Description: Optimized for Hugging Face Spaces & Cloudflare Proxy
#===================================================================

FROM python:3.11-slim-bookworm

LABEL maintainer="White Wolf <https://t.me/j49_c>"
LABEL description="Wolf Host - Private Bot Hosting Dashboard"
LABEL version="2.0.0"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    COMPOSER_ALLOW_SUPERUSER=1 \
    COMPOSER_HOME=/tmp/composer \
    ADMIN_USERNAME=wolf \
    ADMIN_PASSWORD=wolf123456

RUN apt-get update && apt-get install -y --no-install-recommends \
    php-cli \
    php-mbstring \
    php-xml \
    php-curl \
    php-zip \
    php-sqlite3 \
    php-intl \
    php-gd \
    php-bcmath \
    php-opcache \
    composer \
    git \
    curl \
    wget \
    unzip \
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

RUN php -v && composer --version && python --version

RUN groupadd -r wolfhost && useradd -r -g wolfhost -d /app -s /sbin/nologin wolfhost

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/bots /app/logs /app/data /app/tmp \
    && chmod +x entrypoint.sh \
    && chmod -R 770 /app/bots /app/logs /app/data /app/tmp \
    && chown -R wolfhost:wolfhost /app

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

USER wolfhost

ENTRYPOINT ["./entrypoint.sh"]
