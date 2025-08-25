from flask import Flask, request, send_from_directory, redirect, url_for, render_template_string, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from datetime import datetime
import re
import logging

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# 从环境变量读取密钥，如果没有设置则使用默认值
secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')  # 在生产环境中应该使用更安全的密钥
app.secret_key = secret_key
logger.debug("Secret key loaded: %s", secret_key[:10] + "..." if len(secret_key) > 10 else secret_key)  # 只显示前10个字符以保护安全

UPLOAD_FOLDER = '/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 从环境变量读取配置，如果没有设置则使用默认值
users = {}
admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
admin_password = os.environ.get('ADMIN_PASSWORD', 'password123')
users[admin_username] = generate_password_hash(admin_password)
logger.debug("Initialized user: %s", admin_username)

# 最大存储容量（字节），默认1GB
MAX_STORAGE_BYTES = int(os.environ.get('MAX_STORAGE_BYTES', 1024 * 1024 * 1024))  # 1GB

# 登录页面模板
login_template = '''
<!doctype html>
<html>
<head>
    <title>登录</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; max-width: 500px; margin: 50px auto; padding: 20px; }
        h1 { color: #333; }
        form { background: #f5f5f5; padding: 20px; border-radius: 5px; }
        input[type="text"], input[type="password"] { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 3px; }
        input[type="submit"] { background: #007cba; color: white; padding: 10px 20px; border: none; border-radius: 3px; cursor: pointer; }
        input[type="submit"]:hover { background: #005a87; }
        .error { color: red; }
    </style>
</head>
<body>
    <h1>文件上传系统 - 登录</h1>
    {% if error %}
    <p class="error">{{ error }}</p>
    {% endif %}
    <form method="post">
        <p>
            <label>用户名:</label>
            <input type="text" name="username" required>
        </p>
        <p>
            <label>密码:</label>
            <input type="password" name="password" required>
        </p>
        <p>
            <input type="submit" value="登录">
        </p>
    </form>
</body>
</html>
'''

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {
    'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 
    'ppt', 'pptx', 'zip', 'rar', '7z', 'tar', 'gz', 'mp3', 'mp4', 'avi', 'mov',
    'mpg', 'mpeg', 'wmv', 'flv', 'webm', 'mkv', 'wav', 'ogg', 'ogv', 'm4a'
}

# 可预览的文本文件扩展名
TEXT_PREVIEW_EXTENSIONS = {'txt', 'md', 'log', 'csv', 'json', 'xml', 'html', 'css', 'js', 'py', 'java', 'c', 'cpp'}

# 可预览的图片文件扩展名
IMAGE_PREVIEW_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

