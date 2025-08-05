import asyncio
import sys
import os
import argparse
import math
import json
import random
import base64
import re
import time
from datetime import datetime
from functools import wraps
from urllib.parse import urlencode
from typing import Optional, Dict, Any
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

import requests
from dotenv import load_dotenv
from openai import AsyncOpenAI, APIStatusError
from playwright.async_api import async_playwright, Response, TimeoutError as PlaywrightTimeoutError
from requests.exceptions import HTTPError

# 添加数据库导入
from database import XianyuDatabase

# 添加邮件模块导入
from email_sender import email_sender

# 添加Cookie管理器导入
from cookie_manager import CookieManager

# 添加代理管理器导入
from proxy_manager import ProxyManager

# 添加速率限制器导入
from rate_limiter import RateLimiter, adaptive_sleep

"""
闲鱼商品爬虫主模块 (Version 2)

实现功能完整的闲鱼商品爬虫系统，支持：
- 多任务并发爬取
- Cookie池管理和轮换
- 代理池管理和自动切换
- AI智能分析和过滤
- 实时通知推送
- 数据库存储和管理
- 邮件通知功能

主要组件：
- 各种爬取和解析函数
- AI分析和通知功能

作者：ddCat
版本：1.0
创建时间：2025-08-04
"""

# 确保日志目录存在
os.makedirs('logs', exist_ok=True)
# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler('logs/spider.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 读取商品跳过配置，默认为true
SKIP_EXISTING_PRODUCTS = os.getenv('SKIP_EXISTING_PRODUCTS', 'true').lower() == 'true'

# 定义登录状态文件的路径
STATE_FILE = "xianyu_state.json"
# 定义闲鱼搜索API的URL特征
API_URL_PATTERN = "h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search"
# 定义闲鱼详情页API的URL特征
DETAIL_API_URL_PATTERN = "h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail"

# --- AI & Notification Configuration ---
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL")
MODEL_NAME = os.getenv("OPENAI_MODEL_NAME")
NTFY_TOPIC_URL = os.getenv("NTFY_TOPIC_URL")

# 代理配置
PROXY_API_URL = os.getenv('PROXY_API_URL')
PROXY_ENABLED = os.getenv('PROXY_ENABLED', 'false').lower() == 'true'
PROXY_RETRY_COUNT = int(os.getenv('PROXY_RETRY_COUNT', '3'))
PROXY_REFRESH_INTERVAL = int(os.getenv('PROXY_REFRESH_INTERVAL', '1800'))  # 默认30分钟更换一次代理

# 现代浏览器User-Agent池
USER_AGENTS = [
    # Chrome 最新版本
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",

    # Firefox 最新版本
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",

    # Edge 最新版本
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

def get_random_user_agent() -> str:
    """
    获取随机的现代浏览器User-Agent

    从预定义的现代浏览器User-Agent池中随机选择一个，用于模拟真实浏览器访问。
    包含Chrome、Firefox、Edge等主流浏览器的最新版本User-Agent。

    Returns:
        str: 随机选择的User-Agent字符串
    """
    return random.choice(USER_AGENTS)

async def robust_page_goto(page, url: str, task_id: int, max_retries: int = 3,
                          wait_until: str = "domcontentloaded", timeout: int = 30000) -> bool:
    """
    增强的页面导航函数，包含重试逻辑和错误处理

    Args:
        page: Playwright页面对象
        url: 要访问的URL
        task_id: 任务ID，用于日志记录
        max_retries: 最大重试次数
        wait_until: 等待条件
        timeout: 超时时间（毫秒）

    Returns:
        bool: 是否成功导航到页面
    """
    for attempt in range(max_retries):
        try:
            await log_to_database(task_id, 'INFO', f"尝试访问页面 (第{attempt + 1}/{max_retries}次): {url[:100]}...")

            # 使用速率限制器控制请求频率
            await rate_limiter.wait_if_needed(task_id, log_to_database)

            # 在重试时添加额外延迟
            if attempt > 0:
                await log_to_database(task_id, 'INFO', f"重试前增加额外延迟...")
                await adaptive_sleep(5.0, 12.0, attempt, task_id, log_to_database)

            await page.goto(url, wait_until=wait_until, timeout=timeout)
            await log_to_database(task_id, 'INFO', f"成功访问页面: {url[:100]}...")

            # 记录成功
            rate_limiter.record_success()
            return True

        except Exception as e:
            error_str = str(e)
            await log_to_database(task_id, 'WARNING', f"页面访问失败 (第{attempt + 1}/{max_retries}次): {error_str}")

            # 记录错误
            rate_limiter.record_error()

            # 检查是否是网络相关错误
            network_error_keywords = [
                "ERR_EMPTY_RESPONSE", "ERR_CONNECTION_RESET", "ERR_CONNECTION_REFUSED",
                "ERR_TIMED_OUT", "net::", "Protocol error", "Connection closed",
                "Timeout", "Connection reset", "Empty response", "Connection refused",
                "Target page, context or browser has been closed"
            ]

            is_network_error = any(err in error_str for err in network_error_keywords)

            if is_network_error:
                # 提取URL信息
                url_info = url if 'url' in locals() else "未知URL"

                # 详细的网络错误信息
                error_details = {
                    "error_type": "network_error",
                    "error_message": error_str,
                    "target_url": url_info,
                    "attempt_number": attempt + 1,
                    "max_retries": max_retries,
                    "error_keywords": [kw for kw in network_error_keywords if kw in error_str]
                }

                await log_to_database(task_id, 'WARNING', f"网络错误: {error_str} (URL: {url_info[:100]}...)")
                print(f"   [网络错误] 检测到网络错误: {error_str}")

                # 立即尝试切换代理
                if hasattr(robust_page_goto, '_current_context') and robust_page_goto._current_context:
                    await log_to_database(task_id, 'INFO', "网络错误触发代理切换", {"trigger": "network_error"})
                    print(f"   [网络错误] 触发代理切换...")

                    # 这里需要在调用处处理代理切换，因为这个函数没有访问browser和context
                    # 返回特殊标识让调用方知道需要切换代理
                    return "PROXY_SWITCH_NEEDED"

                if attempt < max_retries - 1:
                    retry_delay = random.randint(10, 20)
                    await log_to_database(task_id, 'INFO', f"网络错误重试前延迟 {retry_delay} 秒", {
                        "delay_seconds": retry_delay,
                        "retry_reason": "network_error"
                    })
                    print(f"   [网络错误] 重试前增加额外延迟...")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    await log_to_database(task_id, 'ERROR', f"网络错误重试失败: {error_str}", error_details)
                    return False
            else:
                # 非网络错误，立即失败
                await log_to_database(task_id, 'ERROR', f"页面访问失败: {error_str}")
                return False

    return False


async def robust_page_goto_with_proxy_switch(page, url: str, task_id: int, browser, context, proxy_address: str, max_retries: int = 3) -> tuple[bool, any, any, str]:
    """
    增强的页面导航函数，支持网络错误时自动切换代理

    Args:
        page: Playwright页面对象
        url: 目标URL
        task_id: 任务ID
        browser: 浏览器实例
        context: 浏览器上下文
        proxy_address: 当前代理地址
        max_retries: 最大重试次数

    Returns:
        tuple: (成功标志, 新的context, 新的page, 新的proxy_address)
    """
    current_context = context
    current_page = page
    current_proxy = proxy_address

    for attempt in range(max_retries):
        try:
            await log_to_database(task_id, 'INFO', f"尝试访问页面 (第{attempt + 1}/{max_retries}次): {url}")

            await current_page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await current_page.wait_for_load_state("networkidle", timeout=10000)

            await log_to_database(task_id, 'INFO', f"页面访问成功")
            return True, current_context, current_page, current_proxy

        except Exception as e:
            error_str = str(e)
            await log_to_database(task_id, 'WARNING', f"页面访问失败 (第{attempt + 1}/{max_retries}次): {error_str}")

            # 检查是否是网络相关错误
            network_error_keywords = [
                "ERR_EMPTY_RESPONSE", "ERR_CONNECTION_RESET", "ERR_CONNECTION_REFUSED",
                "ERR_TIMED_OUT", "net::", "Protocol error", "Connection closed",
                "Timeout", "Connection reset", "Empty response", "Connection refused",
                "Target page, context or browser has been closed"
            ]

            is_network_error = any(err in error_str for err in network_error_keywords)

            if is_network_error and attempt < max_retries - 1:
                # 详细的网络错误信息
                error_details = {
                    "error_type": "network_error_with_proxy_switch",
                    "error_message": error_str,
                    "target_url": url,
                    "attempt_number": attempt + 1,
                    "current_proxy": current_proxy
                }

                await log_to_database(task_id, 'WARNING', f"网络错误，尝试切换代理: {error_str} (URL: {url[:100]}...)", error_details)
                print(f"   [网络错误] 检测到网络错误，尝试切换代理: {error_str}")

                # 尝试获取新代理
                new_proxy = await handle_proxy_failure(task_id)
                if new_proxy and new_proxy != current_proxy:
                    try:
                        # 关闭当前上下文
                        await current_context.close()

                        # 创建新的上下文和页面
                        current_context = await create_browser_context(browser, new_proxy)
                        current_page = await current_context.new_page()
                        old_proxy = current_proxy
                        current_proxy = new_proxy

                        # 详细的代理切换成功信息
                        switch_details = {
                            "action": "proxy_switch_success",
                            "old_proxy": old_proxy,
                            "new_proxy": current_proxy,
                            "trigger_error": error_str,
                            "target_url": url
                        }

                        await log_to_database(task_id, 'INFO', f"代理切换成功: {old_proxy} -> {current_proxy}", switch_details)
                        print(f"   [代理切换] 成功切换到新代理: {current_proxy}")

                        # 继续重试
                        continue

                    except Exception as proxy_error:
                        switch_error_details = {
                            "action": "proxy_switch_failed",
                            "old_proxy": current_proxy,
                            "target_proxy": new_proxy,
                            "error_message": str(proxy_error),
                            "original_error": error_str
                        }

                        await log_to_database(task_id, 'ERROR', f"代理切换失败: {str(proxy_error)}", switch_error_details)
                        print(f"   [代理切换] 代理切换失败: {proxy_error}")

                # 如果无法切换代理，增加延迟后重试
                retry_delay = random.randint(10, 20)
                await log_to_database(task_id, 'INFO', f"代理切换后重试前延迟 {retry_delay} 秒", {
                    "delay_seconds": retry_delay,
                    "retry_reason": "proxy_switch_fallback"
                })
                print(f"   [网络错误] 重试前增加额外延迟...")
                await asyncio.sleep(retry_delay)

            elif not is_network_error:
                # 非网络错误，立即失败
                await log_to_database(task_id, 'ERROR', f"页面访问失败: {error_str}")
                return False, current_context, current_page, current_proxy

    await log_to_database(task_id, 'ERROR', f"页面访问重试失败，已达到最大重试次数")
    return False, current_context, current_page, current_proxy


# 创建全局代理管理器实例（稍后设置日志上下文）
proxy_manager = ProxyManager(
    proxy_api_url=PROXY_API_URL,
    proxy_enabled=PROXY_ENABLED,
    refresh_interval=PROXY_REFRESH_INTERVAL,
    retry_count=PROXY_RETRY_COUNT
)

# 全局客户端变量，延迟初始化
client = None

def get_openai_client():
    """
    获取OpenAI客户端实例（延迟初始化）

    只在需要时才初始化OpenAI客户端，避免在模块导入时就要求配置完整。

    Returns:
        AsyncOpenAI: OpenAI客户端实例

    Raises:
        SystemExit: 当配置不完整或初始化失败时退出程序
    """
    global client
    if client is None:
        # 检查配置是否齐全
        if not all([BASE_URL, MODEL_NAME]):
            sys.exit("错误：请确保在 .env 文件中完整设置了 OPENAI_BASE_URL 和 OPENAI_MODEL_NAME。(OPENAI_API_KEY 对于某些服务是可选的)")

        # 初始化 OpenAI 客户端
        try:
            client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
        except Exception as e:
            sys.exit(f"初始化 OpenAI 客户端时出错: {e}")

    return client

# 初始化数据库
db = XianyuDatabase()

# 定义目录和文件名
IMAGE_SAVE_DIR = "images"
os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)

