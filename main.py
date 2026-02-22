name: Linux.Do 自动签到

on:
  workflow_dispatch:
  schedule:
    - cron: '0 18-22 * * *'  # UTC 18-22点 = 北京时间 2-6点

concurrency:
  group: linuxdo-sign
  cancel-in-progress: true

jobs:
  sign-in:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v4

      - name: 设置 Python 环境
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: 安装系统依赖
        run: |
          sudo apt update
          sudo apt install -y chromium-browser chromium-codecs-ffmpeg libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2

      - name: 安装 Python 依赖
        run: |
          python -m pip install --upgrade pip
          pip install loguru drissionpage tabulate curl_cffi beautifulsoup4

      - name: 运行签到脚本
        env:
          LINUXDO_USERNAME: ${{ secrets.LINUXDO_USERNAME }}
          LINUXDO_PASSWORD: ${{ secrets.LINUXDO_PASSWORD }}
          BROWSE_ENABLED: "true"
          TZ: Asia/Shanghai
        run: |
          python linuxdo.py
