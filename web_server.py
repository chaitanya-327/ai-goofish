import uvicorn
import json
import aiofiles
import os
import glob
import asyncio
import sys
from dotenv import dotenv_values, load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
import openai
from openai import AsyncOpenAI
import aiosqlite
from email_sender import email_sender

load_dotenv()

from database import db

class Task(BaseModel):
    task_name: str
    enabled: bool
    keyword: str
    max_pages: int
    personal_only: bool
    min_price: Optional[str] = None
    max_price: Optional[str] = None
    ai_prompt_text: Optional[str] = None
    email_address: Optional[str] = None
    email_enabled: bool = False


class TaskUpdate(BaseModel):
    task_name: Optional[str] = None
    enabled: Optional[bool] = None
    keyword: Optional[str] = None
    max_pages: Optional[int] = None
    personal_only: Optional[bool] = None
    min_price: Optional[str] = None
    max_price: Optional[str] = None
    ai_prompt_text: Optional[str] = None
    email_address: Optional[str] = None
    email_enabled: Optional[bool] = None
    ai_prompt_base_file: Optional[str] = None
    ai_prompt_criteria_file: Optional[str] = None


class TaskGenerateRequest(BaseModel):
    task_name: str
    keyword: str
    description: str
    personal_only: bool = True
    min_price: Optional[str] = None
    max_price: Optional[str] = None


class PromptUpdate(BaseModel):
    content: str


app = FastAPI(title="闲鱼智能监控机器人")

# --- Globals for process management ---
scraper_process = None

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """
    提供 Web UI 的主页面。
    """
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health_check():
    """健康检查端点，用于Docker容器监控"""
    from datetime import datetime
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "AI Goofish Monitor",
        "version": "1.2.0"
    }