# 定义下载图片所需的请求头
IMAGE_DOWNLOAD_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

def get_link_unique_key(link: str) -> str:
    """
    获取链接的唯一标识键

    截取链接中第一个"&"之前的内容作为唯一标识依据，用于判断商品是否已被处理。

    Args:
        link (str): 完整的商品链接URL

    Returns:
        str: 链接的唯一标识部分
    """
    return link.split('&', 1)[0]

async def random_sleep(min_seconds: float, max_seconds: float):
    """
    异步随机延迟函数

    在指定范围内随机等待一段时间，用于模拟人类操作行为，避免被反爬虫机制检测。

    Args:
        min_seconds (float): 最小延迟时间（秒）
        max_seconds (float): 最大延迟时间（秒）
    """
    delay = random.uniform(min_seconds, max_seconds)
    print(f"   [延迟] 等待 {delay:.2f} 秒... (范围: {min_seconds}-{max_seconds}s)") # 调试时可以取消注释
    await asyncio.sleep(delay)



# 全局速率限制器
rate_limiter = RateLimiter()

async def save_to_database(data_record: dict, task_id: int):
    """将商品和AI分析数据保存到数据库，替代JSONL文件"""
    try:
        # 在商品数据中添加task_id
        data_record['task_id'] = task_id
        
        # 保存商品信息
        product_db_id = await db.save_product(data_record)
        if not product_db_id:
            print(f"   [数据库] 商品保存失败")
            return False
            
        # 保存AI分析结果
        ai_analysis = data_record.get('ai_analysis', {})
        if ai_analysis:
            await db.save_ai_analysis(task_id, product_db_id, ai_analysis)
            print(f"   [数据库] 商品和AI分析结果已保存到数据库")
        else:
            print(f"   [数据库] 商品已保存到数据库（无AI分析）")
            
        return True
    except Exception as e:
        print(f"   [数据库] 保存数据时出错: {e}")
        return False

async def calculate_reputation_from_ratings(ratings_json: list) -> dict:
    """从原始评价API数据列表中，计算作为卖家和买家的好评数与好评率。"""
    seller_total = 0
    seller_positive = 0
    buyer_total = 0
    buyer_positive = 0

    for card in ratings_json:
        # 使用 safe_get 保证安全访问
        data = await safe_get(card, 'cardData', default={})
        role_tag = await safe_get(data, 'rateTagList', 0, 'text', default='')
        rate_type = await safe_get(data, 'rate') # 1=好评, 0=中评, -1=差评

        if "卖家" in role_tag:
            seller_total += 1
            if rate_type == 1:
                seller_positive += 1
        elif "买家" in role_tag:
            buyer_total += 1
            if rate_type == 1:
                buyer_positive += 1

    # 计算比率，并处理除以零的情况
    seller_rate = f"{(seller_positive / seller_total * 100):.2f}%" if seller_total > 0 else "N/A"
    buyer_rate = f"{(buyer_positive / buyer_total * 100):.2f}%" if buyer_total > 0 else "N/A"

    return {
        "作为卖家的好评数": f"{seller_positive}/{seller_total}",
        "作为卖家的好评率": seller_rate,
        "作为买家的好评数": f"{buyer_positive}/{buyer_total}",
        "作为买家的好评率": buyer_rate
    }

async def _parse_user_items_data(items_json: list) -> list:
    """解析用户主页的商品列表API的JSON数据。"""
    parsed_list = []
    for card in items_json:
        data = card.get('cardData', {})
        status_code = data.get('itemStatus')
        if status_code == 0:
            status_text = "在售"
        elif status_code == 1:
            status_text = "已售"
        else:
            status_text = f"未知状态 ({status_code})"

        parsed_list.append({
            "商品ID": data.get('id'),
            "商品标题": data.get('title'),
            "商品价格": data.get('priceInfo', {}).get('price'),
            "商品主图": data.get('picInfo', {}).get('picUrl'),
            "商品状态": status_text
        })
    return parsed_list


async def scrape_user_profile(context, user_id: str) -> dict:
    """
    【新版】访问指定用户的个人主页，按顺序采集其摘要信息、完整的商品列表和完整的评价列表。
    """
    print(f"   -> 开始采集用户ID: {user_id} 的完整信息...")
    profile_data = {}
    page = await context.new_page()

    # 为各项异步任务准备Future和数据容器
    head_api_future = asyncio.get_event_loop().create_future()

    all_items, all_ratings = [], []
    stop_item_scrolling, stop_rating_scrolling = asyncio.Event(), asyncio.Event()

    async def handle_response(response: Response):
        # 捕获头部摘要API
        if "mtop.idle.web.user.page.head" in response.url and not head_api_future.done():
            try:
                head_api_future.set_result(await response.json())
                print(f"      [API捕获] 用户头部信息... 成功")
            except Exception as e:
                if not head_api_future.done(): head_api_future.set_exception(e)

        # 捕获商品列表API
        elif "mtop.idle.web.xyh.item.list" in response.url:
            try:
                data = await response.json()
                all_items.extend(data.get('data', {}).get('cardList', []))
                print(f"      [API捕获] 商品列表... 当前已捕获 {len(all_items)} 件")
                if not data.get('data', {}).get('nextPage', True):
                    stop_item_scrolling.set()
            except Exception as e:
                stop_item_scrolling.set()

        # 捕获评价列表API
        elif "mtop.idle.web.trade.rate.list" in response.url:
            try:
                data = await response.json()
                all_ratings.extend(data.get('data', {}).get('cardList', []))
                print(f"      [API捕获] 评价列表... 当前已捕获 {len(all_ratings)} 条")
                if not data.get('data', {}).get('nextPage', True):
                    stop_rating_scrolling.set()
            except Exception as e:
                stop_rating_scrolling.set()

    page.on("response", handle_response)

    try:
        # --- 任务1: 导航并采集头部信息 ---
        await page.goto(f"https://www.goofish.com/personal?userId={user_id}", wait_until="domcontentloaded", timeout=20000)
        head_data = await asyncio.wait_for(head_api_future, timeout=15)
        profile_data = await parse_user_head_data(head_data)

        # --- 任务2: 滚动加载所有商品 (默认页面) ---
        print("      [采集阶段] 开始采集该用户的商品列表...")
        await random_sleep(2, 4) # 等待第一页商品API完成
        while not stop_item_scrolling.is_set():
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            try:
                await asyncio.wait_for(stop_item_scrolling.wait(), timeout=8)
            except asyncio.TimeoutError:
                print("      [滚动超时] 商品列表可能已加载完毕。")
                break
        profile_data["卖家发布的商品列表"] = await _parse_user_items_data(all_items)

        # --- 任务3: 点击并采集所有评价 ---
        print("      [采集阶段] 开始采集该用户的评价列表...")
        rating_tab_locator = page.locator("//div[text()='信用及评价']/ancestor::li")
        if await rating_tab_locator.count() > 0:
            await rating_tab_locator.click()
            await random_sleep(3, 5) # 等待第一页评价API完成

            while not stop_rating_scrolling.is_set():
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                try:
                    await asyncio.wait_for(stop_rating_scrolling.wait(), timeout=8)
                except asyncio.TimeoutError:
                    print("      [滚动超时] 评价列表可能已加载完毕。")
                    break

            profile_data['卖家收到的评价列表'] = await parse_ratings_data(all_ratings)
            reputation_stats = await calculate_reputation_from_ratings(all_ratings)
            profile_data.update(reputation_stats)
        else:
            print("      [警告] 未找到评价选项卡，跳过评价采集。")

    except Exception as e:
        print(f"   [错误] 采集用户 {user_id} 信息时发生错误: {e}")
    finally:
        page.remove_listener("response", handle_response)
        await page.close()
        print(f"   -> 用户 {user_id} 信息采集完成。")

    return profile_data

