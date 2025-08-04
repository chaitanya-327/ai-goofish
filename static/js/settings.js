// Settings module - handles system settings functionality
export class SettingsModule {
    constructor() {
        console.log('SettingsModule initialized');
    }

    async fetchSystemStatus() {
        try {
            const response = await fetch('/api/settings/system-status');
            if (!response.ok) throw new Error('获取系统状态失败');
            return await response.json();
        } catch (error) {
            console.error('获取系统状态失败:', error);
            return null;
        }
    }

    async fetchEnvConfig() {
        try {
            const response = await fetch('/api/settings/env-config');
            if (!response.ok) throw new Error('获取环境配置失败');
            return await response.json();
        } catch (error) {
            console.error('获取环境配置失败:', error);
            return {};
        }
    }

    async saveEnvConfigItem(key) {
        const input = document.querySelector(`input[data-key="${key}"]`);
        const select = document.querySelector(`select[data-key="${key}"]`);

        if (!input && !select) return;

        let value;
        if (select) {
            value = select.value;
        } else {
            value = input.value.trim();
        }
        const button = document.querySelector(`button[data-key="${key}"]`);
        
        if (button) {
            button.disabled = true;
            button.textContent = '保存中...';
        }

        try {
            const response = await fetch(`/api/settings/env-config/${key}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value })
            });

            const result = await response.json();
            
            if (result.success) {
                this.showNotification('配置保存成功', 'success');
            } else {
                this.showNotification(`保存失败: ${result.detail}`, 'error');
            }
        } catch (error) {
            console.error('保存配置失败:', error);
            this.showNotification('保存配置失败', 'error');
        } finally {
            if (button) {
                button.disabled = false;
                button.textContent = '保存';
            }
        }
    }

    renderSettingsSection() {
        return `
            <section id="settings-section" class="content-section">
                <div class="section-header">
                    <h2>系统设置</h2>
                </div>
                
                <div class="settings-container">
                    <div class="settings-card">
                        <h3>系统状态</h3>
                        <div id="system-status-content">
                            <p>正在加载系统状态...</p>
                        </div>
                    </div>
                    
                    <div class="settings-card">
                        <h3>环境配置</h3>
                        <div id="env-config-content">
                            <p>正在加载环境配置...</p>
                        </div>
                    </div>
                    
                    <div class="settings-card">
                        <h3>SMTP邮件测试</h3>
                        <div class="smtp-test-section">
                            <div class="smtp-test-info">
                                <p>测试SMTP邮件配置是否正常工作</p>
                            </div>
                            <div class="smtp-test-controls">
                                <button id="test-smtp-email-btn" class="email-test-btn">📧 发送测试邮件</button>
                            </div>
                        </div>
                    </div>
                </div>
            </section>`;
    }

    renderSystemStatus(status) {
        if (!status) {
            return '<p class="error">❌ 无法获取系统状态</p>';
        }

        return `
            <div class="status-grid">
                <div class="status-item">
                    <span class="status-label">爬虫进程:</span>
                    <span class="status-value ${status.scraper_running ? 'running' : 'stopped'}">
                        ${status.scraper_running ? '🟢 运行中' : '🔴 已停止'}
                    </span>
                </div>
                <div class="status-item">
                    <span class="status-label">登录状态:</span>
                    <span class="status-value ${status.login_state.exists ? 'active' : 'inactive'}">
                        ${status.login_state.exists ? '🟢 已登录' : '🔴 未登录'}
                    </span>
                </div>
                <div class="status-item">
                    <span class="status-label">数据库:</span>
                    <span class="status-value ${status.database.connected ? 'active' : 'inactive'}">
                        ${status.database.connected ? `🟢 已连接 (${status.database.tables_count}张表)` : '🔴 连接失败'}
                    </span>
                </div>
                <div class="status-item smtp-status">
                    <span class="status-label">SMTP邮件:</span>
                    <span class="status-value ${status.smtp.configured ? 'active' : 'inactive'}">
                        ${status.smtp.configured ? '🟢 已配置' : '🔴 未配置'}
                    </span>
                </div>
            </div>
        `;
    }

    renderEnvConfig(config) {
        const configItems = [
            { key: 'OPENAI_BASE_URL', label: 'OpenAI API地址', type: 'url', required: true },
            { key: 'OPENAI_API_KEY', label: 'OpenAI API密钥', type: 'text', required: true },
            { key: 'OPENAI_MODEL_NAME', label: 'OpenAI模型名称', type: 'text', required: true },
            { key: 'SKIP_EXISTING_PRODUCTS', label: '跳过已存在商品', type: 'boolean', required: false },
            { key: 'PROXY_ENABLED', label: '启用代理功能', type: 'boolean', required: false },
            { key: 'PROXY_API_URL', label: '代理API地址', type: 'url', required: false },
            { key: 'PROXY_API_KEY', label: '代理API密钥', type: 'password', required: false },
            { key: 'PROXY_REFRESH_INTERVAL', label: '代理更换间隔，单位秒', type: 'number', required: false },
            { key: 'SMTP_HOST', label: '邮件-SMTP服务器', type: 'text', required: false },
            { key: 'SMTP_PORT', label: '邮件-SMTP端口', type: 'number', required: false },
            { key: 'SMTP_USER', label: '邮件-SMTP用户名', type: 'email', required: false },
            { key: 'SMTP_PASSWORD', label: '邮件-SMTP密码', type: 'text', required: false },
            { key: 'SMTP_USE_TLS', label: '邮件-SMTP使用TLS', type: 'boolean', required: false },
            { key: 'SMTP_FROM_NAME', label: '邮件-发件人名称', type: 'text', required: false },
        ];

        return `
            <table class="env-config-table">
                <thead>
                    <tr>
                        <th>配置项</th>
                        <th>环境变量名</th>
                        <th>当前值</th>
                        <th>状态</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${configItems.map(item => `
                        <tr>
                            <td class="config-label">${item.label}</td>
                            <td class="config-key">${item.key}</td>
                            <td class="config-input">
                                ${item.type === 'boolean' ?
                                    `<select data-key="${item.key}" class="config-select">
                                        <option value="true" ${config[item.key] === 'true' ? 'selected' : ''}>开启</option>
                                        <option value="false" ${config[item.key] === 'false' || !config[item.key] ? 'selected' : ''}>关闭</option>
                                    </select>` :
                                    item.type === 'checkbox' ?
                                        `<input type="checkbox" data-key="${item.key}" ${config[item.key] === 'true' ? 'checked' : ''}>` :
                                        `<input type="${item.type}" data-key="${item.key}" value="${config[item.key] || ''}" placeholder="请输入${item.label}">`
                                }
                            </td>
                            <td class="config-status ${item.required ? 'required' : 'optional'}">
                                ${item.required ? '必需' : '可选'}
                            </td>
                            <td class="config-actions">
                                <button class="save-config-btn" data-key="${item.key}">保存</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
            <div class="env-config-actions">
                <p><small>💡 提示：修改配置后需要重启应用程序才能生效</small></p>
            </div>
        `;
    }

    renderPromptManager() {
        return `
            <div class="prompt-manager">
                <div class="prompt-file-list">
                    <h4>Prompt文件列表</h4>
                    <div id="prompt-files-container">
                        <p>正在加载文件列表...</p>
                    </div>
                    <button id="create-prompt-file-btn" class="create-btn">➕ 创建新文件</button>
                </div>
                <div class="prompt-editor">
                    <div class="editor-header">
                        <h4 id="prompt-editor-title">请选择一个文件</h4>
                        <div class="editor-actions">
                            <button id="prompt-save-btn" class="save-btn" disabled>💾 保存</button>
                        </div>
                    </div>
                    <textarea id="prompt-editor-textarea" rows="15" placeholder="请选择左侧的文件进行编辑..." readonly></textarea>
                </div>
            </div>
        `;
    }

    showNotification(message, type) {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 4px;
            color: white;
            z-index: 10000;
            background: ${type === 'success' ? '#4CAF50' : '#f44336'};
        `;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }

    async sendTestEmail() {
        const testEmail = prompt('请输入测试邮箱地址：', '');
        if (!testEmail) return;
        
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(testEmail)) {
            alert('请输入有效的邮箱地址');
            return;
        }
        
        const button = document.getElementById('test-smtp-email-btn');
        const originalText = button.textContent;
        
        try {
            button.disabled = true;
            button.textContent = '发送中...';
            
            const testProductData = {
                '商品信息': {
                    '商品标题': '【测试商品】DJI Pocket 3 口袋云台相机',
                    '当前售价': '¥2,899',
                    '原价': '¥3,299',
                    '商品链接': 'https://2.taobao.com/item.htm?id=test123456',
                    '商品图片列表': ['https://via.placeholder.com/300x200?text=测试商品图片'],
                    '商品位置': '上海市 浦东新区',
                    '商品ID': 'test_123456'
                },
                '卖家信息': {
                    '卖家昵称': '测试卖家',
                    '卖家信用等级': '4钻'
                },
                '爬取时间': new Date().toISOString()
            };
            
            const testAiAnalysis = {
                'is_recommended': true,
                'reason': '这是一封测试邮件。商品价格合理，卖家信誉良好，符合您的购买需求。如果您收到这封邮件，说明您的邮件配置已经成功！'
            };
            
            const response = await fetch('/api/email/test-product', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: testEmail,
                    product_data: testProductData,
                    ai_analysis: testAiAnalysis,
                    task_name: '邮件配置测试'
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                alert(`✅ 测试邮件发送成功！\n\n请检查邮箱 ${testEmail} 是否收到测试邮件。\n\n如果没有收到，请检查垃圾邮件文件夹。`);
            } else {
                let errorMessage = `❌ 测试邮件发送失败：\n\n${result.error}`;
                
                if (result.diagnostic) {
                    errorMessage += `\n\n📊 诊断信息：`;
                    errorMessage += `\n• SMTP服务器: ${result.diagnostic.smtp_host}:${result.diagnostic.smtp_port}`;
                    errorMessage += `\n• TLS加密: ${result.diagnostic.smtp_use_tls ? '启用' : '禁用'}`;
                    errorMessage += `\n• 错误类型: ${result.diagnostic.error_type}`;
                }
                
                if (result.suggestions && result.suggestions.length > 0) {
                    errorMessage += `\n\n💡 解决建议：`;
                    result.suggestions.forEach((suggestion, index) => {
                        errorMessage += `\n${index + 1}. ${suggestion}`;
                    });
                }
                
                errorMessage += `\n\n请检查SMTP配置是否正确。`;
                alert(errorMessage);
            }
            
        } catch (error) {
            console.error('发送测试邮件失败:', error);
            alert(`❌ 发送测试邮件时发生错误：\n\n${error.message}`);
        } finally {
            button.disabled = false;
            button.textContent = originalText;
        }
    }

    async initialize() {
        console.log('Initializing settings module');
        
        try {
            await Promise.all([
                this.loadSystemStatus(),
                this.loadEnvConfig(),
                this.loadPromptManager()
            ]);
            
            this.bindEvents();
        } catch (error) {
            console.error('Error initializing settings module:', error);
        }
    }

    async loadSystemStatus() {
        const container = document.getElementById('system-status-content');
        if (!container) return;
        
        const status = await this.fetchSystemStatus();
        container.innerHTML = this.renderSystemStatus(status);
    }

    async loadEnvConfig() {
        const container = document.getElementById('env-config-content');
        if (!container) return;
        
        const config = await this.fetchEnvConfig();
        container.innerHTML = this.renderEnvConfig(config);
    }

    async loadPromptManager() {
        const container = document.getElementById('prompt-manager-content');
        if (!container) return;
        
        container.innerHTML = this.renderPromptManager();
    }

    bindEvents() {
        // Bind save config buttons
        document.querySelectorAll('.save-config-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const key = e.target.dataset.key;
                await this.saveEnvConfigItem(key);
            });
        });
        
        // Bind test email button
        const testEmailBtn = document.getElementById('test-smtp-email-btn');
        if (testEmailBtn) {
            testEmailBtn.addEventListener('click', () => this.sendTestEmail());
        }
    }
}