# --- API Endpoints ---
@app.post("/api/tasks/generate", response_model=dict)
async def generate_task(req: TaskGenerateRequest):
    """使用AI生成新任务"""
    try:
        # 读取参考模板
        with open("prompts/dji_pocket3_criteria.txt", 'r', encoding='utf-8') as f:
            reference_criteria = f.read()
        
        # 生成AI提示词
        generated_criteria = await generate_ai_prompt(req.description, reference_criteria)
        
        # 读取基础提示词
        with open("prompts/base_prompt.txt", 'r', encoding='utf-8') as f:
            base_prompt = f.read()
        
        # 组合完整提示词
        full_prompt = base_prompt.replace("{{CRITERIA_SECTION}}", generated_criteria)
        
        # 保存到数据库
        async with aiosqlite.connect(db.db_path) as database:
            await database.execute("""
                INSERT INTO tasks 
                (task_name, keyword, enabled, max_pages, personal_only, min_price, max_price, ai_prompt_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                req.task_name,
                req.keyword,
                True,
                3,
                req.personal_only,
                req.min_price,
                req.max_price,
                full_prompt
            ))
            await database.commit()
        
        return {"success": True, "message": f"任务 '{req.task_name}' 创建成功"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")


@app.post("/api/tasks/start-all", response_model=dict)
async def start_all_tasks():
    """
    启动所有在数据库中启用的任务。
    """
    global scraper_process
    if scraper_process and scraper_process.returncode is None:
        raise HTTPException(status_code=400, detail="监控任务已在运行中。")

    # 检查是否有启用的任务
    try:
        enabled_tasks = await db.get_enabled_tasks()
        if not enabled_tasks:
            raise HTTPException(status_code=400, detail="没有启用的任务。请先创建并启用至少一个任务。")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查任务状态时出错: {e}")

    try:
        # 设置日志目录和文件
        os.makedirs("logs", exist_ok=True)
        log_file_path = os.path.join("logs", "scraper.log")
        
        # 以追加模式打开日志文件，如果不存在则创建。
        # 子进程将继承这个文件句柄。
        log_file_handle = open(log_file_path, 'a', encoding='utf-8')

        # 使用与Web服务器相同的Python解释器来运行爬虫脚本
        # 增加 -u 参数来禁用I/O缓冲，确保日志实时写入文件
        scraper_process = await asyncio.create_subprocess_exec(
            sys.executable, "-u", "spider_v2.py",
            stdout=log_file_handle,
            stderr=log_file_handle
        )
        print(f"启动爬虫进程，PID: {scraper_process.pid}，日志输出到 {log_file_path}")
        return {"message": f"已启动 {len(enabled_tasks)} 个监控任务。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动爬虫进程时出错: {e}")


@app.post("/api/tasks/stop-all", response_model=dict)
async def stop_all_tasks():
    """
    停止当前正在运行的监控任务。
    """
    global scraper_process
    if not scraper_process or scraper_process.returncode is not None:
        raise HTTPException(status_code=400, detail="没有正在运行的监控任务。")

    try:
        scraper_process.terminate()
        await scraper_process.wait()
        print(f"爬虫进程 {scraper_process.pid} 已终止。")
        scraper_process = None
        return {"message": "所有任务已停止。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止爬虫进程时出错: {e}")


@app.get("/api/logs")
async def get_logs(
    page: int = 1, 
    limit: int = 50, 
    task_id: Optional[int] = None, 
    level: Optional[str] = None
):
    """获取任务日志，支持分页和筛选"""
    try:
        async with aiosqlite.connect(db.db_path) as database:
            database.row_factory = aiosqlite.Row
            
            # 构建查询条件
            where_conditions = []
            params = []
            
            if task_id:
                where_conditions.append("tl.task_id = ?")
                params.append(task_id)
            
            if level:
                where_conditions.append("tl.level = ?")
                params.append(level)
            
            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            # 计算总数
            count_query = f"""
                SELECT COUNT(*) as total
                FROM task_logs tl
                LEFT JOIN tasks t ON tl.task_id = t.id
                {where_clause}
            """
            async with database.execute(count_query, params) as cursor:
                total_row = await cursor.fetchone()
                total = total_row['total'] if total_row else 0
            
            # 计算偏移量
            offset = (page - 1) * limit
            
            # 查询日志数据
            query = f"""
                SELECT 
                    tl.id,
                    tl.task_id,
                    tl.level,
                    tl.message,
                    tl.details,
                    tl.timestamp,
                    t.task_name
                FROM task_logs tl
                LEFT JOIN tasks t ON tl.task_id = t.id
                {where_clause}
                ORDER BY tl.timestamp DESC 
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            
            async with database.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                logs = []
                for row in rows:
                    log_dict = dict(row)
                    # 解析details字段
                    if log_dict['details']:
                        try:
                            log_dict['details'] = json.loads(log_dict['details'])
                        except json.JSONDecodeError:
                            log_dict['details'] = None
                    logs.append(log_dict)
                
                return {
                    "logs": logs,
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "has_more": offset + limit < total
                }
                
    except Exception as e:
        print(f"获取日志API错误: {e}")  # 添加调试信息
        raise HTTPException(status_code=500, detail=f"获取日志失败: {str(e)}")

@app.get("/api/logs/levels")
async def get_log_levels():
    """获取所有可用的日志级别"""
    try:
        async with aiosqlite.connect(db.db_path) as database:
            # 首先检查表是否存在
            async with database.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='task_logs'
            """) as cursor:
                table_exists = await cursor.fetchone()
                
            if not table_exists:
                return {"levels": []}
                
            async with database.execute("SELECT DISTINCT level FROM task_logs WHERE level IS NOT NULL ORDER BY level") as cursor:
                rows = await cursor.fetchall()
                levels = [row[0] for row in rows if row[0]]
                return {"levels": levels}
    except Exception as e:
        print(f"获取日志级别API错误: {e}")  # 添加调试信息
        raise HTTPException(status_code=500, detail=f"获取日志级别失败: {str(e)}")


@app.get("/api/results/files")
async def list_result_files():
    """返回数据库中的任务列表，替代JSONL文件列表"""
    try:
        tasks = await db.get_enabled_tasks()
        # 返回任务名称列表，保持与原接口兼容
        files = [f"{task['task_name']}" for task in tasks]
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")


@app.get("/api/results/{task_name}")
async def get_task_results(task_name: str, page: int = 1, limit: int = 50, recommended_only: bool = False):
    """从数据库获取任务结果，替代JSONL文件读取"""
    try:
        # 获取任务ID
        task_id = await db.get_task_id_by_name(task_name)
        if not task_id:
            raise HTTPException(status_code=404, detail=f"任务 '{task_name}' 不存在")
        
        async with aiosqlite.connect(db.db_path) as database:
            database.row_factory = aiosqlite.Row
            
            # 构建查询条件
            where_clause = "WHERE p.task_id = ?"
            params = [task_id]
            
            if recommended_only:
                where_clause += " AND a.is_recommended = 1"
            
            # 计算偏移量
            offset = (page - 1) * limit
            
            # 查询商品和AI分析结果
            query = f"""
                SELECT p.*, a.is_recommended, a.reason, a.full_response as ai_analysis
                FROM products p 
                LEFT JOIN ai_analysis a ON p.id = a.product_id 
                {where_clause}
                ORDER BY p.discovered_at DESC 
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            
            async with database.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                
                items = []
                for row in rows:
                    row_dict = dict(row)
                    
                    # 解析product_data
                    product_data = json.loads(row_dict['product_data']) if row_dict['product_data'] else {}
                    
                    # 解析AI分析结果
                    ai_analysis = {}
                    if row_dict['ai_analysis']:
                        try:
                            ai_analysis = json.loads(row_dict['ai_analysis'])
                        except json.JSONDecodeError:
                            ai_analysis = {
                                'is_recommended': row_dict['is_recommended'],
                                'reason': row_dict['reason']
                            }
                    
                    # 构建返回格式，保持与原JSONL格式兼容
                    item = {
                        **product_data,
                        'ai_analysis': ai_analysis
                    }
                    items.append(item)
                
                return {"items": items, "total": len(items), "page": page, "limit": limit}
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务结果失败: {str(e)}")


@app.get("/api/system/status")
async def get_system_status():
    """获取系统状态信息（前端兼容接口）"""
    return await get_system_status_detailed()

@app.get("/api/settings/system-status")
async def get_system_status_detailed():
    """获取详细的系统状态信息（包含SMTP状态）"""
    try:
        global scraper_process
        env_config = dotenv_values(".env")
        
        # 检查进程状态
        is_running = False
        if scraper_process:
            if scraper_process.returncode is None:
                is_running = True
            else:
                scraper_process = None
        
        # 检查数据库状态
        database_status = {"connected": False, "tables_count": 0}
        try:
            async with aiosqlite.connect(db.db_path) as database:
                cursor = await database.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = await cursor.fetchall()
                database_status = {"connected": True, "tables_count": len(tables)}
        except Exception as e:
            print(f"数据库检查失败: {e}")
        
        # 检查SMTP配置状态
        smtp_status = {"configured": False, "connection_ok": False}
        try:
            if email_sender.is_configured():
                smtp_status["configured"] = True
            else:
                print("SMTP未配置")
        except Exception as e:
            print(f"SMTP检查失败: {e}")
            smtp_status["error"] = str(e)
        
        # 检查依赖
        dependencies_status = {"all_installed": True, "missing": []}
        required_packages = ["playwright", "openai", "fastapi", "aiosqlite", "requests"]
        for package in required_packages:
            try:
                __import__(package)
            except ImportError:
                dependencies_status["all_installed"] = False
                dependencies_status["missing"].append(package)
        
        status = {
            "scraper_running": is_running,
            "login_state": {
                "exists": os.path.exists("xianyu_state.json"),
                "path": "xianyu_state.json"
            },
            "database": database_status,
            "smtp": smtp_status,
            "env_file": {
                "exists": os.path.exists(".env"),
                "openai_api_key_set": bool(env_config.get("OPENAI_API_KEY")),
                "openai_base_url_set": bool(env_config.get("OPENAI_BASE_URL")),
                "openai_model_name_set": bool(env_config.get("OPENAI_MODEL_NAME")),
                "ntfy_topic_url_set": bool(env_config.get("NTFY_TOPIC_URL")),
                "smtp_configured": bool(env_config.get("SMTP_HOST") and env_config.get("SMTP_USER")),
            },
            "dependencies": dependencies_status
        }
        
        return status
        
    except Exception as e:
        print(f"获取系统状态时发生错误: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取系统状态失败: {str(e)}")

@app.get("/api/settings/env-config")
async def get_env_config():
    """获取环境变量配置"""
    try:
        env_config = dotenv_values(".env")
        return env_config
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取环境配置失败: {str(e)}")

@app.get("/api/settings/env-config/{key}")
async def get_env_config_item(key: str):
    """获取单个环境变量配置项"""
    try:
        env_config = dotenv_values(".env")
        return {"key": key, "value": env_config.get(key, "")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取配置项失败: {str(e)}")

@app.put("/api/settings/env-config/{key}")
async def update_env_config_item(key: str, request: dict):
    """更新单个环境变量配置项"""
    try:
        value = request.get("value", "")
        
        # 读取现有配置
        env_file_path = ".env"
        env_lines = []
        
        if os.path.exists(env_file_path):
            with open(env_file_path, 'r', encoding='utf-8') as f:
                env_lines = f.readlines()
        
        # 查找并更新配置项
        key_found = False
        for i, line in enumerate(env_lines):
            if line.strip().startswith(f"{key}="):
                env_lines[i] = f"{key}={value}\n"
                key_found = True
                break
        
        # 如果配置项不存在，添加新的
        if not key_found:
            env_lines.append(f"{key}={value}\n")
        
        # 写回文件
        with open(env_file_path, 'w', encoding='utf-8') as f:
            f.writelines(env_lines)
        
        return {"success": True, "message": f"配置项 {key} 更新成功"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置项失败: {str(e)}")

@app.post("/api/settings/env-config/save-all")
async def save_all_env_config():
    """保存所有环境配置更改"""
    try:
        # 重新加载环境变量
        load_dotenv(override=True)
        return {"success": True, "message": "所有配置保存成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")


@app.post("/api/test-proxy")
async def test_proxy():
    """测试代理配置和连接"""
    try:
        from proxy_manager import ProxyManager
        import aiohttp
        import time
        from dotenv import dotenv_values

        # 读取代理配置
        env_config = dotenv_values(".env")
        proxy_enabled = env_config.get('PROXY_ENABLED', 'false').lower() == 'true'
        proxy_api_url = env_config.get('PROXY_API_URL', '')
        proxy_refresh_interval = int(env_config.get('PROXY_REFRESH_INTERVAL', '30'))
        proxy_retry_count = int(env_config.get('PROXY_RETRY_COUNT', '3'))

        test_result = {
            "success": False,
            "message": "",
            "details": {
                "proxy_enabled": proxy_enabled,
                "proxy_api_url": proxy_api_url[:50] + "..." if len(proxy_api_url) > 50 else proxy_api_url,
                "proxy_ip": None,
                "response_time": None,
                "test_url": "https://www.goofish.com",
                "error": None
            }
        }

        # 检查代理是否启用
        if not proxy_enabled:
            test_result["message"] = "代理功能未启用"
            test_result["details"]["error"] = "PROXY_ENABLED设置为false"
            return test_result

        # 检查代理API配置
        if not proxy_api_url:
            test_result["message"] = "代理API地址未配置"
            test_result["details"]["error"] = "PROXY_API_URL为空"
            return test_result

        # 创建代理管理器进行测试
        proxy_manager = ProxyManager(
            proxy_api_url=proxy_api_url,
            proxy_enabled=True,
            refresh_interval=proxy_refresh_interval,
            retry_count=proxy_retry_count
        )

        # 设置简单的日志回调
        async def test_log_callback(task_id, level, message, details=None):
            print(f"[代理测试] {level}: {message}")

        proxy_manager.set_log_context(test_log_callback, 999)

        # 步骤1: 获取代理IP
        start_time = time.time()
        try:
            proxy_address = await proxy_manager.get_fresh_proxy(force_refresh=True)
            if not proxy_address:
                test_result["message"] = "无法获取代理IP地址"
                test_result["details"]["error"] = "代理API返回空结果或格式错误"
                return test_result

            test_result["details"]["proxy_ip"] = proxy_address

        except Exception as e:
            test_result["message"] = f"获取代理IP失败: {str(e)}"
            test_result["details"]["error"] = str(e)
            return test_result

        # 步骤2: 测试代理连接
        test_url = "https://www.goofish.com"
        try:
            # 配置代理
            proxy_url = f"http://{proxy_address}"

            # 使用代理访问测试网站
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    test_url,
                    proxy=proxy_url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                ) as response:
                    end_time = time.time()
                    response_time = round((end_time - start_time) * 1000, 2)  # 毫秒

                    test_result["details"]["response_time"] = response_time

                    if response.status == 200:
                        test_result["success"] = True
                        test_result["message"] = f"代理测试成功！响应时间: {response_time}ms"
                    else:
                        test_result["message"] = f"代理连接失败，HTTP状态码: {response.status}"
                        test_result["details"]["error"] = f"HTTP {response.status}"

        except asyncio.TimeoutError:
            test_result["message"] = "代理连接超时"
            test_result["details"]["error"] = "连接超时(30秒)"
        except Exception as e:
            test_result["message"] = f"代理连接测试失败: {str(e)}"
            test_result["details"]["error"] = str(e)

        return test_result

    except Exception as e:
        return {
            "success": False,
            "message": f"代理测试过程中发生错误: {str(e)}",
            "details": {
                "error": str(e)
            }
        }


PROMPTS_DIR = "prompts"

@app.post("/api/prompts/generate")
async def generate_prompt_from_template(request: dict):
    """根据模板生成AI提示词"""
    try:
        keyword = request.get('keyword', '')
        description = request.get('description', '')
        
        if not keyword:
            raise HTTPException(status_code=400, detail="关键词不能为空")
        
        # 读取模板文件
        try:
            with open("prompts/dji_pocket3_criteria.txt", 'r', encoding='utf-8') as f:
                reference_criteria = f.read()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="模板文件 dji_pocket3_criteria.txt 未找到")
        
        try:
            with open("prompts/base_prompt.txt", 'r', encoding='utf-8') as f:
                base_prompt = f.read()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="基础模板文件 base_prompt.txt 未找到")
        
        # 生成针对关键词的分析标准
        generated_criteria = await generate_ai_prompt(
            f"关键词：{keyword}\n需求描述：{description}", 
            reference_criteria
        )
        
        # 组合完整提示词
        full_prompt = base_prompt.replace("{{CRITERIA_SECTION}}", generated_criteria)
        
        return {"success": True, "content": full_prompt}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成AI提示词失败: {str(e)}")