# 上传页面模板
upload_template = '''
<!doctype html>
<html>
<head>
    <title>文件管理</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; max-width: 1000px; margin: 20px auto; padding: 20px; }
        h1 { color: #333; }
        .header { display: flex; justify-content: space-between; align-items: center; }
        .logout { background: #dc3545; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; }
        .logout:hover { background: #c82333; }
        .upload-form { background: #f5f5f5; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        input[type="file"] { margin: 10px 0; }
        input[type="submit"] { background: #28a745; color: white; padding: 10px 20px; border: none; border-radius: 3px; cursor: pointer; }
        input[type="submit"]:hover { background: #218838; }
        input[type="submit"]:disabled { background: #6c757d; cursor: not-allowed; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f2f2f2; }
        tr:hover { background-color: #f5f5f5; }
        .actions a { margin-right: 10px; text-decoration: none; padding: 5px 10px; border-radius: 3px; }
        .download { background: #007cba; color: white; }
        .preview { background: #28a745; color: white; }
        .delete { background: #dc3545; color: white; }
        .actions a:hover { opacity: 0.8; }
        .file-info { color: #666; font-size: 0.9em; }
        .storage-info { background: #e9ecef; padding: 10px; border-radius: 5px; margin-bottom: 20px; }
        .storage-warning { color: #856404; background-color: #fff3cd; border-color: #ffeeba; padding: 10px; border-radius: 5px; margin-bottom: 20px; }
        .error { color: red; }
        
        /* 进度条样式 */
        .progress-container { display: none; margin: 20px 0; }
        .progress-bar { 
            width: 100%; 
            background-color: #f0f0f0; 
            border-radius: 5px; 
            overflow: hidden; 
            height: 20px; 
            margin: 10px 0; 
        }
        .progress-fill { 
            height: 100%; 
            background-color: #007cba; 
            width: 0%; 
            transition: width 0.3s ease; 
        }
        .progress-text { 
            text-align: center; 
            font-size: 14px; 
            color: #333; 
        }
        .upload-status { margin: 10px 0; font-size: 14px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>文件管理</h1>
        <p>欢迎, {{ username }}! <a href="/logout" class="logout">退出</a></p>
    </div>
    
    <div class="storage-info">
        <strong>存储使用情况:</strong> {{ used_storage }} / {{ max_storage }} ({{ usage_percentage }}%)
    </div>
    
    {% if storage_warning %}
    <div class="storage-warning">
        警告: 存储空间已使用 {{ usage_percentage }}%，请考虑删除一些文件以释放空间。
    </div>
    {% endif %}
    
    {% if storage_full %}
    <div class="storage-warning">
        错误: 存储空间已满，无法上传更多文件。请删除一些文件以释放空间。
    </div>
    {% else %}
    <div class="upload-form">
        <h2>上传文件</h2>
        {% if error %}
        <p class="error">{{ error }}</p>
        {% endif %}
        <form id="uploadForm" method="post" enctype="multipart/form-data">
            <p>
                <label>选择文件:</label><br>
                <input type="file" name="file" id="fileInput" required>
            </p>
            <p>
                <input type="submit" value="上传" id="uploadButton">
            </p>
        </form>
        
        <!-- 进度条 -->
        <div id="progressContainer" class="progress-container">
            <div class="progress-bar">
                <div id="progressFill" class="progress-fill"></div>
            </div>
            <div id="progressText" class="progress-text">0%</div>
            <div id="uploadStatus" class="upload-status"></div>
            <button id="cancelButton" style="display:none;background:#dc3545;color:white;padding:5px 10px;border:none;border-radius:3px;cursor:pointer;margin-top:10px;">取消上传</button>
        </div>
        <!-- 存储限制信息（用于前端检查） -->
        <div id="storageInfo" style="display:none;" 
             data-max-storage="{{ max_storage }}" 
             data-used-storage="{{ used_storage }}" 
             data-usage-percentage="{{ usage_percentage }}">
        </div>
    </div>
    {% endif %}
    
    <h2>文件列表</h2>
    <div style="margin-bottom: 10px;">
        <button id="selectAllBtn" style="background: #007cba; color: white; padding: 5px 10px; border: none; border-radius: 3px; cursor: pointer; margin-right: 10px;">全选</button>
        <button id="deselectAllBtn" style="background: #6c757d; color: white; padding: 5px 10px; border: none; border-radius: 3px; cursor: pointer; margin-right: 10px;">取消全选</button>
        <button id="deleteSelectedBtn" style="background: #dc3545; color: white; padding: 5px 10px; border: none; border-radius: 3px; cursor: pointer;" onclick="deleteSelectedFiles()">批量删除</button>
    </div>
    <table>
        <thead>
            <tr>
                <th style="width: 40px;"><input type="checkbox" id="selectAllCheckbox"></th>
                <th>文件名</th>
                <th>大小</th>
                <th>修改时间</th>
                <th>操作</th>
            </tr>
        </thead>
        <tbody id="fileTableBody">
            {% for file in files %}
            <tr>
                <td><input type="checkbox" class="fileCheckbox" data-filename="{{ file.name }}"></td>
                <td>{{ file.name }}</td>
                <td>{{ file.size }}</td>
                <td>{{ file.modified }}</td>
                <td class="actions">
                    <a href="/preview/{{ file.name }}" class="preview">预览</a>
                    <a href="/download/{{ file.name }}" class="download">下载</a>
                    <a href="/delete/{{ file.name }}" class="delete" onclick="return confirm('确定要删除 {{ file.name }} 吗？')">删除</a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    
    <script>
        // 文件大小转换函数
        function parseFileSize(sizeStr) {
            const units = {'B': 1, 'KB': 1024, 'MB': 1024*1024, 'GB': 1024*1024*1024, 'TB': 1024*1024*1024*1024};
            const match = sizeStr.match(/^([\d.]+)\s*([A-Z]+)$/);
            if (match) {
                const value = parseFloat(match[1]);
                const unit = match[2];
                return value * (units[unit] || 1);
            }
            return 0;
        }
        
        // 上传进度处理
        document.getElementById('uploadForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const fileInput = document.getElementById('fileInput');
            const file = fileInput.files[0];
            
            if (!file) {
                alert('请选择一个文件');
                return;
            }
            
            // 检查存储限制
            const storageInfo = document.getElementById('storageInfo');
            const maxStorage = storageInfo.getAttribute('data-max-storage');
            const usedStorage = storageInfo.getAttribute('data-used-storage');
            
            // 解析存储大小
            const maxStorageBytes = parseFileSize(maxStorage);
            const usedStorageBytes = parseFileSize(usedStorage);
            const fileSizeBytes = file.size;
            
            // 检查是否会超出存储限制
            if (usedStorageBytes + fileSizeBytes > maxStorageBytes) {
                alert('上传此文件将超出存储限制，请删除一些文件后再试。');
                return;
            }
            
            // 显示进度条
            const progressContainer = document.getElementById('progressContainer');
            const progressFill = document.getElementById('progressFill');
            const progressText = document.getElementById('progressText');
            const uploadStatus = document.getElementById('uploadStatus');
            const uploadButton = document.getElementById('uploadButton');
            const cancelButton = document.getElementById('cancelButton');
            
            progressContainer.style.display = 'block';
            cancelButton.style.display = 'block';
            progressFill.style.width = '0%';
            progressText.textContent = '0%';
            uploadStatus.textContent = '准备上传...';
            uploadButton.disabled = true;
            uploadButton.value = '上传中...';
            
            // 创建FormData对象
            const formData = new FormData();
            formData.append('file', file);
            
            // 创建XMLHttpRequest对象
            const xhr = new XMLHttpRequest();
            
            // 监听上传进度
            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    const percentComplete = Math.round((e.loaded / e.total) * 100);
                    progressFill.style.width = percentComplete + '%';
                    progressText.textContent = percentComplete + '%';
                    uploadStatus.textContent = `已上传 ${formatBytes(e.loaded)} / ${formatBytes(e.total)}`;
                }
            });
            
            // 监听上传完成
            xhr.addEventListener('load', function() {
                if (xhr.status === 200) {
                    // 检查响应是否为JSON格式的错误信息
                    if (xhr.responseText.startsWith('{') && xhr.responseText.endsWith('}')) {
                        try {
                            const response = JSON.parse(xhr.responseText);
                            if (response.error) {
                                // 如果是错误响应，显示错误消息
                                uploadStatus.textContent = '上传失败: ' + response.error;
                                uploadButton.disabled = false;
                                uploadButton.value = '上传';
                                cancelButton.style.display = 'none';
                                return;
                            }
                        } catch (e) {
                            // JSON解析失败，继续下面的处理
                        }
                    }
                    
                    // 检查是否为成功消息
                    if (xhr.responseText === '文件上传成功!') {
                        progressFill.style.width = '100%';
                        progressText.textContent = '100%';
                        uploadStatus.textContent = '上传完成！';
                        cancelButton.style.display = 'none';
                        // 延迟刷新页面以显示新文件
                        setTimeout(function() {
                            window.location.reload();
                        }, 1000);
                        return;
                    }
                    
                    // 检查是否为HTML格式的错误页面
                    if (xhr.responseText.includes('class="error"') || (xhr.responseText.includes('<!doctype') && xhr.responseText.includes('error'))) {
                        uploadStatus.textContent = '上传失败，请查看页面错误信息';
                        uploadButton.disabled = false;
                        uploadButton.value = '上传';
                        cancelButton.style.display = 'none';
                    } else {
                        // 默认成功处理
                        progressFill.style.width = '100%';
                        progressText.textContent = '100%';
                        uploadStatus.textContent = '上传完成！';
                        cancelButton.style.display = 'none';
                        // 延迟刷新页面以显示新文件
                        setTimeout(function() {
                            window.location.reload();
                        }, 1000);
                    }
                } else {
                    uploadStatus.textContent = '上传失败，请重试';
                    uploadButton.disabled = false;
                    uploadButton.value = '上传';
                    cancelButton.style.display = 'none';
                }
            });
            
            // 监听上传错误
            xhr.addEventListener('error', function() {
                uploadStatus.textContent = '上传出错，请重试';
                uploadButton.disabled = false;
                uploadButton.value = '上传';
                cancelButton.style.display = 'none';
            });
            
            // 取消上传功能
            cancelButton.onclick = function() {
                xhr.abort();
                uploadStatus.textContent = '上传已取消';
                uploadButton.disabled = false;
                uploadButton.value = '上传';
                cancelButton.style.display = 'none';
                // 重置文件输入框，允许重新选择文件
                fileInput.value = '';
                // 重置进度条
                progressFill.style.width = '0%';
                progressText.textContent = '0%';
                setTimeout(function() {
                    progressContainer.style.display = 'none';
                }, 2000);
            };
            
            // 发送请求
            xhr.open('POST', '/upload');
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            xhr.send(formData);
        });
        
        // 格式化字节数
        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        // 全选功能
        document.getElementById('selectAllBtn').addEventListener('click', function() {
            const checkboxes = document.querySelectorAll('.fileCheckbox');
            checkboxes.forEach(checkbox => {
                checkbox.checked = true;
            });
            document.getElementById('selectAllCheckbox').checked = true;
        });
        
        // 取消全选功能
        document.getElementById('deselectAllBtn').addEventListener('click', function() {
            const checkboxes = document.querySelectorAll('.fileCheckbox');
            checkboxes.forEach(checkbox => {
                checkbox.checked = false;
            });
            document.getElementById('selectAllCheckbox').checked = false;
        });
        
        // 表头全选框功能
        document.getElementById('selectAllCheckbox').addEventListener('change', function() {
            const checkboxes = document.querySelectorAll('.fileCheckbox');
            checkboxes.forEach(checkbox => {
                checkbox.checked = this.checked;
            });
        });
        
        // 批量删除功能
        function deleteSelectedFiles() {
            const selectedCheckboxes = document.querySelectorAll('.fileCheckbox:checked');
            if (selectedCheckboxes.length === 0) {
                alert('请至少选择一个文件进行删除');
                return;
            }
            
            if (!confirm(`确定要删除选中的 ${selectedCheckboxes.length} 个文件吗？`)) {
                return;
            }
            
            const filenames = Array.from(selectedCheckboxes).map(checkbox => checkbox.dataset.filename);
            
            fetch('/delete_selected', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({filenames: filenames})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert(`成功删除 ${data.deleted_count} 个文件`);
                    // 重新加载页面以显示更新后的文件列表
                    location.reload();
                } else {
                    alert('删除文件时发生错误');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('删除文件时发生错误');
            });
        }
    </script>
</body>
</html>
'''

