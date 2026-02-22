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

# 兼容GitHub Actions无notify模块的环境
class NotificationManager:
    def send_all(self, title, content):
        logger.info(f"[通知] {title}: {content}")


def retry_decorator(retries=3, min_delay=5, max_delay=10):
    """重试装饰器：失败后随机延迟重试"""
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
                        logger.warning(
                            f"函数 {func.__name__} 第 {attempt + 1}/{retries} 次尝试失败: {str(e)}"
                        )
                        sleep_s = random.uniform(min_delay, max_delay)
                        logger.info(f"将在 {sleep_s:.2f}s 后重试")
                        time.sleep(sleep_s)
            return None
        return wrapper
    return decorator


# 启动随机延迟（0-1小时），避免固定时间执行
logger.info("随机延迟0-3600秒后开始执行...")
time.sleep(random.randint(0, 3600))

# 清理环境变量，避免浏览器启动冲突
os.environ.pop("DISPLAY", None)
os.environ.pop("DYLD_LIBRARY_PATH", None)

# 读取环境变量配置
USERNAME = os.environ.get("LINUXDO_USERNAME") or os.environ.get("USERNAME")
PASSWORD = os.environ.get("LINUXDO_PASSWORD") or os.environ.get("PASSWORD")
BROWSE_ENABLED = os.environ.get("BROWSE_ENABLED", "true").strip().lower() not in [
    "false", "0", "off"
]

# 基础URL配置
HOME_URL = "https://linux.do/"
LOGIN_URL = "https://linux.do/login"
SESSION_URL = "https://linux.do/session"
CSRF_URL = "https://linux.do/session/csrf"

# 随机User-Agent列表
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
]