async def parse_user_head_data(head_json: dict) -> dict:
    """解析用户头部API的JSON数据。"""
    data = head_json.get('data', {})
    ylz_tags = await safe_get(data, 'module', 'base', 'ylzTags', default=[])
    seller_credit, buyer_credit = {}, {}
    for tag in ylz_tags:
        if await safe_get(tag, 'attributes', 'role') == 'seller':
            seller_credit = {'level': await safe_get(tag, 'attributes', 'level'), 'text': tag.get('text')}
        elif await safe_get(tag, 'attributes', 'role') == 'buyer':
            buyer_credit = {'level': await safe_get(tag, 'attributes', 'level'), 'text': tag.get('text')}
    return {
        "卖家昵称": await safe_get(data, 'module', 'base', 'displayName'),
        "卖家头像链接": await safe_get(data, 'module', 'base', 'avatar', 'avatar'),
        "卖家个性签名": await safe_get(data, 'module', 'base', 'introduction', default=''),
        "卖家在售/已售商品数": await safe_get(data, 'module', 'tabs', 'item', 'number'),
        "卖家收到的评价总数": await safe_get(data, 'module', 'tabs', 'rate', 'number'),
        "卖家信用等级": seller_credit.get('text', '暂无'),
        "买家信用等级": buyer_credit.get('text', '暂无')
    }


async def parse_ratings_data(ratings_json: list) -> list:
    """解析评价列表API的JSON数据。"""
    parsed_list = []
    for card in ratings_json:
        data = await safe_get(card, 'cardData', default={})
        rate_tag = await safe_get(data, 'rateTagList', 0, 'text', default='未知角色')
        rate_type = await safe_get(data, 'rate')
        if rate_type == 1: rate_text = "好评"
        elif rate_type == 0: rate_text = "中评"
        elif rate_type == -1: rate_text = "差评"
        else: rate_text = "未知"
        parsed_list.append({
            "评价ID": data.get('rateId'),
            "评价内容": data.get('feedback'),
            "评价类型": rate_text,
            "评价来源角色": rate_tag,
            "评价者昵称": data.get('raterUserNick'),
            "评价时间": data.get('gmtCreate'),
            "评价图片": await safe_get(data, 'pictCdnUrlList', default=[])
        })
    return parsed_list

async def safe_get(data, *keys, default="暂无"):
    """
    安全获取嵌套字典值

    递归访问嵌套字典或列表，当任何层级的键不存在时返回默认值，避免KeyError异常。
    支持字典键访问和列表索引访问的混合使用。

    Args:
        data: 要访问的数据结构（字典、列表等）
        *keys: 要访问的键序列，可以是字典键或列表索引
        default: 当访问失败时返回的默认值，默认为"暂无"

    Returns:
        访问到的值或默认值

    Example:
        await safe_get(data, 'user', 'profile', 'name', default='未知用户')
        await safe_get(data, 'items', 0, 'title', default='无标题')
    """
    for key in keys:
        try:
            data = data[key]
        except (KeyError, TypeError, IndexError):
            return default
    return data

async def _parse_search_results_json(json_data: dict, source: str, task_id: int = None) -> list:
    """解析搜索API的JSON数据，返回基础商品信息列表。"""
    page_data = []
    try:
        items = await safe_get(json_data, "data", "resultList", default=[])
        if not items:
            # 尝试其他可能的路径
            items = await safe_get(json_data, "resultList", default=[])
            if not items:
                items = await safe_get(json_data, "data", "items", default=[])
                if not items:
                    debug_message = f"DEBUG: ({source}) 完整JSON响应: {json.dumps(json_data, ensure_ascii=False, indent=2)[:500]}..."
                    log_message = f"LOG: ({source}) API响应中未找到商品列表 (resultList)。"
                    print(debug_message)
                    print(log_message)

                    # 记录到数据库
                    if task_id:
                        await log_to_database(task_id, 'DEBUG', f"({source}) 完整JSON响应",
                                            {"json_preview": json.dumps(json_data, ensure_ascii=False, indent=2)[:500]})
                        await log_to_database(task_id, 'WARNING', f"({source}) API响应中未找到商品列表")
                    return []

        for item in items:
            main_data = await safe_get(item, "data", "item", "main", "exContent", default={})
            click_params = await safe_get(item, "data", "item", "main", "clickParam", "args", default={})

            title = await safe_get(main_data, "title", default="未知标题")
            price_parts = await safe_get(main_data, "price", default=[])
            price = "".join([str(p.get("text", "")) for p in price_parts if isinstance(p, dict)]).replace("当前价", "").strip() if isinstance(price_parts, list) else "价格异常"
            if "万" in price: price = f"¥{float(price.replace('¥', '').replace('万', '')) * 10000:.0f}"
            area = await safe_get(main_data, "area", default="地区未知")
            seller = await safe_get(main_data, "userNickName", default="匿名卖家")
            raw_link = await safe_get(item, "data", "item", "main", "targetUrl", default="")
            image_url = await safe_get(main_data, "picUrl", default="")
            pub_time_ts = click_params.get("publishTime", "")
            item_id = await safe_get(main_data, "itemId", default="未知ID")
            original_price = await safe_get(main_data, "oriPrice", default="暂无")
            wants_count = await safe_get(click_params, "wantNum", default='NaN')


            tags = []
            if await safe_get(click_params, "tag") == "freeship":
                tags.append("包邮")
            r1_tags = await safe_get(main_data, "fishTags", "r1", "tagList", default=[])
            for tag_item in r1_tags:
                content = await safe_get(tag_item, "data", "content", default="")
                if "验货宝" in content:
                    tags.append("验货宝")

            page_data.append({
                "商品标题": title,
                "当前售价": price,
                "商品原价": original_price,
                "“想要”人数": wants_count,
                "商品标签": tags,
                "发货地区": area,
                "卖家昵称": seller,
                "商品链接": raw_link.replace("fleamarket://", "https://www.goofish.com/"),
                "发布时间": datetime.fromtimestamp(int(pub_time_ts)/1000).strftime("%Y-%m-%d %H:%M") if pub_time_ts.isdigit() else "未知时间",
                "商品ID": item_id
            })
        print(f"LOG: ({source}) 成功解析到 {len(page_data)} 条商品基础信息。")
        return page_data
    except Exception as e:
        print(f"LOG: ({source}) JSON数据处理异常: {str(e)}")
        return []

def format_registration_days(total_days: int) -> str:
    """
    将总天数格式化为“X年Y个月”的字符串。
    """
    if not isinstance(total_days, int) or total_days <= 0:
        return '未知'

    # 使用更精确的平均天数
    DAYS_IN_YEAR = 365.25
    DAYS_IN_MONTH = DAYS_IN_YEAR / 12  # 大约 30.44

    # 计算年数
    years = math.floor(total_days / DAYS_IN_YEAR)

    # 计算剩余天数
    remaining_days = total_days - (years * DAYS_IN_YEAR)

    # 计算月数，四舍五入
    months = round(remaining_days / DAYS_IN_MONTH)

    # 处理进位：如果月数等于12，则年数加1，月数归零
    if months == 12:
        years += 1
        months = 0

    # 构建最终的输出字符串
    if years > 0 and months > 0:
        return f"来闲鱼{years}年{months}个月"
    elif years > 0 and months == 0:
        return f"来闲鱼{years}年整"
    elif years == 0 and months > 0:
        return f"来闲鱼{months}个月"
    else: # years == 0 and months == 0
        return "来闲鱼不足一个月"


# --- AI分析及通知辅助函数 (从 ai_filter.py 移植并异步化改造) ---