# 预览页面模板
preview_template = '''
<!doctype html>
<html>
<head>
    <title>文件预览 - {{ filename }}</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; max-width: 1000px; margin: 20px auto; padding: 20px; }
        h1 { color: #333; }
        .header { display: flex; justify-content: space-between; align-items: center; }
        .back { background: #007cba; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; }
        .back:hover { background: #005a87; }
        .download { background: #28a745; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; }
        .download:hover { background: #218838; }
        .preview-container { margin-top: 20px; }
        .file-info { background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .preview-content { 
            border: 1px solid #ddd; 
            border-radius: 5px; 
            padding: 15px; 
            max-height: 70vh; 
            overflow: auto; 
            background: white;
        }
        pre { 
            white-space: pre-wrap; 
            word-wrap: break-word; 
            margin: 0; 
            font-family: 'Courier New', monospace;
        }
        img { max-width: 100%; height: auto; }
        .pdf-container { width: 100%; height: 80vh; }
        .no-preview { 
            text-align: center; 
            padding: 40px; 
            color: #666; 
            font-style: italic;
        }
        .preview-error { 
            color: #dc3545; 
            background-color: #f8d7da; 
            border: 1px solid #f5c6cb; 
            padding: 15px; 
            border-radius: 5px;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>文件预览</h1>
        <div>
            <a href="/" class="back">返回文件列表</a>
            <a href="/download/{{ filename }}" class="download">下载文件</a>
        </div>
    </div>
    
    <div class="file-info">
        <strong>文件名:</strong> {{ filename }}<br>
        <strong>文件大小:</strong> {{ file_size }}<br>
        <strong>修改时间:</strong> {{ modified_time }}
    </div>
    
    <div class="preview-container">
        {% if error %}
        <div class="preview-error">
            <strong>预览错误:</strong> {{ error }}
        </div>
        {% elif preview_type == 'text' %}
        <div class="preview-content">
            <pre>{{ content }}</pre>
        </div>
        {% elif preview_type == 'image' %}
        <div class="preview-content">
            <img src="/download/{{ filename }}" alt="{{ filename }}">
        </div>
        {% elif preview_type == 'pdf' %}
        <div class="preview-content">
            <embed src="/download/{{ filename }}" type="application/pdf" class="pdf-container">
            <p>如果上方没有显示PDF，请<a href="/download/{{ filename }}">点击下载</a>查看。</p>
        </div>
        {% else %}
        <div class="no-preview">
            <p>该文件类型不支持在线预览。</p>
            <p><a href="/download/{{ filename }}" class="download">点击下载</a>文件到本地查看。</p>
        </div>
        {% endif %}
    </div>
</body>
</html>
'''

