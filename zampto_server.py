import os
import sys
import signal
from DrissionPage import Chromium
from DrissionPage.common import Settings
from DrissionPage import ChromiumPage, ChromiumOptions
import asyncio
import logging
import random
import requests
from datetime import datetime
from time import sleep
from functools import wraps
import argparse
import socket
import json
import shutil
import string
import tempfile
import urllib.parse
import re
import time

def signal_handler(sig, frame):
    print("\n捕捉到 Ctrl+C，正在退出...")
    # 这里可以添加清理逻辑，比如关闭文件、保存状态等
    exit(1)
signal.signal(signal.SIGINT, signal_handler)
#解析url中的id
from urllib.parse import urlparse, parse_qs
def get_id_from_url(url):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    return query_params.get('id', [None])[0]
#解析参数
parser = argparse.ArgumentParser(description="-k 在脚本运行结束后不结束浏览器")
parser.add_argument('-k', '--keep', action='store_true', help='启用保留模式')
parser.add_argument('-d', '--debug', action='store_true', help='启用调试模式')
parser.add_argument('-r', '--retry', type=int, default=0, help='重试次数（整数）')
iargs = parser.parse_args()
# 定义浏览器可执行候选路径
chrome_candidates = [
    "/usr/bin/chromium",
    "/usr/lib/chromium/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
    "/app/bin/chromium",
    "/opt/chromium/chrome",
    "/usr/local/bin/chromium",
    "/run/host/usr/bin/chromium",
    "/run/host/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/opt/google/chrome/chrome",
    "/run/host/usr/bin/microsoft-edge-stable"
]

USER_AGENTS = [
    # Windows Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    # macOS Chrome
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    # Windows Edge (Chromium)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
    # macOS Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    # iPhone Safari (iOS 17)
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    # Android Chrome (Pixel 7 Pro)
    "Mozilla/5.0 (Linux; Android 13; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36",
    # Android Chrome (generic)
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36",
    # Windows Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    # macOS Firefox
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
    # Linux Chrome
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
]

chromepath = next((path for path in chrome_candidates if os.path.exists(path)), None)
# 配置标准 logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
std_logger = logging.getLogger(__name__)

# 设置语言
Settings.set_language('en')
# 浏览器参数
options: ChromiumOptions
page: ChromiumPage
browser: Chromium

binpath = os.environ.get('CHROME_PATH', chromepath)
# 登录信息
username = os.getenv("USERNAME")
password = os.getenv("PASSWORD")

# 通知
info = ""
# tg通知
tgbot_token = os.getenv("TG_TOKEN", "")
user_id = os.getenv("TG_USERID", "")
# chrome的代理
chrome_proxy=os.getenv("CHROME_PROXY")
# 用来判断登录是否成功
login_deny=False
# 全局常量
signurl="https://auth.zampto.net/sign-in"
signurl_end="auth.zampto.net/sign-in"
homeurl="https://dash.zampto.net/homepage"
homeurlend="/homepage"
overviewurl="https://dash.zampto.net/overview"
overviewurl_end="/overview"
if chromepath:
    std_logger.info(f"✅ 使用浏览器路径：{chromepath}")
else:
    error_exit("❌ 未找到可用的浏览器路径")
print(username)
if not username or not password:
    std_logger.warning("💡 请使用 Docker 的 -e 参数传入，例如：")
    std_logger.warning("docker run -itd -e USERNAME=your_username -e PASSWORD=your_password mingli2038/zam_ser:alpine")
    error_exit("❌ 缺少必要的环境变量 USERNAME 或 PASSWORD。")


if not tgbot_token:
    std_logger.warning("⚠️ 环境变量 TG_TOKEN 未设置，Telegram 通知功能将无法使用。")
    std_logger.warning("💡 请使用 Docker 的 -e TG_TOKEN=your_bot_token 传入。")