def retry_on_failure(retries=3, delay=5):
    """
    一个通用的异步重试装饰器，增加了对HTTP错误的详细日志记录。
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    return await func(*args, **kwargs)
                except (APIStatusError, HTTPError) as e:
                    print(f"函数 {func.__name__} 第 {i + 1}/{retries} 次尝试失败，发生HTTP错误。")
                    if hasattr(e, 'status_code'):
                        print(f"  - 状态码 (Status Code): {e.status_code}")
                    if hasattr(e, 'response') and hasattr(e.response, 'text'):
                        response_text = e.response.text
                        print(
                            f"  - 返回值 (Response): {response_text[:300]}{'...' if len(response_text) > 300 else ''}")
                except json.JSONDecodeError as e:
                    print(f"函数 {func.__name__} 第 {i + 1}/{retries} 次尝试失败: JSON解析错误 - {e}")
                except Exception as e:
                    print(f"函数 {func.__name__} 第 {i + 1}/{retries} 次尝试失败: {type(e).__name__} - {e}")

                if i < retries - 1:
                    print(f"将在 {delay} 秒后重试...")
                    await asyncio.sleep(delay)

            print(f"函数 {func.__name__} 在 {retries} 次尝试后彻底失败。")
            return None
        return wrapper
    return decorator


@retry_on_failure(retries=2, delay=3)
async def _download_single_image(url, save_path):
    """一个带重试的内部函数，用于异步下载单个图片。"""
    loop = asyncio.get_running_loop()
    # 使用 run_in_executor 运行同步的 requests 代码，避免阻塞事件循环
    response = await loop.run_in_executor(
        None,
        lambda: requests.get(url, headers=IMAGE_DOWNLOAD_HEADERS, timeout=20, stream=True)
    )
    response.raise_for_status()
    with open(save_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    return save_path


async def download_all_images(product_id, image_urls):
    """
    批量下载商品图片

    异步下载指定商品的所有图片，按商品ID创建独立目录进行组织。
    支持断点续传（跳过已存在的图片）和错误处理。

    Args:
        product_id: 商品ID，用于创建图片存储目录
        image_urls (list): 图片URL列表

    Returns:
        list: 成功下载的图片本地路径列表
    """
    if not image_urls:
        return []

    urls = [url.strip() for url in image_urls if url.strip().startswith('http')]
    if not urls:
        return []

    # 为每个商品创建独立的图片目录
    product_image_dir = os.path.join(IMAGE_SAVE_DIR, str(product_id))
    os.makedirs(product_image_dir, exist_ok=True)

    saved_paths = []
    total_images = len(urls)
    for i, url in enumerate(urls):
        try:
            clean_url = url.split('.heic')[0] if '.heic' in url else url
            file_name_base = os.path.basename(clean_url).split('?')[0]
            # 新的文件命名格式：image_{index}_{filename}
            file_name = f"image_{i + 1}_{file_name_base}"
            file_name = re.sub(r'[\\/*?:"<>|]', "", file_name)
            if not os.path.splitext(file_name)[1]:
                file_name += ".jpg"

            # 新的保存路径：images/{product_id}/image_{index}_{filename}
            save_path = os.path.join(product_image_dir, file_name)

            if os.path.exists(save_path):
                print(f"   [图片] 图片 {i + 1}/{total_images} 已存在，跳过下载: {os.path.basename(save_path)}")
                saved_paths.append(save_path)
                continue

            print(f"   [图片] 正在下载图片 {i + 1}/{total_images}: {url}")
            if await _download_single_image(url, save_path):
                print(f"   [图片] 图片 {i + 1}/{total_images} 已成功下载到: {save_path}")
                saved_paths.append(save_path)
        except Exception as e:
            print(f"   [图片] 处理图片 {url} 时发生错误，已跳过此图: {e}")

    return saved_paths


def encode_image_to_base64(image_path):
    """
    图片Base64编码函数

    将本地图片文件读取并编码为Base64字符串，用于发送给AI模型进行图像分析。

    Args:
        image_path (str): 本地图片文件路径

    Returns:
        str: Base64编码的图片字符串，如果文件不存在或编码失败则返回None
    """
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"编码图片时出错: {e}")
        return None


@retry_on_failure(retries=3, delay=5)
async def send_ntfy_notification(product_data, reason):
    """
    发送ntfy推送通知

    当AI分析发现推荐商品时，通过ntfy.sh服务发送高优先级的推送通知到用户设备。
    支持自定义通知标题、内容和优先级设置。

    Args:
        product_data (dict): 商品数据字典，包含标题、价格、链接等信息
        reason (str): 推荐理由，来自AI分析结果

    Raises:
        Exception: 当通知发送失败时抛出异常（会被重试装饰器处理）
    """
    if not NTFY_TOPIC_URL:
        print("警告：未在 .env 文件中配置 NTFY_TOPIC_URL，跳过通知。")
        return

    title = product_data.get('商品标题', 'N/A')
    price = product_data.get('当前售价', 'N/A')
    link = product_data.get('商品链接', '#')

    message = f"价格: {price}\n原因: {reason}\n链接: {link}"
    notification_title = f"🚨 新推荐! {title[:30]}..."

    try:
        print(f"   -> 正在发送 ntfy 通知到: {NTFY_TOPIC_URL}")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: requests.post(
                NTFY_TOPIC_URL,
                data=message.encode('utf-8'),
                headers={
                    "Title": notification_title.encode('utf-8'),
                    "Priority": "urgent",
                    "Tags": "bell,vibration"
                },
                timeout=10
            )
        )
        print("   -> 通知发送成功。")
    except Exception as e:
        print(f"   -> 发送 ntfy 通知失败: {e}")
        raise


@retry_on_failure(retries=5, delay=10)
async def get_ai_analysis(product_data, image_paths=None, prompt_text=""):
    """
    AI商品分析函数

    将完整的商品JSON数据和商品图片发送给AI模型进行智能分析，
    根据用户提供的提示词判断商品是否符合购买条件。

    Args:
        product_data (dict): 完整的商品数据字典，包含商品信息、卖家信息等
        image_paths (list, optional): 商品图片的本地路径列表
        prompt_text (str): AI分析的提示词，定义分析标准和输出格式

    Returns:
        dict: AI分析结果的JSON对象，包含推荐状态、理由等信息

    Raises:
        Exception: 当AI API调用失败或响应解析失败时抛出异常
    """
    item_info = product_data.get('商品信息', {})
    product_id = item_info.get('商品ID', 'N/A')

    print(f"\n   [AI分析] 开始分析商品 #{product_id} (含 {len(image_paths or [])} 张图片)...")
    print(f"   [AI分析] 标题: {item_info.get('商品标题', '无')}")

    if not prompt_text:
        print("   [AI分析] 错误：未提供AI分析所需的prompt文本。")
        return None

    product_details_json = json.dumps(product_data, ensure_ascii=False, indent=2)
    system_prompt = prompt_text

    combined_text_prompt = f"""{system_prompt}

请基于你的专业知识和我的要求，分析以下完整的商品JSON数据：

