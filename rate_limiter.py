"""
请求速率限制模块

该模块提供请求速率限制功能，用于控制爬虫的请求频率，
防止触发目标网站的反爬虫机制。支持自适应延迟调整和错误恢复。

主要功能：
- 请求频率控制
- 自适应延迟调整
- 错误次数统计和恢复
- 智能延迟策略

作者：AI Assistant
创建时间：2025-08-04
"""

import time
import asyncio
import random
from typing import List


async def adaptive_sleep(base_min: float = 3.0, base_max: float = 7.0, error_count: int = 0, task_id: int = None, log_callback=None):
    """
    自适应延迟函数

    根据错误次数动态调整延迟时间，错误越多延迟越长，用于应对反爬虫机制。

    Args:
        base_min (float): 基础最小延迟时间（秒）
        base_max (float): 基础最大延迟时间（秒）
        error_count (int): 连续错误次数，用于增加延迟
        task_id (int): 任务ID，用于数据库日志记录
        log_callback: 日志回调函数
    """
    # 根据错误次数增加延迟
    multiplier = 1 + (error_count * 0.5)  # 每次错误增加50%延迟
    min_delay = base_min * multiplier
    max_delay = base_max * multiplier

    # 限制最大延迟时间
    min_delay = min(min_delay, 30.0)
    max_delay = min(max_delay, 60.0)

    delay = random.uniform(min_delay, max_delay)
    message = f"自适应延迟等待 {delay:.2f} 秒 (错误次数: {error_count}, 倍数: {multiplier:.1f}x)"
    print(f"   [自适应延迟] {message}")

    # 记录到数据库
    if task_id and log_callback:
        await log_callback(task_id, 'INFO', message)

    await asyncio.sleep(delay)


class RateLimiter:
    """
    请求速率限制器
    
    防止触发反爬虫机制，通过控制请求频率和自适应延迟来避免被目标网站封禁。
    支持基于错误次数的自适应延迟调整和请求历史记录。
    
    Attributes:
        request_times (List[float]): 最近请求的时间戳列表
        error_count (int): 连续错误次数计数
        last_error_time (float): 最后一次错误的时间戳
        max_requests_per_minute (int): 每分钟最大请求数
        high_frequency_threshold (int): 高频请求阈值
        medium_frequency_threshold (int): 中频请求阈值
    """

    def __init__(self, max_requests_per_minute: int = 10, 
                 high_frequency_threshold: int = 10,
                 medium_frequency_threshold: int = 5):
        """
        初始化速率限制器
        
        Args:
            max_requests_per_minute (int): 每分钟最大请求数，默认10
            high_frequency_threshold (int): 高频请求阈值，默认10
            medium_frequency_threshold (int): 中频请求阈值，默认5
        """
        self.request_times: List[float] = []
        self.error_count: int = 0
        self.last_error_time: float = 0
        self.max_requests_per_minute = max_requests_per_minute
        self.high_frequency_threshold = high_frequency_threshold
        self.medium_frequency_threshold = medium_frequency_threshold

    async def wait_if_needed(self, task_id: int = None, log_callback=None):
        """
        根据请求历史和错误情况决定是否需要等待

        分析最近的请求频率和错误情况，智能调整延迟时间。
        请求越频繁，延迟越长；错误越多，延迟也越长。

        Args:
            task_id (int, optional): 任务ID，用于日志记录
            log_callback (callable, optional): 日志回调函数，用于记录到数据库
        """
        current_time = time.time()

        # 清理超过1分钟的请求记录
        self.request_times = [t for t in self.request_times if current_time - t < 60]

        # 根据请求频率决定延迟策略
        recent_requests = len(self.request_times)

        if recent_requests >= self.high_frequency_threshold:
            # 高频请求：增加较长延迟
            message = "检测到请求频率过高，增加延迟..."
            if task_id and log_callback:
                await log_callback(task_id, 'INFO', message)
            else:
                await self._log_rate_limit(task_id, message)
            await adaptive_sleep(5.0, 12.0, self.error_count, task_id, log_callback)
        elif recent_requests >= self.medium_frequency_threshold:
            # 中频请求：增加中等延迟
            await adaptive_sleep(3.0, 8.0, self.error_count, task_id, log_callback)
        else:
            # 低频请求：基础延迟
            await adaptive_sleep(2.0, 5.0, self.error_count, task_id, log_callback)

        # 记录本次请求时间
        self.request_times.append(current_time)

    def record_error(self):
        """
        记录错误
        
        增加错误计数，用于调整后续请求的延迟策略。
        连续错误会导致更长的延迟时间。
        """
        self.error_count += 1
        self.last_error_time = time.time()

    def record_success(self):
        """
        记录成功
        
        重置或减少错误计数，表示系统恢复正常。
        成功的请求会逐渐减少延迟时间。
        """
        # 成功后逐渐减少错误计数
        if self.error_count > 0:
            self.error_count = max(0, self.error_count - 1)

    def get_stats(self) -> dict:
        """
        获取速率限制器统计信息
        
        返回当前的请求频率、错误次数等统计信息。
        
        Returns:
            dict: 统计信息字典，包含请求次数、错误次数、最后错误时间等
        """
        current_time = time.time()
        
        # 清理过期的请求记录
        recent_requests = [t for t in self.request_times if current_time - t < 60]
        
        return {
            "recent_requests_count": len(recent_requests),
            "max_requests_per_minute": self.max_requests_per_minute,
            "error_count": self.error_count,
            "last_error_time": self.last_error_time,
            "time_since_last_error": current_time - self.last_error_time if self.last_error_time > 0 else 0,
            "current_frequency_level": self._get_frequency_level(len(recent_requests))
        }
    
    def _get_frequency_level(self, request_count: int) -> str:
        """
        获取当前请求频率级别
        
        Args:
            request_count (int): 最近一分钟的请求次数
            
        Returns:
            str: 频率级别描述
        """
        if request_count >= self.high_frequency_threshold:
            return "高频"
        elif request_count >= self.medium_frequency_threshold:
            return "中频"
        else:
            return "低频"
    
    async def _log_rate_limit(self, task_id: int, message: str):
        """
        记录速率限制日志
        
        Args:
            task_id (int): 任务ID
            message (str): 日志消息
        """
        # 这里可以集成数据库日志记录
        # 为了避免循环导入，暂时使用print
        print(f"   [速率限制] 任务{task_id}: {message}")

    def reset(self):
        """
        重置速率限制器
        
        清空所有请求历史和错误计数，用于重新开始计算。
        """
        self.request_times.clear()
        self.error_count = 0
        self.last_error_time = 0
        print("   [速率限制] 速率限制器已重置")
