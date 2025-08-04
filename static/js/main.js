// Main application controller - handles navigation and module coordination
import { TasksModule } from './tasks.js';
import { ResultsModule } from './results.js';
import { LogsModule } from './logs.js';
import { CookiesModule } from './cookies.js';
import { SettingsModule } from './settings.js';

document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing modules...');
    
    // Initialize modules
    const modules = {
        tasks: new TasksModule(),
        results: new ResultsModule(),
        logs: new LogsModule(),
        cookies: new CookiesModule(),
        settings: new SettingsModule()
    };

    console.log('Modules initialized:', modules);

    // Make modules globally accessible for onclick handlers
    window.tasksModule = modules.tasks;
    window.resultsModule = modules.results;
    window.logsModule = modules.logs;
    window.cookiesModule = modules.cookies;
    window.settingsModule = modules.settings;

    // Template mapping
    const templates = {
        tasks: () => modules.tasks.renderTasksSection(),
        results: () => modules.results.renderResultsSection(),
        logs: () => modules.logs.renderLogsSection(),
        cookies: () => modules.cookies.renderCookiesSection(),
        settings: () => modules.settings.renderSettingsSection()
    };

    // Navigation elements
    const navLinks = document.querySelectorAll('.nav-link');
    const mainContent = document.getElementById('main-content');

    // Navigation function
    async function navigateTo(hash) {
        const sectionId = hash.replace('#', '') || 'tasks';
        
        // Update active nav link
        navLinks.forEach(link => {
            link.classList.toggle('active', link.getAttribute('href') === `#${sectionId}`);
        });

        if (templates[sectionId]) {
            console.log(`Rendering template for: ${sectionId}`);
            try {
                mainContent.innerHTML = templates[sectionId]();
                
                const newSection = mainContent.querySelector('.content-section');
                if (newSection) {
                    requestAnimationFrame(() => {
                        newSection.classList.add('active');
                    });
                }

                // Initialize the specific module
                if (modules[sectionId]) {
                    console.log(`Initializing module: ${sectionId}`);
                    await modules[sectionId].initialize();
                }
            } catch (error) {
                console.error(`Error rendering ${sectionId}:`, error);
                mainContent.innerHTML = `<section class="content-section active"><h2>加载错误</h2><p>${error.message}</p></section>`;
            }
        } else {
            console.warn(`No template found for: ${sectionId}`);
            mainContent.innerHTML = '<section class="content-section active"><h2>页面未找到</h2></section>';
        }
    }

    // System status functions
    async function fetchSystemStatus() {
        try {
            const response = await fetch('/api/system/status');
            if (!response.ok) throw new Error('获取系统状态失败');
            return await response.json();
        } catch (error) {
            console.error('获取系统状态失败:', error);
            return null;
        }
    }

    async function refreshSystemStatus() {
        const statusIndicator = document.getElementById('status-indicator');
        const statusText = document.getElementById('status-text');
        
        if (!statusIndicator || !statusText) return;
        
        const status = await fetchSystemStatus();
        if (status) {
            const isRunning = status.scraper_running;
            statusIndicator.className = isRunning ? 'status-running' : 'status-stopped';
            statusText.textContent = isRunning ? '运行中' : '已停止';
        }
    }

    // Format JSON content for display
    function formatJsonContent(data) {
        return `<pre class="json-content">${JSON.stringify(data, null, 2)}</pre>`;
    }

    // Global event delegation for dynamic content
    mainContent.addEventListener('click', async (event) => {
        const target = event.target;
        const button = target.closest('button');
        if (!button) return;

        const row = button.closest('tr');
        const taskId = row ? row.dataset.taskId : null;

        if (button.matches('.view-json-btn')) {
            const card = button.closest('.result-card');
            const itemData = JSON.parse(card.dataset.item);
            const jsonContent = document.getElementById('json-viewer-content');
            
            jsonContent.innerHTML = formatJsonContent(itemData);
            
            const modal = document.getElementById('json-viewer-modal');
            modal.style.display = 'flex';
            setTimeout(() => modal.classList.add('visible'), 10);
        } else if (button.matches('.edit-btn') && taskId) {
            const taskData = await modules.tasks.getTaskById(taskId);
            if (!taskData) return;
            // Handle task editing...
        } else if (button.matches('#add-task-btn')) {
            const modal = document.getElementById('add-task-modal');
            if (modal) {
                modal.style.display = 'flex';
                setTimeout(() => modal.classList.add('visible'), 10);
            }
        }
    });

    // Handle navigation clicks
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const hash = this.getAttribute('href');
            if (window.location.hash !== hash) {
                window.location.hash = hash;
            }
        });
    });

    // Handle hash changes (e.g., back/forward buttons, direct URL)
    window.addEventListener('hashchange', () => {
        navigateTo(window.location.hash);
    });

    // Initial load
    const initialSection = window.location.hash || '#tasks';
    navigateTo(initialSection);
    refreshSystemStatus();

    // Refresh system status periodically
    setInterval(refreshSystemStatus, 30000);

    // System control buttons
    const startAllBtn = document.getElementById('start-all-tasks');
    const stopAllBtn = document.getElementById('stop-all-tasks');

    if (startAllBtn) {
        startAllBtn.addEventListener('click', async () => {
            console.log('Start all tasks button clicked');
            
            // Set loading state
            startAllBtn.disabled = true;
            const originalText = startAllBtn.textContent;
            startAllBtn.innerHTML = '<span class="spinner" style="display: inline-block; margin-right: 6px; width: 12px; height: 12px; border: 2px solid #f0f0f0; border-top: 2px solid #fff; border-radius: 50%; animation: spin 1s linear infinite;"></span>启动中...';
            
            try {
                const response = await fetch('/api/tasks/start-all', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    console.log('Tasks started successfully:', result);
                    showNotification(result.message || '所有任务已启动', 'success');
                    
                    // Update UI state
                    startAllBtn.style.display = 'none';
                    stopAllBtn.style.display = 'inline-block';
                    
                    // Refresh system status
                    await refreshSystemStatus();
                } else {
                    throw new Error(result.detail || '启动任务失败');
                }
            } catch (error) {
                console.error('Failed to start tasks:', error);
                showNotification(`启动失败: ${error.message}`, 'error');
            } finally {
                // Restore button state
                startAllBtn.disabled = false;
                startAllBtn.innerHTML = originalText;
            }
        });
    } else {
        console.error('Start all tasks button not found');
    }

    if (stopAllBtn) {
        stopAllBtn.addEventListener('click', async () => {
            console.log('Stop all tasks button clicked');
            
            if (!confirm('确定要停止所有正在运行的任务吗？')) {
                return;
            }
            
            // Set loading state
            stopAllBtn.disabled = true;
            const originalText = stopAllBtn.textContent;
            stopAllBtn.innerHTML = '<span class="spinner" style="display: inline-block; margin-right: 6px; width: 12px; height: 12px; border: 2px solid #f0f0f0; border-top: 2px solid #fff; border-radius: 50%; animation: spin 1s linear infinite;"></span>停止中...';
            
            try {
                const response = await fetch('/api/tasks/stop-all', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    console.log('Tasks stopped successfully:', result);
                    showNotification(result.message || '所有任务已停止', 'success');
                    
                    // Update UI state
                    stopAllBtn.style.display = 'none';
                    startAllBtn.style.display = 'inline-block';
                    
                    // Refresh system status
                    await refreshSystemStatus();
                } else {
                    throw new Error(result.detail || '停止任务失败');
                }
            } catch (error) {
                console.error('Failed to stop tasks:', error);
                showNotification(`停止失败: ${error.message}`, 'error');
            } finally {
                // Restore button state
                stopAllBtn.disabled = false;
                stopAllBtn.innerHTML = originalText;
            }
        });
    } else {
        console.error('Stop all tasks button not found');
    }

    // Global notification function
    function showNotification(message, type = 'info') {
        console.log(`Notification: ${type} - ${message}`);
        
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

    // Make showNotification globally accessible
    window.showNotification = showNotification;
});
