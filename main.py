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
# 注意：notify 模块需自行确保存在（如青龙面板的通知模块）
try:
    from notify import NotificationManager
except ImportError:
    # 兼容无通知模块的环境
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
    "false",
    "0",
    "off",
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
        """初始化浏览器配置（DrissionPage兼容版）"""
        from sys import platform

        # 适配不同系统的UA标识
        if platform == "linux" or platform == "linux2":
            platformIdentifier = "X11; Linux x86_64"
        elif platform == "darwin":
            platformIdentifier = "Macintosh; Intel Mac OS X 10_15_7"
        elif platform == "win32":
            platformIdentifier = "Windows NT 10.0; Win64; x64"
        else:
            platformIdentifier = "X11; Linux x86_64"

        # 核心修复：DrissionPage 正确的浏览器参数配置
        co = (
            ChromiumOptions()
            .headless(True)          # 无头模式
            .incognito(True)         # 无痕模式
            .set_argument("--no-sandbox")  # 禁用沙箱（Linux必备）
            .set_argument("--disable-blink-features=AutomationControlled")  # 隐藏自动化标识
            .set_argument("--disable-extensions")  # 禁用扩展
            .set_argument("--disable-dev-shm-usage")  # 解决内存不足
            .set_argument("--exclude-switches=enable-automation")  # 替代set_experimental_option
            .set_argument("--disable-automation")  # 禁用自动化扩展
        )
        
        # 随机选择User-Agent
        random_ua = random.choice(USER_AGENTS)
        co.set_user_agent(random_ua)
        
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
            if resp_login.status_code != 200:
                logger.error(f"登录失败，状态码: {resp_login.status_code}")
                logger.error(f"响应内容: {resp_login.text}")
                return False
            
            login_result = resp_login.json()
            if login_result.get("error"):
                logger.error(f"登录失败: {login_result['error']}")
                return False
            logger.info("登录请求提交成功")
        except Exception as e:
            logger.error(f"登录请求异常: {str(e)}")
            return False

        # 3. 打印连接信息
        self.print_connect_info()

        # 4. 同步Cookie到浏览器并验证登录状态
        logger.info("同步Cookie到浏览器...")
        cookies_dict = self.session.cookies.get_dict()
        dp_cookies = [
            {
                "name": name,
                "value": value,
                "domain": ".linux.do",
                "path": "/",
            }
            for name, value in cookies_dict.items()
        ]
        self.page.set.cookies(dp_cookies)
        
        # 访问首页验证登录
        self.page.get(HOME_URL)
        time.sleep(random.uniform(3, 6))  # 模拟加载等待
        
        # 验证登录状态
        try:
            user_ele = self.page.ele("@id=current-user")
            if user_ele or "avatar" in self.page.html:
                logger.info("登录验证成功")
                return True
            else:
                logger.error("登录验证失败：未找到用户标识")
                return False
        except Exception as e:
            logger.warning(f"登录验证异常: {str(e)}，降级检测avatar...")
            return "avatar" in self.page.html

    def click_topic(self):
        """随机浏览帖子"""
        try:
            topic_list = self.page.ele("@id=list-area").eles(".:title")
            if not topic_list:
                logger.error("未找到任何帖子")
                return False
            
            # 随机选择8-15个帖子（避免数量不足）
            browse_count = random.randint(8, 15)
            browse_count = min(browse_count, len(topic_list))
            logger.info(f"共发现{len(topic_list)}个帖子，随机浏览{browse_count}个")
            
            # 随机选择帖子并浏览
            for topic in random.sample(topic_list, browse_count):
                self.click_one_topic(topic.attr("href"))
            return True
        except Exception as e:
            logger.error(f"浏览帖子异常: {str(e)}")
            return False

    @retry_decorator()
    def click_one_topic(self, topic_url):
        """浏览单个帖子（带重试）"""
        # 模拟真人犹豫
        click_delay = random.uniform(0.5, 2)
        logger.info(f"模拟犹豫 {click_delay:.2f} 秒后点击帖子: {topic_url}")
        time.sleep(click_delay)
        
        new_page = self.browser.new_tab()
        try:
            new_page.get(topic_url)
            
            # 随机点赞（10%-25%概率）
            like_prob = random.uniform(0.1, 0.25)
            if random.random() < like_prob:
                self.click_like(new_page)
            
            # 模拟浏览帖子
            self.browse_post(new_page)
        finally:
            try:
                new_page.close()
            except Exception:
                pass

    def browse_post(self, page):
        """模拟真人滚动浏览帖子"""
        prev_url = None
        scroll_times = random.randint(3, 8)  # 随机滚动次数
        logger.info(f"当前帖子计划滚动 {scroll_times} 次")
        
        for _ in range(scroll_times):
            # 随机滚动距离（模拟不规律浏览）
            scroll_distance = random.choice([
                random.randint(200, 400),
                random.randint(500, 700),
                random.randint(800, 1000),
                0  # 偶尔停留
            ])
            
            if scroll_distance > 0:
                logger.info(f"向下滚动 {scroll_distance} 像素")
                page.run_js(f"window.scrollBy(0, {scroll_distance})")
            else:
                logger.info("模拟真人停留，本次不滚动")
            
            # 8%概率模拟分心退出
            if random.random() < 0.08:
                logger.info("模拟真人分心，退出当前帖子浏览")
                break
            
            # 检查是否到底部
            at_bottom = page.run_js(
                "window.scrollY + window.innerHeight >= document.body.scrollHeight"
            )
            current_url = page.url
            if current_url != prev_url:
                prev_url = current_url
            elif at_bottom:
                logger.info("已到达页面底部，退出浏览")
                break
            
            # 随机等待（模拟阅读）
            wait_time = random.choice([
                random.uniform(1, 3),
                random.uniform(3, 6),
                random.uniform(8, 12)
            ])
            logger.info(f"等待 {wait_time:.2f} 秒（模拟阅读）")
            time.sleep(wait_time)

    def click_like(self, page):
        """模拟点赞"""
        try:
            like_button = page.ele(".discourse-reactions-reaction-button")
            if like_button:
                logger.info("找到点赞按钮，准备点赞")
                like_delay = random.uniform(0.3, 1.2)
                time.sleep(like_delay)
                like_button.click()
                logger.info("点赞成功")
                time.sleep(random.uniform(1, 2))
            else:
                logger.info("未找到可点赞的按钮（可能已点赞）")
        except Exception as e:
            logger.error(f"点赞失败: {str(e)}")

    def print_connect_info(self):
        """打印用户连接信息"""
        logger.info("获取用户连接信息...")
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
                    current = cells[1].text.strip() or "0"
                    requirement = cells[2].text.strip() or "0"
                    info.append([project, current, requirement])
            
            if info:
                logger.info("--------------用户连接信息--------------")
                logger.info(tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty"))
            else:
                logger.info("未获取到连接信息")
        except Exception as e:
            logger.error(f"获取连接信息失败: {str(e)}")

    def send_notifications(self, success):
        """发送执行结果通知"""
        title = "Linux.Do 签到任务"
        if success:
            content = f"✅ 执行成功\n用户名: {USERNAME}\n任务: 登录+浏览完成"
        else:
            content = f"❌ 执行失败\n用户名: {USERNAME}\n请检查账号密码或网络"
        
        try:
            self.notifier.send_all(title, content)
            logger.info("通知发送成功")
        except Exception as e:
            logger.warning(f"通知发送失败: {str(e)}")

    def run(self):
        """主执行流程"""
        success = False
        try:
            # 登录
            login_success = self.login()
            if not login_success:
                logger.error("登录失败，终止任务")
                self.send_notifications(False)
                return
            
            # 浏览帖子（可选）
            if BROWSE_ENABLED:
                browse_success = self.click_topic()
                if not browse_success:
                    logger.warning("浏览帖子失败，但登录已成功")
                    success = True  # 登录成功即算任务基本完成
                else:
                    success = True
                    logger.info("所有任务执行完成")
            else:
                success = True
                logger.info("仅执行登录任务，已完成")
            
            # 发送通知
            self.send_notifications(success)
        except Exception as e:
            logger.error(f"主流程异常: {str(e)}")
            self.send_notifications(False)
        finally:
            # 确保浏览器关闭
            try:
                self.page.close()
                self.browser.quit()
                logger.info("浏览器已关闭")
            except Exception as e:
                logger.warning(f"关闭浏览器异常: {str(e)}")


if __name__ == "__main__":
    # 检查必要配置
    if not USERNAME or not PASSWORD:
        logger.error("❌ 未配置账号密码！请设置 LINUXDO_USERNAME 和 LINUXDO_PASSWORD 环境变量")
        exit(1)
    
    # 启动任务
    logger.info("========== Linux.Do 签到任务启动 ==========")
    browser = LinuxDoBrowser()
    browser.run()
    logger.info("========== Linux.Do 签到任务结束 ==========")