if not user_id:
    std_logger.warning("⚠️ 环境变量 TG_USERID 未设置，Telegram 通知功能将无法使用。")
    std_logger.warning("💡 请使用 Docker 的 -e TG_USERID=your_user_id 传入。")

def get_random_user_agent():
    """随机返回一个 User-Agent 字符串"""
    return random.choice(USER_AGENTS)

def is_proxy_available(proxy_url: str, test_url: str = "http://www.google.com/generate_204", timeout: int = 5) -> bool:
    """
    使用 requests 检查代理是否可用
    proxy_url: 例如 "socks5://127.0.0.1:1080"
    test_url: 用来测试的目标网站 (默认使用 Google 的 204 检测地址)
    timeout: 超时时间（秒）
    """
    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }
    try:
        resp = requests.get(test_url, proxies=proxies, timeout=timeout)
        if resp.status_code == 204:
            std_logger.info(f"✅ 代理可用: {proxy_url}\n")
            return True
        else:
            std_logger.error(f"❌ 代理返回非预期状态码: {resp.status_code}\n")
            return False
    except Exception as e:
        std_logger.error(f"❌ 代理不可用: {e}\n")
        return False

def check_google():
    try:
        response = requests.get("https://www.google.com", timeout=5)
        if response.status_code == 200:
            return True
        else:
            print(f"⚠️ 无法访问 Google，tg通知将不起作用，状态码：{response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ ⚠️ 无法访问 Google，tg通知将不起作用：{e}")
        return False
def exit_process(num=0):
    global iargs,info,tgbot_token
    if info and info.strip():
        info = f"ℹ️ Zampto服务器续期通知\n用户：{username}\n{info}"
        if check_google() and tgbot_token and user_id :
            tg_notifacation(info)
    if iargs.keep:
        if 'page' in globals():
            if page.url.startswith("https://dash.zampto.net/server?id="):
                page.get(overviewurl)
                print("✅ 跳回overview页面。")
        print("✅ 启用了 -k 参数，保留浏览器模式")
    else:
        std_logger.info("✅ 浏览器已关闭，避免进程驻留")
        safe_close_broser()
    exit(num)  
def safe_close_broser():
    if 'browser' in globals() and browser:
        try:
            browser.quit()
            print("✅ 浏览器已安全关闭")
        except Exception as e:
            print(f"⚠️ 关闭浏览器时出错：{e}")
    else:
        print("⚠️ 浏览器对象不存在或未初始化，跳过关闭")
def error_exit(msg):
    global std_logger,info,iargs
    std_logger.debug(f"[ERROR] {msg}")
    info+=f"[ERROR] {msg}\n"
    exit(1)

async def get_latest_tab_safe():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: browser.latest_tab)
def require_browser_alive(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        global browser,iargs
        if browser.tabs_count == 0:
            error_exit("⚠️ 页面已崩溃或未附加，请重试运行一次脚本/镜像")
        try:
            page = await asyncio.wait_for(get_latest_tab_safe(), timeout=5)
        except asyncio.TimeoutError:
            if iargs.keep and iargs.debug:
                pass
            else:
                save_close_broser()
            error_exit("⚠️ 获取 latest_tab 超时，页面可能已崩溃")
        
        return await func(*args, **kwargs)
    return wrapper
def capture_screenshot( file_name=None,save_dir='screenshots'):
    global page
    import os
    os.makedirs(save_dir, exist_ok=True)
    if not file_name:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_name = f'screenshot_{timestamp}.png'
    full_path = os.path.join(save_dir, file_name)
    try:
        page.get_screenshot(path=save_dir, name=file_name, full_page=True)
        print(f"📸 截图已保存：{full_path}")
    except Exception as e:
        print("⚠️ 截图失败，未能成功保存。")

def tg_notifacation(meg):
    url = f"https://api.telegram.org/bot{tgbot_token}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": meg
    }
    response = requests.post(url, data=payload)
    print(response.json())


