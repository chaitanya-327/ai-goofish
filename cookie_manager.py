"""
Cookie管理模块

该模块提供Cookie池管理功能，用于管理和轮换闲鱼爬虫的登录状态。
支持从数据库获取可用Cookie，自动轮换失效Cookie，以及状态管理。

主要功能：
- Cookie池管理和轮换
- Cookie状态监控和更新
- 失效Cookie自动标记
- 数据库集成支持

作者：AI Assistant
创建时间：2025-08-04
"""

import json
from typing import Optional, Dict, Any


class CookieManager:
    """
    Cookie池管理器
    
    负责管理闲鱼爬虫的Cookie池，包括获取可用Cookie、标记失效Cookie、
    以及在多个Cookie之间进行轮换以避免单个账号被封禁。
    
    Attributes:
        db: 数据库实例，用于存储和获取Cookie信息
        current_cookie_id: 当前正在使用的Cookie ID
    """
    
    def __init__(self, db_instance, log_callback=None, task_id: int = None):
        """
        初始化Cookie管理器

        Args:
            db_instance: 数据库实例，必须实现Cookie相关的数据库操作方法
            log_callback (callable): 日志回调函数，用于记录到数据库
            task_id (int): 当前任务ID，用于日志记录
        """
        self.db = db_instance
        self.current_cookie_id = None
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
        print(f"   [Cookie管理] {message}")
        if self.log_callback and self.task_id:
            try:
                await self.log_callback(self.task_id, level, f"[Cookie管理] {message}")
            except Exception as e:
                print(f"   [Cookie管理] 记录数据库日志失败: {e}")
        
    async def get_available_cookie(self) -> Optional[Dict[str, Any]]:
        """
        获取可用的Cookie
        
        从数据库中获取状态为活跃的Cookie，使用轮询策略选择最久未使用的Cookie。
        如果数据库中没有可用Cookie，则返回None。
        
        Returns:
            Dict[str, Any]: Cookie数据字典，包含浏览器状态信息，如果无可用Cookie则返回None
            
        Raises:
            Exception: 当数据库操作失败时抛出异常
        """
        try:
            # 首先尝试从数据库获取可用Cookie
            active_cookies = await self.db.get_active_cookies()
            
            if active_cookies:
                # 使用轮询策略：选择最久未使用的Cookie
                selected_cookie = active_cookies[0]
                self.current_cookie_id = selected_cookie['id']
                
                # 更新使用时间
                await self.db.update_cookie_last_used(self.current_cookie_id)
                
                # 解析Cookie值
                cookie_data = json.loads(selected_cookie['cookie_value'])
                await self._log('INFO', f"使用Cookie: {selected_cookie['name']} (ID: {selected_cookie['id']})")
                return cookie_data

            # 如果数据库中没有可用Cookie，回退到文件模式
            await self._log('WARNING', "数据库中无可用Cookie，尝试使用状态文件")
            return None

        except Exception as e:
            await self._log('ERROR', f"获取Cookie失败: {e}")
            return None
    
    async def mark_cookie_invalid(self, reason: str = "访问失败"):
        """
        标记当前Cookie为无效
        
        将当前正在使用的Cookie标记为过期状态，使其不再被选择使用。
        这通常在检测到Cookie失效或访问被拒绝时调用。
        
        Args:
            reason (str): 标记为无效的原因，用于日志记录和调试
        """
        if self.current_cookie_id:
            try:
                await self.db.update_cookie(self.current_cookie_id, status='expired')
                await self._log('INFO', f"Cookie {self.current_cookie_id} 已标记为过期: {reason}")
            except Exception as e:
                await self._log('ERROR', f"标记Cookie失败: {e}")
    
    async def switch_to_next_cookie(self) -> Optional[Dict[str, Any]]:
        """
        切换到下一个可用Cookie
        
        标记当前Cookie为无效，然后获取下一个可用的Cookie。
        这是一个便捷方法，用于在当前Cookie出现问题时快速切换。
        
        Returns:
            Dict[str, Any]: 新的Cookie数据字典，如果无可用Cookie则返回None
        """
        if self.current_cookie_id:
            await self.mark_cookie_invalid("主动切换")
        
        return await self.get_available_cookie()