@app.get("/api/prompts")
async def list_prompts():
    """
    列出 prompts/ 目录下的所有 .txt 文件。
    """
    if not os.path.isdir(PROMPTS_DIR):
        return []
    return [f for f in os.listdir(PROMPTS_DIR) if f.endswith(".txt")]

@app.get("/api/prompts/{filename}")
async def get_prompt_content(filename: str):
    """
    获取指定 prompt 文件的内容。
    """
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="无效的文件名。")
    
    filepath = os.path.join(PROMPTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Prompt 文件未找到。")
    
    async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
        content = await f.read()
    return {"filename": filename, "content": content}

@app.put("/api/prompts/{filename}")
async def update_prompt_content(filename: str, prompt_update: PromptUpdate):
    """
    更新指定 prompt 文件的内容。
    """
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="无效的文件名。")

    filepath = os.path.join(PROMPTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Prompt 文件未找到。")

    try:
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(prompt_update.content)
        return {"message": f"Prompt 文件 '{filename}' 更新成功。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入 Prompt 文件时出错: {e}")

@app.post("/api/prompts/{filename}")
async def create_prompt_file(filename: str, request: dict):
    """创建新的Prompt文件"""
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")
    
    if not filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="文件名必须以.txt结尾")
    
    filepath = os.path.join(PROMPTS_DIR, filename)
    
    if os.path.exists(filepath):
        raise HTTPException(status_code=409, detail="文件已存在")
    
    try:
        content = request.get("content", "")
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(content)
        return {"success": True, "message": f"文件 {filename} 创建成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建文件失败: {str(e)}")