def setup(user_agent: str, user_data_path: str = None):
    """
    初始化浏览器
    
    ⚠️ 重要改动：
    1. 移除了 --guest 参数（会阻止扩展加载）
    2. 添加了扩展加载相关参数
    3. 不使用 incognito 模式（扩展在隐身模式下不工作）
    """
    global options
    global page, browser
    
    options = (
        ChromiumOptions()
        .set_user_agent(user_agent)
        .set_argument('--no-sandbox')
        .set_argument('--disable-gpu')
        .set_argument('--disable-dev-shm-usage')
        .set_argument('--window-size=1280,800')
        .set_argument('--remote-debugging-port=9222')
        .set_browser_path(binpath)
    )
    
    # ⚠️ 重要：不要添加 --guest 参数（代理认证模式下）
    
    # 无头模式配置
    if 'DISPLAY' not in os.environ:
        options.headless(True)
        options.set_argument('--headless=new')
        std_logger.info("✅ 浏览器使用无头模式")
    else:
        options.headless(False)
        std_logger.info("✅ 浏览器使用正常模式")
    
    # 配置代理
    plugin_path = setup_proxy()
    
    # 如果有代理认证插件，加载它
    if plugin_path:
        std_logger.info(f"正在加载扩展: {plugin_path}")
        
        # 确保扩展文件存在
        manifest_file = os.path.join(plugin_path, "manifest.json")
        background_file = os.path.join(plugin_path, "background.js")
        
        if not os.path.exists(manifest_file) or not os.path.exists(background_file):
            std_logger.error(f"❌ 扩展文件不完整")
            return
        
        # ⚠️ 关键修复：使用正确的方式加载扩展
        options.add_extension(path=plugin_path)
        options.set_argument(f'--load-extension={plugin_path}')
        options.set_argument(f'--disable-extensions-except={plugin_path}')
        options.set_argument('--allow-file-access-from-files')
        
        std_logger.info("✅ 代理认证扩展已配置")
        
        # 代理认证模式下，必须启动新浏览器
        std_logger.info("⚠️ 代理认证模式：启动全新浏览器实例（不接管已有浏览器）")
        
        if user_data_path:
            std_logger.warning("⚠️ 代理认证模式下不建议使用 user_data_path")
        
        # 直接启动新浏览器
        std_logger.info("正在启动浏览器...")
        browser = Chromium(options)
        std_logger.info("✅ 浏览器启动成功")
        
    else:
        # 无代理认证，可以正常使用
        if user_data_path:
            options.set_user_data_path(user_data_path)
        
        options.set_argument('--guest')
        
        # 尝试接管已有浏览器
        browser = attach_browser()
        if browser is None or not browser.states.is_alive:
            std_logger.info("正在启动新浏览器实例...")
            browser = Chromium(options)
            std_logger.info("✅ 浏览器启动成功")
    
    # 获取当前激活的标签页
    page = browser.latest_tab
    
    # 查看扩展是否创建成功
    plugin_path = os.path.join('/tmp', 'drission_proxy_auth')
    print(f"扩展目录: {plugin_path}")
    print(f"manifest.json 存在: {os.path.exists(os.path.join(plugin_path, 'manifest.json'))}")
    print(f"background.js 存在: {os.path.exists(os.path.join(plugin_path, 'background.js'))}")
    # 验证提示
    if chrome_proxy:
        verify_proxy_simple(page)
    exit(1)