# 登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # 检查表单字段是否存在
        if 'username' not in request.form or 'password' not in request.form:
            return render_template_string(login_template, error='请填写用户名和密码')
        
        username = request.form['username']
        password = request.form['password']
        logger.debug("Login attempt - Username: %s", username)
        logger.debug("Available users: %s", list(users.keys()))
        
        # 验证用户凭据
        if username in users and check_password_hash(users[username], password):
            logger.debug("Login successful for user: %s", username)
            session['username'] = username
            return redirect(url_for('upload_file'))
        else:
            logger.debug("Login failed for user: %s", username)
            return render_template_string(login_template, error='无效的用户名或密码')
    
    return render_template_string(login_template)

# 登出路由
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# 获取文件列表
def get_file_list():
    files = []
    upload_dir = app.config['UPLOAD_FOLDER']
    
    if os.path.exists(upload_dir):
        for filename in os.listdir(upload_dir):
            filepath = os.path.join(upload_dir, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                files.append({
                    'name': filename,
                    'size': format_file_size(stat.st_size),
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
    
    # 按修改时间排序，最新的在前
    files.sort(key=lambda x: x['modified'], reverse=True)
    return files

# 格式化文件大小
def format_file_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

# 获取目录总大小
def get_directory_size(directory):
    total_size = 0
    if os.path.exists(directory):
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
    return total_size

# 格式化存储信息
def format_storage_info():
    used_bytes = get_directory_size(app.config['UPLOAD_FOLDER'])
    max_bytes = MAX_STORAGE_BYTES
    
    used_formatted = format_file_size(used_bytes)
    max_formatted = format_file_size(max_bytes)
    usage_percentage = round((used_bytes / max_bytes) * 100, 2) if max_bytes > 0 else 0
    
    return {
        'used_storage': used_formatted,
        'max_storage': max_formatted,
        'usage_percentage': usage_percentage,
        'used_bytes': used_bytes,
        'max_bytes': max_bytes
    }

# 检查文件扩展名是否允许
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 检查文件名是否安全（防止路径遍历攻击）
def is_safe_filename(filename):
    # 检查是否包含路径遍历字符
    if '..' in filename or '/' in filename or '\\' in filename:
        return False
    
    # 检查是否以点开头（隐藏文件）
    if filename.startswith('.'):
        return False
    
    # 检查是否包含非法字符
    if re.search(r'[<>:"|?*\x00-\x1f]', filename):
        return False
    
    # 检查文件名长度
    if len(filename) > 255:
        return False
    
    return True

# 获取文件类型描述
def get_file_type_description(filename):
    if '.' in filename:
        ext = filename.rsplit('.', 1)[1].lower()
        descriptions = {
            'php': 'PHP脚本文件',
            'jsp': 'Java服务器页面文件',
            'asp': 'Active Server Page文件',
            'aspx': 'ASP.NET页面文件',
            'sh': 'Shell脚本文件',
            'exe': '可执行文件',
            'bat': '批处理文件',
            'cmd': '命令脚本文件',
            'js': 'JavaScript文件',
            'jar': 'Java归档文件',
            'war': 'Web归档文件',
            'py': 'Python脚本文件',
            'pl': 'Perl脚本文件',
            'rb': 'Ruby脚本文件'
        }
        return descriptions.get(ext, f'{ext.upper()}文件')
    return '未知类型文件'

# 文件管理页面（上传和文件列表）
@app.route('/', methods=['GET', 'POST'])
@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    # 调试信息
    logger.debug("Session contents: %s", dict(session))
    # 检查用户是否已登录
    if 'username' not in session:
        logger.debug("User not in session, redirecting to login")
        return redirect(url_for('login'))
    logger.debug("User is logged in: %s", session['username'])
    
    # 获取存储信息
    storage_info = format_storage_info()
    storage_full = storage_info['used_bytes'] >= storage_info['max_bytes']
    storage_warning = storage_info['usage_percentage'] >= 80
    
    if request.method == 'POST':
        # 检查存储空间是否已满
        if storage_full:
            files = get_file_list()
            return render_template_string(upload_template, 
                                        username=session['username'], 
                                        files=files,
                                        **storage_info,
                                        storage_full=True,
                                        storage_warning=storage_warning)
        
        # 检查是否有文件上传
        if 'file' not in request.files:
            files = get_file_list()
            return render_template_string(upload_template, 
                                        username=session['username'], 
                                        files=files,
                                        **storage_info,
                                        storage_full=storage_full,
                                        storage_warning=storage_warning)
        
        file = request.files['file']
        if file and file.filename != '':
            filename = file.filename
            # 检查文件名是否安全
            if not is_safe_filename(filename):
                # 对于AJAX请求，返回JSON错误信息
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return '{"error": "文件名包含非法字符或路径遍历字符（如../），请使用合法的文件名。文件名不应包含以下字符：/\\<>:\\"|?*以及控制字符。"}'
                # 对于普通表单提交，返回带错误的页面
                error_message = '文件名包含非法字符或路径遍历字符（如../），请使用合法的文件名。文件名不应包含以下字符：/\\<>:"|?*以及控制字符。'
                files = get_file_list()
                return render_template_string(upload_template, 
                                            username=session['username'], 
                                            files=files,
                                            **storage_info,
                                            storage_full=storage_full,
                                            storage_warning=storage_warning,
                                            error=error_message)
            
            # 检查文件扩展名是否允许
            if not allowed_file(filename):
                file_type_desc = get_file_type_description(filename)
                # 对于AJAX请求，返回JSON错误信息
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return f'{{"error": "出于安全考虑，系统不允许上传{file_type_desc}。请上传以下类型的文件：文本文件、图片、文档、压缩包、音频或视频文件。"}}'
                # 对于普通表单提交，返回带错误的页面
                error_message = f'出于安全考虑，系统不允许上传{file_type_desc}。请上传以下类型的文件：文本文件、图片、文档、压缩包、音频或视频文件。'
                files = get_file_list()
                return render_template_string(upload_template, 
                                            username=session['username'], 
                                            files=files,
                                            **storage_info,
                                            storage_full=storage_full,
                                            storage_warning=storage_warning,
                                            error=error_message)
            
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # 检查上传此文件后是否会超出存储限制
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)  # 重置文件指针
            
            new_total_size = storage_info['used_bytes'] + file_size
            if new_total_size > storage_info['max_bytes']:
                files = get_file_list()
                return render_template_string(upload_template, 
                                            username=session['username'], 
                                            files=files,
                                            **storage_info,
                                            storage_full=False,
                                            storage_warning=storage_warning,
                                            error='上传此文件将超出存储限制，请删除一些文件后再试。')
            
            file.save(filepath)
            # 对于AJAX请求，返回成功消息
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return '文件上传成功!'
            # 对于普通表单提交，重定向
            return redirect(url_for('upload_file'))
        else:
            files = get_file_list()
            return render_template_string(upload_template, 
                                        username=session['username'], 
                                        files=files,
                                        **storage_info,
                                        storage_full=storage_full,
                                        storage_warning=storage_warning,
                                        error='没有选择文件')
    
    # GET请求 - 显示文件列表和上传表单
    files = get_file_list()
    return render_template_string(upload_template, 
                                username=session['username'], 
                                files=files,
                                **storage_info,
                                storage_full=storage_full,
                                storage_warning=storage_warning)

# 下载文件的路由（无需登录即可下载）
@app.route('/download/<filename>')
def download_file(filename):
    # 检查文件名是否安全
    if not is_safe_filename(filename):
        abort(404)
    
    # 检查文件是否存在
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        abort(404)
        
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# 获取文件预览类型
def get_preview_type(filename):
    if '.' in filename:
        ext = filename.rsplit('.', 1)[1].lower()
        if ext in TEXT_PREVIEW_EXTENSIONS:
            return 'text'
        elif ext in IMAGE_PREVIEW_EXTENSIONS:
            return 'image'
        elif ext == 'pdf':
            return 'pdf'
    return 'unknown'

# 读取文本文件内容（带大小限制）
def read_text_file(filepath, max_size=1024*1024):  # 限制1MB
    try:
        file_size = os.path.getsize(filepath)
        if file_size > max_size:
            return None, f"文件太大，无法预览（文件大小：{format_file_size(file_size)}，最大支持：{format_file_size(max_size)}）"
        
        # 尝试不同的编码方式读取文件
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.read()
                    # 如果文件内容过大，截取前部分
                    if len(content) > 10000:  # 限制显示字符数
                        content = content[:10000] + '\n\n... (内容已截取，仅显示前10000个字符)'
                    return content, None
            except UnicodeDecodeError:
                continue
        
        return None, "文件编码格式不支持预览"
    except Exception as e:
        return None, f"读取文件时发生错误：{str(e)}"

# 预览文件的路由
@app.route('/preview/<filename>')
def preview_file(filename):
    # 检查用户是否已登录
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # 检查文件名是否安全
    if not is_safe_filename(filename):
        return render_template_string(preview_template, 
                                    filename=filename,
                                    error="文件名不安全，无法预览")
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    # 检查文件是否存在
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        return render_template_string(preview_template, 
                                    filename=filename,
                                    error="文件不存在，无法预览")
    
    # 获取文件信息
    stat = os.stat(filepath)
    file_size = format_file_size(stat.st_size)
    modified_time = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    
    # 获取预览类型
    preview_type = get_preview_type(filename)
    
    # 根据文件类型处理预览
    if preview_type == 'text':
        content, error = read_text_file(filepath)
        if error:
            return render_template_string(preview_template, 
                                        filename=filename,
                                        file_size=file_size,
                                        modified_time=modified_time,
                                        error=error)
        return render_template_string(preview_template, 
                                    filename=filename,
                                    file_size=file_size,
                                    modified_time=modified_time,
                                    preview_type='text',
                                    content=content)
    elif preview_type == 'image':
        return render_template_string(preview_template, 
                                    filename=filename,
                                    file_size=file_size,
                                    modified_time=modified_time,
                                    preview_type='image')
    elif preview_type == 'pdf':
        return render_template_string(preview_template, 
                                    filename=filename,
                                    file_size=file_size,
                                    modified_time=modified_time,
                                    preview_type='pdf')
    else:
        return render_template_string(preview_template, 
                                    filename=filename,
                                    file_size=file_size,
                                    modified_time=modified_time,
                                    preview_type='unknown')

# 删除文件的路由
@app.route('/delete/<filename>')
def delete_file(filename):
    # 检查用户是否已登录
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # 检查文件名是否安全
    if not is_safe_filename(filename):
        return redirect(url_for('upload_file'))
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        os.remove(filepath)
    
    return redirect(url_for('upload_file'))

# 批量删除文件的路由
@app.route('/delete_selected', methods=['POST'])
def delete_selected_files():
    # 检查用户是否已登录
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # 获取要删除的文件名列表
    data = request.get_json()
    filenames = data.get('filenames', [])
    
    # 删除每个文件
    deleted_count = 0
    for filename in filenames:
        # 检查文件名是否安全
        if is_safe_filename(filename):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(filepath) and os.path.isfile(filepath):
                os.remove(filepath)
                deleted_count += 1
    
    return {'success': True, 'deleted_count': deleted_count}

if __name__ == '__main__':
    # 获取环境变量设置，如果没有设置则默认为False
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)