@app.delete("/api/prompts/{filename}")
async def delete_prompt_file(filename: str):
    """删除Prompt文件"""
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")
    
    filepath = os.path.join(PROMPTS_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    try:
        os.remove(filepath)
        return {"success": True, "message": f"文件 {filename} 删除成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除文件失败: {str(e)}")


@app.on_event("shutdown")
async def shutdown_event():
    """
    应用退出时，确保终止所有子进程。
    """
    global scraper_process
    if scraper_process and scraper_process.returncode is None:
        print(f"Web服务器正在关闭，正在终止爬虫进程 {scraper_process.pid}...")
        scraper_process.terminate()
        try:
            await asyncio.wait_for(scraper_process.wait(), timeout=5.0)
            print("爬虫进程已成功终止。")
        except asyncio.TimeoutError:
            print("等待爬虫进程终止超时，将强制终止。")
            scraper_process.kill()
        scraper_process = None

# 添加AI提示词生成函数
async def generate_ai_prompt(description: str, reference_criteria: str) -> str:
    """使用OpenAI API生成AI分析提示词"""
    try:
        client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        )
        
        system_prompt = f"""你是一个专业的商品分析标准生成器。请基于用户的购买需求描述，参考以下标准模板，生成一个详细的商品分析标准文本。

参考模板：
{reference_criteria}

要求：
1. 保持模板的结构和格式
2. 根据用户需求调整具体的筛选条件
3. 确保生成的标准具有可操作性
4. 输出纯文本，不要markdown格式"""
        
        response = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL_NAME", "gpt-4o"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"用户需求：{description}"}
            ],
            temperature=0.7
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"生成AI提示词时出错: {e}")
        raise e

