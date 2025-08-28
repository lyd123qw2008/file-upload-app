from flask import Flask, request, send_from_directory, redirect, url_for, render_template_string, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from datetime import datetime
import re
import logging
import markdown
import uuid

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

# 剪贴板数据存储文件路径
CLIPBOARD_FILE = os.path.join(UPLOAD_FOLDER, 'clipboard.json')
# 个人剪贴板数据存储文件路径
PERSONAL_CLIPBOARD_FILE = os.path.join(UPLOAD_FOLDER, 'personal_clipboard.json')

# 初始化剪贴板数据存储
def init_clipboard_storage():
    if not os.path.exists(CLIPBOARD_FILE):
        with open(CLIPBOARD_FILE, 'w', encoding='utf-8') as f:
            json.dump({"clipboard_items": []}, f)

# 初始化个人剪贴板数据存储
def init_personal_clipboard_storage():
    if not os.path.exists(PERSONAL_CLIPBOARD_FILE):
        with open(PERSONAL_CLIPBOARD_FILE, 'w', encoding='utf-8') as f:
            json.dump({"personal_clipboards": []}, f)

# 加载剪贴板数据
def load_clipboard_data():
    try:
        with open(CLIPBOARD_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # 如果文件不存在或解析失败，初始化文件
        init_clipboard_storage()
        with open(CLIPBOARD_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

# 保存剪贴板数据
def save_clipboard_data(data):
    with open(CLIPBOARD_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 加载个人剪贴板数据
def load_personal_clipboard_data():
    try:
        with open(PERSONAL_CLIPBOARD_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # 如果文件不存在或解析失败，初始化文件
        init_personal_clipboard_storage()
        with open(PERSONAL_CLIPBOARD_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

# 保存个人剪贴板数据
def save_personal_clipboard_data(data):
    with open(PERSONAL_CLIPBOARD_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 创建个人剪贴板
def create_personal_clipboard(name, content, creator):
    # 对于单用户场景，创建者就是所有者
    data = load_personal_clipboard_data()
    clipboard = {
        "id": str(uuid.uuid4()),
        "name": name,
        "content": content,
        "creator": creator,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    data["personal_clipboards"].append(clipboard)
    save_personal_clipboard_data(data)
    return clipboard

# 获取用户创建的个人剪贴板
def get_user_personal_clipboards(username):
    data = load_personal_clipboard_data()
    return [clipboard for clipboard in data["personal_clipboards"] 
            if clipboard["creator"] == username]

# 获取特定个人剪贴板
def get_personal_clipboard(clipboard_id, username):
    data = load_personal_clipboard_data()
    for clipboard in data["personal_clipboards"]:
        if clipboard["id"] == clipboard_id and clipboard["creator"] == username:
            return clipboard
    return None

# 更新个人剪贴板内容
def update_personal_clipboard(clipboard_id, content, username):
    data = load_personal_clipboard_data()
    for clipboard in data["personal_clipboards"]:
        if clipboard["id"] == clipboard_id and clipboard["creator"] == username:
            clipboard["content"] = content
            clipboard["updated_at"] = datetime.now().isoformat()
            save_personal_clipboard_data(data)
            return clipboard
    return None

# 删除个人剪贴板
def delete_personal_clipboard(clipboard_id, username):
    data = load_personal_clipboard_data()
    # 用户可以删除自己创建的剪贴板
    data["personal_clipboards"] = [
        clipboard for clipboard in data["personal_clipboards"] 
        if not (clipboard["id"] == clipboard_id and clipboard["creator"] == username)
    ]
    save_personal_clipboard_data(data)

# 添加剪贴板项目
def add_clipboard_item(content, owner, is_public=False):
    # 限制剪贴板内容大小（最大1MB）
    if len(content.encode('utf-8')) > 1024 * 1024:
        raise ValueError("剪贴板内容不得超过1MB")
    
    # 过滤潜在的危险内容
    # 移除可能的脚本标签（基础过滤）
    filtered_content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.IGNORECASE | re.DOTALL)
    
    data = load_clipboard_data()
    item = {
        "id": str(uuid.uuid4()),
        "content": filtered_content,
        "owner": owner,
        "created_at": datetime.now().isoformat(),
        "is_public": is_public
    }
    data["clipboard_items"].append(item)
    save_clipboard_data(data)
    return item

# 获取用户的所有剪贴板项目
def get_user_clipboard_items(username):
    data = load_clipboard_data()
    # 返回用户自己的项目和公开项目
    return [item for item in data["clipboard_items"] 
            if item["owner"] == username or item["is_public"]]

# 获取特定的剪贴板项目
def get_clipboard_item(item_id, username):
    data = load_clipboard_data()
    for item in data["clipboard_items"]:
        # 用户可以访问自己的项目或公开项目
        if item["id"] == item_id and (item["owner"] == username or item["is_public"]):
            return item
    return None

# 删除剪贴板项目
def delete_clipboard_item(item_id, username):
    data = load_clipboard_data()
    # 用户只能删除自己的项目
    data["clipboard_items"] = [item for item in data["clipboard_items"] 
                              if not (item["id"] == item_id and item["owner"] == username)]
    save_clipboard_data(data)

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
    'mpg', 'mpeg', 'wmv', 'flv', 'webm', 'mkv', 'wav', 'ogg', 'ogv', 'm4a',
    'py', 'js', 'java', 'c', 'cpp', 'html', 'css', 'php', 'go', 'rb', 'pl', 'sh', 'sql',
    'md', 'yaml', 'yml', 'json', 'xml', 'conf', 'config', 'ini', 'cfg', 'env', 'env.example'
}

# 可预览的文本文件扩展名
TEXT_PREVIEW_EXTENSIONS = {'txt', 'md', 'log', 'csv', 'json', 'xml', 'html', 'css', 'js', 'py', 'java', 'c', 'cpp', 'sql', 'yaml', 'yml', 'ini', 'cfg', 'conf', 'env', 'sh', 'pl', 'rb', 'go', 'php'}

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
        <p>欢迎, {{ username }}! <a href="/clipboard">网络剪贴板</a> | <a href="/personal_clipboard">个人剪贴板</a> | <a href="/logout" class="logout">退出</a></p>
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

# 剪贴板页面模板
clipboard_template = '''
<!doctype html>
<html>
<head>
    <title>网络剪贴板</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; max-width: 1000px; margin: 20px auto; padding: 20px; }
        h1 { color: #333; }
        .header { display: flex; justify-content: space-between; align-items: center; }
        .logout { background: #dc3545; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; }
        .logout:hover { background: #c82333; }
        .back { background: #007cba; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; }
        .back:hover { background: #005a87; }
        .clipboard-form { background: #f5f5f5; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        textarea { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 3px; }
        input[type="submit"] { background: #28a745; color: white; padding: 10px 20px; border: none; border-radius: 3px; cursor: pointer; }
        input[type="submit"]:hover { background: #218838; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f2f2f2; }
        tr:hover { background-color: #f5f5f5; }
        .actions a { margin-right: 10px; text-decoration: none; padding: 5px 10px; border-radius: 3px; }
        .copy { background: #28a745; color: white; }
        .delete { background: #dc3545; color: white; }
        .actions a:hover { opacity: 0.8; }
        .public { color: #28a745; font-weight: bold; }
        .private { color: #6c757d; }
        .content-preview { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    </style>
</head>
<body>
    <div class="header">
        <h1>网络剪贴板</h1>
        <div>
            <a href="/" class="back">返回文件管理</a>
            <a href="/personal_clipboard" class="back">个人剪贴板</a>
            <a href="/logout" class="logout">退出 ({{ username }})</a>
        </div>
    </div>
    
    <div class="clipboard-form">
        <h2>添加新内容</h2>
        {% if error %}
        <p style="color: red;">错误: {{ error }}</p>
        {% endif %}
        <form method="post">
            <p>
                <label>内容:</label><br>
                <textarea name="content" rows="4" placeholder="在此输入要保存到剪贴板的内容..." required></textarea>
            </p>
            <p>
                <input type="checkbox" name="is_public" id="is_public">
                <label for="is_public">公开内容（其他用户可见）</label>
            </p>
            <p>
                <input type="submit" value="保存到剪贴板">
            </p>
        </form>
    </div>
    
    <h2>剪贴板内容</h2>
    {% if clipboard_items %}
    <table>
        <thead>
            <tr>
                <th>内容预览</th>
                <th>所有者</th>
                <th>可见性</th>
                <th>创建时间</th>
                <th>操作</th>
            </tr>
        </thead>
        <tbody>
            {% for item in clipboard_items %}
            <tr>
                <td class="content-preview">{{ item.content[:50] }}{% if item.content|length > 50 %}...{% endif %}</td>
                <td>{{ item.owner }}</td>
                <td>
                    {% if item.is_public %}
                    <span class="public">公开</span>
                    {% else %}
                    <span class="private">私有</span>
                    {% endif %}
                </td>
                <td>{{ item.created_at[:19].replace('T', ' ') }}</td>
                <td class="actions">
                    {% if item.is_public %}
                    <a href="/clipboard/public/{{ item.id }}" class="copy" target="_blank">复制链接</a>
                    {% else %}
                    <a href="/clipboard/get/{{ item.id }}" class="copy" target="_blank">复制</a>
                    {% endif %}
                    {% if item.owner == username %}
                    <a href="/clipboard/delete/{{ item.id }}" class="delete" onclick="return confirm('确定要删除此剪贴板内容吗？')">删除</a>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p>剪贴板中没有内容。</p>
    {% endif %}
    
    <script>
        // 复制到剪贴板的辅助函数
        function copyToClipboard(text, successMessage, fallbackLabel) {
            // 首先尝试使用现代Clipboard API
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).then(() => {
                    alert(successMessage);
                }).catch(err => {
                    console.error('Clipboard API 失败:', err);
                    // 如果Clipboard API失败，使用降级方案
                    fallbackCopyTextToClipboard(text, fallbackLabel);
                });
            } else {
                // 如果不支持Clipboard API，使用降级方案
                fallbackCopyTextToClipboard(text, fallbackLabel);
            }
        }
        
        // 降级方案：使用临时textarea元素
        function fallbackCopyTextToClipboard(text, label) {
            const textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.style.position = "fixed";
            textArea.style.left = "-999999px";
            textArea.style.top = "-999999px";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            
            try {
                const successful = document.execCommand('copy');
                document.body.removeChild(textArea);
                if (successful) {
                    alert(label + '已复制到剪贴板');
                } else {
                    // 如果execCommand也失败，显示提示框
                    prompt('请手动复制 ' + label + ':', text);
                }
            } catch (err) {
                console.error('execCommand 失败:', err);
                document.body.removeChild(textArea);
                // 显示提示框让用户手动复制
                prompt('请手动复制 ' + label + ':', text);
            }
        }
        
        // 添加复制到剪贴板功能
        document.querySelectorAll('.copy').forEach(link => {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                const url = this.href;
                
                // 检查是否是复制链接操作（公开项目）
                if (this.textContent === '复制链接') {
                    // 复制完整链接到剪贴板
                    const fullUrl = url.startsWith('http') ? url : window.location.origin + url;
                    copyToClipboard(fullUrl, '链接已复制到剪贴板', '链接');
                } else {
                    // 复制内容到剪贴板
                    fetch(url)
                        .then(response => response.text())
                        .then(text => {
                            copyToClipboard(text, '内容已复制到剪贴板', '内容');
                        })
                        .catch(err => {
                            console.error('获取内容失败:', err);
                            alert('获取内容失败，请重试');
                        });
                }
            });
        });
    </script>
</body>
</html>
'''

# 个人剪贴板列表页面模板
personal_clipboard_template = '''
<!doctype html>
<html>
<head>
    <title>个人剪贴板</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; max-width: 1000px; margin: 20px auto; padding: 20px; }
        h1 { color: #333; }
        .header { display: flex; justify-content: space-between; align-items: center; }
        .logout { background: #dc3545; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; }
        .logout:hover { background: #c82333; }
        .back { background: #007cba; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; }
        .back:hover { background: #005a87; }
        .personal-form { background: #f5f5f5; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        input[type="text"], textarea { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 3px; }
        input[type="submit"] { background: #28a745; color: white; padding: 10px 20px; border: none; border-radius: 3px; cursor: pointer; }
        input[type="submit"]:hover { background: #218838; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f2f2f2; }
        tr:hover { background-color: #f5f5f5; }
        .actions a { margin-right: 10px; text-decoration: none; padding: 5px 10px; border-radius: 3px; }
        .view { background: #007cba; color: white; }
        .delete { background: #dc3545; color: white; }
        .actions a:hover { opacity: 0.8; }
        .content-preview { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    </style>
</head>
<body>
    <div class="header">
        <h1>个人剪贴板</h1>
        <div>
            <a href="/clipboard" class="back">返回网络剪贴板</a>
            <a href="/" class="back">返回文件管理</a>
            <a href="/logout" class="logout">退出 ({{ username }})</a>
        </div>
    </div>
    
    <div class="personal-form">
        <h2>创建新的个人剪贴板</h2>
        {% if error %}
        <p style="color: red;">错误: {{ error }}</p>
        {% endif %}
        <form method="post">
            <p>
                <label>名称:</label><br>
                <input type="text" name="name" placeholder="剪贴板名称" required>
            </p>
            <p>
                <label>初始内容:</label><br>
                <textarea name="content" rows="4" placeholder="初始内容..."></textarea>
            </p>
            <p>
                <input type="submit" value="创建剪贴板">
            </p>
        </form>
    </div>
    
    <h2>我的个人剪贴板</h2>
    {% if personal_clipboards %}
    <table>
        <thead>
            <tr>
                <th>名称</th>
                <th>创建时间</th>
                <th>最后更新</th>
                <th>操作</th>
            </tr>
        </thead>
        <tbody>
            {% for clipboard in personal_clipboards %}
            <tr>
                <td>{{ clipboard.name }}</td>
                <td>{{ clipboard.created_at[:19].replace('T', ' ') }}</td>
                <td>{{ clipboard.updated_at[:19].replace('T', ' ') }}</td>
                <td class="actions">
                    <a href="/personal_clipboard/{{ clipboard.id }}" class="view">查看/编辑</a>
                    <a href="/personal_clipboard/delete/{{ clipboard.id }}" class="delete" onclick="return confirm('确定要删除 {{ clipboard.name }} 吗？')">删除</a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p>没有个人剪贴板。</p>
    {% endif %}
</body>
</html>
'''

# 个人剪贴板详情页面模板
personal_clipboard_detail_template = '''
<!doctype html>
<html>
<head>
    <title>个人剪贴板 - {{ clipboard.name }}</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; max-width: 1000px; margin: 20px auto; padding: 20px; }
        h1 { color: #333; }
        .header { display: flex; justify-content: space-between; align-items: center; }
        .logout { background: #dc3545; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; }
        .logout:hover { background: #c82333; }
        .back { background: #007cba; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; }
        .back:hover { background: #005a87; }
        .personal-detail-form { background: #f5f5f5; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        textarea { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 3px; }
        input[type="submit"] { background: #28a745; color: white; padding: 10px 20px; border: none; border-radius: 3px; cursor: pointer; }
        input[type="submit"]:hover { background: #218838; }
        .info { background: #e9ecef; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>个人剪贴板 - {{ clipboard.name }}</h1>
        <div>
            <a href="/personal_clipboard" class="back">返回列表</a>
            <a href="/personal_clipboard/{{ clipboard.id }}" class="back">刷新</a>
            <a href="/logout" class="logout">退出 ({{ username }})</a>
        </div>
    </div>
    
    <div class="info">
        <strong>创建时间:</strong> {{ clipboard.created_at[:19].replace('T', ' ') }}<br>
        <strong>最后更新:</strong> {{ clipboard.updated_at[:19].replace('T', ' ') }}
    </div>
    
    <div class="personal-detail-form">
        <h2>编辑内容</h2>
        {% if error %}
        <p style="color: red;">错误: {{ error }}</p>
        {% endif %}
        <form method="post">
            <p>
                <textarea name="content" rows="15">{{ clipboard.content }}</textarea>
            </p>
            <p>
                <input type="submit" value="保存内容">
            </p>
        </form>
    </div>
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
    <meta http-equiv="Content-Security-Policy" content="script-src 'self' 'unsafe-eval' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com;">
    <script src="https://cdn.jsdelivr.net/npm/markdown-it@14.1.0/dist/markdown-it.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/default.min.css">
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
        code { font-family: 'Courier New', monospace; }
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
        /* 代码高亮样式 */
        .highlight .hll { background-color: #ffffcc }
        .highlight  { background: #f8f8f8; }
        .highlight .c { color: #408080; font-style: italic } /* Comment */
        .highlight .err { border: 1px solid #FF0000 } /* Error */
        .highlight .k { color: #008000; font-weight: bold } /* Keyword */
        .highlight .o { color: #666666 } /* Operator */
        .highlight .cm { color: #408080; font-style: italic } /* Comment.Multiline */
        .highlight .cp { color: #BC7A00 } /* Comment.Preproc */
        .highlight .c1 { color: #408080; font-style: italic } /* Comment.Single */
        .highlight .cs { color: #408080; font-style: italic } /* Comment.Special */
        .highlight .gd { color: #A00000 } /* Generic.Deleted */
        .highlight .ge { font-style: italic } /* Generic.Emph */
        .highlight .gr { color: #FF0000 } /* Generic.Error */
        .highlight .gh { color: #000080; font-weight: bold } /* Generic.Heading */
        .highlight .gi { color: #00A000 } /* Generic.Inserted */
        .highlight .go { color: #888888 } /* Generic.Output */
        .highlight .gp { color: #000080; font-weight: bold } /* Generic.Prompt */
        .highlight .gs { font-weight: bold } /* Generic.Strong */
        .highlight .gu { color: #800080; font-weight: bold } /* Generic.Subheading */
        .highlight .gt { color: #0044DD } /* Generic.Traceback */
        .highlight .kc { color: #008000; font-weight: bold } /* Keyword.Constant */
        .highlight .kd { color: #008000; font-weight: bold } /* Keyword.Declaration */
        .highlight .kn { color: #008000; font-weight: bold } /* Keyword.Namespace */
        .highlight .kp { color: #008000 } /* Keyword.Pseudo */
        .highlight .kr { color: #008000; font-weight: bold } /* Keyword.Reserved */
        .highlight .kt { color: #B00040 } /* Keyword.Type */
        .highlight .m { color: #666666 } /* Literal.Number */
        .highlight .s { color: #BA2121 } /* Literal.String */
        .highlight .na { color: #7D9029 } /* Name.Attribute */
        .highlight .nb { color: #008000 } /* Name.Builtin */
        .highlight .nc { color: #0000FF; font-weight: bold } /* Name.Class */
        .highlight .no { color: #880000 } /* Name.Constant */
        .highlight .nd { color: #AA22FF } /* Name.Decorator */
        .highlight .ni { color: #999999; font-weight: bold } /* Name.Entity */
        .highlight .ne { color: #D2413A; font-weight: bold } /* Name.Exception */
        .highlight .nf { color: #0000FF } /* Name.Function */
        .highlight .nl { color: #A0A000 } /* Name.Label */
        .highlight .nn { color: #0000FF; font-weight: bold } /* Name.Namespace */
        .highlight .nt { color: #008000; font-weight: bold } /* Name.Tag */
        .highlight .nv { color: #19177C } /* Name.Variable */
        .highlight .ow { color: #AA22FF; font-weight: bold } /* Operator.Word */
        .highlight .w { color: #bbbbbb } /* Text.Whitespace */
        .highlight .mf { color: #666666 } /* Literal.Number.Float */
        .highlight .mh { color: #666666 } /* Literal.Number.Hex */
        .highlight .mi { color: #666666 } /* Literal.Number.Integer */
        .highlight .mo { color: #666666 } /* Literal.Number.Oct */
        .highlight .sb { color: #BA2121 } /* Literal.String.Backtick */
        .highlight .sc { color: #BA2121 } /* Literal.String.Char */
        .highlight .sd { color: #BA2121; font-style: italic } /* Literal.String.Doc */
        .highlight .s2 { color: #BA2121 } /* Literal.String.Double */
        .highlight .se { color: #BB6622; font-weight: bold } /* Literal.String.Escape */
        .highlight .sh { color: #BA2121 } /* Literal.String.Heredoc */
        .highlight .si { color: #BB6688; font-weight: bold } /* Literal.String.Interpol */
        .highlight .sx { color: #008000 } /* Literal.String.Other */
        .highlight .sr { color: #BB6688 } /* Literal.String.Regex */
        .highlight .s1 { color: #BA2121 } /* Literal.String.Single */
        .highlight .ss { color: #19177C } /* Literal.String.Symbol */
        .highlight .bp { color: #008000 } /* Name.Builtin.Pseudo */
        .highlight .vc { color: #19177C } /* Name.Variable.Class */
        .highlight .vg { color: #19177C } /* Name.Variable.Global */
        .highlight .vi { color: #19177C } /* Name.Variable.Instance */
        .highlight .il { color: #666666 } /* Literal.Number.Integer.Long */
        
        /* Markdown渲染样式 */
        .markdown-content { font-family: Arial, sans-serif; }
        .markdown-content h1 { color: #333; border-bottom: 1px solid #ddd; padding-bottom: 10px; }
        .markdown-content h2 { color: #444; border-bottom: 1px solid #eee; padding-bottom: 8px; }
        .markdown-content h3 { color: #555; }
        .markdown-content code { background-color: #f5f5f5; padding: 2px 4px; border-radius: 3px; font-family: 'Courier New', monospace; }
        .markdown-content pre { background-color: #f8f8f8; padding: 10px; border-radius: 5px; overflow: auto; }
        .markdown-content pre code { background-color: transparent; padding: 0; }
        .markdown-content blockquote { border-left: 4px solid #ddd; padding: 0 15px; color: #666; }
        .markdown-content ul, .markdown-content ol { padding-left: 30px; }
        .markdown-content li { margin-bottom: 5px; }
        .markdown-content a { color: #007cba; text-decoration: none; }
        .markdown-content a:hover { text-decoration: underline; }
        .markdown-content table { border-collapse: collapse; width: 100%; margin: 15px 0; }
        .markdown-content th, .markdown-content td { border: 1px solid #ddd; padding: 8px 12px; }
        .markdown-content th { background-color: #f5f5f5; font-weight: bold; }
        
        /* 切换按钮样式 */
        .toggle-buttons { margin: 10px 0; }
        .toggle-btn { 
            background: #007cba; 
            color: white; 
            padding: 5px 10px; 
            border: none; 
            border-radius: 3px; 
            cursor: pointer; 
            margin-right: 10px;
        }
        .toggle-btn:hover { background: #005a87; }
        .toggle-btn.active { background: #28a745; }
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
        <div class="toggle-buttons">
            <button id="rawBtn" class="toggle-btn active" onclick="toggleView('raw')">纯文本</button>
            <button id="renderedBtn" class="toggle-btn" onclick="toggleView('rendered')">渲染显示</button>
        </div>
        <div class="preview-content">
            <pre id="rawContent" style="display: block;">{{ content }}</pre>
            <div id="renderedContent" style="display: none;"></div>
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
    
    <script>
        // 获取文件扩展名
        function getFileExtension(filename) {
            return filename.split('.').pop().toLowerCase();
        }
        
        // 切换视图
        function toggleView(view) {
            const rawBtn = document.getElementById('rawBtn');
            const renderedBtn = document.getElementById('renderedBtn');
            const rawContent = document.getElementById('rawContent');
            const renderedContent = document.getElementById('renderedContent');
            
            if (view === 'raw') {
                rawBtn.classList.add('active');
                renderedBtn.classList.remove('active');
                rawContent.style.display = 'block';
                renderedContent.style.display = 'none';
            } else {
                rawBtn.classList.remove('active');
                renderedBtn.classList.add('active');
                rawContent.style.display = 'none';
                renderedContent.style.display = 'block';
                
                // 渲染内容
                renderContent();
            }
        }
        
        // 渲染内容
        function renderContent() {
            const filename = "{{ filename }}";
            const extension = getFileExtension(filename);
            const content = {{ content|tojson }};
            const renderedContent = document.getElementById('renderedContent');
            
            if (extension === 'md') {
                // Markdown渲染
                const md = markdownit();
                renderedContent.innerHTML = '<div class="markdown-content">' + md.render(content) + '</div>';
            } else if (['py', 'js', 'java', 'c', 'cpp', 'html', 'css', 'php', 'sql', 'xml', 'json', 'yaml', 'yml', 'ini', 'cfg', 'conf', 'sh', 'pl', 'rb', 'go'].includes(extension)) {
                // 代码高亮
                // 转义HTML特殊字符以提高安全性
                const escapedContent = content
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#039;');
                renderedContent.innerHTML = '<pre><code class="language-' + extension + '">' + escapedContent + '</code></pre>';
                // 使用highlight.js进行代码高亮
                if (typeof hljs !== 'undefined' && typeof hljs.highlightAll === 'function') {
                    hljs.highlightAll();
                }
            } else {
                // 其他文本文件保持原样显示
                // 转义HTML特殊字符以提高安全性
                const escapedContent = content
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#039;');
                renderedContent.innerHTML = '<pre>' + escapedContent + '</pre>';
            }
        }
        
        // 页面加载完成后初始化
        document.addEventListener('DOMContentLoaded', function() {
            // 如果是文本文件，默认显示纯文本视图
            const rawBtn = document.getElementById('rawBtn');
            if (rawBtn) {
                rawBtn.classList.add('active');
            }
        });
    </script>
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
                                    preview_type='image',
                                    content='')
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

# 剪贴板页面路由
@app.route('/clipboard', methods=['GET', 'POST'])
def clipboard():
    # 检查用户是否已登录
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    error_message = None
    
    if request.method == 'POST':
        # 处理添加新剪贴板内容
        content = request.form.get('content', '')
        is_public = request.form.get('is_public') == 'on'
        
        if content:
            try:
                add_clipboard_item(content, username, is_public)
            except ValueError as e:
                error_message = str(e)
    
    # 获取用户的剪贴板项目
    clipboard_items = get_user_clipboard_items(username)
    
    # 按创建时间倒序排列
    clipboard_items.sort(key=lambda x: x['created_at'], reverse=True)
    
    return render_template_string(clipboard_template, 
                                username=username, 
                                clipboard_items=clipboard_items,
                                error=error_message)

# 删除剪贴板项目的路由
@app.route('/clipboard/delete/<item_id>')
def delete_clipboard_item_route(item_id):
    # 检查用户是否已登录
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    delete_clipboard_item(item_id, username)
    
    return redirect(url_for('clipboard'))

# 获取剪贴板内容的API路由（需要认证）
@app.route('/clipboard/get/<item_id>')
def get_clipboard_item_route(item_id):
    # 检查用户是否已登录
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    item = get_clipboard_item(item_id, username)
    
    if item:
        return item['content']
    else:
        return "剪贴板项目未找到或无权访问", 404

# 获取公开剪贴板内容的路由（无需认证）
@app.route('/clipboard/public/<item_id>')
def get_public_clipboard_item_route(item_id):
    data = load_clipboard_data()
    for item in data["clipboard_items"]:
        if item["id"] == item_id and item["is_public"]:
            return item['content']
    
    return "公开剪贴板项目未找到", 404

# 个人剪贴板列表页面
@app.route('/personal_clipboard', methods=['GET', 'POST'])
def personal_clipboard():
    # 检查用户是否已登录
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    error_message = None
    
    if request.method == 'POST':
        # 处理创建新的个人剪贴板
        name = request.form.get('name', '')
        content = request.form.get('content', '')
        
        if name and content is not None:
            try:
                create_personal_clipboard(name, content, username)
            except Exception as e:
                error_message = str(e)
    
    # 获取用户创建的个人剪贴板
    personal_clipboards = get_user_personal_clipboards(username)
    
    return render_template_string(personal_clipboard_template, 
                                username=username, 
                                personal_clipboards=personal_clipboards,
                                error=error_message)

# 个人剪贴板详情页面
@app.route('/personal_clipboard/<clipboard_id>', methods=['GET', 'POST'])
def personal_clipboard_detail(clipboard_id):
    # 检查用户是否已登录
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    error_message = None
    
    # 获取个人剪贴板
    clipboard = get_personal_clipboard(clipboard_id, username)
    if not clipboard:
        return "个人剪贴板未找到或无权访问", 404
    
    if request.method == 'POST':
        # 处理保存内容
        content = request.form.get('content', '')
        try:
            update_personal_clipboard(clipboard_id, content, username)
            # 更新成功后重新获取剪贴板内容
            clipboard = get_personal_clipboard(clipboard_id, username)
        except Exception as e:
            error_message = str(e)
    
    return render_template_string(personal_clipboard_detail_template, 
                                username=username, 
                                clipboard=clipboard,
                                error=error_message)

# 删除个人剪贴板的路由
@app.route('/personal_clipboard/delete/<clipboard_id>')
def delete_personal_clipboard_route(clipboard_id):
    # 检查用户是否已登录
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    delete_personal_clipboard(clipboard_id, username)
    
    return redirect(url_for('personal_clipboard'))

# 应用启动时初始化剪贴板存储
init_clipboard_storage()
init_personal_clipboard_storage()

if __name__ == '__main__':
    # 获取环境变量设置，如果没有设置则默认为False
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)