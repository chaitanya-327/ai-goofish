#!/usr/bin/env python3
"""
数据库初始化和迁移脚本
"""
import asyncio
from database import db

async def main():
    print("正在初始化数据库...")
    await db.init_database()
    print("数据库表结构创建完成。")
    
    print("正在从config.json迁移数据...")
    await db.migrate_from_config_json()
    print("数据迁移完成。")
    
    print("数据库初始化成功！")

if __name__ == "__main__":
    asyncio.run(main())