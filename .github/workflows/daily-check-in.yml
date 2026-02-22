name: Linux.Do 自动签到

on:
  workflow_dispatch:  # 手动触发
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
      - name: 检出代码
        uses: actions/checkout@v4

      - name: 设置 Chrome
        uses: browser-actions/setup-chrome@v1
        with:
          chrome-version: latest
          install-dependencies: true  # 自动安装依赖

      - name: 设置 Python 环境
        uses: actions/setup-python@v5
        with:
          python-version: '3.9.19'

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
          python main.py
