"""
cron: 0 2-6 * * *  # 优化为每天2-6点随机执行一次，降低频率
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
from notify import NotificationManager


def retry_decorator(retries=3, min_delay=5, max_delay=10):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == retries - 1:  # 最后一次尝试
                        logger.error(f"函数 {func.__name__} 最终执行失败: {str(e)}")
                    logger.warning(
                        f"函数 {func.__name__} 第 {attempt + 1}/{retries} 次尝试失败: {str(e)}"
                    )
                    if attempt < retries - 1:
                        sleep_s = random.uniform(min_delay, max_delay)
                        logger.info(
                            f"将在 {sleep_s:.2f}s 后重试 ({min_delay}-{max_delay}s 随机延迟)"
                        )
                        time.sleep(sleep_s)
            return None

        return wrapper

    return decorator


# 启动时随机延迟0-1小时，避免固定时间执行
logger.info("随机延迟0-3600秒后开始执行...")
time.sleep(random.randint(0, 20))

os.environ.pop("DISPLAY", None)
os.environ.pop("DYLD_LIBRARY_PATH", None)

USERNAME = os.environ.get("LINUXDO_USERNAME")
PASSWORD = os.environ.get("LINUXDO_PASSWORD")
BROWSE_ENABLED = os.environ.get("BROWSE_ENABLED", "true").strip().lower() not in [
    "false",
    "0",
    "off",
]
if not USERNAME:
    USERNAME = os.environ.get("USERNAME")
if not PASSWORD:
    PASSWORD = os.environ.get("PASSWORD")

HOME_URL = "https://linux.do/"
LOGIN_URL = "https://linux.do/login"
SESSION_URL = "https://linux.do/session"
CSRF_URL = "https://linux.do/session/csrf"

# 新增：随机User-Agent列表，模拟不同浏览器/设备
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
]


class LinuxDoBrowser:
    def __init__(self) -> None:
        from sys import platform

        if platform == "linux" or platform == "linux2":
            platformIdentifier = "X11; Linux x86_64"
        elif platform == "darwin":
            platformIdentifier = "Macintosh; Intel Mac OS X 10_15_7"
        elif platform == "win32":
            platformIdentifier = "Windows NT 10.0; Win64; x64"
        else:
            platformIdentifier = "X11; Linux x86_64"

        # 优化：添加隐藏自动化特征的配置
        co = (
            ChromiumOptions()
            .headless(True)
            .incognito(True)
            .set_argument("--no-sandbox")
            .set_argument("--disable-blink-features=AutomationControlled")  # 隐藏自动化标识
            .set_argument("--disable-extensions")  # 禁用扩展
            .set_argument("--disable-dev-shm-usage")  # 解决内存不足问题
        )
        # 随机选择User-Agent
        random_ua = random.choice(USER_AGENTS)
        co.set_user_agent(random_ua)
        # 禁用自动化扩展
        co.set_experimental_option("excludeSwitches", ["enable-automation"])
        co.set_experimental_option("useAutomationExtension", False)
        
        self.browser = Chromium(co)
        self.page = self.browser.new_tab()
        self.session = requests.Session()
        # 优化：会话也使用随机User-Agent
        self.session.headers.update(
            {
                "User-Agent": random_ua,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )
        self.notifier = NotificationManager()

    def login(self):
        logger.info("开始登录")
        logger.info("获取 CSRF token...")
        headers = {
            "User-Agent": random.choice(USER_AGENTS),  # 随机UA
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LOGIN_URL,
        }
        resp_csrf = self.session.get(CSRF_URL, headers=headers, impersonate="firefox135")
        if resp_csrf.status_code != 200:
            logger.error(f"获取 CSRF token 失败: {resp_csrf.status_code}")
            return False        
        csrf_data = resp_csrf.json()
        csrf_token = csrf_data.get("csrf")
        logger.info(f"CSRF Token obtained: {csrf_token[:10]}...")

        logger.info("正在登录...")
        headers.update(
            {
                "X-CSRF-Token": csrf_token,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://linux.do",
            }
        )

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

            if resp_login.status_code == 200:
                response_json = resp_login.json()
                if response_json.get("error"):
                    logger.error(f"登录失败: {response_json.get('error')}")
                    return False
                logger.info("登录成功!")
            else:
                logger.error(f"登录失败，状态码: {resp_login.status_code}")
                logger.error(resp_login.text)
                return False
        except Exception as e:
            logger.error(f"登录请求异常: {e}")
            return False

        self.print_connect_info()

        logger.info("同步 Cookie 到 DrissionPage...")
        cookies_dict = self.session.cookies.get_dict()

        dp_cookies = []
        for name, value in cookies_dict.items():
            dp_cookies.append(
                {
                    "name": name,
                    "value": value,
                    "domain": ".linux.do",
                    "path": "/",
                }
            )

        self.page.set.cookies(dp_cookies)

        logger.info("Cookie 设置完成，导航至 linux.do...")
        self.page.get(HOME_URL)

        # 优化：登录后随机延迟，模拟真人等待页面加载
        time.sleep(random.uniform(3, 6))
        
        try:
            user_ele = self.page.ele("@id=current-user")
        except Exception as e:
            logger.warning(f"登录验证失败: {str(e)}")
            return True
        if not user_ele:
            if "avatar" in self.page.html:
                logger.info("登录验证成功 (通过 avatar)")
                return True
            logger.error("登录验证失败 (未找到 current-user)")
            return False
        else:
            logger.info("登录验证成功")
            return True

    def click_topic(self):
        topic_list = self.page.ele("@id=list-area").eles(".:title")
        if not topic_list:
            logger.error("未找到主题帖")
            return False
        
        # 优化：随机浏览8-15个帖子，避免固定数量
        browse_count = random.randint(8, 15)
        # 防止帖子数量不足导致报错
        browse_count = min(browse_count, len(topic_list))
        logger.info(f"发现 {len(topic_list)} 个主题帖，随机选择{browse_count}个")
        
        for topic in random.sample(topic_list, browse_count):
            self.click_one_topic(topic.attr("href"))
        return True

    @retry_decorator()
    def click_one_topic(self, topic_url):
        # 优化：模拟真人点击前的犹豫
        click_delay = random.uniform(0.5, 2)
        logger.info(f"模拟真人犹豫 {click_delay:.2f} 秒后点击帖子")
        time.sleep(click_delay)
        
        new_page = self.browser.new_tab()
        try:
            new_page.get(topic_url)
            
            # 优化：随机点赞概率（10%-25%）
            like_prob = random.uniform(0.1, 0.25)
            if random.random() < like_prob:
                self.click_like(new_page)
                
            self.browse_post(new_page)
        finally:
            try:
                new_page.close()
            except Exception:
                pass

    def browse_post(self, page):
        prev_url = None
        # 优化：每个帖子滚动次数随机（3-8次），而非固定10次
        scroll_times = random.randint(3, 8)
        logger.info(f"当前帖子计划滚动 {scroll_times} 次")
        
        for _ in range(scroll_times):
            # 优化：随机滚动距离，模拟真人不规律滚动
            scroll_distance = random.choice([
                random.randint(200, 400),  # 小幅滚动
                random.randint(500, 700),  # 中等滚动
                random.randint(800, 1000), # 大幅滚动
                0  # 偶尔不滚动（模拟停留）
            ])
            
            if scroll_distance > 0:
                logger.info(f"向下滚动 {scroll_distance} 像素...")
                page.run_js(f"window.scrollBy(0, {scroll_distance})")
            else:
                logger.info("模拟真人停留，本次不滚动")
            
            logger.info(f"已加载页面: {page.url}")

            # 优化：8%概率模拟分心退出
            if random.random() < 0.08:
                logger.success("模拟真人分心，退出当前帖子浏览")
                break

            at_bottom = page.run_js(
                "window.scrollY + window.innerHeight >= document.body.scrollHeight"
            )
            current_url = page.url
            if current_url != prev_url:
                prev_url = current_url
            elif at_bottom and prev_url == current_url:
                logger.success("已到达页面底部，退出浏览")
                break

            # 优化：随机等待时间，包含长短等待
            wait_time = random.choice([
                random.uniform(1, 3),   # 短等待
                random.uniform(3, 6),   # 中等等待
                random.uniform(8, 12)   # 偶尔长等待（模拟思考）
            ])
            logger.info(f"等待 {wait_time:.2f} 秒...")
            time.sleep(wait_time)

    def run(self):
        try:
            login_res = self.login()
            if not login_res:
                logger.warning("登录验证失败")

            if BROWSE_ENABLED:
                click_topic_res = self.click_topic()
                if not click_topic_res:
                    logger.error("点击主题失败，程序终止")
                    return
                logger.info("完成浏览任务")

            self.send_notifications(BROWSE_ENABLED)
        finally:
            try:
                self.page.close()
            except Exception:
                pass
            try:
                self.browser.quit()
            except Exception:
                pass

    def click_like(self, page):
        try:
            like_button = page.ele(".discourse-reactions-reaction-button")
            if like_button:
                logger.info("找到未点赞的帖子，准备点赞")
                # 优化：点赞前随机延迟，模拟真人操作
                like_delay = random.uniform(0.3, 1.2)
                time.sleep(like_delay)
                like_button.click()
                logger.info("点赞成功")
                time.sleep(random.uniform(1, 2))
            else:
                logger.info("帖子可能已经点过赞了")
        except Exception as e:
            logger.error(f"点赞失败: {str(e)}")

    def print_connect_info(self):
        logger.info("获取连接信息")
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "User-Agent": random.choice(USER_AGENTS),  # 随机UA
        }
        resp = self.session.get(
            "https://connect.linux.do/", headers=headers, impersonate="chrome136"
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table tr")
        info = []

        for row in rows:
            cells = row.select("td")
            if len(cells) >= 3:
                project = cells[0].text.strip()
                current = cells[1].text.strip() if cells[1].text.strip() else "0"
                requirement = cells[2].text.strip() if cells[2].text.strip() else "0"
                info.append([project, current, requirement])

        print("--------------Connect Info-----------------")
        print(tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty"))

    def send_notifications(self, browse_enabled):
        """发送签到通知"""
        status_msg = f"✅每日登录成功: {USERNAME}"
        if browse_enabled:
            status_msg += " + 浏览任务完成"
        
        self.notifier.send_all("LINUX DO", status_msg)


if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("Please set USERNAME and PASSWORD")
        exit(1)
    browser = LinuxDoBrowser()
    browser.run()
