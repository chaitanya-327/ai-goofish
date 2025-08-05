import asyncio
import smtplib
import os
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.utils import formataddr
from typing import Optional, Dict, List
import logging
from functools import wraps
import aiofiles
import requests
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)

def retry_on_failure(retries=3, delay=5):
    """邮件发送重试装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"邮件发送第 {i + 1}/{retries} 次尝试失败: {e}")
                    if i < retries - 1:
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"邮件发送在 {retries} 次尝试后彻底失败")
                        raise e
        return wrapper
    return decorator

class EmailSender:
    """邮件发送器类"""
    
    def __init__(self):
        self.smtp_host = os.getenv('SMTP_HOST')
        self.smtp_port = int(os.getenv('SMTP_PORT', '465'))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.smtp_use_tls = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
        self.from_name = os.getenv('SMTP_FROM_NAME', '闲鱼智能监控')
        
    def is_configured(self) -> bool:
        """检查邮件配置是否完整"""
        return all([
            self.smtp_host,
            self.smtp_port,
            self.smtp_user,
            self.smtp_password
        ])
    
    @retry_on_failure(retries=3, delay=3)
    async def send_email(self, to_email: str, subject: str, html_content: str, 
                        attachments: Optional[List[str]] = None) -> bool:
        """
        发送HTML邮件
        
        Args:
            to_email: 收件人邮箱
            subject: 邮件主题
            html_content: HTML邮件内容
            attachments: 附件文件路径列表
            
        Returns:
            bool: 发送是否成功
        """
        if not self.is_configured():
            logger.error("邮件配置不完整，无法发送邮件")
            return False
            
        try:
            # 在线程池中执行同步的SMTP操作
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, 
                self._send_email_sync, 
                to_email, 
                subject, 
                html_content, 
                attachments
            )
        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            return False
    
    def _send_email_sync(self, to_email: str, subject: str, html_content: str, 
                        attachments: Optional[List[str]] = None) -> bool:
        """同步发送邮件的内部方法"""
        try:
            # 创建邮件对象
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = formataddr((self.from_name, self.smtp_user))
            msg['To'] = to_email
            
            # 添加HTML内容
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # 添加附件
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, 'rb') as f:
                                img_data = f.read()
                            img = MIMEImage(img_data)
                            img.add_header('Content-Disposition', 
                                         f'attachment; filename={os.path.basename(file_path)}')
                            msg.attach(img)
                        except Exception as e:
                            logger.warning(f"添加附件失败 {file_path}: {e}")
            
            # 连接SMTP服务器并发送
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
                
            logger.info(f"邮件发送成功: {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"SMTP发送失败: {e}")
            raise e
    
    async def test_connection(self) -> Dict[str, any]:
        """测试SMTP连接"""
        if not self.is_configured():
            return {
                "success": False,
                "error": "邮件配置不完整",
                "details": {
                    "smtp_host": bool(self.smtp_host),
                    "smtp_port": bool(self.smtp_port),
                    "smtp_user": bool(self.smtp_user),
                    "smtp_password": bool(self.smtp_password)
                }
            }
        print('smtp_host:' + self.smtp_host)
        print('smtp_port:' + str(self.smtp_port))
        print('smtp_use_tls:' + str(self.smtp_use_tls))
        print('smtp_user:' + self.smtp_user)
        print('smtp_password:' + self.smtp_password)
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, self._test_connection_sync)
            return {"success": True, "message": "SMTP连接测试成功", "details": result}
        except Exception as e:
            error_msg = str(e)
            print('error_msg:' + error_msg)
            # 提供更详细的错误诊断
            diagnostic_info = {
                "smtp_host": self.smtp_host,
                "smtp_port": self.smtp_port,
                "smtp_use_tls": self.smtp_use_tls,
                "error_type": type(e).__name__
            }
            
            # 根据错误类型提供建议
            suggestions = []
            if "Connection unexpectedly closed" in error_msg:
                suggestions.extend([
                    "检查SMTP服务器地址和端口是否正确",
                    "确认网络连接正常",
                    "检查防火墙设置",
                    "尝试使用不同的端口（如587、465、25）"
                ])
            elif "Authentication failed" in error_msg:
                suggestions.extend([
                    "检查用户名和密码是否正确",
                    "确认邮箱是否开启了SMTP服务",
                    "检查是否需要应用专用密码"
                ])
            elif "SSL" in error_msg or "TLS" in error_msg:
                suggestions.extend([
                    "检查TLS设置是否正确",
                    "尝试切换TLS开关状态",
                    "确认服务器是否支持当前的加密方式"
                ])
            
            return {
                "success": False, 
                "error": error_msg,
                "diagnostic": diagnostic_info,
                "suggestions": suggestions
            }
    
    def _test_connection_sync(self):
        """同步测试SMTP连接"""
        try:
            print(f"测试SMTP连接: {self.smtp_host}:{self.smtp_port}")
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                print("SMTP连接已建立")
                
                if self.smtp_use_tls:
                    print("启动TLS加密")
                    server.starttls()
                    print("TLS加密已启动")
                
                print("开始SMTP认证")
                server.login(self.smtp_user, self.smtp_password)
                print("SMTP认证成功")
                
                return {
                    "connection_established": True,
                    "tls_enabled": self.smtp_use_tls,
                    "authentication_successful": True
                }
                
        except Exception as e:
            print(f"SMTP连接测试失败: {e}")
            raise e
    
    async def send_product_notification(self, to_email: str, product_data: Dict, 
                                      ai_analysis: Dict, task_name: str) -> bool:
        """
        发送商品推荐通知邮件
        
        Args:
            to_email: 收件人邮箱
            product_data: 商品数据
            ai_analysis: AI分析结果
            task_name: 任务名称
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 生成邮件内容
            html_content = await self._generate_product_email_html(
                product_data, ai_analysis, task_name
            )
            
            # 生成邮件主题
            # 适配spider_v2.py的数据结构
            if '商品信息' in product_data:
                # 新的数据结构：final_record
                product_title = product_data.get('商品信息', {}).get('商品标题', '未知商品')
            else:
                # 直接的商品数据结构
                product_title = product_data.get('商品标题', '未知商品')
            subject = f"🚨 闲鱼推荐 | {product_title[:30]}..."
            
            # 发送邮件
            return await self.send_email(to_email, subject, html_content)
            
        except Exception as e:
            logger.error(f"发送商品通知邮件失败: {e}")
            return False
    
    async def _generate_product_email_html(self, product_data: Dict,
                                         ai_analysis: Dict, task_name: str) -> str:
        """生成商品推荐邮件的HTML内容"""

        # 适配不同的数据结构
        if '商品信息' in product_data:
            # 新的数据结构：final_record
            product_info = product_data.get('商品信息', {})
            seller_info = product_data.get('卖家信息', {})
        else:
            # 直接的商品数据结构
            product_info = product_data
            seller_info = {}

        product_title = product_info.get('商品标题', '未知商品')
        current_price = product_info.get('当前售价', product_info.get('商品价格', 'N/A'))
        original_price = product_info.get('原价', '')
        product_link = product_info.get('商品链接', '#')
        product_images = product_info.get('商品图片列表', [])
        location = product_info.get('商品位置', 'N/A')

        # 卖家信息
        seller_nick = seller_info.get('卖家昵称', 'N/A')
        seller_credit = seller_info.get('卖家信用等级', 'N/A')
        
        # AI分析结果
        ai_reason = ai_analysis.get('reason', '无推荐理由')
        
        # 获取第一张商品图片
        main_image = product_images[0] if product_images else ''
        
        # 生成HTML模板
        html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>闲鱼商品推荐</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: #f5f5f5;
            line-height: 1.6;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: #ffffff;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #1890ff 0%, #40a9ff 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
            font-weight: 600;
        }}
        .header p {{
            margin: 8px 0 0 0;
            opacity: 0.9;
            font-size: 14px;
        }}
        .product-card {{
            padding: 24px;
            border-bottom: 1px solid #f0f0f0;
        }}
        .product-image {{
            width: 100%;
            max-width: 300px;
            height: 200px;
            object-fit: cover;
            border-radius: 8px;
            margin: 0 auto 16px auto;
            display: block;
            border: 1px solid #e8e8e8;
        }}
        .product-title {{
            font-size: 18px;
            font-weight: 600;
            color: #1a1a1a;
            margin: 0 0 12px 0;
            line-height: 1.4;
        }}
        .price-section {{
            margin: 16px 0;
        }}
        .current-price {{
            font-size: 24px;
            font-weight: 700;
            color: #ff4d4f;
            margin-right: 12px;
        }}
        .original-price {{
            font-size: 16px;
            color: #999;
            text-decoration: line-through;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin: 16px 0;
            padding: 16px;
            background-color: #fafafa;
            border-radius: 6px;
        }}
        .info-item {{
            font-size: 14px;
        }}
        .info-label {{
            color: #666;
            margin-bottom: 4px;
        }}
        .info-value {{
            color: #1a1a1a;
            font-weight: 500;
        }}
        .ai-analysis {{
            background: linear-gradient(135deg, #f6ffed 0%, #d9f7be 100%);
            border-left: 4px solid #52c41a;
            padding: 16px;
            margin: 20px 0;
            border-radius: 0 6px 6px 0;
        }}
        .ai-analysis h3 {{
            margin: 0 0 8px 0;
            color: #389e0d;
            font-size: 16px;
            display: flex;
            align-items: center;
        }}
        .ai-analysis p {{
            margin: 0;
            color: #52c41a;
            font-size: 14px;
            line-height: 1.5;
        }}
        .action-button {{
            display: inline-block;
            background: linear-gradient(135deg, #1890ff 0%, #40a9ff 100%);
            color: white;
            text-decoration: none;
            padding: 12px 24px;
            border-radius: 6px;
            font-weight: 500;
            text-align: center;
            margin: 20px 0;
            transition: transform 0.2s;
        }}
        .action-button:hover {{
            transform: translateY(-1px);
        }}
        .footer {{
            background-color: #fafafa;
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 12px;
            border-top: 1px solid #f0f0f0;
        }}
        .footer p {{
            margin: 4px 0;
        }}
        .task-badge {{
            display: inline-block;
            background-color: #e6f7ff;
            color: #1890ff;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
            margin-bottom: 16px;
        }}
        @media (max-width: 600px) {{
            .container {{
                margin: 0;
                box-shadow: none;
            }}
            .product-card {{
                padding: 16px;
            }}
            .info-grid {{
                grid-template-columns: 1fr;
                gap: 8px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚨 闲鱼智能推荐</h1>
            <p>发现了一个符合您要求的优质商品</p>
        </div>
        
        <div class="product-card">
            <div class="task-badge">任务: {task_name}</div>
            
            {f'<img src="{main_image}" alt="商品图片" class="product-image">' if main_image else ''}
            
            <h2 class="product-title">{product_title}</h2>
            
            <div class="price-section">
                <span class="current-price">{current_price}</span>
                {f'<span class="original-price">{original_price}</span>' if original_price else ''}
            </div>
            
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">卖家昵称</div>
                    <div class="info-value">{seller_nick}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">信用等级</div>
                    <div class="info-value">{seller_credit}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">商品位置</div>
                    <div class="info-value">{location}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">发现时间</div>
                    <div class="info-value">{product_data.get('爬取时间', 'N/A')[:19]}</div>
                </div>
            </div>
            
            <div class="ai-analysis">
                <h3>🤖 AI推荐理由</h3>
                <p>{ai_reason}</p>
            </div>
            
            <a href="{product_link}" class="action-button" target="_blank">
                🔗 查看商品详情
            </a>
        </div>
        
        <div class="footer">
            <p><strong>闲鱼智能监控机器人</strong></p>
            <p>本邮件由系统自动发送，请勿回复</p>
            <p>如需停止接收通知，请在系统设置中关闭邮件通知</p>
        </div>
    </div>
</body>
</html>
        """
        
        return html_template
    
    async def send_test_email(self, to_email: str) -> bool:
        """发送测试邮件"""
        try:
            html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>邮件测试</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
        .container { max-width: 500px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .header { text-align: center; color: #1890ff; margin-bottom: 20px; }
        .content { color: #333; line-height: 1.6; }
        .footer { margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee; text-align: center; color: #666; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📧 邮件配置测试</h1>
        </div>
        <div class="content">
            <p>恭喜！您的邮件配置已成功设置。</p>
            <p>这是一封来自<strong>闲鱼智能监控机器人</strong>的测试邮件。</p>
            <p>当系统发现符合您要求的商品时，会自动发送推荐邮件到此邮箱。</p>
        </div>
        <div class="footer">
            <p>闲鱼智能监控机器人 - 邮件通知系统</p>
        </div>
    </div>
</body>
</html>
            """
            
            return await self.send_email(
                to_email, 
                "📧 闲鱼监控 - 邮件配置测试", 
                html_content
            )
            
        except Exception as e:
            logger.error(f"发送测试邮件失败: {e}")
            return False

# 创建全局邮件发送器实例
email_sender = EmailSender()