def verify_proxy_simple(page):
    """
    简单快速的代理验证函数
    """
    print("\n" + "=" * 70)
    print("🔍 验证代理IP")
    print("=" * 70)
    
    try:
        print("\n正在访问 ifconfig.me ...")
        page.get('https://ifconfig.me', timeout=20)
        
        # 等待页面加载
        time.sleep(5)
        
        # 获取页面内容
        print(f"页面URL: {page.url}")
        print(f"页面HTML长度: {len(page.html)}")
        
        # 尝试获取IP
        body_elem = page.ele('tag:body')
        if body_elem and body_elem.text:
            ip = body_elem.text.strip()
            print(f"\n✅✅✅ 当前IP: {ip}")
            
            # 验证是否是代理IP
            if ip == "103.137.185.66":
                print(f"✅✅✅ 代理已生效！（越南代理IP）")
            else:
                print(f"⚠️ 这个IP不是预期的代理IP (103.137.185.66)")
            
            return ip
        else:
            print(f"\n❌ 无法获取IP")
            print(f"完整HTML: {page.html[:500]}")
            
            # 尝试其他方式
            print("\n尝试访问 api.ipify.org ...")
            page.get('https://api.ipify.org', timeout=20)
            time.sleep(3)
            body_elem = page.ele('tag:body')
            if body_elem and body_elem.text:
                ip = body_elem.text.strip()
                print(f"✅ 当前IP: {ip}")
                return ip
            
    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
    
    print("=" * 70)

@require_browser_alive
async def test():
    pass
    
def is_port_open(host='127.0.0.1', port=9222, timeout=1):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

def attach_browser(port=9222):
    try:
        if is_port_open():
            browser = Chromium(port)
            if browser.states.is_alive:
                std_logger.info(f"✅ 成功接管浏览器（端口 {port}）")
                return browser
            print("❌ 接管失败，浏览器未响应")
        else:
            print(f"⚠️ 端口 {port} 未开放，跳过接管")
        return None
    except Exception as e:
        print(f"⚠️ 接管浏览器时出错：{e}")
        return None
        
def mask_sensitive_info(text):
    """脱敏处理敏感信息"""
    if not text:
        return "***"
    masked = re.sub(r'://[^:]+:[^@]+@', '://***:***@', text)
    return masked

def parse_proxy_url(proxy_url):
    """
    解析代理URL
    格式: http://username:password@host:port
    返回: (scheme, username, password, host, port)
    """
    try:
        pattern = r'^(https?|socks5)://([^:]+):([^@]+)@([^:]+):(\d+)$'
        match = re.match(pattern, proxy_url)
        
        if match:
            scheme = match.group(1)
            username = match.group(2)
            password = match.group(3)
            host = match.group(4)
            port = int(match.group(5))
            
            std_logger.debug(f"代理解析成功 - 协议:{scheme}, 主机:{host}, 端口:{port}")
            return scheme, username, password, host, port
        
        # 尝试解析无认证的代理
        pattern_no_auth = r'^(https?|socks5)://([^:]+):(\d+)$'
        match_no_auth = re.match(pattern_no_auth, proxy_url)
        
        if match_no_auth:
            scheme = match_no_auth.group(1)
            host = match_no_auth.group(2)
            port = int(match_no_auth.group(3))
            std_logger.debug(f"无认证代理解析成功 - 协议:{scheme}, 主机:{host}, 端口:{port}")
            return scheme, None, None, host, port
        
        std_logger.error("❌ 代理URL格式不正确")
        return None, None, None, None, None
        
    except Exception as e:
        std_logger.error(f"❌ 代理URL解析失败: {e}")
        return None, None, None, None, None

