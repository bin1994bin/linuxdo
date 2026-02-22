"""
cron: 0 2-6 * * *  # 每天2-6点随机执行一次
new Env("Linux.Do 签到")
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

# 启动随机延迟
logger.info("随机延迟0-3600秒后开始执行...")
time.sleep(random.randint(0, 3600))

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
        # 初始化浏览器配置（无任何错误方法）
        co = (
            ChromiumOptions()
            .headless(True)
            .incognito(True)
            .set_argument("--no-sandbox")
            .set_argument("--disable-blink-features=AutomationControlled")
            .set_argument("--disable-extensions")
            .set_argument("--disable-dev-shm-usage")
            .set_argument("--exclude-switches=enable-automation")  # 替代错误方法
            .set_argument("--disable-automation")  # 替代错误方法
            .set_argument("--disable-gpu")
            .set_argument("--single-process")
        )
        # 随机UA
        random_ua = random.choice(USER_AGENTS)
        co.set_user_agent(random_ua)
        # 指定GitHub的Chromium路径
        co.set_browser_path("/usr/bin/chromium-browser")
        
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
        logger.info("开始登录")
        # 获取CSRF
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LOGIN_URL,
        }
        resp_csrf = self.session.get(CSRF_URL, headers=headers, impersonate="firefox135")
        if resp_csrf.status_code != 200:
            logger.error(f"获取CSRF失败: {resp_csrf.status_code}")
            return False
        csrf_token = resp_csrf.json().get("csrf")
        if not csrf_token:
            logger.error("无CSRF Token")
            return False
        
        # 登录
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
        resp_login = self.session.post(SESSION_URL, data=data, impersonate="chrome136", headers=headers)
        if resp_login.status_code != 200 or resp_login.json().get("error"):
            logger.error(f"登录失败: {resp_login.text}")
            return False
        
        # 同步Cookie
        cookies_dict = self.session.cookies.get_dict()
        dp_cookies = [{"name": k, "value": v, "domain": ".linux.do", "path": "/"} for k, v in cookies_dict.items()]
        self.page.set.cookies(dp_cookies)
        self.page.get(HOME_URL)
        time.sleep(3)
        
        # 验证登录
        if "avatar" in self.page.html or self.page.ele("@id=current-user", timeout=5):
            logger.info("登录成功")
            self.print_connect_info()
            return True
        logger.error("登录验证失败")
        return False

    def click_topic(self):
        try:
            topic_list = self.page.ele("@id=list-area").eles(".:title")
            if not topic_list:
                logger.error("无帖子")
                return False
            browse_count = min(random.randint(8, 15), len(topic_list))
            for topic in random.sample(topic_list, browse_count):
                self.click_one_topic(topic.attr("href"))
            return True
        except Exception as e:
            logger.error(f"浏览失败: {e}")
            return False

    @retry_decorator()
    def click_one_topic(self, topic_url):
        time.sleep(random.uniform(0.5, 2))
        new_page = self.browser.new_tab()
        try:
            new_page.get(topic_url)
            # 随机点赞
            if random.random() < 0.2:
                like_btn = new_page.ele(".discourse-reactions-reaction-button", timeout=3)
                if like_btn:
                    time.sleep(random.uniform(0.3, 1.2))
                    like_btn.click()
                    logger.info("点赞成功")
            # 模拟滚动
            for _ in range(random.randint(3, 8)):
                scroll_dist = random.choice([0, random.randint(200, 1000)])
                if scroll_dist > 0:
                    new_page.run_js(f"window.scrollBy(0, {scroll_dist})")
                time.sleep(random.uniform(1, 12))
                if random.random() < 0.08:
                    break
        finally:
            new_page.close()

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
                logger.info(tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty"))
        except Exception as e:
            logger.error(f"获取连接信息失败: {e}")

    def run(self):
        try:
            if self.login():
                if BROWSE_ENABLED:
                    self.click_topic()
                self.notifier.send_all("Linux.Do", f"✅ 成功: {USERNAME}")
            else:
                self.notifier.send_all("Linux.Do", f"❌ 失败: {USERNAME}")
        except Exception as e:
            logger.error(f"主流程错误: {e}")
            self.notifier.send_all("Linux.Do", f"❌ 异常: {USERNAME}")
        finally:
            try:
                self.page.close()
                self.browser.quit()
            except:
                pass

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        logger.error("未配置账号密码！")
        exit(1)
    browser = LinuxDoBrowser()
    browser.run()