# 添加新的API端点
@app.get("/api/tasks", response_model=List[dict])
async def get_tasks():
    """获取所有任务"""
    async with aiosqlite.connect(db.db_path) as database:
        database.row_factory = aiosqlite.Row
        async with database.execute("SELECT * FROM tasks ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            tasks = []
            for row in rows:
                task_dict = dict(row)
                # 确保ai_prompt_text字段存在且不为None
                if task_dict.get('ai_prompt_text') is None:
                    task_dict['ai_prompt_text'] = ''
                tasks.append(task_dict)
            return tasks

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: int):
    """获取单个任务"""
    async with aiosqlite.connect(db.db_path) as database:
        database.row_factory = aiosqlite.Row
        async with database.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                task_dict = dict(row)
                if task_dict.get('ai_prompt_text') is None:
                    task_dict['ai_prompt_text'] = ''
                return task_dict
            else:
                raise HTTPException(status_code=404, detail="任务未找到")

@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, task_update: TaskUpdate):
    """更新任务"""
    try:
        # 添加调试日志
        print(f"收到更新请求，任务ID: {task_id}")
        update_data = task_update.model_dump(exclude_unset=True)
        print(f"更新数据: {update_data}")
        
        async with aiosqlite.connect(db.db_path) as database:
            # 检查任务是否存在
            async with database.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cursor:
                task = await cursor.fetchone()
                if not task:
                    raise HTTPException(status_code=404, detail="任务未找到")
            
            # 构建更新语句
            update_fields = []
            update_values = []
            
            for field, value in update_data.items():
                update_fields.append(f"{field} = ?")
                update_values.append(value)
                print(f"准备更新字段: {field} = {value}")
            
            if update_fields:
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                query = f"UPDATE tasks SET {', '.join(update_fields)} WHERE id = ?"
                update_values.append(task_id)
                
                print(f"执行SQL: {query}")
                print(f"参数: {update_values}")
                
                await database.execute(query, update_values)
                await database.commit()
                print("数据库更新完成")
            
            # 验证更新结果
            database.row_factory = aiosqlite.Row
            async with database.execute("SELECT ai_prompt_text FROM tasks WHERE id = ?", (task_id,)) as cursor:
                result = await cursor.fetchone()
                print(f"更新后的ai_prompt_text: {result['ai_prompt_text'] if result else 'None'}")
            
            return {"message": "任务更新成功"}
                
    except Exception as e:
        print(f"更新任务时出错: {e}")
        raise HTTPException(status_code=500, detail=f"更新任务失败: {str(e)}")

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int):
    """删除任务"""
    try:
        async with aiosqlite.connect(db.db_path) as database:
            # 检查任务是否存在
            async with database.execute("SELECT task_name FROM tasks WHERE id = ?", (task_id,)) as cursor:
                task = await cursor.fetchone()
                if not task:
                    raise HTTPException(status_code=404, detail="任务未找到")
            
            task_name = task[0]
            
            # 删除任务
            await database.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            await database.commit()
            
            return {"message": "任务删除成功", "task_name": task_name}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除任务失败: {str(e)}")