def create_proxy_auth_extension(proxy_username, proxy_password, plugin_path=None):
    """
    创建Chrome代理认证扩展插件
    
    ⚠️ 关键：此扩展只处理认证，代理地址通过命令行参数设置
    """
    if plugin_path is None:
        plugin_path = os.path.join(tempfile.gettempdir(), 'drission_proxy_auth')
    
    # 确保目录存在且为空
    if os.path.exists(plugin_path):
        import shutil
        shutil.rmtree(plugin_path)
    os.makedirs(plugin_path, exist_ok=True)
    
    # Manifest V2 配置
    manifest_json = """{
    "manifest_version": 2,
    "name": "Proxy Authentication Helper",
    "version": "1.0.0",
    "description": "Auto-fill proxy authentication credentials",
    "permissions": [
        "webRequest",
        "webRequestBlocking",
        "<all_urls>"
    ],
    "background": {
        "scripts": ["background.js"],
        "persistent": true
    },
    "minimum_chrome_version": "22.0.0"
}"""
    
    # JavaScript字符串转义
    escaped_password = proxy_password.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'").replace('\n', '\\n')
    escaped_username = proxy_username.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'").replace('\n', '\\n')
    
    # background.js - 处理代理认证
    background_js = f"""
console.log('=================================================');
console.log('🔌 Proxy Authentication Extension Loading...');
console.log('=================================================');

var authAttempts = 0;
var MAX_AUTH_ATTEMPTS = 3;

// 监听代理认证请求
chrome.webRequest.onAuthRequired.addListener(
    function(details, callback) {{
        authAttempts++;
        
        console.log('🔐 Proxy Authentication Required');
        console.log('  - URL: ' + details.url);
        console.log('  - Attempt: ' + authAttempts + '/' + MAX_AUTH_ATTEMPTS);
        
        if (authAttempts > MAX_AUTH_ATTEMPTS) {{
            console.error('❌ Max authentication attempts reached!');
            callback({{cancel: true}});
            return {{cancel: true}};
        }}
        
        var credentials = {{
            username: "{escaped_username}",
            password: "{escaped_password}"
        }};
        
        console.log('✅ Providing credentials...');
        
        callback({{authCredentials: credentials}});
        return {{authCredentials: credentials}};
    }},
    {{urls: ["<all_urls>"]}},
    ['blocking']
);

// 监听请求完成
chrome.webRequest.onCompleted.addListener(
    function(details) {{
        if (details.statusCode === 200) {{
            console.log('✅ Request successful: ' + details.url);
        }}
    }},
    {{urls: ["<all_urls>"]}}
);

// 监听请求错误
chrome.webRequest.onErrorOccurred.addListener(
    function(details) {{
        console.error('❌ Request failed: ' + details.url);
        console.error('  - Error: ' + details.error);
    }},
    {{urls: ["<all_urls>"]}}
);

console.log('✅ Proxy Authentication Extension Loaded Successfully');
console.log('=================================================');
"""
    
    # 写入文件
    with open(os.path.join(plugin_path, "manifest.json"), "w", encoding='utf-8') as f:
        f.write(manifest_json)
    
    with open(os.path.join(plugin_path, "background.js"), "w", encoding='utf-8') as f:
        f.write(background_js)
    
    # 创建一个简单的图标
    import base64
    icon_data = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
    with open(os.path.join(plugin_path, "icon.png"), "wb") as f:
        f.write(icon_data)
    
    std_logger.info(f"✅ 代理认证插件创建成功: {plugin_path}")
    return plugin_path


def setup_proxy():
    """
    配置代理设置
    
    ⚠️ 关键修复：
    1. 通过命令行参数设置代理服务器
    2. 通过扩展处理认证
    3. 添加必要的Chrome启动参数
    """
    global options
    
    if not chrome_proxy:
        std_logger.info("未检测到代理配置，直接启动浏览器")
        return None
    
    masked_proxy = mask_sensitive_info(chrome_proxy)
    
    # 检查代理可用性
    pava = is_proxy_available(chrome_proxy)
    if not pava:
        std_logger.error(f"❌ 代理不可用: {masked_proxy}")
        error_exit("❌ 指定代理不可用，为了保证账号安全退出不进入下一步操作。")
    
    std_logger.info(f"✅ 代理连接测试通过: {masked_proxy}")
    
    # 解析代理URL
    scheme, username, password, host, port = parse_proxy_url(chrome_proxy)
    
    if not host or not port:
        std_logger.error("❌ 代理URL格式错误")
        return None
    
    # ⚠️ 关键：设置代理服务器（命令行参数）
    proxy_server = f"{scheme}://{host}:{port}"
    
    # 设置代理相关参数
    options.set_argument(f'--proxy-server={proxy_server}')
    options.set_argument('--proxy-bypass-list=localhost;127.0.0.1')
    options.set_argument('--ignore-certificate-errors')
    options.set_argument('--ignore-ssl-errors')
    
    std_logger.info(f"✅ 代理服务器已设置: {host}:{port}")
    
    # 如果有认证信息，创建认证扩展
    if username and password:
        std_logger.info("✅ 检测到代理认证信息，创建认证扩展")
        plugin_path = create_proxy_auth_extension(
            proxy_username=username,
            proxy_password=password
        )
        return plugin_path
    else:
        std_logger.info("✅ 无需认证")
        return None

        
