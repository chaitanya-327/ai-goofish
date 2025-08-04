// Tasks module - handles task management functionality
export class TasksModule {
    constructor() {
        this.tasks = [];
        console.log('TasksModule initialized');
    }

    async fetchTasks() {
        try {
            const response = await fetch('/api/tasks');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error("无法获取任务列表:", error);
            return [];
        }
    }

    async getTaskById(taskId) {
        try {
            const response = await fetch(`/api/tasks/${taskId}`);
            if (!response.ok) throw new Error('获取任务详情失败');
            return await response.json();
        } catch (error) {
            console.error('获取任务详情失败:', error);
            return null;
        }
    }

    async createTask(data) {
        try {
            const response = await fetch('/api/tasks', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data),
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '创建任务失败');
            }
            console.log('任务创建成功!');
            return await response.json();
        } catch (error) {
            console.error('无法创建任务:', error);
            alert(`错误: ${error.message}`);
            return null;
        }
    }

    async createTaskWithAI(data) {
        try {
            const response = await fetch(`/api/tasks/generate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data),
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '通过AI创建任务失败');
            }
            console.log(`AI任务创建成功!`);
            return await response.json();
        } catch (error) {
            console.error(`无法通过AI创建任务:`, error);
            alert(`错误: ${error.message}`);
            return null;
        }
    }

    async updateTask(taskId, data) {
        try {
            const response = await fetch(`/api/tasks/${taskId}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data),
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '更新任务失败');
            }
            console.log(`任务 ${taskId} 更新成功!`);
            return await response.json();
        } catch (error) {
            console.error(`无法更新任务 ${taskId}:`, error);
            alert(`错误: ${error.message}`);
            return null;
        }
    }

    async deleteTask(taskId) {
        try {
            const response = await fetch(`/api/tasks/${taskId}`, {
                method: 'DELETE'
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '删除任务失败');
            }
            return await response.json();
        } catch (error) {
            console.error(`删除任务失败:`, error);
            alert(`错误: ${error.message}`);
            return null;
        }
    }

    async savePromptText(taskId, promptText) {
        try {
            const response = await fetch(`/api/tasks/${taskId}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ ai_prompt_text: promptText }),
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '保存AI标准失败');
            }
            
            return await response.json();
        } catch (error) {
            console.error('保存AI标准失败:', error);
            alert(`错误: ${error.message}`);
            return null;
        }
    }

    renderTasksSection() {
        console.log('Rendering tasks section');
        return `
            <section id="tasks-section" class="content-section">
                <div class="section-header">
                    <h2>任务管理</h2>
                    <button id="add-task-btn" class="control-button primary-btn">➕ 创建新任务</button>
                </div>
                <div id="tasks-table-container">
                    <p>正在加载任务列表...</p>
                </div>

                <!-- Add Task Modal -->
                <div id="add-task-modal" class="modal-overlay">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h3>创建新任务</h3>
                            <button id="close-modal-btn" class="close-btn">&times;</button>
                        </div>
                        <form id="add-task-form">
                            <div class="form-group">
                                <label for="task-name">任务名称:</label>
                                <input type="text" id="task-name" name="task_name" required>
                            </div>
                            <div class="form-group">
                                <label for="keyword">搜索关键词:</label>
                                <input type="text" id="keyword" name="keyword" required>
                            </div>
                            <div class="form-group">
                                <label for="max-pages">最大页数:</label>
                                <input type="number" id="max-pages" name="max_pages" value="3" min="1" max="10">
                            </div>
                            <div class="form-group">
                                <label for="min-price">最低价格:</label>
                                <input type="number" id="min-price" name="min_price" placeholder="留空表示不限">
                            </div>
                            <div class="form-group">
                                <label for="max-price">最高价格:</label>
                                <input type="number" id="max-price" name="max_price" placeholder="留空表示不限">
                            </div>
                            <div class="form-group">
                                <label>
                                    <input type="checkbox" id="personal-only" name="personal_only" checked>
                                    仅个人闲置（排除商家）
                                </label>
                            </div>
                            <div class="form-group">
                                <label>
                                    <input type="checkbox" id="email-enabled" name="email_enabled">
                                    启用邮件通知
                                </label>
                                <input type="email" id="email-address" name="email_address" placeholder="邮箱地址" style="margin-top: 5px;">
                            </div>
                            <div class="form-group">
                                <label for="ai-description">AI任务描述 (可选):</label>
                                <textarea id="ai-description" name="ai_description" placeholder="用自然语言描述你的购买需求，AI将自动生成筛选标准..." rows="3"></textarea>
                            </div>
                            <div class="modal-actions">
                                <button type="button" id="cancel-add-task-btn" class="cancel-btn">取消</button>
                                <button type="submit" id="save-add-task-btn" class="submit-btn">
                                    <span class="btn-text">保存任务</span>
                                    <span class="spinner" style="display: none;"></span>
                                </button>
                            </div>
                        </form>
                    </div>
                </div>

                <!-- Prompt Modal -->
                <div id="prompt-modal" class="modal-overlay">
                    <div class="modal-content large">
                        <div class="modal-header">
                            <h3 id="prompt-modal-title">AI标准</h3>
                            <button id="close-prompt-modal-btn" class="close-btn">&times;</button>
                        </div>
                        <div class="modal-body">
                            <textarea id="prompt-modal-content" rows="15" placeholder="请输入AI分析标准..."></textarea>
                        </div>
                        <div class="modal-actions">
                            <button id="generate-prompt-btn" class="control-button">🤖 AI生成</button>
                            <button id="save-prompt-modal-btn" class="submit-btn">保存更改</button>
                        </div>
                    </div>
                </div>
            </section>`;
    }

    renderTasksTable(tasks) {
        if (!tasks || tasks.length === 0) {
            return '<p>没有找到任何任务。请点击右上角"创建新任务"来添加一个。</p>';
        }

        const tableHeader = `
            <thead>
                <tr>
                    <th>启用</th>
                    <th>任务名称</th>
                    <th>关键词</th>
                    <th>价格范围</th>
                    <th>筛选条件</th>
                    <th>邮件通知</th>
                    <th>AI 标准</th>
                    <th>操作</th>
                </tr>
            </thead>`;

        const tableBody = tasks.map(task => {
            const emailStatus = task.email_enabled ? 
                '<span class="tag enabled">已启用</span>' : 
                '<span class="tag disabled">未启用</span>';
            
            const hasPrompt = task.ai_prompt_text && task.ai_prompt_text.trim();
            const promptPreview = hasPrompt ? 
                (task.ai_prompt_text.length > 30 ? task.ai_prompt_text.substring(0, 30) + '...' : task.ai_prompt_text) : 
                '未配置';
            
            return `
            <tr data-task-id="${task.id}">
                <td>
                    <label class="switch">
                        <input type="checkbox" ${task.enabled ? 'checked' : ''}>
                        <span class="slider round"></span>
                    </label>
                </td>
                <td>${task.task_name}</td>
                <td><span class="tag">${task.keyword}</span></td>
                <td>${task.min_price || '不限'} - ${task.max_price || '不限'}</td>
                <td>${task.personal_only ? '<span class="tag personal">个人闲置</span>' : '<span class="tag business">包含商家</span>'}</td>
                <td class="email-status-cell">${emailStatus}</td>
                <td>
                    <div class="ai-prompt-cell">
                        <span class="prompt-preview" title="${hasPrompt ? task.ai_prompt_text.replace(/"/g, '&quot;').replace(/\n/g, ' ') : '未配置AI分析标准'}">${promptPreview}</span>
                        ${hasPrompt ? '<button class="action-btn view-prompt-btn">查看</button>' : '<span class="no-prompt">N/A</span>'}
                    </div>
                </td>
                <td>
                    <button class="action-btn edit-btn">编辑</button>
                    <button class="action-btn delete-btn">删除</button>
                </td>
            </tr>
            `;
        }).join('');

        return `<table class="tasks-table">${tableHeader}<tbody>${tableBody}</tbody></table>`;
    }

    showPromptModal(taskData, mode = 'view') {
        const modal = document.getElementById('prompt-modal');
        const title = document.getElementById('prompt-modal-title');
        const textarea = document.getElementById('prompt-modal-content');
        const saveBtn = document.getElementById('save-prompt-modal-btn');
        const generateBtn = document.getElementById('generate-prompt-btn');
        
        title.textContent = mode === 'edit' ? `编辑AI标准 - ${taskData.task_name}` : `查看AI标准 - ${taskData.task_name}`;
        textarea.value = taskData.ai_prompt_text || '';
        textarea.readOnly = mode === 'view';
        saveBtn.style.display = mode === 'edit' ? 'inline-block' : 'none';
        generateBtn.style.display = mode === 'edit' ? 'inline-block' : 'none';
        
        modal.dataset.taskId = taskData.id;
        modal.dataset.keyword = taskData.keyword;
        modal.dataset.mode = mode;
        
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.add('visible'), 10);
    }

    closePromptModal() {
        const modal = document.getElementById('prompt-modal');
        modal.classList.remove('visible');
        setTimeout(() => {
            modal.style.display = 'none';
        }, 300);
    }

    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <span class="notification-icon">${type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'}</span>
                <span class="notification-message">${message}</span>
            </div>
        `;
        
        // Add to page
        document.body.appendChild(notification);
        
        // Show animation
        setTimeout(() => notification.classList.add('show'), 100);
        
        // Auto remove
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }

    async initialize() {
        console.log('Initializing tasks module');
        try {
            const container = document.getElementById('tasks-table-container');
            if (!container) {
                console.error('Tasks table container not found');
                return;
            }
            
            const tasks = await this.fetchTasks();
            console.log('Fetched tasks:', tasks);
            container.innerHTML = this.renderTasksTable(tasks);

            this.bindEvents();
        } catch (error) {
            console.error('Error initializing tasks module:', error);
        }
    }

    bindEvents() {
        const mainContent = document.getElementById('main-content');
        
        // Task table events
        mainContent.addEventListener('click', async (event) => {
            const target = event.target;
            const button = target.closest('button');
            if (!button) return;

            const row = button.closest('tr');
            const taskId = row ? row.dataset.taskId : null;

            if (button.matches('.edit-btn')) {
                if (!taskId) return;
                const taskData = await this.getTaskById(taskId);
                if (!taskData) return;

                // Convert row to edit mode
                row.classList.add('editing');
                row.innerHTML = `
                    <td>
                        <label class="switch">
                            <input type="checkbox" ${taskData.enabled ? 'checked' : ''} data-field="enabled">
                            <span class="slider round"></span>
                        </label>
                    </td>
                    <td><input type="text" value="${taskData.task_name}" data-field="task_name" style="width: 120px;"></td>
                    <td><input type="text" value="${taskData.keyword}" data-field="keyword" style="width: 100px;"></td>
                    <td>
                        <input type="number" value="${taskData.min_price || ''}" placeholder="最低" data-field="min_price" style="width: 60px;">
                        -
                        <input type="number" value="${taskData.max_price || ''}" placeholder="最高" data-field="max_price" style="width: 60px;">
                    </td>
                    <td>
                        <label>
                            <input type="checkbox" ${taskData.personal_only ? 'checked' : ''} data-field="personal_only"> 个人闲置
                        </label>
                    </td>
                    <td>
                        <div class="email-edit-container">
                            <label>
                                <input type="checkbox" ${taskData.email_enabled ? 'checked' : ''} data-field="email_enabled"> 启用邮件
                            </label>
                            <input type="email" value="${taskData.email_address || ''}" placeholder="邮箱地址" data-field="email_address" style="width: 120px; margin-top: 4px;">
                        </div>
                    </td>
                    <td>
                        <div class="ai-prompt-edit">
                            <button class="action-btn edit-prompt-btn">编辑AI标准</button>
                        </div>
                    </td>
                    <td>
                        <button class="action-btn save-btn">保存</button>
                        <button class="action-btn cancel-btn">取消</button>
                    </td>
                `;
            } else if (button.matches('.view-prompt-btn')) {
                if (!taskId) return;
                const taskData = await this.getTaskById(taskId);
                if (taskData) {
                    this.showPromptModal(taskData, 'view');
                }
            } else if (button.matches('.edit-prompt-btn')) {
                if (!taskId) return;
                const taskData = await this.getTaskById(taskId);
                if (taskData) {
                    this.showPromptModal(taskData, 'edit');
                }
            } else if (button.matches('.save-btn')) {
                const taskNameInput = row.querySelector('input[data-field="task_name"]');
                const keywordInput = row.querySelector('input[data-field="keyword"]');
                if (!taskNameInput.value.trim() || !keywordInput.value.trim()) {
                    alert('任务名称和关键词不能为空。');
                    return;
                }

                const inputs = row.querySelectorAll('input[data-field]');
                const updatedData = {};
                inputs.forEach(input => {
                    const field = input.dataset.field;
                    if (input.type === 'checkbox') {
                        updatedData[field] = input.checked;
                    } else {
                        updatedData[field] = input.value.trim() === '' ? null : input.value.trim();
                    }
                });

                const result = await this.updateTask(taskId, updatedData);
                if (result && result.message) {
                    const container = document.getElementById('tasks-table-container');
                    const tasks = await this.fetchTasks();
                    container.innerHTML = this.renderTasksTable(tasks);
                    alert(result.message);
                }
            } else if (button.matches('.cancel-btn')) {
                const container = document.getElementById('tasks-table-container');
                const tasks = await this.fetchTasks();
                container.innerHTML = this.renderTasksTable(tasks);
            } else if (button.matches('.delete-btn')) {
                if (!taskId) return;
                if (confirm('确定要删除这个任务吗？')) {
                    const result = await this.deleteTask(taskId);
                    if (result) {
                        const container = document.getElementById('tasks-table-container');
                        const tasks = await this.fetchTasks();
                        container.innerHTML = this.renderTasksTable(tasks);
                        alert('任务删除成功');
                    }
                }
            } else if (button.matches('#add-task-btn')) {
                const modal = document.getElementById('add-task-modal');
                modal.style.display = 'flex';
                setTimeout(() => modal.classList.add('visible'), 10);
            }
        });

        // Task enable/disable toggle
        mainContent.addEventListener('change', async (event) => {
            const target = event.target;
            if (target.matches('.tasks-table input[type="checkbox"]') && !target.closest('tr.editing')) {
                const row = target.closest('tr');
                const taskId = row.dataset.taskId;
                const isEnabled = target.checked;

                if (taskId) {
                    await this.updateTask(taskId, { enabled: isEnabled });
                }
            }
        });

        // Modal events
        const modal = document.getElementById('add-task-modal');
        const promptModal = document.getElementById('prompt-modal');

        // Add task modal
        const closeModalBtn = document.getElementById('close-modal-btn');
        const cancelBtn = document.getElementById('cancel-add-task-btn');
        const form = document.getElementById('add-task-form');

        const closeModal = () => {
            modal.classList.remove('visible');
            setTimeout(() => {
                modal.style.display = 'none';
                if (form) form.reset();
            }, 300);
        };

        if (closeModalBtn) closeModalBtn.addEventListener('click', closeModal);
        if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
        modal.addEventListener('click', (event) => {
            if (event.target === modal) {
                closeModal();
            }
        });

        // Form submission
        if (form) {
            form.addEventListener('submit', async (event) => {
                event.preventDefault();
                const saveBtn = document.getElementById('save-add-task-btn');
                const formData = new FormData(form);
                const data = Object.fromEntries(formData.entries());

                // Convert checkbox values
                data.personal_only = document.getElementById('personal-only').checked;
                data.email_enabled = document.getElementById('email-enabled').checked;

                // Convert numeric values
                if (data.max_pages) data.max_pages = parseInt(data.max_pages);
                if (data.min_price) data.min_price = parseFloat(data.min_price);
                if (data.max_price) data.max_price = parseFloat(data.max_price);

                // Remove empty values
                Object.keys(data).forEach(key => {
                    if (data[key] === '' || data[key] === null) {
                        delete data[key];
                    }
                });

                const btnText = saveBtn.querySelector('.btn-text');
                const spinner = saveBtn.querySelector('.spinner');
                btnText.style.display = 'none';
                spinner.style.display = 'inline-block';
                saveBtn.disabled = true;

                let result;
                if (data.ai_description) {
                    result = await this.createTaskWithAI(data);
                } else {
                    result = await this.createTask(data);
                }

                btnText.style.display = 'inline-block';
                spinner.style.display = 'none';
                saveBtn.disabled = false;

                if (result && (result.task || result.message)) {
                    closeModal();
                    const container = document.getElementById('tasks-table-container');
                    if (container) {
                        const tasks = await this.fetchTasks();
                        container.innerHTML = this.renderTasksTable(tasks);
                    }
                }
            });
        }

        // Prompt modal events
        const closePromptBtn = document.getElementById('close-prompt-modal-btn');
        const savePromptBtn = document.getElementById('save-prompt-modal-btn');

        if (closePromptBtn) {
            closePromptBtn.addEventListener('click', () => this.closePromptModal());
        }

        promptModal.addEventListener('click', (event) => {
            if (event.target === promptModal) {
                this.closePromptModal();
            }
        });

        if (savePromptBtn) {
            savePromptBtn.addEventListener('click', async () => {
                const taskId = promptModal.dataset.taskId;
                const promptText = document.getElementById('prompt-modal-content').value;
                
                savePromptBtn.disabled = true;
                savePromptBtn.textContent = '保存中...';
                
                const result = await this.savePromptText(taskId, promptText);
                
                savePromptBtn.disabled = false;
                savePromptBtn.textContent = '保存更改';
                
                if (result) {
                    alert('AI标准保存成功！');
                    this.closePromptModal();
                    const container = document.getElementById('tasks-table-container');
                    if (container) {
                        const tasks = await this.fetchTasks();
                        container.innerHTML = this.renderTasksTable(tasks);
                    }
                }
            });
        }

        // Generate prompt button event
        const generatePromptBtn = document.getElementById('generate-prompt-btn');
        if (generatePromptBtn) {
            generatePromptBtn.addEventListener('click', async () => {
                const taskId = promptModal.dataset.taskId;
                const keyword = promptModal.dataset.keyword;
                
                if (!keyword) {
                    alert('无法获取任务关键词，请重新打开编辑窗口');
                    return;
                }
                
                // Set loading state
                generatePromptBtn.disabled = true;
                const originalText = generatePromptBtn.textContent;
                generatePromptBtn.innerHTML = '<span class="spinner" style="display: inline-block; margin-right: 6px; width: 14px; height: 14px; border: 2px solid #f0f0f0; border-top: 2px solid #1890ff; border-radius: 50%; animation: spin 1s linear infinite;"></span>生成中...';
                
                try {
                    const response = await fetch('/api/prompts/generate', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ 
                            keyword: keyword,
                            description: `我想购买与"${keyword}"相关的商品，请帮我生成专业的AI分析标准。`
                        }),
                    });
                    
                    if (!response.ok) {
                        const errorData = await response.json();
                        throw new Error(errorData.detail || '生成AI标准失败');
                    }
                    
                    const result = await response.json();
                    
                    if (result.success && result.content) {
                        // Populate the textarea with generated content
                        const textarea = document.getElementById('prompt-modal-content');
                        textarea.value = result.content;
                        
                        // Show success notification
                        this.showNotification('AI标准生成成功！请检查内容后保存。', 'success');
                    } else {
                        throw new Error('生成结果为空或格式错误');
                    }
                } catch (error) {
                    console.error('生成AI标准失败:', error);
                    this.showNotification(`生成失败: ${error.message}`, 'error');
                } finally {
                    // Restore button state
                    generatePromptBtn.disabled = false;
                    generatePromptBtn.innerHTML = originalText;
                }
            });
        }
    }
}
