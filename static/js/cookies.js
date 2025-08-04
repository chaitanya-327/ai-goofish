// Cookies module - handles cookie management functionality
export class CookiesModule {
    constructor() {
        console.log('CookiesModule initialized');
    }

    async fetchCookies() {
        try {
            const response = await fetch('/api/cookies');
            if (!response.ok) throw new Error('获取Cookie列表失败');
            const data = await response.json();
            console.log('获取到的Cookie数据:', data); // 添加调试日志
            return data.cookies || [];
        } catch (error) {
            console.error('获取Cookie列表失败:', error);
            return [];
        }
    }

    renderCookiesSection() {
        return `
            <section id="cookies-section" class="content-section">
                <div class="section-header">
                    <h2>Cookie管理</h2>
                    <div class="section-actions">
                        <button id="migrate-cookies-btn" class="control-button">📥 从文件迁移</button>
                        <button id="add-cookie-btn" class="control-button primary-btn">➕ 添加Cookie</button>
                    </div>
                </div>
                <div id="cookies-table-container">
                    <div class="loading-container">
                        <div class="loading-spinner"></div>
                        <p>正在加载Cookie列表...</p>
                    </div>
                </div>
            </section>`;
    }

    renderCookiesTable(cookies) {
        if (!cookies || cookies.length === 0) {
            return `
                <div class="empty-state">
                    <div class="empty-state-icon">🍪</div>
                    <h3>暂无Cookie</h3>
                    <p>还没有添加任何Cookie。请点击右上角"添加Cookie"来添加一个。</p>
                </div>
            `;
        }

        return `
            <div class="table-container">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>备注名称</th>
                            <th>状态</th>
                            <th>最后使用时间</th>
                            <th>创建时间</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${cookies.map(cookie => `
                            <tr>
                                <td>${cookie.id}</td>
                                <td class="cookie-name">${this.escapeHtml(cookie.name)}</td>
                                <td>${this.getStatusBadge(cookie.status)}</td>
                                <td>${this.formatDate(cookie.last_used)}</td>
                                <td>${this.formatDate(cookie.created_at)}</td>
                                <td class="actions">
                                    <button onclick="window.cookiesModule.testCookie(${cookie.id}, this)" class="action-btn test-btn" title="测试有效性">🧪</button>
                                    <button onclick="window.cookiesModule.editCookie(${cookie.id})" class="action-btn edit-btn" title="编辑">✏️</button>
                                    <button onclick="window.cookiesModule.deleteCookie(${cookie.id})" class="action-btn delete-btn" title="删除">🗑️</button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    getStatusBadge(status) {
        const statusMap = {
            'active': { text: '可用', class: 'status-active' },
            'inactive': { text: '禁用', class: 'status-inactive' },
            'expired': { text: '已过期', class: 'status-expired' },
            'blocked': { text: '被封', class: 'status-blocked' }
        };
        const statusInfo = statusMap[status] || { text: status, class: 'status-unknown' };
        return `<span class="status-badge ${statusInfo.class}">${statusInfo.text}</span>`;
    }

    formatDate(dateString) {
        if (!dateString) return '从未';
        return new Date(dateString).toLocaleString('zh-CN');
    }

    escapeHtml(text) {
        if (!text || text === undefined || text === null) return '';
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
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
            border-radius: 8px;
            color: white;
            z-index: 10000;
            font-size: 14px;
            font-weight: 500;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            background: ${type === 'success' ? '#52c41a' : '#ff4d4f'};
            animation: slideInRight 0.3s ease-out;
        `;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOutRight 0.3s ease-in';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    showAddCookieModal() {
        // 先移除可能存在的旧模态框
        const existingModal = document.querySelector('.modal-overlay');
        if (existingModal) {
            existingModal.remove();
        }
        
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 9999;
            opacity: 1;
            visibility: visible;
        `;
        
        modal.innerHTML = `
            <div class="modal-content" style="
                background: white;
                border-radius: 8px;
                padding: 24px;
                max-width: 600px;
                width: 90%;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                position: relative;
                z-index: 10000;
            ">
                <div class="modal-header">
                    <h3>添加新Cookie</h3>
                    <button onclick="this.closest('.modal-overlay').remove()" class="modal-close">&times;</button>
                </div>
                <form id="add-cookie-form">
                    <div class="form-group">
                        <label for="cookie-name">备注名称:</label>
                        <input type="text" id="cookie-name" required placeholder="例如：主账号Cookie" maxlength="100">
                    </div>
                    <div class="form-group">
                        <label for="cookie-value">Cookie值 (JSON格式):</label>
                        <textarea id="cookie-value" rows="10" required placeholder='{"cookies": [...], "origins": [...]}' style="font-family: 'Consolas', 'Monaco', monospace; font-size: 13px;"></textarea>
                        <small class="form-hint">请粘贴从浏览器导出的完整Cookie JSON数据</small>
                    </div>
                    <div class="form-actions">
                        <button type="button" onclick="this.closest('.modal-overlay').remove()" class="btn-cancel">取消</button>
                        <button type="submit" class="btn-primary">添加Cookie</button>
                    </div>
                </form>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // 确保模态框显示
        setTimeout(() => {
            modal.style.display = 'flex';
            const nameInput = document.getElementById('cookie-name');
            if (nameInput) nameInput.focus();
        }, 10);
        
        // 绑定表单提交事件
        const form = document.getElementById('add-cookie-form');
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.addCookie();
            });
        }
        
        // 绑定点击外部关闭事件
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        });
    }

    async addCookie() {
        const nameInput = document.getElementById('cookie-name');
        const valueInput = document.getElementById('cookie-value');
        const name = nameInput.value.trim();
        const cookieValue = valueInput.value.trim();
        
        if (!name || !cookieValue) {
            this.showNotification('请填写完整信息', 'error');
            return;
        }
        
        try {
            JSON.parse(cookieValue);
        } catch (e) {
            this.showNotification('Cookie值必须是有效的JSON格式', 'error');
            valueInput.focus();
            return;
        }
        
        const submitBtn = document.querySelector('#add-cookie-form .btn-primary');
        const originalText = submitBtn.textContent;
        
        try {
            submitBtn.disabled = true;
            submitBtn.textContent = '添加中...';
            
            const response = await fetch('/api/cookies', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, cookie_value: cookieValue })
            });
            
            const result = await response.json();
            
            if (result.success) {
                document.querySelector('.modal-overlay').remove();
                this.showNotification('Cookie添加成功', 'success');
                await this.initialize();
            } else {
                this.showNotification(`添加失败: ${result.detail || '未知错误'}`, 'error');
            }
        } catch (error) {
            console.error('添加Cookie失败:', error);
            this.showNotification('添加Cookie失败，请检查网络连接', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    }

    async testCookie(cookieId, buttonElement = null) {
        // 如果没有传入按钮元素，尝试通过事件获取，或者查找对应的按钮
        let button = buttonElement;
        if (!button) {
            // 尝试从事件获取
            if (typeof event !== 'undefined' && event.target) {
                button = event.target;
            } else {
                // 查找对应的测试按钮
                button = document.querySelector(`button[onclick*="testCookie(${cookieId})"]`);
            }
        }

        if (!button) {
            console.error('无法找到测试按钮');
            this.showNotification('测试Cookie时发生错误', 'error');
            return;
        }

        const originalText = button.textContent;

        try {
            button.disabled = true;
            button.textContent = '🔄';
            button.classList.add('loading');

            const response = await fetch(`/api/cookies/${cookieId}/test`, {
                method: 'POST'
            });

            const result = await response.json();

            if (result.success) {
                this.showNotification('Cookie测试通过，状态正常', 'success');
            } else {
                this.showNotification(`Cookie测试失败: ${result.message}`, 'error');
            }

            await this.initialize();

        } catch (error) {
            console.error('测试Cookie失败:', error);
            this.showNotification('测试Cookie时发生错误', 'error');
        } finally {
            button.disabled = false;
            button.textContent = originalText;
            button.classList.remove('loading');
        }
    }

    async editCookie(cookieId) {
        try {
            // 调用详情接口获取Cookie信息
            const response = await fetch(`/api/cookies/${cookieId}`);
            if (!response.ok) {
                if (response.status === 404) {
                    this.showNotification('Cookie不存在', 'error');
                    return;
                }
                throw new Error(`获取Cookie详情失败: ${response.status}`);
            }
            
            const cookie = await response.json();
            
            // 先移除可能存在的旧模态框
            const existingModal = document.querySelector('.modal-overlay');
            if (existingModal) {
                existingModal.remove();
            }
            
            let cookieValueFormatted = '';
            try {
                if (cookie.cookie_value) {
                    const parsedValue = JSON.parse(cookie.cookie_value);
                    cookieValueFormatted = JSON.stringify(parsedValue, null, 2);
                } else {
                    cookieValueFormatted = '{\n  "cookies": [],\n  "origins": []\n}';
                }
            } catch (parseError) {
                console.warn('Cookie值不是有效JSON，使用原始值:', parseError);
                cookieValueFormatted = cookie.cookie_value || '';
            }
            
            const modal = document.createElement('div');
            modal.className = 'modal-overlay';
            modal.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                justify-content: center;
                align-items: center;
                z-index: 9999;
                opacity: 1;
                visibility: visible;
            `;
            
            modal.innerHTML = `
                <div class="modal-content" style="
                    background: white;
                    border-radius: 8px;
                    padding: 24px;
                    max-width: 600px;
                    width: 90%;
                    max-height: 80vh;
                    overflow-y: auto;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                    position: relative;
                    z-index: 10000;
                ">
                    <div class="modal-header">
                        <h3>编辑Cookie</h3>
                        <button onclick="this.closest('.modal-overlay').remove()" class="modal-close">&times;</button>
                    </div>
                    <form id="edit-cookie-form">
                        <div class="form-group">
                            <label for="edit-cookie-name">备注名称:</label>
                            <input type="text" id="edit-cookie-name" value="${this.escapeHtml(cookie.name || '')}" required maxlength="100">
                        </div>
                        <div class="form-group">
                            <label for="edit-cookie-status">状态:</label>
                            <select id="edit-cookie-status" class="form-select">
                                <option value="active" ${cookie.status === 'active' ? 'selected' : ''}>可用</option>
                                <option value="inactive" ${cookie.status === 'inactive' ? 'selected' : ''}>禁用</option>
                                <option value="expired" ${cookie.status === 'expired' ? 'selected' : ''}>已过期</option>
                                <option value="blocked" ${cookie.status === 'blocked' ? 'selected' : ''}>被封</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="edit-cookie-value">Cookie值:</label>
                            <textarea id="edit-cookie-value" rows="8" required style="font-family: 'Consolas', 'Monaco', monospace; font-size: 13px;">${this.escapeHtml(cookieValueFormatted)}</textarea>
                        </div>
                        <div class="form-actions">
                            <button type="button" onclick="this.closest('.modal-overlay').remove()" class="btn-cancel">取消</button>
                            <button type="submit" class="btn-primary">保存更改</button>
                        </div>
                    </form>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            // 确保模态框显示
            setTimeout(() => {
                modal.style.display = 'flex';
            }, 10);
            
            // 绑定表单提交事件
            const form = document.getElementById('edit-cookie-form');
            if (form) {
                form.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    await this.updateCookie(cookieId);
                });
            }
            
            // 绑定点击外部关闭事件
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.remove();
                }
            });
            
        } catch (error) {
            console.error('获取Cookie详情失败:', error);
            this.showNotification('获取Cookie详情失败', 'error');
        }
    }

    async updateCookie(cookieId) {
        const name = document.getElementById('edit-cookie-name').value.trim();
        const status = document.getElementById('edit-cookie-status').value;
        const cookieValue = document.getElementById('edit-cookie-value').value.trim();
        
        try {
            JSON.parse(cookieValue);
        } catch (e) {
            this.showNotification('Cookie值必须是有效的JSON格式', 'error');
            return;
        }
        
        const submitBtn = document.querySelector('#edit-cookie-form .btn-primary');
        const originalText = submitBtn.textContent;
        
        try {
            submitBtn.disabled = true;
            submitBtn.textContent = '保存中...';
            
            const response = await fetch(`/api/cookies/${cookieId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    name, 
                    status, 
                    cookie_value: cookieValue 
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                document.querySelector('.modal-overlay').remove();
                this.showNotification('Cookie更新成功', 'success');
                await this.initialize();
            } else {
                this.showNotification(`更新失败: ${result.detail || '未知错误'}`, 'error');
            }
        } catch (error) {
            console.error('更新Cookie失败:', error);
            this.showNotification('更新Cookie失败，请检查网络连接', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    }

    async deleteCookie(cookieId) {
        if (!confirm('确定要删除这个Cookie吗？此操作不可撤销。')) {
            return;
        }
        
        try {
            const response = await fetch(`/api/cookies/${cookieId}`, {
                method: 'DELETE'
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification('Cookie删除成功', 'success');
                await this.initialize();
            } else {
                this.showNotification(`删除失败: ${result.detail || '未知错误'}`, 'error');
            }
        } catch (error) {
            console.error('删除Cookie失败:', error);
            this.showNotification('删除Cookie失败', 'error');
        }
    }

    async migrateCookies() {
        if (!confirm('确定要从 xianyu_state.json 文件迁移Cookie到数据库吗？')) {
            return;
        }
        
        const button = document.getElementById('migrate-cookies-btn');
        const originalText = button.textContent;
        
        try {
            button.disabled = true;
            button.textContent = '📥 迁移中...';
            
            const response = await fetch('/api/cookies/migrate', {
                method: 'POST'
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification(`迁移成功: ${result.message}`, 'success');
                await this.initialize();
            } else {
                this.showNotification(`迁移失败: ${result.detail || '未知错误'}`, 'error');
            }
        } catch (error) {
            console.error('迁移Cookie失败:', error);
            this.showNotification('迁移Cookie失败', 'error');
        } finally {
            button.disabled = false;
            button.textContent = originalText;
        }
    }

    async initialize() {
        console.log('Initializing cookies module');
        
        const container = document.getElementById('cookies-table-container');
        if (!container) {
            console.error('Cookies table container not found');
            return;
        }
        
        try {
            const cookies = await this.fetchCookies();
            container.innerHTML = this.renderCookiesTable(cookies);
            
            // 确保在DOM更新后绑定事件
            setTimeout(() => {
                this.bindEvents();
            }, 100);
            
        } catch (error) {
            console.error('Error initializing cookies module:', error);
            container.innerHTML = `
                <div class="error-message">
                    <p>❌ 加载Cookie列表失败: ${error.message}</p>
                    <button onclick="window.cookiesModule.initialize()" class="retry-btn">重试</button>
                </div>
            `;
        }
    }

    bindEvents() {
        console.log('绑定Cookie模块事件');
        
        // 添加Cookie按钮
        const addBtn = document.getElementById('add-cookie-btn');
        if (addBtn) {
            console.log('找到添加Cookie按钮，绑定事件');
            addBtn.removeEventListener('click', this.handleAddCookie);
            addBtn.addEventListener('click', this.handleAddCookie.bind(this));
        } else {
            console.error('未找到添加Cookie按钮');
        }
        
        // 迁移Cookie按钮
        const migrateBtn = document.getElementById('migrate-cookies-btn');
        if (migrateBtn) {
            console.log('找到迁移Cookie按钮，绑定事件');
            migrateBtn.removeEventListener('click', this.handleMigrateCookies);
            migrateBtn.addEventListener('click', this.handleMigrateCookies.bind(this));
        } else {
            console.error('未找到迁移Cookie按钮');
        }
    }

    handleAddCookie(e) {
        e.preventDefault();
        console.log('添加Cookie按钮被点击');
        this.showAddCookieModal();
    }

    handleMigrateCookies(e) {
        e.preventDefault();
        console.log('迁移Cookie按钮被点击');
        this.migrateCookies();
    }
}