async def is_page_crashed(browser):
    async def check_title():
        page = browser.latest_tab
        title = page.title
        return 'Aw, Snap!' in title or '糟糕' in title
    try:
        crashed = await asyncio.wait_for(check_title(), timeout=5)
        return crashed
    except (TimeoutError, asyncio.TimeoutError):
        return True
    except Exception as e:
        print(f'其他错误: {e}')
        return False    

async def dev_setup():
    global options
    global page,browser
    user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    # user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    # user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
    # user_agent = "Mozilla/5.0 (Linux; Android 13; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36"
    # user_agent = "Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Mobile Safari/537.36"


    options = (
        ChromiumOptions()
        .incognito(True)
        .set_user_agent(user_agent)
        .set_argument('--guest')
        .set_argument('--no-sandbox')
        .set_argument('--disable-gpu')
        .set_argument('--window-size=1280,720')
        .set_argument('--remote-debugging-port=9222')
        .set_browser_path(binpath)
    )
    
    if 'DISPLAY' not in os.environ:
        options.headless(True)
        options.set_argument('--headless=new') 
        std_logger.info("✅ DISPLAY环境变量为空，浏览器使用无头模式")
    else:
        options.headless(False)
        std_logger.info("✅ DISPLAY环境变量存在，浏览器使用正常模式")
    setup_proxy()
    browser = attach_browser()
    # print( browser.timeouts.base)
    # print( browser.timeouts.page_load)
    # print( browser.timeouts.script)
    # browser.set.timeouts(base=5,page_load=5,script=5)


    if browser is None or not browser.states.is_alive:
        # 接管失败，启动新浏览器
        browser = Chromium(options)
    # await test()
    page = browser.latest_tab
    # exit_code=await continue_execution()
    #1 await open_web()
    #2 login()
    #3 await open_overview()
    # check_renew_result(page)
    # print(browser.tab_ids)
    # browser.quit()
    # print(f"browser{browser}")
    # print(f"browser{browser.tabs_count}")
    # try:
    #     print("成功获取页面对象")
    # except asyncio.TimeoutError:
    #     print("获取 latest_tab 超时，可能页面崩溃")
    #     browser.new_tab('about:blank')
        # browser.refresh()  # 或 
        
    

def inputauth(inpage):
    u = inpage.ele('x://*[@autocomplete="username email"]', timeout=30)
    print(u.set.value)
    if u.set.value:   # 如果不为空
        u.clear(by_js=True)
    u.input(username)
    b= inpage.ele('x://button[normalize-space(.)="Sign in"]',timeout=30)
    b.click(by_js=False)
    p = inpage.ele('x://*[@type="password"]', timeout=30)
    p.input(password)


def clickloginin(inpage):
    c = inpage.ele('x://button[normalize-space(.)="Continue"]',timeout=30)
    xof = random.randint(1, 20)
    yof = random.randint(1, 10)
    c.offset(x=xof, y=yof).click(by_js=False)
    skip = inpage.ele('x://div[@role="button" and normalize-space(.)="Skip"]',timeout=30)
    if skip:
        skip.click(by_js=False)