@app.get("/api/products")
async def get_products(limit: int = 50):
    """获取商品列表"""
    async with aiosqlite.connect(db.db_path) as database:
        database.row_factory = aiosqlite.Row
        async with database.execute("""
            SELECT p.*, a.is_recommended, a.reason 
            FROM products p 
            LEFT JOIN ai_analysis a ON p.id = a.product_id 
            ORDER BY p.discovered_at DESC 
            LIMIT ?
        """, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


@app.get("/api/products/failed-details")
async def get_failed_detail_products(task_id: int = None):
    """获取详情获取失败的商品列表"""
    try:
        failed_products = await db.get_failed_detail_products(task_id)
        return {"products": failed_products, "count": len(failed_products)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取失败详情列表失败: {str(e)}")

@app.post("/api/retry-analysis")
async def retry_analysis(request: dict):
    """重新进行AI分析 - 前端兼容接口"""
    try:
        product_id = request.get('product_id')
        if not product_id:
            raise HTTPException(status_code=400, detail="缺少product_id参数")

        # 查找商品是否存在
        async with aiosqlite.connect(db.db_path) as database:
            database.row_factory = aiosqlite.Row
            async with database.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)) as cursor:
                product = await cursor.fetchone()
                if not product:
                    raise HTTPException(status_code=404, detail=f"商品ID {product_id} 不存在")

            # 获取任务信息以获取AI提示词
            async with database.execute("SELECT ai_prompt FROM tasks WHERE id = ?", (product['task_id'],)) as cursor:
                task = await cursor.fetchone()
                if not task:
                    raise HTTPException(status_code=404, detail=f"任务ID {product['task_id']} 不存在")

                ai_prompt = task['ai_prompt']
                if not ai_prompt:
                    return {"success": False, "message": f"任务未配置AI提示词，无法进行AI分析"}

            # 删除现有的AI分析记录
            await database.execute("""
                DELETE FROM ai_analysis
                WHERE product_id = (SELECT id FROM products WHERE product_id = ?)
            """, (product_id,))
            await database.commit()

            # 记录操作日志
            await db.log_task_event(
                product['task_id'],
                'INFO',
                f"开始手动重新AI分析商品 {product_id}",
                {"product_id": product_id, "action": "retry_analysis_start"}
            )

        # 解析商品数据
        try:
            product_data = json.loads(product['product_data']) if product['product_data'] else {}
        except json.JSONDecodeError:
            return {"success": False, "message": f"商品数据格式错误，无法进行AI分析"}

        if not product_data:
            return {"success": False, "message": f"商品数据为空，无法进行AI分析"}

        # 在后台执行AI分析
        asyncio.create_task(perform_ai_analysis_background(
            product_id=product_id,
            product_db_id=product['id'],
            task_id=product['task_id'],
            product_data=product_data,
            ai_prompt=ai_prompt
        ))

        return {"success": True, "message": f"商品 {product_id} 的AI分析已开始，请稍后查看结果"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新分析失败: {str(e)}")


async def perform_ai_analysis_background(product_id: str, product_db_id: int, task_id: int, product_data: dict, ai_prompt: str):
    """在后台执行AI分析"""
    try:
        # 导入必要的模块
        from spider_v2 import get_ai_analysis, download_all_images

        # 记录开始分析
        await db.log_task_event(
            task_id,
            'INFO',
            f"后台AI分析开始: 商品 {product_id}",
            {"product_id": product_id, "action": "background_analysis_start"}
        )

        # 获取商品图片
        item_info = product_data.get('商品信息', {})
        image_urls = item_info.get('商品图片列表', [])

        # 下载图片
        downloaded_image_paths = []
        if image_urls:
            try:
                downloaded_image_paths = await download_all_images(product_id, image_urls)
            except Exception as img_error:
                await db.log_task_event(
                    task_id,
                    'WARNING',
                    f"商品 {product_id} 图片下载失败: {str(img_error)}",
                    {"product_id": product_id, "error": str(img_error)}
                )

        # 执行AI分析
        ai_analysis_result = None
        try:
            ai_analysis_result = await get_ai_analysis(product_data, downloaded_image_paths, prompt_text=ai_prompt)

            if ai_analysis_result:
                # 保存AI分析结果
                await db.save_ai_analysis(task_id, product_db_id, ai_analysis_result, 'completed')

                # 记录成功日志
                await db.log_task_event(
                    task_id,
                    'INFO',
                    f"商品 {product_id} AI分析完成: 推荐={ai_analysis_result.get('is_recommended', False)}",
                    {
                        "product_id": product_id,
                        "is_recommended": ai_analysis_result.get('is_recommended', False),
                        "reason": ai_analysis_result.get('reason', ''),
                        "action": "background_analysis_success"
                    }
                )
            else:
                # AI分析返回空结果
                error_result = {'error': 'AI analysis returned None', 'status': 'failed'}
                await db.save_ai_analysis(task_id, product_db_id, error_result, 'failed')

                await db.log_task_event(
                    task_id,
                    'ERROR',
                    f"商品 {product_id} AI分析失败: 返回空结果",
                    {"product_id": product_id, "action": "background_analysis_failed"}
                )

        except Exception as ai_error:
            # AI分析过程中出错
            error_result = {'error': str(ai_error), 'status': 'failed'}
            await db.save_ai_analysis(task_id, product_db_id, error_result, 'failed')

            await db.log_task_event(
                task_id,
                'ERROR',
                f"商品 {product_id} AI分析异常: {str(ai_error)}",
                {"product_id": product_id, "error": str(ai_error), "action": "background_analysis_error"}
            )

    except Exception as e:
        # 整个后台分析过程出错
        await db.log_task_event(
            task_id,
            'ERROR',
            f"商品 {product_id} 后台AI分析过程异常: {str(e)}",
            {"product_id": product_id, "error": str(e), "action": "background_analysis_exception"}
        )


@app.get("/api/analysis-status/{product_id}")
async def get_analysis_status(product_id: str):
    """获取商品AI分析状态"""
    try:
        async with aiosqlite.connect(db.db_path) as database:
            database.row_factory = aiosqlite.Row

            # 查找商品和AI分析结果
            async with database.execute("""
                SELECT p.product_id, a.analysis_status, a.is_recommended, a.reason, a.full_response
                FROM products p
                LEFT JOIN ai_analysis a ON p.id = a.product_id
                WHERE p.product_id = ?
            """, (product_id,)) as cursor:
                result = await cursor.fetchone()

                if not result:
                    raise HTTPException(status_code=404, detail=f"商品ID {product_id} 不存在")

                if result['analysis_status']:
                    # 有AI分析结果
                    ai_analysis = {}
                    if result['full_response']:
                        try:
                            ai_analysis = json.loads(result['full_response'])
                        except json.JSONDecodeError:
                            ai_analysis = {
                                'is_recommended': result['is_recommended'],
                                'reason': result['reason']
                            }

                    return {
                        "product_id": product_id,
                        "status": result['analysis_status'],
                        "analysis_result": ai_analysis
                    }
                else:
                    # 没有AI分析结果
                    return {
                        "product_id": product_id,
                        "status": "pending",
                        "analysis_result": None
                    }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分析状态失败: {str(e)}")


@app.post("/api/retry-detail")
async def retry_detail(request: dict):
    """重新获取商品详情 - 前端兼容接口"""
    try:
        product_id = request.get('product_id')
        if not product_id:
            raise HTTPException(status_code=400, detail="缺少product_id参数")

        # 查找商品是否存在
        async with aiosqlite.connect(db.db_path) as database:
            database.row_factory = aiosqlite.Row
            async with database.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)) as cursor:
                product = await cursor.fetchone()
                if not product:
                    raise HTTPException(status_code=404, detail=f"商品ID {product_id} 不存在")

            # 更新商品状态为待重试
            await database.execute("""
                UPDATE products
                SET detail_fetch_status = '待重试'
                WHERE product_id = ?
            """, (product_id,))
            await database.commit()

            # 记录操作日志
            await db.log_task_event(
                product['task_id'],
                'INFO',
                f"手动标记商品 {product_id} 为待重试获取详情",
                {"product_id": product_id, "action": "retry_detail"}
            )

        return {"success": True, "message": f"商品 {product_id} 已标记为待重试，将在下次运行时重新获取详情"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重试详情获取失败: {str(e)}")

@app.post("/api/products/{product_id}/retry-detail")
async def retry_product_detail(product_id: int):
    """重新获取商品详情 - RESTful接口"""
    try:
        # 查找商品是否存在
        async with aiosqlite.connect(db.db_path) as database:
            database.row_factory = aiosqlite.Row
            async with database.execute("SELECT * FROM products WHERE id = ?", (product_id,)) as cursor:
                product = await cursor.fetchone()
                if not product:
                    raise HTTPException(status_code=404, detail=f"商品数据库ID {product_id} 不存在")

            # 更新商品状态为待重试
            await database.execute("""
                UPDATE products
                SET detail_fetch_status = '待重试'
                WHERE id = ?
            """, (product_id,))
            await database.commit()

            # 记录操作日志
            await db.log_task_event(
                product['task_id'],
                'INFO',
                f"手动标记商品 {product['product_id']} 为待重试获取详情",
                {"db_id": product_id, "product_id": product['product_id'], "action": "retry_detail"}
            )

        return {"success": True, "message": f"商品已标记为待重试，将在下次运行时重新获取详情"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重试详情获取失败: {str(e)}")

# 启动时初始化数据库
@app.on_event("startup")
async def startup_event():
    await db.init_database()
    await db.migrate_from_config_json()

@app.post("/api/tasks", response_model=dict)
async def create_task(task: Task):
    """创建新任务"""
    try:
        task_data = task.dict()
        task_id = await db.save_task(task_data)
        return {"success": True, "message": "任务创建成功", "task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")

@app.put("/api/tasks", response_model=dict)
async def update_task(task: Task):
    """更新任务"""
    try:
        task_data = task.dict()
        if not task_data.get('id'):
            raise HTTPException(status_code=400, detail="缺少任务ID")
        
        await db.save_task(task_data)
        return {"success": True, "message": "任务更新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新任务失败: {str(e)}")

@app.get("/api/email/logs")
async def get_email_logs(task_id: int = None, limit: int = 100):
    """获取邮件发送日志"""
    try:
        logs = await db.get_email_logs(task_id, limit)
        return {"logs": logs, "count": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取邮件日志失败: {str(e)}")

@app.post("/api/email/test-product")
async def test_product_email(request: dict):
    """发送测试商品推荐邮件"""
    try:
        email_address = request.get('email')
        product_data = request.get('product_data')
        ai_analysis = request.get('ai_analysis')
        task_name = request.get('task_name', '测试任务')
        
        if not email_address:
            raise HTTPException(status_code=400, detail="缺少邮箱地址")
        
        if not product_data or not ai_analysis:
            raise HTTPException(status_code=400, detail="缺少测试数据")
        
        # 检查SMTP配置
        if not email_sender.is_configured():
            return {
                "success": False, 
                "error": "SMTP配置不完整，请在环境变量中配置SMTP相关参数"
            }
        
        # 测试SMTP连接
        connection_test = await email_sender.test_connection()
        if not connection_test["success"]:
            return {
                "success": False,
                "error": f"SMTP连接失败: {connection_test['error']}"
            }
        
        # 发送测试商品推荐邮件
        success = await email_sender.send_product_notification(
            email_address, 
            product_data, 
            ai_analysis, 
            task_name
        )
        
        if success:
            return {"success": True, "message": "测试商品推荐邮件发送成功"}
        else:
            return {"success": False, "error": "测试邮件发送失败"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


class CookieCreate(BaseModel):
    name: str
    cookie_value: str

class CookieUpdate(BaseModel):
    name: Optional[str] = None
    cookie_value: Optional[str] = None
    status: Optional[str] = None

@app.get("/api/cookies")
async def get_cookies():
    """获取所有Cookie列表"""
    try:
        # 确保数据库已初始化
        await db.init_database()
        
        cookies = await db.get_all_cookies()
        return {"success": True, "cookies": cookies}
    except Exception as e:
        print(f"获取Cookie列表失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取Cookie列表失败: {str(e)}")

@app.get("/api/cookies/{cookie_id}")
async def get_cookie_by_id(cookie_id: int):
    """获取指定Cookie详情"""
    try:
        cookie = await db.get_cookie_by_id(cookie_id)
        if not cookie:
            raise HTTPException(status_code=404, detail="Cookie不存在")
        return cookie
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取Cookie详情失败: {str(e)}")

@app.post("/api/cookies")
async def create_cookie(cookie_data: CookieCreate):
    """新增Cookie"""
    try:
        # 验证Cookie格式
        try:
            json.loads(cookie_data.cookie_value)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Cookie值必须是有效的JSON格式")
        
        cookie_id = await db.add_cookie(cookie_data.name, cookie_data.cookie_value)
        return {"success": True, "message": "Cookie添加成功", "id": cookie_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加Cookie失败: {str(e)}")

@app.put("/api/cookies/{cookie_id}")
async def update_cookie(cookie_id: int, cookie_data: CookieUpdate):
    """更新指定Cookie"""
    try:
        # 检查Cookie是否存在
        existing_cookie = await db.get_cookie_by_id(cookie_id)
        if not existing_cookie:
            raise HTTPException(status_code=404, detail="Cookie不存在")
        
        # 如果更新cookie_value，验证JSON格式
        if cookie_data.cookie_value:
            try:
                json.loads(cookie_data.cookie_value)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Cookie值必须是有效的JSON格式")
        
        await db.update_cookie(
            cookie_id, 
            cookie_data.name, 
            cookie_data.cookie_value, 
            cookie_data.status
        )
        return {"success": True, "message": "Cookie更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新Cookie失败: {str(e)}")

@app.delete("/api/cookies/{cookie_id}")
async def delete_cookie(cookie_id: int):
    """删除指定Cookie"""
    try:
        # 检查Cookie是否存在
        existing_cookie = await db.get_cookie_by_id(cookie_id)
        if not existing_cookie:
            raise HTTPException(status_code=404, detail="Cookie不存在")
        
        await db.delete_cookie(cookie_id)
        return {"success": True, "message": "Cookie删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除Cookie失败: {str(e)}")

@app.post("/api/cookies/{cookie_id}/test")
async def test_cookie(cookie_id: int):
    """测试指定Cookie的有效性"""
    try:
        cookie_data = await db.get_cookie_by_id(cookie_id)
        if not cookie_data:
            raise HTTPException(status_code=404, detail="Cookie不存在")
        
        # 这里实现Cookie有效性测试逻辑
        # 可以尝试用该Cookie访问闲鱼页面来验证
        from playwright.async_api import async_playwright
        
        try:
            cookie_value = json.loads(cookie_data['cookie_value'])

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    storage_state=cookie_value,
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                try:
                    # 尝试访问闲鱼首页，然后检查登录状态
                    await page.goto("https://www.goofish.com", timeout=30000)
                    await page.wait_for_load_state("networkidle", timeout=10000)

                    # 等待页面完全加载
                    await page.wait_for_timeout(2000)

                    # 多重检查登录状态
                    login_checks = []

                    # 检查1: 查找登录按钮
                    login_btn_count = await page.locator("text=登录").count()
                    login_checks.append(("登录按钮检查", login_btn_count == 0))

                    # 检查2: 查找用户头像或用户名
                    user_avatar_count = await page.locator("[class*='avatar'], [class*='user']").count()
                    login_checks.append(("用户头像检查", user_avatar_count > 0))

                    # 检查3: 查找个人中心链接
                    personal_link_count = await page.locator("a[href*='personal'], a[href*='user']").count()
                    login_checks.append(("个人中心链接检查", personal_link_count > 0))

                    # 检查4: 尝试访问需要登录的API
                    try:
                        # 监听网络请求，查看是否有认证相关的响应
                        response = await page.goto("https://www.goofish.com/personal", timeout=20000)
                        if response and response.status == 200:
                            # 检查页面内容是否包含登录相关元素
                            page_content = await page.content()
                            has_login_form = "登录" in page_content and ("密码" in page_content or "验证码" in page_content)
                            login_checks.append(("个人页面访问检查", not has_login_form))
                        else:
                            login_checks.append(("个人页面访问检查", False))
                    except Exception as personal_error:
                        login_checks.append(("个人页面访问检查", False))
                        print(f"个人页面访问失败: {personal_error}")

                    await browser.close()

                    # 分析检查结果
                    passed_checks = sum(1 for _, passed in login_checks if passed)
                    total_checks = len(login_checks)

                    print(f"Cookie {cookie_id} 测试结果:")
                    for check_name, passed in login_checks:
                        print(f"  {check_name}: {'✅' if passed else '❌'}")
                    print(f"  总体: {passed_checks}/{total_checks} 通过")

                    # 如果大部分检查通过，认为Cookie有效
                    if passed_checks >= total_checks * 0.5:  # 至少50%的检查通过
                        await db.update_cookie_last_used(cookie_id)
                        await db.update_cookie(cookie_id, status='active')
                        return {"success": True, "message": f"Cookie有效 ({passed_checks}/{total_checks} 检查通过)"}
                    else:
                        await db.update_cookie(cookie_id, status='expired')
                        return {"success": False, "message": f"Cookie已过期，需要重新登录 ({passed_checks}/{total_checks} 检查通过)"}

                except Exception as page_error:
                    await browser.close()
                    print(f"页面测试过程出错: {page_error}")
                    return {"success": False, "message": f"Cookie测试过程出错: {str(page_error)}"}

        except json.JSONDecodeError:
            return {"success": False, "message": "Cookie格式无效，不是有效的JSON"}
        except Exception as test_error:
            print(f"Cookie测试异常: {test_error}")
            return {"success": False, "message": f"Cookie测试失败: {str(test_error)}"}
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试Cookie失败: {str(e)}")

@app.post("/api/cookies/migrate")
async def migrate_cookies():
    """从xianyu_state.json迁移Cookie到数据库"""
    try:
        success = await db.migrate_state_file_to_cookies()
        if success:
            return {"success": True, "message": "Cookie迁移成功"}
        else:
            return {"success": False, "message": "状态文件不存在或迁移失败"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"迁移Cookie失败: {str(e)}")


if __name__ == "__main__":
    print("启动 Web 管理界面，请在浏览器访问 http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
