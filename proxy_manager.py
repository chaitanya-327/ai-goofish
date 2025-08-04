"""
代理管理模块

该模块提供代理池管理功能，用于管理和轮换爬虫的代理IP。
支持定时自动更换代理、代理失效检测、使用统计等功能。

主要功能：
- 代理池管理和自动轮换
- 代理使用统计和监控
- 失效代理检测和处理
- API集成支持

作者：AI Assistant
创建时间：2025-08-04
"""

import asyncio
import time
import json
import requests
from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class ProxyInfo:
    """
    代理信息数据类
    
    存储单个代理的基本信息和使用统计。
    
    Attributes:
        address (str): 代理地址，格式为 "ip:port"
        start_time (float): 代理开始使用的时间戳
        usage_count (int): 代理的使用次数计数
    """
    address: str
    start_time: float
    usage_count: int = 0


class ProxyManager:
    """
    代理管理器

    负责代理的获取、更换和监控，支持定时自动更换代理以避免IP被封禁。
    提供代理池管理、失效检测、使用统计等功能。

    Attributes:
        current_proxy (Optional[ProxyInfo]): 当前正在使用的代理信息
        refresh_interval (int): 代理刷新间隔时间（秒）
        proxy_api_url (str): 代理API的URL地址
        proxy_enabled (bool): 是否启用代理功能
        proxy_retry_count (int): 代理获取重试次数
        log_callback (callable): 日志回调函数，用于记录到数据库
        task_id (int): 当前任务ID，用于日志记录
    """

    def __init__(self, proxy_api_url: str = None, proxy_enabled: bool = False,
                 refresh_interval: int = 1800, retry_count: int = 3,
                 log_callback=None, task_id: int = None):
        """
        初始化代理管理器

        Args:
            proxy_api_url (str): 代理API的URL地址
            proxy_enabled (bool): 是否启用代理功能
            refresh_interval (int): 代理刷新间隔时间（秒），默认30分钟
            retry_count (int): 代理获取重试次数，默认3次
            log_callback (callable): 日志回调函数，用于记录到数据库
            task_id (int): 当前任务ID，用于日志记录
        """
        self.current_proxy: Optional[ProxyInfo] = None
        self.refresh_interval = refresh_interval
        self.proxy_api_url = proxy_api_url or os.getenv('PROXY_API_URL')
        self.proxy_enabled = proxy_enabled or (os.getenv('PROXY_ENABLED', 'false').lower() == 'true')
        self.proxy_retry_count = retry_count or int(os.getenv('PROXY_RETRY_COUNT', '3'))
        self.log_callback = log_callback
        self.task_id = task_id

    def set_log_context(self, log_callback, task_id: int):
        """
        设置日志记录上下文

        Args:
            log_callback (callable): 日志回调函数
            task_id (int): 任务ID
        """
        self.log_callback = log_callback
        self.task_id = task_id

    async def _log(self, level: str, message: str):
        """
        内部日志记录方法

        Args:
            level (str): 日志级别
            message (str): 日志消息
        """
        # 同时输出到控制台和数据库
        print(f"   [代理管理] {message}")
        if self.log_callback and self.task_id:
            try:
                await self.log_callback(self.task_id, level, f"[代理管理] {message}")
            except Exception as e:
                print(f"   [代理管理] 记录数据库日志失败: {e}")

    async def get_fresh_proxy(self, force_refresh: bool = False) -> Optional[str]:
        """
        获取新鲜的代理地址
        
        检查当前代理是否需要更换，如果需要则获取新的代理地址。
        支持强制刷新和定时自动刷新。
        
        Args:
            force_refresh (bool): 是否强制刷新代理，不考虑时间间隔
            
        Returns:
            Optional[str]: 代理地址字符串或None
        """
        if not self.proxy_enabled:
            await self._log('INFO', "代理功能已禁用")
            return None

        current_time = time.time()

        # 检查是否需要更换代理
        need_refresh = (
            force_refresh or
            self.current_proxy is None or
            (current_time - self.current_proxy.start_time) >= self.refresh_interval
        )

        if need_refresh:
            await self._log('INFO', f"触发代理更换 - 强制刷新: {force_refresh}, 当前代理: {self.current_proxy.address if self.current_proxy else '无'}")

            if self.current_proxy:
                usage_time = current_time - self.current_proxy.start_time
                await self._log('INFO', f"当前代理使用时长: {usage_time:.1f}秒, 刷新间隔: {self.refresh_interval}秒")
            await self._refresh_proxy()
            
        return self.current_proxy.address if self.current_proxy else None
    
    async def _refresh_proxy(self):
        """
        内部方法：刷新代理
        
        获取新的代理地址并更新当前代理信息。
        包含重试逻辑和详细的日志记录。
        """
        old_proxy = self.current_proxy.address if self.current_proxy else "无"
        old_usage_time = 0
        old_usage_count = 0
        
        if self.current_proxy:
            old_usage_time = time.time() - self.current_proxy.start_time
            old_usage_count = self.current_proxy.usage_count

        await self._log('INFO', "开始更换代理...")
        await self._log('INFO', f"旧代理: {old_proxy}, 使用时长: {old_usage_time:.1f}秒, 使用次数: {old_usage_count}")

        # 获取新代理
        for attempt in range(self.proxy_retry_count):
            try:
                new_proxy_address = await self._fetch_proxy_from_api()
                if new_proxy_address and new_proxy_address != old_proxy:
                    self.current_proxy = ProxyInfo(
                        address=new_proxy_address,
                        start_time=time.time()
                    )
                    await self._log('INFO', f"成功更换为新代理: {new_proxy_address}")
                    return
                elif new_proxy_address == old_proxy:
                    await self._log('WARNING', "API返回相同代理，重试获取...")
                    await asyncio.sleep(1)
                    continue
            except Exception as e:
                await self._log('WARNING', f"第 {attempt + 1}/{self.proxy_retry_count} 次获取新代理失败: {e}")
                if attempt < self.proxy_retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # 指数退避

        await self._log('ERROR', "所有代理获取尝试均失败，将继续使用旧代理或无代理模式")
        
    async def _fetch_proxy_from_api(self) -> Optional[str]:
        """
        从API获取代理地址
        
        调用代理API获取新的代理地址，支持异步操作。
        
        Returns:
            Optional[str]: 代理地址或None
            
        Raises:
            Exception: 当API调用失败时抛出异常
        """
        if not self.proxy_api_url:
            await self._log('WARNING', "未配置代理API URL")
            return None

        try:
            loop = asyncio.get_running_loop()

            # 使用 run_in_executor 执行同步请求
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(self.proxy_api_url, timeout=10)
            )
            response.raise_for_status()

            data = response.json()

            # 验证响应格式
            if data.get('code') != 200:
                await self._log('ERROR', f"API返回错误: {data.get('msg', '未知错误')}")
                return None

            proxy_list = data.get('data', {}).get('proxy_list', [])
            if not proxy_list:
                await self._log('WARNING', "API返回的代理列表为空")
                return None

            return proxy_list[0]

        except requests.exceptions.RequestException as e:
            await self._log('ERROR', f"网络请求失败: {e}")
            raise
        except json.JSONDecodeError as e:
            await self._log('ERROR', f"JSON解析失败: {e}")
            raise
        except Exception as e:
            await self._log('ERROR', f"获取代理时发生未知错误: {e}")
            raise
    
    def record_usage(self):
        """
        记录代理使用次数
        
        增加当前代理的使用计数，用于统计和监控。
        """
        if self.current_proxy:
            self.current_proxy.usage_count += 1
            
    def get_proxy_stats(self) -> dict:
        """
        获取当前代理的使用统计
        
        返回当前代理的详细使用统计信息，包括使用时长、次数等。
        
        Returns:
            dict: 代理统计信息字典
        """
        if not self.current_proxy:
            return {"status": "no_proxy"}
            
        current_time = time.time()
        usage_time = current_time - self.current_proxy.start_time
        remaining_time = max(0, self.refresh_interval - usage_time)
        
        return {
            "status": "active",
            "address": self.current_proxy.address,
            "usage_time": usage_time,
            "usage_count": self.current_proxy.usage_count,
            "remaining_time": remaining_time,
            "refresh_interval": self.refresh_interval
        }
