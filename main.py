#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Linux.Do 自动签到脚本 - 测试版（仅延迟10秒）
作者：辅助调试
功能：自动登录Linux.do并完成签到/浏览任务
"""

import os
import random
import time
import functools
from loguru import logger
from DrissionPage import ChromiumOptions, Chromium
from tabulate import tabulate
from curl_cffi import requests
from bs4 import BeautifulSoup

# 兼容无notify模块的环境
class NotificationManager:
    def send_all(self, title, content):
        logger.info(f"[通知] {title}: {content}")

def retry_decorator(retries=3, min_delay=5, max_delay=10):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == retries - 1:
                        logger.error(f"函数 {func.__name__} 最终执行失败: {str(e)}")
                    else:
                        logger.warning(f"函数 {func.__name__} 第 {attempt + 1}/{retries} 次尝试失败: {str(e)}")
                        sleep_s = random.uniform(min_delay, max_delay)
                        logger.info(f"将在 {sleep_s:.2f}s 后重试")
                        time.sleep(sleep_s)
            return None
        return wrapper
    return decorator

# 测试版：仅延迟10秒（取消原0-3600秒延迟）
logger.info("测试模式：延迟10秒后开始执行...")
time.sleep(10)  # 固定延迟10秒，方便测试

# 清理环境变量
os.environ.pop("DISPLAY", None)
os.environ.pop("DYLD_LIBRARY_PATH", None)

# 读取配置
USERNAME = os.environ.get("LINUXDO_USERNAME") or os.environ.get("USERNAME")
PASSWORD = os.environ.get("LINUXDO_PASSWORD") or os.environ.get("PASSWORD")
BROWSE_ENABLED = os.environ.get("BROWSE_ENABLED", "true").strip().lower() not in ["false", "0", "off"]

# URL配置
HOME_URL = "https://linux.do/"
LOGIN_URL = "https://linux.do/login"
SESSION_URL = "https://linux.do/session"
CSRF_URL = "https://linux.do/session/csrf"

# 随机UA
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
]

class LinuxDoBrowser:
    def __init__(self) -> None:
        # 初始化浏览器配置（无任何错误方法！）
        co = (
            ChromiumOptions()
            .headless(True)
            .incognito(True)
            .set_argument("--no-sandbox")
            .set_argument("--disable-blink-features=AutomationControlled")
            .set_argument("--disable-extensions")
            .set_argument("--disable-dev-shm-usage")
            .set_argument("--exclude-switches=enable-automation")  # 替代错误的set_experimental_option
            .set_argument("--disable-automation")  # 替代错误的set_experimental_option
            .set_argument("--disable-gpu")
            .set_argument("--single-process")
        )
        # 随机UA
        random_ua = random.choice(USER_AGENTS)
        co.set_user_agent(random_ua)
        # 指定GitHub Actions中Chrome的实际路径（从日志中提取）
        co.set_browser_path("/opt/hostedtoolcache/setup-chrome/chromium/1588410/x64/chrome")
        
        self.browser = Chromium(co)
        self.page = self.browser.new_tab()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": random_ua,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self.notifier = NotificationManager()

    def login(self):
        logger.info("开始登录流程")
        # 获取CSRF Token
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LOGIN_URL,
        }
        try:
            resp_csrf = self.session.get(CSRF_URL, headers=headers, impersonate="firefox135")
            if resp_csrf.status_code != 200:
                logger.error(f"获取CSRF失败，状态码: {resp_csrf.status_code}")
                return False
            csrf_token = resp_csrf.json().get("csrf")
            if not csrf_token:
                logger.error("未获取到CSRF Token")
                return False
            logger.info(f"CSRF Token获取成功: {csrf_token[:10]}...")
        except Exception as e:
            logger.error(f"获取CSRF异常: {str(e)}")
            return False

        # 提交登录
        headers.update({
            "X-CSRF-Token": csrf_token,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://linux.do",
        })
        data = {
            "login": USERNAME,
            "password": PASSWORD,
            "second_factor_method": "1",
            "timezone": "Asia/Shanghai",
        }
        try:
            resp_login = self.session.post(
                SESSION_URL, data=data, impersonate="chrome136", headers=headers
            )
            if resp_login.status_code != 200:
                logger.error(f"登录失败，状态码: {resp_login.status_code}")
                return False
            login_result = resp_login.json()
            if login_result.get("error"):
                logger.error(f"登录失败: {login_result['error']}")
                return False
            logger.info("登录请求提交成功")
        except Exception as e:
            logger.error(f"登录请求异常: {str(e)}")
            return False

        # 同步Cookie到浏览器
        cookies_dict = self.session.cookies.get_dict()
        dp_cookies = [
            {"name": name, "value": value, "domain": ".linux.do", "path": "/"}
            for name, value in cookies_dict.items()
        ]
        self.page.set.cookies(dp_cookies)
        self.page.get(HOME_URL)
        time.sleep(3)
        
        # 验证登录
        try:
            user_ele = self.page.ele("@id=current-user")
            if user_ele or "avatar" in self.page.html:
                logger.info("登录验证成功")
                self.print_connect_info()
                return True
            else:
                logger.error("登录验证失败（未找到用户标识）")
                return False
        except Exception as e:
            logger.warning(f"登录验证异常: {str(e)}")
            return "avatar" in self.page.html

    def click_topic(self):
        try:
            topic_list = self.page.ele("@id=list-area").eles(".:title")
            if not topic_list:
                logger.error("未找到任何帖子")
                return False
            browse_count = min(random.randint(8, 15), len(topic_list))
            logger.info(f"随机浏览 {browse_count} 个帖子")
            for topic in random.sample(topic_list, browse_count):
                self.click_one_topic(topic.attr("href"))
            return True
        except Exception as e:
            logger.error(f"浏览帖子异常: {str(e)}")
            return False

    @retry_decorator()
    def click_one_topic(self, topic_url):
        time.sleep(random.uniform(0.5, 2))
        new_page = self.browser.new_tab()
        try:
            new_page.get(topic_url)
            # 随机点赞
            if random.random() < 0.2:
                self.click_like(new_page)
            # 模拟滚动浏览
            self.browse_post(new_page)
        finally:
            new_page.close()

    def browse_post(self, page):
        scroll_times = random.randint(3, 8)
        for _ in range(scroll_times):
            scroll_distance = random.choice([0, random.randint(200, 1000)])
            if scroll_distance > 0:
                page.run_js(f"window.scrollBy(0, {scroll_distance})")
            time.sleep(random.uniform(1, 12))
            if random.random() < 0.08:
                break

    def click_like(self, page):
        try:
            like_button = page.ele(".discourse-reactions-reaction-button")
            if like_button:
                time.sleep(random.uniform(0.3, 1.2))
                like_button.click()
                logger.info("点赞成功")
                time.sleep(random.uniform(1, 2))
        except Exception as e:
            logger.error(f"点赞失败: {str(e)}")

    def print_connect_info(self):
        try:
            resp = self.session.get("https://connect.linux.do/", impersonate="chrome136")
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table tr")
            info = []
            for row in rows:
                cells = row.select("td")
                if len(cells) >= 3:
                    info.append([cells[0].text.strip(), cells[1].text.strip() or "0", cells[2].text.strip() or "0"])
            if info:
                logger.info("-------------- 连接信息 --------------")
                logger.info(tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty"))
        except Exception as e:
            logger.error(f"获取连接信息失败: {str(e)}")

    def run(self):
        success = False
        try:
            if self.login():
                if BROWSE_ENABLED:
                    self.click_topic()
                success = True
                logger.info("任务执行完成")
            self.notifier.send_all("Linux.Do 签到", f"✅ 执行成功" if success else "❌ 执行失败")
        except Exception as e:
            logger.error(f"主流程异常: {str(e)}")
            self.notifier.send_all("Linux.Do 签到", f"❌ 执行异常: {str(e)}")
        finally:
            try:
                self.page.close()
                self.browser.quit()
                logger.info("浏览器已正常关闭")
            except Exception as e:
                logger.warning(f"关闭浏览器异常: {str(e)}")

if __name__ == "__main__":
    # 检查账号密码配置
    if not USERNAME or not PASSWORD:
        logger.error("❌ 未配置账号密码！请在Secrets中设置LINUXDO_USERNAME和LINUXDO_PASSWORD")
        exit(1)
    # 启动主程序
    logger.info("========== Linux.Do 签到脚本（测试版）启动 ==========")
    browser = LinuxDoBrowser()
    browser.run()
    logger.info("========== Linux.Do 签到脚本（测试版）结束 ==========")
