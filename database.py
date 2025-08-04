import sqlite3
import json
import asyncio
import aiosqlite
from datetime import datetime
from typing import Dict, List, Optional, Any
import os

class XianyuDatabase:
    def __init__(self, db_path: str = "xianyu_monitor.db"):
        self.db_path = db_path
        
    async def init_database(self):
        """初始化数据库和表结构"""
        async with aiosqlite.connect(self.db_path) as db:
            # 创建任务表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT UNIQUE NOT NULL,
                    keyword TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT 1,
                    max_pages INTEGER DEFAULT 3,
                    personal_only BOOLEAN DEFAULT 0,
                    min_price TEXT,
                    max_price TEXT,
                    ai_prompt_text TEXT,
                    email_address TEXT,
                    email_enabled BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 创建Cookie管理表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cookies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    cookie_value TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    last_used TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 检查并添加新字段（用于数据库迁移）
            await self._add_column_if_not_exists(db, 'tasks', 'email_address', 'TEXT')
            await self._add_column_if_not_exists(db, 'tasks', 'email_enabled', 'BOOLEAN DEFAULT 0')

            # 为products表添加updated_at字段（SQLite不支持CURRENT_TIMESTAMP作为默认值，使用NULL）
            await self._add_column_if_not_exists(db, 'products', 'updated_at', 'TIMESTAMP')
            
            # 创建商品表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    product_id TEXT NOT NULL,
                    title TEXT,
                    price TEXT,
                    link TEXT UNIQUE,
                    location TEXT,
                    seller_nick TEXT,
                    detail_fetch_status TEXT DEFAULT '成功',
                    product_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks (id)
                )
            """)
            
            # 创建AI分析表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ai_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    analysis_status TEXT DEFAULT 'pending',
                    is_recommended BOOLEAN,
                    reason TEXT,
                    full_response TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks (id),
                    FOREIGN KEY (product_id) REFERENCES products (id)
                )
            """)
            
            # 创建任务日志表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS task_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks (id)
                )
            """)
            
            # 创建邮件发送记录表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS email_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    product_id INTEGER,
                    email_address TEXT NOT NULL,
                    subject TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks (id),
                    FOREIGN KEY (product_id) REFERENCES products (id)
                )
            """)
            
            await db.commit()
            print("数据库初始化完成，Cookie表已创建")

    async def _add_column_if_not_exists(self, db, table_name: str, column_name: str, column_definition: str):
        """如果列不存在则添加列（用于数据库迁移）"""
        try:
            # 检查列是否存在
            cursor = await db.execute(f"PRAGMA table_info({table_name})")
            columns = await cursor.fetchall()
            column_names = [column[1] for column in columns]
            
            if column_name not in column_names:
                await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
                print(f"已添加列 {table_name}.{column_name}")
        except Exception as e:
            print(f"添加列失败 {table_name}.{column_name}: {e}")

    async def get_enabled_tasks(self):
        """获取启用的任务列表"""
        async with aiosqlite.connect(self.db_path) as database:
            database.row_factory = aiosqlite.Row
            async with database.execute("SELECT * FROM tasks WHERE enabled = 1") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_task_id_by_name(self, task_name: str):
        """根据任务名称获取任务ID"""
        async with aiosqlite.connect(self.db_path) as database:
            async with database.execute("SELECT id FROM tasks WHERE task_name = ?", (task_name,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def save_product(self, product_data: Dict) -> Optional[int]:
        """保存商品信息到数据库"""
        item_info = product_data.get('商品信息', {})
        seller_info = product_data.get('卖家信息', {})
        task_id = product_data.get('task_id')
        detail_status = product_data.get('详情获取状态', '成功')
        
        product_id = item_info.get('商品ID')
        if not product_id:
            return None
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO products 
                (product_id, title, price, seller_name, seller_credit, product_url, 
                 image_paths, product_data, task_id, discovered_at, detail_fetch_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product_id,
                item_info.get('商品标题'),
                item_info.get('当前售价'),
                seller_info.get('卖家昵称') or item_info.get('卖家昵称'),
                seller_info.get('卖家信用等级'),
                item_info.get('商品链接'),
                json.dumps(product_data.get('图片路径', [])),
                json.dumps(product_data, ensure_ascii=False),
                task_id,
                datetime.now().isoformat(),
                detail_status
            ))
            await db.commit()
            
            # 获取插入的product ID
            async with db.execute("SELECT id FROM products WHERE product_id = ? AND task_id = ?", (product_id, task_id)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def save_ai_analysis(self, task_id: int, product_db_id: int, ai_analysis: Dict, status: str = 'completed'):
        """保存AI分析结果"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO ai_analysis 
                (task_id, product_id, analysis_status, is_recommended, reason, full_response)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                task_id,
                product_db_id,
                status,
                ai_analysis.get('is_recommended', None) if status == 'completed' else None,
                ai_analysis.get('reason', ai_analysis.get('error', '')),
                json.dumps(ai_analysis, ensure_ascii=False)
            ))
            await db.commit()

    async def log_task_event(self, task_id: int, level: str, message: str, details: dict = None):
        """记录任务事件日志"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO task_logs (task_id, level, message, details)
                VALUES (?, ?, ?, ?)
            """, (
                task_id,
                level,
                message,
                json.dumps(details, ensure_ascii=False) if details else None
            ))
            await db.commit()

    async def get_processed_product_links(self, task_id: int):
        """获取已处理的商品链接集合"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT product_id FROM products WHERE task_id = ?", (task_id,)) as cursor:
                rows = await cursor.fetchall()
                return {row[0] for row in rows}

    async def get_failed_detail_products(self, task_id: int = None):
        """获取详情获取失败的商品列表"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            query = """
                SELECT * FROM products
                WHERE detail_fetch_status != '成功'
            """
            params = []

            if task_id:
                query += " AND task_id = ?"
                params.append(task_id)

            query += " ORDER BY discovered_at DESC"

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def update_product_detail_status(self, product_id: str, status: str):
        """更新商品详情获取状态"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE products
                SET detail_fetch_status = ?
                WHERE product_id = ?
            """, (status, product_id))
            await db.commit()

    async def get_failed_ai_analysis(self, task_id: int = None):
        """获取AI分析失败的商品列表"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            query = """
                SELECT p.*, a.id as analysis_id, a.full_response as error_info
                FROM products p 
                JOIN ai_analysis a ON p.id = a.product_id 
                WHERE a.analysis_status = 'failed'
            """
            params = []
            
            if task_id:
                query += " AND p.task_id = ?"
                params.append(task_id)
                
            query += " ORDER BY p.discovered_at DESC"
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def retry_ai_analysis(self, product_id: int):
        """重置AI分析状态为pending，准备重新分析"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE ai_analysis 
                SET analysis_status = 'pending', 
                    is_recommended = NULL,
                    reason = 'Retry requested',
                    full_response = '{"status": "pending", "reason": "Retry requested"}'
                WHERE product_id = ?
            """, (product_id,))
            await db.commit()

    async def migrate_from_config_json(self):
        """从config.json迁移数据到数据库（如果存在）"""
        config_file = "config.json"
        if not os.path.exists(config_file):
            print("config.json文件不存在，跳过迁移。")
            return
            
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            tasks = config.get('tasks', [])
            if not tasks:
                print("config.json中没有任务配置，跳过迁移。")
                return
                
            async with aiosqlite.connect(self.db_path) as db:
                for task in tasks:
                    # 检查任务是否已存在
                    async with db.execute("SELECT id FROM tasks WHERE task_name = ?", (task['task_name'],)) as cursor:
                        existing = await cursor.fetchone()
                        
                    if not existing:
                        # 读取AI提示词文件
                        ai_prompt_text = ""
                        try:
                            base_file = task.get('ai_prompt_base_file', 'prompts/base_prompt.txt')
                            criteria_file = task.get('ai_prompt_criteria_file', '')
                            
                            if os.path.exists(base_file):
                                with open(base_file, 'r', encoding='utf-8') as f:
                                    base_prompt = f.read()
                                    
                                if criteria_file and os.path.exists(criteria_file):
                                    with open(criteria_file, 'r', encoding='utf-8') as f:
                                        criteria = f.read()
                                    ai_prompt_text = base_prompt.replace("{{CRITERIA_SECTION}}", criteria)
                                else:
                                    ai_prompt_text = base_prompt
                        except Exception as e:
                            print(f"读取提示词文件失败: {e}")
                            
                        # 插入任务
                        await db.execute("""
                            INSERT INTO tasks 
                            (task_name, keyword, enabled, max_pages, personal_only, min_price, max_price, ai_prompt_text)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            task['task_name'],
                            task['keyword'],
                            task.get('enabled', True),
                            task.get('max_pages', 3),
                            task.get('personal_only', True),
                            task.get('min_price'),
                            task.get('max_price'),
                            ai_prompt_text
                        ))
                        print(f"已迁移任务: {task['task_name']}")
                    else:
                        print(f"任务已存在，跳过: {task['task_name']}")
                        
                await db.commit()
                print("config.json迁移完成。")
                
        except Exception as e:
            print(f"迁移config.json时出错: {e}")

    async def save_task(self, task_data: Dict) -> int:
        """保存或更新任务"""
        async with aiosqlite.connect(self.db_path) as db:
            if task_data.get('id'):
                # 更新现有任务
                await db.execute("""
                    UPDATE tasks SET 
                    task_name = ?, keyword = ?, enabled = ?, max_pages = ?, 
                    personal_only = ?, min_price = ?, max_price = ?, ai_prompt_text = ?,
                    email_address = ?, email_enabled = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    task_data['task_name'], task_data['keyword'], task_data['enabled'],
                    task_data['max_pages'], task_data['personal_only'], 
                    task_data.get('min_price'), task_data.get('max_price'),
                    task_data.get('ai_prompt_text'), task_data.get('email_address'),
                    task_data.get('email_enabled', False), task_data['id']
                ))
                task_id = task_data['id']
            else:
                # 创建新任务
                cursor = await db.execute("""
                    INSERT INTO tasks 
                    (task_name, keyword, enabled, max_pages, personal_only, min_price, max_price, 
                     ai_prompt_text, email_address, email_enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task_data['task_name'], task_data['keyword'], task_data.get('enabled', True),
                    task_data.get('max_pages', 3), task_data.get('personal_only', False),
                    task_data.get('min_price'), task_data.get('max_price'),
                    task_data.get('ai_prompt_text'), task_data.get('email_address'),
                    task_data.get('email_enabled', False)
                ))
                task_id = cursor.lastrowid
            
            await db.commit()
            return task_id

    async def log_email_send(self, task_id: int, product_id: int, email_address: str, 
                            subject: str, status: str, error_message: str = None):
        """记录邮件发送日志"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO email_logs 
                (task_id, product_id, email_address, subject, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task_id, product_id, email_address, subject, status, error_message))
            await db.commit()

    async def get_email_logs(self, task_id: int = None, limit: int = 100) -> List[Dict]:
        """获取邮件发送日志"""
        async with aiosqlite.connect(self.db_path) as db:
            if task_id:
                cursor = await db.execute("""
                    SELECT el.*, t.task_name, p.title as product_title
                    FROM email_logs el
                    LEFT JOIN tasks t ON el.task_id = t.id
                    LEFT JOIN products p ON el.product_id = p.id
                    WHERE el.task_id = ?
                    ORDER BY el.sent_at DESC
                    LIMIT ?
                """, (task_id, limit))
            else:
                cursor = await db.execute("""
                    SELECT el.*, t.task_name, p.title as product_title
                    FROM email_logs el
                    LEFT JOIN tasks t ON el.task_id = t.id
                    LEFT JOIN products p ON el.product_id = p.id
                    ORDER BY el.sent_at DESC
                    LIMIT ?
                """, (limit,))
            
            rows = await cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    async def get_all_cookies(self) -> List[Dict]:
        """获取所有Cookie列表"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT id, name, cookie_value, status, last_used, created_at, updated_at
                FROM cookies ORDER BY created_at DESC
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_active_cookies(self) -> List[Dict]:
        """获取所有可用的Cookie"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row  # 添加这行
            cursor = await db.execute("""
                SELECT id, name, cookie_value, last_used
                FROM cookies 
                WHERE status = 'active'
                ORDER BY last_used ASC NULLS FIRST
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def add_cookie(self, name: str, cookie_value: str) -> int:
        """添加新Cookie"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO cookies (name, cookie_value, status)
                VALUES (?, ?, 'active')
            """, (name, cookie_value))
            await db.commit()
            return cursor.lastrowid

    async def update_cookie(self, cookie_id: int, name: str = None, cookie_value: str = None, status: str = None):
        """更新Cookie信息"""
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if cookie_value is not None:
            updates.append("cookie_value = ?")
            params.append(cookie_value)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(cookie_id)
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(f"""
                    UPDATE cookies SET {', '.join(updates)}
                    WHERE id = ?
                """, params)
                await db.commit()

    async def delete_cookie(self, cookie_id: int):
        """删除Cookie"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM cookies WHERE id = ?", (cookie_id,))
            await db.commit()

    async def update_cookie_last_used(self, cookie_id: int):
        """更新Cookie最后使用时间"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE cookies 
                SET last_used = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (cookie_id,))
            await db.commit()

    async def get_cookie_by_id(self, cookie_id: int) -> Optional[Dict]:
        """根据ID获取Cookie详情"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row  # 添加这行
            cursor = await db.execute("""
                SELECT id, name, cookie_value, status, last_used, created_at, updated_at
                FROM cookies WHERE id = ?
            """, (cookie_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def migrate_state_file_to_cookies(self, state_file_path: str = "xianyu_state.json"):
        """从状态文件迁移Cookie到数据库"""
        if not os.path.exists(state_file_path):
            return False
        
        try:
            with open(state_file_path, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            # 检查是否已经存在同名的Cookie
            existing_cookies = await self.get_all_cookies()
            existing_names = [cookie['name'] for cookie in existing_cookies]
            
            cookie_name = f"从{state_file_path}迁移"
            if cookie_name in existing_names:
                cookie_name = f"{cookie_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 将状态文件内容作为Cookie值存储
            cookie_value = json.dumps(state_data, ensure_ascii=False)
            await self.add_cookie(cookie_name, cookie_value)
            
            print(f"成功从 {state_file_path} 迁移Cookie到数据库")
            return True
        
        except Exception as e:
            print(f"迁移状态文件失败: {e}")
            return False

# 创建全局数据库实例
db = XianyuDatabase()