def check_element(desc, element, exit_on_fail=True):
    global std_logger
    if element:
        std_logger.debug(f'✓ {desc}: {element}')
        return True
    else:
        std_logger.debug(f'✗ {desc}: 获取失败')
        if exit_on_fail:
            std_logger.error('✗ cloudflare认证失败，退出')
            error_exit('✗ cloudflare认证失败，退出')
        return False

async def wait_for(a, b=None):
    global std_logger
    if b is None:
        b = a
    wait_time = random.uniform(a, b)
    std_logger.debug(f"即将等待 {wait_time:.2f} 秒（范围：{a} 到 {b}）...")
    await asyncio.sleep(wait_time)
    std_logger.debug(f"等待结束：{wait_time:.2f} 秒")
    

def click_if_cookie_option(tab):
    deny = tab.ele("x://button[@class='fc-button fc-cta-do-not-consent fc-secondary-button']", timeout=15)
    if deny:
        deny.click()
        print('发现出现cookie使用协议，跳过')

def renew_server(tab):
    renewbutton = tab.ele("x://a[contains(@onclick, 'handleServerRenewal')]", timeout=15)
    if renewbutton:
        print(f"找到{renewbutton}")
        renewbutton.click(by_js=False)
    else:
        print("没找到renew按钮，无事发生")

def check_renew_result(tab):
    global info
    nextRenewalTime = tab.ele("x://span[@id='nextRenewalTime']", timeout=15)
    server_name_span=tab.ele("x://span[contains(@class,'server-name')]", timeout=15)
    if not nextRenewalTime:
        print("❌ [严重错误] 无法检查服务器存活时间状态，已终止程序执行！")
        error_exit(f'❌ [严重错误] 无法检查服务器存活时间状态，已终止程序执行！\n')
    server_name = server_name_span.inner_html
    if server_name:
        info += f'✅ 服务器 [{server_name}] 续期成功\n'
        print(f'✅ 服务器 [{server_name}] 续期成功')
        sleep(5)
        report_left_time(server_name)
    else:
        print(f'❌ [服务器: {server_name}] 续期失败')
        report_left_time(server_name)
        error_exit(f'❌ [服务器: {server_name}] 续期失败\n')

def report_left_time(server_name):
    global info
    left_time = page.ele('x://*[@id="nextRenewalTime"]', timeout=15)
    if left_time:
        info += f'🕒 [服务器: {server_name}] 存活期限：{left_time.inner_html}\n'
        print(f'🕒 [服务器: {server_name}] 存活期限：{left_time.inner_html}')

@require_browser_alive
async def open_server_tab():
    global std_logger
    manage_server = page.eles("x://a[contains(@href, 'server?id')]", timeout=15)
    std_logger.info(manage_server)
    std_logger.debug(f"url_now:{page.url}")
    server_list = []
    for a in manage_server:
        server_list.append(a.attr('href'))
    if not server_list:
        capture_screenshot(f"serverlist_overview.png")
        server_list.append('https://dash.zampto.net/server?id=1715')
        server_list.append('https://dash.zampto.net/server?id=1716')
        print("⚠️ server_list 为空，继续使用默认配置续期")
        # error_exit("⚠️ server_list 为空，跳过服务器续期流程")
    std_logger.info(f"待续期服务器：{server_list}")
    for s in server_list:
        page.get(s)
        await asyncio.sleep(5)
        renew_server(page)
        check_renew_result(page)
        ser_id=get_id_from_url(s)
        capture_screenshot(f"{ser_id}.png")

@require_browser_alive
async def open_overview():
    global std_logger
    if page.url.startswith(homeurl):
        overview = page.ele('x://a[normalize-space(span)="Servers Overview"]')
        if overview:
            std_logger.info(f"找到overview入口点击{overview}")
            overview.click(by_js=False)
    else:
        std_logger.error("没有在帐户主页找到overview入口，回退到直接访问")
        page.get(overviewurl)
    await wait_for(7,10)