class LinuxDoBrowser:
    def __init__(self) -> None:
        """初始化浏览器（修复所有GitHub Actions兼容问题）"""
        from sys import platform

        if platform == "linux" or platform == "linux2":
            platformIdentifier = "X11; Linux x86_64"
        elif platform == "darwin":
            platformIdentifier = "Macintosh; Intel Mac OS X 10_15_7"
        elif platform == "win32":
            platformIdentifier = "Windows NT 10.0; Win64; x64"
        else:
            platformIdentifier = "X11; Linux x86_64"

        # 核心修复：DrissionPage正确配置（移除set_experimental_option）
        co = (
            ChromiumOptions()
            .headless(True)          # 无头模式
            .incognito(True)         # 无痕模式
            .set_argument("--no-sandbox")  # Linux环境必备
            .set_argument("--disable-blink-features=AutomationControlled")  # 隐藏自动化标识
            .set_argument("--disable-extensions")  # 禁用扩展
            .set_argument("--disable-dev-shm-usage")  # 解决内存不足
            .set_argument("--exclude-switches=enable-automation")  # 替代set_experimental_option
            .set_argument("--disable-automation")  # 禁用自动化扩展
            .set_argument("--disable-gpu")  # GitHub Actions必备
            .set_argument("--single-process")  # GitHub Actions必备
            .set_argument("--disable-setuid-sandbox")  # 额外兼容
        )
        
        # 随机选择User-Agent
        random_ua = random.choice(USER_AGENTS)
        co.set_user_agent(random_ua)
        
        # 关键：指定GitHub Actions中Chromium的绝对路径
        co.set_browser_path("/usr/bin/chromium-browser")
        
        # 初始化浏览器和会话
        self.browser = Chromium(co)
        self.page = self.browser.new_tab()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": random_ua,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )
        self.notifier = NotificationManager()

    def login(self):
        """登录Linux.do论坛"""
        logger.info("开始登录流程")
        
        # 1. 获取CSRF Token
        logger.info("获取CSRF Token...")
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
                logger.error(f"获取CSRF Token失败: {resp_csrf.status_code}")
                return False        
            csrf_data = resp_csrf.json()
            csrf_token = csrf_data.get("csrf")
            if not csrf_token:
                logger.error("未获取到有效CSRF Token")
                return False
            logger.info(f"CSRF Token获取成功: {csrf_token[:10]}...")
        except Exception as e:
            logger.error(f"获取CSRF Token异常: {str(e)}")
            return False

        # 2. 提交登录请求
        logger.info("提交登录信息...")
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
                logger.error(f"响应内容: {resp_login.text}")
                return False
        except Exception as e:
            logger.error(f"登录请求异常: {str(e)}")
            return False

        # 3. 打印连接信息
        self.print_connect_info()

        # 4. 同步Cookie到浏览器
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

        # 5. 验证登录状态
        logger.info("Cookie 设置完成，导航至 linux.do...")
        self.page.get(HOME_URL)
        time.sleep(random.uniform(3, 6))
        
        try:
            user_ele = self.page.ele("@id=current-user")
            if user_ele or "avatar" in self.page.html:
                logger.info("登录验证成功")
                return True
            logger.error("登录验证失败 (未找到用户标识)")
            return False
        except Exception as e:
            logger.warning(f"登录验证异常: {str(e)}")
            return "avatar" in self.page.html

    def click_topic(self):
        """随机浏览帖子"""
        try:
            topic_list = self.page.ele("@id=list-area").eles(".:title")
            if not topic_list:
                logger.error("未找到主题帖")
                return False
            
            browse_count = random.randint(8, 15)
            browse_count = min(browse_count, len(topic_list))
            logger.info(f"发现 {len(topic_list)} 个主题帖，随机选择{browse_count}个")
            
            for topic in random.sample(topic_list, browse_count):
                self.click_one_topic(topic.attr("href"))
            return True
        except Exception as e:
            logger.error(f"浏览帖子异常: {str(e)}")
            return False

    @retry_decorator()
    def click_one_topic(self, topic_url):
        """浏览单个帖子"""
        click_delay = random.uniform(0.5, 2)
        logger.info(f"模拟真人犹豫 {click_delay:.2f} 秒后点击帖子")
        time.sleep(click_delay)
        
        new_page = self.browser.new_tab()
        try:
            new_page.get(topic_url)
            
            # 随机点赞
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
        """模拟真人滚动浏览"""
        prev_url = None
        scroll_times = random.randint(3, 8)
        logger.info(f"当前帖子计划滚动 {scroll_times} 次")
        
        for _ in range(scroll_times):
            scroll_distance = random.choice([
                random.randint(200, 400),
                random.randint(500, 700),
                random.randint(800, 1000),
                0
            ])
            
            if scroll_distance > 0:
                logger.info(f"向下滚动 {scroll_distance} 像素...")
                page.run_js(f"window.scrollBy(0, {scroll_distance})")
            else:
                logger.info("模拟真人停留，本次不滚动")
            
            # 8%概率提前退出
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

            # 随机等待
            wait_time = random.choice([
                random.uniform(1, 3),
                random.uniform(3, 6),
                random.uniform(8, 12)
            ])
            logger.info(f"等待 {wait_time:.2f} 秒...")
            time.sleep(wait_time)

    def click_like(self, page):
        """模拟点赞"""
        try:
            like_button = page.ele(".discourse-reactions-reaction-button")
            if like_button:
                logger.info("找到未点赞的帖子，准备点赞")
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
        """打印用户连接信息"""
        logger.info("获取连接信息")
        try:
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": random.choice(USER_AGENTS),
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

            if info:
                logger.info("--------------Connect Info-----------------")
                logger.info(tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty"))
            else:
                logger.info("未获取到连接信息")
        except Exception as e:
            logger.error(f"获取连接信息失败: {str(e)}")

    def send_notifications(self, browse_enabled):
        """发送通知"""
        if browse_enabled:
            status_msg = f"✅每日登录成功: {USERNAME} + 浏览任务完成"
        else:
            status_msg = f"❌执行失败: {USERNAME} (登录失败或浏览任务未完成)"
        
        self.notifier.send_all("LINUX DO", status_msg)

    def run(self):
        """主执行流程"""
        try:
            login_res = self.login()
            if not login_res:
                logger.warning("登录验证失败")
                self.send_notifications(False)
                return

            if BROWSE_ENABLED:
                click_topic_res = self.click_topic()
                if not click_topic_res:
                    logger.error("点击主题失败，程序终止")
                    self.send_notifications(False)
                    return
                logger.info("完成浏览任务")

            self.send_notifications(BROWSE_ENABLED)
        except Exception as e:
            logger.error(f"程序执行异常: {str(e)}")
            self.send_notifications(False)
        finally:
            # 确保浏览器关闭
            try:
                self.page.close()
                self.browser.quit()
                logger.info("浏览器已正常关闭")
            except Exception as e:
                logger.warning(f"关闭浏览器异常: {str(e)}")


if __name__ == "__main__":
    # 检查账号密码配置
    if not USERNAME or not PASSWORD:
        logger.error("❌ 未配置账号密码！请设置 LINUXDO_USERNAME 和 LINUXDO_PASSWORD 环境变量")
        exit(1)
    
    # 启动主程序
    logger.info("========== Linux.Do 签到脚本启动 ==========")
    browser = LinuxDoBrowser()
    browser.run()
    logger.info("========== Linux.Do 签到脚本结束 ==========")