```json
    {product_details_json}
"""
    user_content_list = [{"type": "text", "text": combined_text_prompt}]

    if image_paths:
        for path in image_paths:
            base64_image = encode_image_to_base64(path)
            if base64_image:
                user_content_list.append(
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}})

    messages = [{"role": "user", "content": user_content_list}]

    # 确保OpenAI客户端已初始化
    ai_client = get_openai_client()

    response = await ai_client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        response_format={"type": "json_object"}
    )

    ai_response_content = response.choices[0].message.content

    try:
        return json.loads(ai_response_content)
    except json.JSONDecodeError as e:
        print("---!!! AI RESPONSE PARSING FAILED (JSONDecodeError) !!!---")
        print(f"原始返回值 (Raw response from AI):\n---\n{ai_response_content}\n---")
        raise e


async def log_to_database(task_id: int, level: str, message: str, details: dict = None):
    """
    记录任务日志到数据库

    将任务执行过程中的重要事件和状态变化记录到数据库中，便于后续分析和调试。
    支持不同级别的日志记录，包括INFO、WARNING、ERROR等。

    Args:
        task_id (int): 任务ID，用于关联日志记录
        level (str): 日志级别，如'INFO'、'WARNING'、'ERROR'
        message (str): 日志消息内容
        details (dict, optional): 额外的详细信息，以字典形式存储
    """
    try:
        await db.log_task_event(task_id, level, message, details)
    except Exception as e:
        print(f"记录数据库日志失败: {e}")


async def process_retry_products(retry_products, task_id: int, task_name: str, ai_prompt_text: str, email_enabled: bool, email_address: str):
    """
    处理待重试获取详情的商品

    Args:
        retry_products: 待重试的商品列表
        task_id: 任务ID
        task_name: 任务名称
        ai_prompt_text: AI分析提示词
        email_enabled: 是否启用邮件通知
        email_address: 邮件地址
    """
    await log_to_database(task_id, 'INFO', f"开始处理 {len(retry_products)} 个待重试商品")
    print(f"\n=== 开始处理待重试商品详情 ===")

    retry_success_count = 0
    retry_fail_count = 0

    for product in retry_products:
        try:
            product_id = product['product_id']
            product_link = product['product_url']

            await log_to_database(task_id, 'INFO', f"重新获取详情: {product['title'][:30]}...")
            print(f"   -> 重新获取商品详情: {product['title'][:30]}...")

            # 这里应该实现重新获取详情的逻辑
            # 由于需要浏览器上下文，暂时标记为处理中
            await db.update_product_detail_status(product_id, '重试中')

            # 模拟重新获取详情的过程
            # 实际实现需要在主爬虫逻辑中集成
            await log_to_database(task_id, 'INFO', f"商品 {product_id} 已标记为重试中，将在主爬虫流程中处理")

            retry_success_count += 1

        except Exception as e:
            await log_to_database(task_id, 'ERROR', f"处理重试商品 {product.get('product_id', 'unknown')} 失败: {str(e)}")
            print(f"   -> 处理重试商品失败: {e}")
            retry_fail_count += 1

    await log_to_database(task_id, 'INFO', f"重试处理完成: 成功 {retry_success_count}, 失败 {retry_fail_count}")
    print(f"=== 重试处理完成: 成功 {retry_success_count}, 失败 {retry_fail_count} ===")



# 初始化Cookie管理器
cookie_manager = CookieManager(db)

async def create_browser_context(browser, proxy_address: Optional[str] = None):
    """
    创建配置完整的浏览器上下文

    使用Cookie池和代理池创建浏览器上下文，包含登录状态、随机User-Agent和代理配置。
    这是爬虫系统的核心组件，确保每个请求都有合适的身份和网络配置。

    Args:
        browser: Playwright浏览器实例
        proxy_address (Optional[str]): 代理地址，格式为"ip:port"，如果为None则不使用代理

    Returns:
        BrowserContext: 配置完整的浏览器上下文对象

    Raises:
        Exception: 当无可用Cookie时抛出异常
    """
    # 获取可用Cookie
    cookie_data = await cookie_manager.get_available_cookie()

    if not cookie_data:
        raise Exception("无可用Cookie，请先添加Cookie")

    # 使用随机的现代浏览器User-Agent
    user_agent = get_random_user_agent()
    context_options = {
        'storage_state': cookie_data,
        'user_agent': user_agent
    }
    print(f"   [浏览器] 使用User-Agent: {user_agent}")

    if proxy_address:
        context_options['proxy'] = {
            'server': f"http://{proxy_address}"
        }
        print(f"   [代理] 使用代理: {proxy_address}")
        proxy_manager.record_usage()
    else:
        print("   [代理] 不使用代理")

    return await browser.new_context(**context_options)

async def scrape_xianyu(task_config: dict, debug_limit: int = 0):
    """
    闲鱼商品爬取核心执行器

    根据任务配置异步爬取闲鱼商品数据，支持多页爬取、实时AI分析、智能通知推送。
    包含完整的错误处理、代理轮换、Cookie管理等功能。

    Args:
        task_config (dict): 任务配置字典，包含以下字段：
            - task_id (int, optional): 任务ID
            - keyword (str): 搜索关键词
            - task_name (str): 任务名称
            - max_pages (int, optional): 最大爬取页数，默认1
            - personal_only (bool, optional): 是否只爬取个人商品，默认False
            - min_price (int, optional): 最低价格筛选
            - max_price (int, optional): 最高价格筛选
            - ai_prompt_text (str, optional): AI分析提示词
            - email_enabled (bool, optional): 是否启用邮件通知
            - email_address (str, optional): 邮件接收地址
        debug_limit (int, optional): 调试模式下的商品处理数量限制，0表示无限制

    Returns:
        int: 本次运行处理的新商品数量

    Raises:
        Exception: 当无法找到任务ID或创建浏览器上下文失败时抛出异常
    """
    keyword = task_config['keyword']
    task_id = task_config['task_id']
    task_name = task_config['task_name']
    max_pages = task_config.get('max_pages', 1)
    personal_only = task_config.get('personal_only', False)
    min_price = task_config.get('min_price')
    max_price = task_config.get('max_price')
    ai_prompt_text = task_config.get('ai_prompt_text', '')
    
    # 邮件通知配置
    email_enabled = task_config.get('email_enabled', False)
    email_address = task_config.get('email_address', '')

    await log_to_database(task_id, 'INFO', f"开始执行任务: {task_name}")

    # 设置代理管理器和Cookie管理器的日志上下文
    proxy_manager.set_log_context(log_to_database, task_id)
    cookie_manager.set_log_context(log_to_database, task_id)

    # 检查邮件配置
    if email_enabled and email_address:
        if email_sender.is_configured():
            await log_to_database(task_id, 'INFO', f"邮件通知已启用: {email_address}")
        else:
            await log_to_database(task_id, 'WARNING', "邮件通知已启用但SMTP配置不完整")
            print(f"   [邮件] 任务 '{task_name}' 启用了邮件通知，但SMTP配置不完整")

    processed_item_count = 0
    stop_scraping = False

    # 从数据库获取已处理的商品链接
    processed_links = await db.get_processed_product_links(task_id)
    print(f"LOG: 从数据库加载了 {len(processed_links)} 个已处理过的商品。")
    await log_to_database(task_id, 'INFO', f"从数据库加载了 {len(processed_links)} 个已处理过的商品")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # 获取初始代理地址
        proxy_address = await get_proxy_with_fallback()
        if proxy_address:
            await log_to_database(task_id, 'INFO', f"使用代理: {proxy_address}")
            await log_proxy_stats(task_id)
        else:
            await log_to_database(task_id, 'INFO', "不使用代理")
        
        # 创建带代理和Cookie池的浏览器上下文
        try:
            context = await create_browser_context(browser, proxy_address)
        except Exception as e:
            await log_to_database(task_id, 'ERROR', f"创建浏览器上下文失败: {str(e)}")
            print(f"LOG: 创建浏览器上下文失败: {e}")
            return 0
            
        page = await context.new_page()

        try:
            # 构建搜索URL
            search_url = f"https://www.goofish.com/search?q={keyword}"
            if personal_only:
                search_url += "&st=1"
            if min_price:
                search_url += f"&price_start={min_price}"
            if max_price:
                search_url += f"&price_end={max_price}"

            await log_to_database(task_id, 'INFO', f"开始搜索: {search_url}")
            print(f"LOG: 任务 '{task_name}' 开始搜索关键词: {keyword}")

            # 访问搜索页面并等待API响应
            try:
                async with page.expect_response(lambda r: API_URL_PATTERN in r.url, timeout=30000) as response_info:
                    # 使用增强的页面导航函数
                    navigation_success = await robust_page_goto(page, search_url, task_id, max_retries=3)
                    if not navigation_success:
                        raise Exception("页面导航失败，已达到最大重试次数")
                current_response = await response_info.value
            except Exception as e:
                # 检查是否是Cookie问题
                if "登录" in str(e) or "验证" in str(e):
                    await log_to_database(task_id, 'WARNING', "检测到Cookie可能失效，尝试切换Cookie")
                    print("   [Cookie管理] 检测到可能的Cookie问题，尝试切换")
                    
                    # 切换到下一个Cookie
                    new_cookie_data = await cookie_manager.switch_to_next_cookie()
                    if new_cookie_data:
                        await context.close()
                        context = await create_browser_context(browser, proxy_address)
                        page = await context.new_page()
                        
                        # 重试访问
                        try:
                            async with page.expect_response(lambda r: API_URL_PATTERN in r.url, timeout=30000) as response_info:
                                # 使用增强的页面导航函数
                                navigation_success = await robust_page_goto(page, search_url, task_id, max_retries=2)
                                if not navigation_success:
                                    raise Exception("Cookie切换后页面导航仍然失败")
                            current_response = await response_info.value
                        except Exception as retry_e:
                            await log_to_database(task_id, 'ERROR', f"切换Cookie后仍然失败: {str(retry_e)}")
                            raise retry_e
                    else:
                        await log_to_database(task_id, 'ERROR', "无更多可用Cookie")
                        raise Exception("无可用Cookie")
                else:
                    raise e

            if not current_response.ok:
                error_msg = f"搜索API响应失败: {current_response.status}"
                await log_to_database(task_id, 'ERROR', error_msg)
                print(f"LOG: {error_msg}")
                return 0

            await log_to_database(task_id, 'INFO', f"成功获取搜索API响应")

            # 处理多页数据
            for page_num in range(1, max_pages + 1):
                if stop_scraping:
                    break

                # 在每页开始前检查代理状态
                current_proxy = await get_proxy_with_fallback()
                if current_proxy != proxy_address:
                    await log_to_database(task_id, 'INFO', f"代理已自动更换: {proxy_address} -> {current_proxy}")
                    print(f"   [代理管理] 代理已自动更换: {proxy_address} -> {current_proxy}")
                    # 重新创建浏览器上下文
                    await context.close()
                    context = await create_browser_context(browser, current_proxy)
                    page = await context.new_page()
                    proxy_address = current_proxy
                    await log_proxy_stats(task_id)

                await log_to_database(task_id, 'INFO', f"开始处理第 {page_num} 页")
                print(f"LOG: 正在处理第 {page_num} 页...")

                if page_num > 1:
                    # 翻页前再次检查代理
                    current_proxy = await get_proxy_with_fallback()
                    if current_proxy != proxy_address:
                        await log_to_database(task_id, 'INFO', f"翻页前代理更换: {proxy_address} -> {current_proxy}")
                        print(f"   [代理管理] 翻页前代理更换: {proxy_address} -> {current_proxy}")
                        await context.close()
                        context = await create_browser_context(browser, current_proxy)
                        page = await context.new_page()
                        proxy_address = current_proxy
                        await log_proxy_stats(task_id)
                    
                    # 翻页逻辑
                    await random_sleep(5, 10)
                    next_page_url = f"{search_url}&page={page_num}"
                    
                    try:
                        async with page.expect_response(lambda r: API_URL_PATTERN in r.url, timeout=30000) as response_info:
                            # 使用增强的页面导航函数进行翻页
                            navigation_success = await robust_page_goto(page, next_page_url, task_id, max_retries=2)
                            if not navigation_success:
                                raise Exception("翻页导航失败")
                        current_response = await response_info.value
                    except Exception as e:
                        # 网络错误时立即尝试更换代理
                        await log_to_database(task_id, 'WARNING', f"翻页时网络错误，尝试更换代理: {str(e)}")
                        print(f"   [网络错误] 翻页失败，立即尝试更换代理: {e}")
                        new_proxy = await handle_proxy_failure(task_id)
                        if new_proxy and new_proxy != proxy_address:
                            await context.close()
                            context = await create_browser_context(browser, new_proxy)
                            page = await context.new_page()
                            proxy_address = new_proxy
                            # 重试翻页
                            try:
                                async with page.expect_response(lambda r: API_URL_PATTERN in r.url, timeout=30000) as response_info:
                                    # 使用增强的页面导航函数重试翻页
                                    navigation_success = await robust_page_goto(page, next_page_url, task_id, max_retries=2)
                                    if not navigation_success:
                                        raise Exception("代理更换后翻页导航仍然失败")
                                current_response = await response_info.value
                            except Exception as retry_e:
                                await log_to_database(task_id, 'ERROR', f"更换代理后翻页仍失败: {str(retry_e)}")
                                print(f"   [网络错误] 更换代理后翻页仍失败: {retry_e}")
                                continue
                        else:
                            continue

                if not (current_response and current_response.ok):
                    await log_to_database(task_id, 'WARNING', f"第 {page_num} 页响应无效，跳过")
                    print(f"LOG: 第 {page_num} 页响应无效，跳过。")
                    continue

                basic_items = await _parse_search_results_json(await current_response.json(), f"第 {page_num} 页", task_id)
                if not basic_items: 
                    await log_to_database(task_id, 'INFO', f"第 {page_num} 页没有商品数据")
                    break

                await log_to_database(task_id, 'INFO', f"第 {page_num} 页解析到 {len(basic_items)} 个商品")

                total_items_on_page = len(basic_items)
                for i, item_data in enumerate(basic_items, 1):
                    if debug_limit > 0 and processed_item_count >= debug_limit:
                        await log_to_database(task_id, 'INFO', f"已达到调试上限 ({debug_limit})，停止获取新商品")
                        print(f"LOG: 已达到调试上限 ({debug_limit})，停止获取新商品。")
                        stop_scraping = True
                        break

                    unique_key = get_link_unique_key(item_data["商品链接"])
                    
                    # 检查商品是否已存在的逻辑
                    if unique_key in processed_links:
                        if SKIP_EXISTING_PRODUCTS:
                            await log_to_database(task_id, 'INFO', f"商品已存在，根据配置跳过: {item_data['商品标题'][:30]}...")
                            print(f"   -> [页内进度 {i}/{total_items_on_page}] 商品 '{item_data['商品标题'][:20]}...' 已存在，根据配置跳过。")
                            continue
                        else:
                            await log_to_database(task_id, 'INFO', f"商品已存在，但配置为重新获取: {item_data['商品标题'][:30]}...")
                            print(f"   -> [页内进度 {i}/{total_items_on_page}] 商品 '{item_data['商品标题'][:20]}...' 已存在，但将重新获取详情。")

                    await log_to_database(task_id, 'INFO', f"发现新商品: {item_data['商品标题'][:30]}...")
                    print(f"-> [页内进度 {i}/{total_items_on_page}] {'发现新商品' if unique_key not in processed_links else '重新获取商品'}，获取详情: {item_data['商品标题'][:30]}...")
                    
                    # 访问详情页前的等待时间
                    await random_sleep(3, 6)

                    detail_page = await context.new_page()
                    detail_fetch_success = False
                    detail_retry_count = 0
                    max_detail_retries = 3
                    
                    while not detail_fetch_success and detail_retry_count < max_detail_retries:
                        try:
                            detail_retry_count += 1
                            if detail_retry_count > 1:
                                await log_to_database(task_id, 'INFO', f"重试获取商品详情 (第{detail_retry_count}次): {item_data['商品标题'][:30]}...")
                                print(f"   -> 重试获取商品详情 (第{detail_retry_count}次)...")
                                # 重试前检查是否需要更换代理
                                current_proxy = await get_proxy_with_fallback()
                                if current_proxy != proxy_address:
                                    await log_to_database(task_id, 'INFO', f"重试前更换代理: {proxy_address} -> {current_proxy}")
                                    print(f"   [代理管理] 重试前更换代理: {proxy_address} -> {current_proxy}")
                                    await context.close()
                                    context = await create_browser_context(browser, current_proxy)
                                    page = await context.new_page()
                                    detail_page = await context.new_page()
                                    proxy_address = current_proxy
                                    await log_proxy_stats(task_id)
                                
                                # 重试前的指数退避延迟
                                retry_delay = min(10 * (2 ** (detail_retry_count - 2)), 60)
                                await asyncio.sleep(retry_delay)
                            
                            async with detail_page.expect_response(lambda r: DETAIL_API_URL_PATTERN in r.url, timeout=25000) as detail_info:
                                # 使用增强的页面导航函数访问商品详情页
                                navigation_success = await robust_page_goto(detail_page, item_data["商品链接"], task_id, max_retries=2, timeout=25000)
                                if not navigation_success:
                                    raise Exception("商品详情页导航失败")

                            detail_response = await detail_info.value
                            if detail_response.ok:
                                detail_json = await detail_response.json()

                                ret_string = str(await safe_get(detail_json, 'ret', default=[]))
                                if "FAIL_SYS_USER_VALIDATE" in ret_string:
                                    print("\n==================== CRITICAL BLOCK DETECTED ====================")
                                    print("检测到闲鱼反爬虫验证 (FAIL_SYS_USER_VALIDATE)，尝试更换代理...")
                                    
                                    # 立即尝试获取新代理
                                    new_proxy = await handle_proxy_failure(task_id)
                                    if new_proxy and new_proxy != proxy_address:
                                        print(f"   [代理] 更换为新代理: {new_proxy}")
                                        await context.close()
                                        context = await create_browser_context(browser, new_proxy)
                                        page = await context.new_page()
                                        proxy_address = new_proxy
                                        await log_proxy_stats(task_id)
                                        continue
                                    else:
                                        await log_to_database(task_id, 'ERROR', "无法获取新代理，执行长时间休眠后退出")
                                        print("   [代理] 无法获取新代理，执行长时间休眠...")
                                        long_sleep_duration = random.randint(300, 600)
                                        print(f"为避免账户风险，将执行一次长时间休眠 ({long_sleep_duration} 秒) 后再退出...")
                                        await asyncio.sleep(long_sleep_duration)
                                        print("长时间休眠结束，现在将安全退出。")
                                        print("===================================================================")
                                        stop_scraping = True
                                        break

                                # 解析商品详情数据并更新 item_data
                                item_do = await safe_get(detail_json, 'data', 'itemDO', default={})
                                seller_do = await safe_get(detail_json, 'data', 'sellerDO', default={})

                                reg_days_raw = await safe_get(seller_do, 'userRegDay', default=0)
                                registration_duration_text = format_registration_days(reg_days_raw)

                                # 1. 提取卖家的芝麻信用信息
                                zhima_credit_text = await safe_get(seller_do, 'zhimaLevelInfo', 'levelName')

                                # 2. 提取该商品的完整图片列表
                                image_infos = await safe_get(item_do, 'imageInfos', default=[])
                                if image_infos:
                                    all_image_urls = [img.get('url') for img in image_infos if img.get('url')]
                                    if all_image_urls:
                                        item_data['商品图片列表'] = all_image_urls
                                        item_data['商品主图链接'] = all_image_urls[0]

                                item_data['"想要"人数'] = await safe_get(item_do, 'wantCnt', default=item_data.get('"想要"人数', 'NaN'))
                                item_data['浏览量'] = await safe_get(item_do, 'browseCnt', default='-')

                                # 调用核心函数采集卖家信息
                                user_profile_data = {}
                                user_id = await safe_get(seller_do, 'sellerId')
                                if user_id:
                                    user_profile_data = await scrape_user_profile(context, str(user_id))
                                else:
                                    print("   [警告] 未能从详情API中获取到卖家ID。")
                                user_profile_data['卖家芝麻信用'] = zhima_credit_text
                                user_profile_data['卖家注册时长'] = registration_duration_text

                                detail_fetch_success = True
                                await log_to_database(task_id, 'INFO', f"成功获取商品详情: {item_data['商品标题'][:30]}...")
                                
                            else:
                                error_msg = f"详情页API响应失败: HTTP {detail_response.status}"
                                await log_to_database(task_id, 'WARNING', error_msg)
                                print(f"   -> {error_msg}")
                                if detail_retry_count >= max_detail_retries:
                                    # 最后一次重试失败，使用基础数据
                                    user_profile_data = {"获取状态": "详情页访问失败"}
                                    detail_fetch_success = True  # 标记为成功以继续处理
                                
                        except PlaywrightTimeoutError as e:
                            error_msg = f"访问商品详情页超时 (第{detail_retry_count}次尝试)"
                            await log_to_database(task_id, 'WARNING', error_msg)
                            print(f"   -> {error_msg}: {str(e)}")
                            
                            if detail_retry_count >= max_detail_retries:
                                # 超时重试次数用完，使用基础数据继续
                                user_profile_data = {"获取状态": "详情页访问超时"}
                                detail_fetch_success = True
                                
                        except Exception as e:
                            error_str = str(e)
                            
                            # 识别网络级别错误
                            is_network_error = any(keyword in error_str.lower() for keyword in [
                                'net::err_empty_response', 'net::err_connection_reset', 
                                'net::err_connection_refused', 'net::err_timed_out',
                                'connection reset', 'empty response', 'connection refused'
                            ])
                            
                            if is_network_error:
                                # 详细的商品详情网络错误信息
                                detail_error_info = {
                                    "error_type": "product_detail_network_error",
                                    "error_message": error_str,
                                    "product_id": item_data.get('商品ID', 'unknown'),
                                    "product_title": item_data.get('商品标题', 'unknown')[:50],
                                    "product_url": item_data.get('商品链接', 'unknown'),
                                    "retry_count": detail_retry_count,
                                    "max_retries": max_detail_retries,
                                    "current_proxy": proxy_address
                                }

                                error_msg = f"商品详情网络错误 (第{detail_retry_count}次): {error_str}"
                                await log_to_database(task_id, 'WARNING', error_msg, detail_error_info)
                                print(f"   -> {error_msg}")

                                # 网络错误时尝试切换代理
                                if detail_retry_count < max_detail_retries:
                                    await log_to_database(task_id, 'INFO', "商品详情获取网络错误，尝试切换代理", {
                                        "action": "attempting_proxy_switch",
                                        "product_id": item_data.get('商品ID', 'unknown')
                                    })
                                    print(f"   [网络错误] 商品详情获取失败，尝试切换代理...")

                                    new_proxy = await handle_proxy_failure(task_id)
                                    if new_proxy and new_proxy != proxy_address:
                                        try:
                                            # 关闭当前上下文
                                            await context.close()

                                            # 创建新的上下文和页面
                                            context = await create_browser_context(browser, new_proxy)
                                            page = await context.new_page()
                                            old_proxy = proxy_address
                                            proxy_address = new_proxy

                                            # 详细的代理切换成功信息
                                            switch_success_info = {
                                                "action": "product_detail_proxy_switch_success",
                                                "old_proxy": old_proxy,
                                                "new_proxy": proxy_address,
                                                "product_id": item_data.get('商品ID', 'unknown'),
                                                "trigger_error": error_str
                                            }

                                            await log_to_database(task_id, 'INFO', f"商品详情代理切换成功: {old_proxy} -> {proxy_address}", switch_success_info)
                                            print(f"   [代理切换] 商品详情获取代理切换成功: {proxy_address}")

                                            # 重置重试计数，给新代理一个机会
                                            detail_retry_count = 0
                                            continue

                                        except Exception as proxy_error:
                                            switch_error_info = {
                                                "action": "product_detail_proxy_switch_failed",
                                                "old_proxy": proxy_address,
                                                "target_proxy": new_proxy,
                                                "error_message": str(proxy_error),
                                                "product_id": item_data.get('商品ID', 'unknown')
                                            }

                                            await log_to_database(task_id, 'ERROR', f"商品详情代理切换失败: {str(proxy_error)}", switch_error_info)
                                            print(f"   [代理切换] 商品详情获取代理切换失败: {proxy_error}")

                                    # 增加延迟后重试
                                    retry_delay = random.randint(5, 15)
                                    await log_to_database(task_id, 'INFO', f"商品详情重试前延迟 {retry_delay} 秒", {
                                        "delay_seconds": retry_delay,
                                        "retry_reason": "product_detail_network_error",
                                        "product_id": item_data.get('商品ID', 'unknown')
                                    })
                                    print(f"   [网络错误] 商品详情获取重试前增加延迟...")
                                    await asyncio.sleep(retry_delay)
                                else:
                                    # 网络错误重试次数用完
                                    final_error_info = {
                                        "error_type": "product_detail_network_error_final",
                                        "product_id": item_data.get('商品ID', 'unknown'),
                                        "product_title": item_data.get('商品标题', 'unknown')[:50],
                                        "final_error": error_str,
                                        "total_retries": detail_retry_count
                                    }

                                    await log_to_database(task_id, 'ERROR', f"商品详情网络错误重试失败: {item_data['商品标题'][:30]}...", final_error_info)
                                    user_profile_data = {"获取状态": f"网络错误: {error_str}"}
                                    detail_fetch_success = True
                            else:
                                # 非网络错误，立即失败
                                error_msg = f"处理商品详情时发生错误: {error_str}"
                                await log_to_database(task_id, 'ERROR', error_msg)
                                print(f"   -> {error_msg}")
                                user_profile_data = {"获取状态": f"处理错误: {error_str}"}
                                detail_fetch_success = True

                    # 构建基础记录（无论详情获取是否成功）
                    final_record = {
                        "爬取时间": datetime.now().isoformat(),
                        "搜索关键字": keyword,
                        "任务名称": task_config.get('task_name', 'Untitled Task'),
                        "商品信息": item_data,
                        "卖家信息": user_profile_data,
                        "详情获取状态": "成功" if detail_fetch_success and user_profile_data.get("获取状态") is None else user_profile_data.get("获取状态", "失败")
                    }

                    # --- START: Real-time AI Analysis & Notification ---
                    print(f"   -> 开始对商品 #{item_data['商品ID']} 进行实时AI分析...")
                    # 1. Download images
                    image_urls = item_data.get('商品图片列表', [])
                    downloaded_image_paths = await download_all_images(item_data['商品ID'], image_urls)

                    # 2. Get AI analysis
                    ai_analysis_result = None
                    if ai_prompt_text:
                        try:
                            ai_analysis_result = await get_ai_analysis(final_record, downloaded_image_paths, prompt_text=ai_prompt_text)
                            if ai_analysis_result:
                                final_record['ai_analysis'] = ai_analysis_result
                                
                                # 检查是否是错误状态
                                if 'error' in ai_analysis_result:
                                    print(f"   -> AI分析失败: {ai_analysis_result.get('error', '未知错误')}")
                                else:
                                    print(f"   -> AI分析完成。推荐状态: {ai_analysis_result.get('is_recommended')}")
                            else:
                                final_record['ai_analysis'] = {'error': 'AI analysis returned None after retries.', 'status': 'failed'}
                                print(f"   -> AI分析失败: 重试后仍返回空结果")
                        except Exception as e:
                            print(f"   -> AI分析过程中发生严重错误: {e}")
                            final_record['ai_analysis'] = {'error': str(e), 'status': 'failed'}
                    else:
                        print("   -> 任务未配置AI prompt，跳过分析。")
                        final_record['ai_analysis'] = {'status': 'pending', 'reason': 'No AI prompt configured'}

                    # 3. Send notification if recommended (only for successful analysis)
                    if ai_analysis_result and ai_analysis_result.get('is_recommended') and 'error' not in ai_analysis_result:
                        print(f"   -> 商品被AI推荐，准备发送通知...")
                        
                        # 发送ntfy通知
                        await send_ntfy_notification(item_data, ai_analysis_result.get("reason", "无"))
                        print(f"   -> 邮件通知条件检查: email_enabled={email_enabled}, email_address={email_address}, smtp_configured={email_sender.is_configured()}")
                        # 发送邮件通知
                        if email_enabled and email_address and email_sender.is_configured():
                            print(f"   -> 准备发送邮件通知到: {email_address}")
                            await log_to_database(task_id, 'INFO', f"准备发送邮件通知: {final_record['商品信息']['商品标题'][:30]}...")
                            try:
                                email_success = await email_sender.send_product_notification(
                                    email_address,
                                    final_record,
                                    ai_analysis_result,
                                    task_name
                                )
                                
                                if email_success:
                                    print(f"   -> 邮件通知发送成功")
                                    await db.log_email_send(
                                        task_id, 
                                        processed_item_count,  # 使用商品序号作为临时ID
                                        email_address,
                                        f"🚨 闲鱼推荐 | {item_data['商品标题'][:30]}...",
                                        "success"
                                    )
                                else:
                                    print(f"   -> 邮件通知发送失败")
                                    await db.log_email_send(
                                        task_id,
                                        processed_item_count,
                                        email_address,
                                        f"🚨 闲鱼推荐 | {item_data['商品标题'][:30]}...",
                                        "failed",
                                        "邮件发送失败"
                                    )
                            except Exception as e:
                                print(f"   -> 邮件通知发送异常: {e}")
                                await db.log_email_send(
                                    task_id,
                                    processed_item_count,
                                    email_address,
                                    f"🚨 闲鱼推荐 | {item_data['商品标题'][:30]}...",
                                    "error",
                                    str(e)
                                )
                        elif email_enabled and email_address:
                            print(f"   -> 邮件通知已启用但SMTP配置不完整，跳过邮件发送")
                    # --- END: Real-time AI Analysis & Notification ---

                    # 4. 保存包含AI结果的完整记录到数据库
                    await save_to_database(final_record, task_id)

                    processed_links.add(unique_key)
                    processed_item_count += 1
                    print(f"   -> 商品处理流程完毕。累计处理 {processed_item_count} 个新商品。")

                    # --- 修改: 增加单个商品处理后的主要延迟 ---
                    print("   [反爬] 执行一次主要的随机延迟以模拟用户浏览间隔...")
                    await random_sleep(15, 30)

                    await detail_page.close()
                    await random_sleep(2, 4)

                # 页面间休息
                if not stop_scraping and page_num < max_pages:
                    await log_to_database(task_id, 'INFO', f"第 {page_num} 页处理完毕，准备翻页")
                    print(f"--- 第 {page_num} 页处理完毕，准备翻页。执行一次页面间的长时休息... ---")
                    await random_sleep(25, 50)

        except PlaywrightTimeoutError as e:
            await log_to_database(task_id, 'ERROR', f"操作超时: {str(e)}")
            print(f"\n操作超时错误: 页面元素或网络响应未在规定时间内出现。\n{e}")
        except Exception as e:
            await log_to_database(task_id, 'ERROR', f"爬取过程中发生错误: {str(e)}")
            print(f"\n爬取过程中发生未知错误: {e}")
        finally:
            # 记录最终的代理使用统计
            await log_proxy_stats(task_id)
            await log_to_database(task_id, 'INFO', f"任务执行完毕，共处理 {processed_item_count} 个新商品")
            print("\nLOG: 任务执行完毕，浏览器将在5秒后自动关闭...")
            await asyncio.sleep(5)
            if debug_limit:
                input("按回车键关闭浏览器...")
            await browser.close()

    # 记录任务执行完毕到数据库
    await log_to_database(task_id, 'INFO', f"任务执行完毕，共处理 {processed_item_count} 个新商品",
                        {"processed_count": processed_item_count})

    logger.info(f"任务完成，共处理 {processed_item_count} 个新商品")
    return processed_item_count

def setup_task_logger(task_id: int, task_name: str):
    """为每个任务设置独立的日志记录器"""
    logger = logging.getLogger(f"task_{task_id}")
    logger.setLevel(logging.INFO)
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    # 创建日志目录
    os.makedirs("logs", exist_ok=True)
    
    # 创建文件handler
    log_file = f"logs/{task_id}.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    
    # 创建控制台handler
    console_handler = logging.StreamHandler()
    
    # 设置格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

async def main():
    """
    主程序入口函数

    解析命令行参数，从数据库加载任务配置，并发执行所有爬取任务。
    支持调试模式、任务筛选等功能。
    """
    parser = argparse.ArgumentParser(
        description="闲鱼商品监控脚本，支持多任务配置和实时AI分析。",
        epilog="""
使用示例:
  # 运行数据库中定义的所有启用任务
  python spider_v2.py

  # 调试模式: 运行所有任务，但每个任务只处理前3个新发现的商品
  python spider_v2.py --debug-limit 3
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--debug-limit", type=int, default=0, help="调试模式：每个任务仅处理前 N 个新商品（0 表示无限制）")
    args = parser.parse_args()

    # 记录当前配置
    print(f"当前配置 - 跳过已存在商品: {'是' if SKIP_EXISTING_PRODUCTS else '否'}")

    # 初始化数据库
    await db.init_database()
    
    try:
        # 从数据库获取启用的任务配置
        tasks_config = await db.get_enabled_tasks()
    except Exception as e:
        sys.exit(f"错误: 从数据库获取任务配置失败: {e}")

    if not tasks_config:
        print("数据库中没有启用的任务。请通过Web界面添加任务。")
        return

    # 转换数据库格式为原有的任务配置格式
    converted_tasks = []
    for task in tasks_config:
        converted_task = {
            'task_id': task['id'],
            'task_name': task['task_name'],
            'keyword': task['keyword'],
            'max_pages': task.get('max_pages', 3),
            'personal_only': task.get('personal_only', True),
            'ai_prompt_text': task.get('ai_prompt_text', ''),
            'email_enabled': task.get('email_enabled', False),
            'email_address': task.get('email_address', '')
        }
        
        # 添加价格范围（如果存在）
        if task.get('min_price'):
            converted_task['min_price'] = task['min_price']
        if task.get('max_price'):
            converted_task['max_price'] = task['max_price']
            
        converted_tasks.append(converted_task)

    print("\n--- 开始执行监控任务 ---")
    if args.debug_limit > 0:
        print(f"** 调试模式已激活，每个任务最多处理 {args.debug_limit} 个新商品 **")
    print("--------------------")

    if not converted_tasks:
        print("没有启用的任务，程序退出。")
        return

    # 为每个启用的任务创建一个异步执行协程
    coroutines = []
    for task_conf in converted_tasks:
        print(f"-> 任务 '{task_conf['task_name']}' 已加入执行队列。")
        coroutines.append(scrape_xianyu(task_config=task_conf, debug_limit=args.debug_limit))

    # 并发执行所有任务
    results = await asyncio.gather(*coroutines, return_exceptions=True)

    print("\n--- 所有任务执行完毕 ---")
    for i, result in enumerate(results):
        task_name = converted_tasks[i]['task_name']
        task_id = converted_tasks[i]['task_id']
        if isinstance(result, Exception):
            error_message = f"任务 '{task_name}' 因异常而终止: {result}"
            print(error_message)
            # 记录异常到数据库
            await log_to_database(task_id, 'ERROR', error_message)
        else:
            completion_message = f"任务 '{task_name}' 正常结束，本次运行共处理了 {result} 个新商品。"
            print(completion_message)
            # 记录任务完成到数据库
            await log_to_database(task_id, 'INFO', completion_message,
                                {"processed_count": result, "status": "completed"})


@retry_on_failure(retries=3, delay=2)
async def get_proxy() -> Optional[str]:
    """
    从代理API获取代理地址
    返回格式: "ip:port" 或 None (如果获取失败)
    """
    if not PROXY_API_URL:
        print("   [代理] 未配置代理API URL")
        return None
        
    try:
        print("   [代理] 正在从API获取代理地址...")
        loop = asyncio.get_running_loop()
        
        # 使用 run_in_executor 执行同步请求
        response = await loop.run_in_executor(
            None,
            lambda: requests.get(PROXY_API_URL, timeout=10)
        )
        response.raise_for_status()
        
        data = response.json()
        
        # 验证响应格式
        if data.get('code') != 200:
            print(f"   [代理] API返回错误: {data.get('msg', '未知错误')}")
            return None
            
        proxy_list = data.get('data', {}).get('proxy_list', [])
        if not proxy_list:
            print("   [代理] API返回的代理列表为空")
            return None
            
        proxy_address = proxy_list[0]
        print(f"   [代理] 成功获取代理: {proxy_address}")
        return proxy_address
        
    except requests.exceptions.RequestException as e:
        print(f"   [代理] 网络请求失败: {e}")
        raise
    except json.JSONDecodeError as e:
        print(f"   [代理] JSON解析失败: {e}")
        raise
    except Exception as e:
        print(f"   [代理] 获取代理时发生未知错误: {e}")
        raise

async def get_proxy_with_fallback(force_refresh: bool = False) -> Optional[str]:
    """
    获取代理地址（带回退机制）

    通过代理管理器获取可用的代理地址，支持定时自动更换和强制刷新。
    当代理获取失败时提供优雅的错误处理。

    Args:
        force_refresh (bool): 是否强制刷新代理，忽略时间间隔限制

    Returns:
        Optional[str]: 代理地址字符串（格式：ip:port）或None（获取失败时）
    """
    try:
        return await proxy_manager.get_fresh_proxy(force_refresh=force_refresh)
    except Exception as e:
        print(f"   [代理管理] 获取代理时发生错误: {e}")
        return None

async def handle_proxy_failure(task_id: int) -> Optional[str]:
    """
    代理失效处理函数

    当检测到当前代理失效时，立即尝试获取新的代理地址。
    包含完整的日志记录和错误处理机制。

    Args:
        task_id (int): 任务ID，用于关联日志记录和错误追踪

    Returns:
        Optional[str]: 新的代理地址或None（如果无法获取新代理）
    """
    await log_to_database(task_id, 'WARNING', "检测到代理失效，立即尝试更换代理")
    print("   [代理管理] 检测到代理失效，立即尝试更换代理...")
    
    # 强制刷新代理
    new_proxy = await get_proxy_with_fallback(force_refresh=True)
    
    if new_proxy:
        await log_to_database(task_id, 'INFO', f"成功更换为新代理: {new_proxy}")
        print(f"   [代理管理] 成功更换为新代理: {new_proxy}")
        # 记录代理使用
        proxy_manager.record_usage()
    else:
        await log_to_database(task_id, 'ERROR', "无法获取新代理，将继续无代理模式")
        print("   [代理管理] 无法获取新代理，将继续无代理模式")
        
    return new_proxy

async def log_proxy_stats(task_id: int):
    """记录代理使用统计到数据库"""
    stats = proxy_manager.get_proxy_stats()
    
    if stats["status"] == "active":
        await log_to_database(task_id, 'INFO', 
            f"代理使用统计 - 地址: {stats['address']}, "
            f"使用时长: {stats['usage_time']:.1f}秒, "
            f"使用次数: {stats['usage_count']}, "
            f"剩余时间: {stats['remaining_time']:.1f}秒"
        )

if __name__ == "__main__":
    asyncio.run(main())