@require_browser_alive
async def login():
    global info,login_deny
    if login_deny and page.url.endswith(signurl_end):
        page.get(signurl)
        login_deny=False
        await wait_for(1)
    inputauth(page)
    clickloginin(page)
    await wait_for(10,15)
    if signurl_end in page.url:
        msg = f"⚠️ {username}登录失败，请检查认证信息是否正确。"
        login_deny=True
        error_exit(msg)
    else:
        std_logger.info(f"{username}登录成功")
@require_browser_alive
async def open_web():
    if not page.url.startswith(signurl):
        page.get(signurl)
        await wait_for(10,15)
steps = [
    {"match": "/newtab/", "action": open_web, "name": "open_web"},
    {"match": signurl_end, "action": login, "name": "account"},
    {"match": homeurlend, "action": open_overview, "name": "open_overview"},
    {"match": overviewurl_end, "action": open_server_tab, "name": "open_server_tab"},
]

async def continue_execution(current_url: str = ""):
    global page, std_logger
    url = current_url or (page.url if page else "")
    std_logger.debug(f"当前页面 URL: {url}")
    if not url:
        std_logger.warning("URL为空，无法确定当前步骤")
        return
    # 找到当前步骤
    start_index = 0
    current_step_name = "unknown"
    
    for i, step in enumerate(steps):
        if step["match"] in url:
            start_index = i 
            current_step_name = step.get("name", f"step_{i}")
            std_logger.info(f"检测到当前步骤: {current_step_name}")
            break
    else:
        std_logger.warning(f"未找到匹配的步骤，URL: {url}")
        error_exit("没有匹配的步骤，退出")
    std_logger.info(f"从步骤 {start_index} 开始执行")

    # 从下一步继续执行
    for i, step in enumerate(steps[start_index:], start=start_index):
        step_name = step.get("name", f"step_{i}")
        std_logger.info(f"执行步骤 {i}: {step_name}")
        action = step["action"]
        try:
            # 执行操作
            result = action()
            if asyncio.iscoroutine(result):
                await result
            
            std_logger.debug(f"步骤 {step_name} 执行完成")
            await wait_for(5,7)
            std_logger.debug(f"当前URL: {page.url if page else 'N/A'}")

            
            # 截图记录
            screenshot_name = f"{step_name}_{i}.png"
            if i!=1:
                capture_screenshot(screenshot_name)
            
            # 给截图一点时间
            if i < len(steps) - 1:  # 不是最后一步
                await wait_for(3)
                
        except Exception as e:
            std_logger.error(f"步骤 {step_name} 执行失败: {e}")
            error_exit(f"步骤 {step_name} 执行失败: {e}")
            return 1

    std_logger.info("所有步骤执行完成")
    return 0

async def main():
    global std_logger,iargs
    exit_code=0
    user_agent = "Mozilla/5.0 (Linux; Android 13; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36"
    if iargs.debug:
        std_logger.info("DEBUG模式")
        await dev_setup()
        # exit_code=await continue_execution()
    else:
        setup(get_random_user_agent())
        try:
            exit_code=await continue_execution()
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1
            print(f"捕获到系统退出，退出码: {exit_code}")
        except Exception as e:
            exit_code=1
            print(f"执行过程中出现错误: {e}")
            # 可以选择记录日志或发送错误通知
        finally:
            return exit_code

# 在脚本入口点运行
if __name__ == "__main__":
    
    if iargs.retry > 0 :
        for attempt in range(1,iargs.retry + 1):  # 包括第一次尝试
            info+=f"开始第 {attempt} 次尝试，共 {iargs.retry} 次机会\n"
            success = asyncio.run(main())
            if success==0:
                std_logger.debug("执行成功，无需重试")
                exit_process(0)
                break
            else:
                std_logger.debug(f"第 {attempt} 次执行失败")
                if attempt < iargs.retry:
                    std_logger.debug("准备重试...")
                else:
                    std_logger.debug("已达到最大重试次数")
        else:
            exit_process(success)
    else:
        success=asyncio.run(main())
        exit_process(success)
