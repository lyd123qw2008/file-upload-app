from flask import Flask, request, send_from_directory, redirect, url_for, render_template_string, session, abort, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from datetime import datetime
import re
import logging
import markdown
import uuid
import random
import string
import io
import base64
from PIL import Image, ImageDraw, ImageFont

# 配置日志
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
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

# 生成验证码
def generate_captcha_text(length=4):
    """生成随机验证码文本"""
    characters = string.digits  # 只使用数字
    return ''.join(random.choice(characters) for _ in range(length))

# 生成验证码图片
def generate_captcha_image(text):
    """生成验证码图片"""
    width = 120
    height = 40

    # 创建图片
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    try:
        # 尝试使用DejaVu字体，减小字体大小
        font_size = 24
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
    except:
        try:
            # 尝试使用Liberation字体
            font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", font_size)
        except:
            # 使用默认字体
            font = ImageFont.load_default()

    # 计算字符位置，使4个数字均匀分布并最大化利用空间
    char_width = width // len(text)

    # 简化的文本绘制 - 直接绘制，不旋转
    for i, char in enumerate(text):
        x = i * char_width + (char_width // 2) - (font_size // 3)
        y = 10  # 固定垂直位置，减少随机计算
        draw.text((x, y), char, font=font, fill=(0, 0, 0))

    # 减少干扰线数量
    for _ in range(2):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)), width=1)

    # 减少干扰点数量
    for _ in range(10):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))

    # 将图片转换为base64
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

# 验证验证码
def validate_captcha(user_input, session_captcha):
    """验证用户输入的验证码是否正确"""
    if not session_captcha or not user_input:
        return False
    return user_input.upper() == session_captcha.upper()

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
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(120deg, #eff6ff, #f8fafc);
            color: #0f172a;
        }
        .auth-shell {
            width: 100%;
            max-width: 420px;
            padding: 32px 24px 48px;
        }
        .auth-card {
            background: #ffffff;
            border-radius: 20px;
            padding: 32px;
            box-shadow: 0 24px 48px rgba(15, 23, 42, 0.12);
            border: 1px solid rgba(148, 163, 184, 0.16);
            display: flex;
            flex-direction: column;
            gap: 24px;
        }
        h1 {
            margin: 0;
            font-size: 28px;
            font-weight: 700;
            color: #0f172a;
        }
        .subtitle {
            margin: 0;
            font-size: 15px;
            color: #475569;
        }
        form {
            display: flex;
            flex-direction: column;
            gap: 18px;
        }
        label { font-weight: 600; color: #1e293b; }
        .input-group { display: flex; flex-direction: column; gap: 8px; }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 14px 16px;
            border-radius: 14px;
            border: 1px solid rgba(148, 163, 184, 0.6);
            background: rgba(248, 250, 252, 0.9);
            font-size: 15px;
        }
        input[type="text"]:focus, input[type="password"]:focus {
            outline: none;
            border-color: #2563eb;
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
        }
        .captcha-row {
            display: flex;
            gap: 12px;
            align-items: center;
            flex-wrap: wrap;
        }
        .captcha-input {
            flex: 1;
            min-width: 180px;
        }
        .captcha-image {
            border-radius: 12px;
            border: 1px solid rgba(148, 163, 184, 0.6);
            height: 48px;
            cursor: pointer;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 12px 20px;
            border-radius: 999px;
            font-size: 15px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.2s ease;
        }
        .btn:focus { outline: none; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.35); }
        .btn-primary {
            background: linear-gradient(90deg, #2563eb, #1d4ed8);
            color: #ffffff;
            box-shadow: 0 12px 24px rgba(29, 78, 216, 0.28);
        }
        .btn-primary:hover { background: linear-gradient(90deg, #1d4ed8, #1e40af); transform: translateY(-1px); }
        .btn-secondary {
            background: rgba(15, 23, 42, 0.08);
            color: #1f2937;
        }
        .btn-secondary:hover { background: rgba(15, 23, 42, 0.12); transform: translateY(-1px); }
        .alert {
            background: #fee2e2;
            color: #991b1b;
            border: 1px solid #fca5a5;
            border-radius: 14px;
            padding: 14px 18px;
            font-size: 14px;
            font-weight: 500;
        }
        .helper-footer {
            font-size: 13px;
            color: #64748b;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="auth-shell">
        <div class="auth-card">
            <div>
                <h1>文件上传系统</h1>
                <p class="subtitle">请输入账号信息完成身份验证。</p>
            </div>
            {% if error %}
            <div class="alert">{{ error }}</div>
            {% endif %}
            <form method="post">
                <div class="input-group">
                    <label for="username">用户名</label>
                    <input type="text" name="username" id="username" placeholder="输入用户名" required>
                </div>
                <div class="input-group">
                    <label for="password">密码</label>
                    <input type="password" name="password" id="password" placeholder="输入密码" required>
                </div>
                <div class="input-group">
                    <label for="captcha">验证码</label>
                    <div class="captcha-row">
                        <input type="text" name="captcha" id="captcha" class="captcha-input" placeholder="请输入验证码" required>
                        <img src="{{ captcha_image }}" alt="验证码" class="captcha-image" onclick="refreshCaptcha()" title="点击刷新验证码">
                        <button type="button" class="btn btn-secondary" onclick="refreshCaptcha()">刷新</button>
                    </div>
                </div>
                <button type="submit" class="btn btn-primary">登录系统</button>
            </form>
            <p class="helper-footer">多次失败会触发验证码刷新，请妥善保管管理员凭证。</p>
        </div>
    </div>

    <script>
        function refreshCaptcha() {
            // 添加时间戳防止缓存
            const timestamp = new Date().getTime();
            fetch('/captcha?' + timestamp)
                .then(response => response.json())
                .then(data => {
                    document.querySelector('.captcha-image').src = data.captcha_image;
                })
                .catch(error => {
                    console.error('获取验证码失败:', error);
                });
        }
    </script>
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

# 压缩包文件扩展名
ARCHIVE_EXTENSIONS = {'zip', 'rar', '7z', 'tar', 'gz'}

# 上传页面模板
upload_template = '''
<!doctype html>
<html>
<head>
    <title>文件管理</title>
    <meta charset="utf-8">
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(120deg, #eff6ff, #f8fafc);
            color: #0f172a;
        }
        a { text-decoration: none; }
        .page-wrapper {
            max-width: 1080px;
            margin: 48px auto;
            padding: 0 24px 48px;
            display: flex;
            flex-direction: column;
            gap: 32px;
        }
        .card {
            background: #ffffff;
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 24px 48px rgba(15, 23, 42, 0.08);
            border: 1px solid rgba(148, 163, 184, 0.16);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 24px;
        }
        .header h1 {
            margin: 0;
            font-size: 32px;
            font-weight: 700;
            color: #0f172a;
        }
        .nav-actions {
            display: flex;
            gap: 12px;
            align-items: center;
            font-size: 15px;
        }
        .nav-actions a {
            color: #1d4ed8;
            font-weight: 600;
        }
        .nav-actions a:hover { color: #1e3a8a; }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 10px 20px;
            border-radius: 999px;
            font-size: 14px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.2s ease;
        }
        .btn:focus { outline: none; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.35); }
        .btn:disabled { cursor: not-allowed; opacity: 0.6; box-shadow: none; }
        .btn-primary {
            background: linear-gradient(90deg, #2563eb, #1d4ed8);
            color: #ffffff;
            box-shadow: 0 12px 24px rgba(29, 78, 216, 0.28);
        }
        .btn-primary:hover { background: linear-gradient(90deg, #1d4ed8, #1e40af); transform: translateY(-1px); }
        .btn-secondary {
            background: rgba(15, 23, 42, 0.08);
            color: #1f2937;
        }
        .btn-secondary:hover { background: rgba(15, 23, 42, 0.12); transform: translateY(-1px); }
        .btn-danger {
            background: linear-gradient(90deg, #ef4444, #dc2626);
            color: #ffffff;
            box-shadow: 0 12px 24px rgba(239, 68, 68, 0.25);
        }
        .btn-danger:hover { background: linear-gradient(90deg, #dc2626, #b91c1c); transform: translateY(-1px); }
        .storage-card {
            display: flex;
            flex-direction: column;
            gap: 16px;
            background: linear-gradient(135deg, #eef2ff, #ffffff);
        }
        .storage-summary { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; }
        .storage-text { font-size: 16px; color: #1e293b; }
        .storage-usage { font-weight: 600; color: #1d4ed8; }
        .storage-meter {
            width: 100%;
            height: 12px;
            background: rgba(148, 163, 184, 0.25);
            border-radius: 999px;
            overflow: hidden;
        }
        .storage-meter-fill {
            height: 100%;
            background: linear-gradient(90deg, #38bdf8, #1d4ed8);
            transition: width 0.4s ease;
        }
        .alert {
            padding: 16px 20px;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 500;
            display: flex;
            gap: 12px;
            align-items: flex-start;
            margin-bottom: 24px;
        }
        .alert::before {
            content: '⚠';
            font-size: 18px;
        }
        .alert-warning {
            background: #fef3c7;
            color: #92400e;
            border: 1px solid #fcd34d;
        }
        .alert-error {
            background: #fee2e2;
            color: #991b1b;
            border: 1px solid #fca5a5;
        }
        .upload-panel {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        .upload-panel h2 { margin: 0; font-size: 22px; color: #0f172a; }
        .upload-form-inner { display: flex; flex-direction: column; gap: 16px; }
        .input-label { font-weight: 600; color: #1e293b; }
        input[type="file"] {
            width: 100%;
            padding: 16px;
            border-radius: 14px;
            border: 1px solid rgba(148, 163, 184, 0.6);
            background: rgba(248, 250, 252, 0.9);
            cursor: pointer;
        }
        input[type="file"]:hover { border-color: #2563eb; }
        .drop-zone {
            border: 2px dashed rgba(37, 99, 235, 0.55);
            border-radius: 16px;
            padding: 36px;
            text-align: center;
            background: rgba(59, 130, 246, 0.08);
            transition: all 0.25s ease;
            cursor: pointer;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .drop-zone::before {
            content: '📁';
            font-size: 32px;
        }
        .drop-zone.dragover {
            background: rgba(59, 130, 246, 0.16);
            border-color: #2563eb;
            transform: translateY(-2px);
        }
        .drop-zone-text { color: #1d4ed8; font-size: 16px; font-weight: 600; }
        .drop-zone-highlight { font-weight: 700; }
        .drop-zone-or { color: #475569; font-size: 14px; }
        .progress-container {
            display: none;
            flex-direction: column;
            gap: 12px;
        }
        .progress-bar {
            width: 100%;
            background-color: rgba(203, 213, 225, 0.5);
            border-radius: 999px;
            overflow: hidden;
            height: 16px;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #34d399, #059669);
            width: 0%;
            transition: width 0.3s ease;
        }
        .progress-text { text-align: center; font-size: 14px; color: #1f2937; font-weight: 600; }
        .upload-status { font-size: 14px; color: #475569; }
        .table-card { padding: 0; }
        .table-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 24px;
            border-bottom: 1px solid rgba(148, 163, 184, 0.16);
        }
        .table-header h2 { margin: 0; font-size: 22px; color: #0f172a; }
        .table-actions { display: flex; gap: 12px; flex-wrap: wrap; }
        .table-wrapper { overflow-x: auto; }
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 14px;
        }
        thead tr { background: rgba(248, 250, 252, 0.9); }
        th, td {
            padding: 16px 20px;
            text-align: left;
            border-bottom: 1px solid rgba(226, 232, 240, 0.9);
        }
        th:first-child, td:first-child { padding-left: 24px; }
        th:last-child, td:last-child { padding-right: 24px; }
        tbody tr:hover { background: rgba(59, 130, 246, 0.06); }
        .actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .actions a {
            padding: 8px 14px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 600;
            color: #ffffff;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .actions a:hover { transform: translateY(-1px); }
        .preview { background: linear-gradient(90deg, #22c55e, #16a34a); box-shadow: 0 10px 20px rgba(34, 197, 94, 0.25); }
        .download { background: linear-gradient(90deg, #0ea5e9, #0284c7); box-shadow: 0 10px 20px rgba(14, 165, 233, 0.25); }
        .delete { background: linear-gradient(90deg, #ef4444, #dc2626); box-shadow: 0 10px 20px rgba(239, 68, 68, 0.3); }
        .error { color: #b91c1c; font-weight: 600; }
        .helper-text { font-size: 13px; color: #64748b; }
        .tag {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 999px;
            background: rgba(37, 99, 235, 0.1);
            color: #1d4ed8;
            font-size: 13px;
            font-weight: 600;
        }
        @media (max-width: 768px) {
            .header { flex-direction: column; align-items: flex-start; }
            .nav-actions { flex-wrap: wrap; }
            .card { padding: 20px; }
            th:nth-child(3), td:nth-child(3), th:nth-child(4), td:nth-child(4) { white-space: nowrap; }
            .table-header { flex-direction: column; align-items: flex-start; gap: 16px; }
            .table-actions { width: 100%; }
            .actions { width: 100%; }
        }
    </style>
</head>
<body>
    <div class="page-wrapper">
        <header class="header card">
            <div>
                <h1>文件管理</h1>
                <p class="helper-text">拖拽、筛选与批量操作，让日常协作更顺畅。</p>
            </div>
            <div class="nav-actions">
                <span class="tag">欢迎 {{ username }}</span>
                <a href="/clipboard">网络剪贴板</a>
                <a href="/personal_clipboard">个人剪贴板</a>
                <a href="/logout" class="btn btn-danger">退出</a>
            </div>
        </header>

        <section class="card storage-card">
            <div class="storage-summary">
                <div class="storage-text">当前存储使用情况</div>
                <div class="storage-usage">{{ used_storage }} / {{ max_storage }} ({{ usage_percentage }}%)</div>
            </div>
            <div class="storage-meter">
                <div class="storage-meter-fill" style="width: {{ usage_percentage }}%;"></div>
            </div>
        </section>

        {% if storage_warning %}
        <div class="alert alert-warning">
            警告: 存储空间已使用 {{ usage_percentage }}%，请考虑删除一些文件以释放空间。
        </div>
        {% endif %}

        {% if storage_full %}
        <div class="alert alert-error">
            错误: 存储空间已满，无法上传更多文件。请删除一些文件以释放空间。
        </div>
        {% else %}
        <section class="card upload-panel">
            <div>
                <h2>上传文件</h2>
                <p class="helper-text">支持多文件批量上传，系统会自动校验容量与格式。</p>
            </div>
            {% if error %}
            <p class="error">{{ error }}</p>
            {% endif %}
            <form id="uploadForm" method="post" enctype="multipart/form-data" class="upload-form-inner">
                <!-- 拖拽上传区域 -->
                <div id="dropZone" class="drop-zone">
                    <div class="drop-zone-text"><span class="drop-zone-highlight">拖拽文件到此处</span></div>
                    <div class="drop-zone-or">或</div>
                    <div class="drop-zone-text">点击选择多个文件</div>
                </div>

                <div>
                    <label for="fileInput" class="input-label">选择文件</label>
                    <input type="file" name="file" id="fileInput" multiple required>
                    <p class="helper-text">建议按批次上传，方便快速撤销或重试。</p>
                </div>
                <div>
                    <button type="submit" class="btn btn-primary" id="uploadButton">开始上传</button>
                </div>
            </form>

            <!-- 进度条 -->
            <div id="progressContainer" class="progress-container">
                <div class="progress-bar">
                    <div id="progressFill" class="progress-fill"></div>
                </div>
                <div id="progressText" class="progress-text">0%</div>
                <div id="uploadStatus" class="upload-status"></div>
                <button id="cancelButton" type="button" class="btn btn-danger" style="display:none;">取消上传</button>
            </div>
            <!-- 存储限制信息（用于前端检查） -->
            <div id="storageInfo" style="display:none;" 
                 data-max-storage="{{ max_storage }}" 
                 data-used-storage="{{ used_storage }}" 
                 data-usage-percentage="{{ usage_percentage }}">
            </div>
        </section>
        {% endif %}

        <section class="card table-card">
            <div class="table-header">
                <h2>文件列表</h2>
                <div class="table-actions">
                    <button id="selectAllBtn" type="button" class="btn btn-secondary">全选</button>
                    <button id="deselectAllBtn" type="button" class="btn btn-secondary">取消全选</button>
                    <button id="deleteSelectedBtn" type="button" class="btn btn-danger" onclick="deleteSelectedFiles()">批量删除</button>
                </div>
            </div>
            <div class="table-wrapper">
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
            </div>
        </section>
    </div>
    
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
        
        const uploadForm = document.getElementById('uploadForm');
        const fileInput = document.getElementById('fileInput');
        const progressContainer = document.getElementById('progressContainer');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        const uploadStatus = document.getElementById('uploadStatus');
        const uploadButton = document.getElementById('uploadButton');
        const cancelButton = document.getElementById('cancelButton');
        const storageInfo = document.getElementById('storageInfo');
        const dropZone = document.getElementById('dropZone');

        // 上传进度处理
        uploadForm.addEventListener('submit', function(e) {
            e.preventDefault();
            startUpload(Array.from(fileInput.files));
        });

        function startUpload(files) {
            if (!files || files.length === 0) {
                alert('请选择至少一个文件');
                return;
            }

            // 计算本次上传的总大小
            const totalSize = files.reduce((acc, file) => acc + file.size, 0);

            const maxStorageBytes = parseFileSize(storageInfo.getAttribute('data-max-storage'));
            const usedStorageBytes = parseFileSize(storageInfo.getAttribute('data-used-storage'));

            if (usedStorageBytes + totalSize > maxStorageBytes) {
                alert('本次上传的文件总大小将超出存储限制，请删除一些文件或减少上传数量。');
                return;
            }

            progressContainer.style.display = 'block';
            cancelButton.style.display = 'block';
            progressFill.style.width = '0%';
            progressText.textContent = '0%';
            uploadStatus.textContent = files.length > 1 ? `准备上传 ${files.length} 个文件...` : '准备上传...';
            uploadButton.disabled = true;
            uploadButton.value = '上传中...';

            const formData = new FormData();
            files.forEach(file => formData.append('file', file));

            const xhr = new XMLHttpRequest();

            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    const percentComplete = Math.round((e.loaded / e.total) * 100);
                    progressFill.style.width = percentComplete + '%';
                    progressText.textContent = percentComplete + '%';
                    uploadStatus.textContent = `已上传 ${formatBytes(e.loaded)} / ${formatBytes(e.total)}${files.length > 1 ? `（共 ${files.length} 个文件）` : ''}`;
                }
            });

            xhr.addEventListener('load', function() {
                cancelButton.style.display = 'none';

                if (xhr.status !== 200) {
                    uploadStatus.textContent = '上传失败，请重试';
                    resetUploadState();
                    return;
                }

                let response;
                try {
                    response = JSON.parse(xhr.responseText);
                } catch (error) {
                    uploadStatus.textContent = '服务器返回了无法解析的响应';
                    resetUploadState();
                    return;
                }

                const { success, uploaded, errors, storage } = response;

                if (Array.isArray(uploaded) && storage && storage.used_storage) {
                    storageInfo.setAttribute('data-used-storage', storage.used_storage);
                }

                if (success) {
                    progressFill.style.width = '100%';
                    progressText.textContent = '100%';
                    const uploadedNames = uploaded.map(item => item.name).join('，');
                    let statusMessage = uploaded.length > 1 ? `成功上传 ${uploaded.length} 个文件：${uploadedNames}` : `成功上传 ${uploaded[0].name}`;
                    const hasErrors = errors && errors.length > 0;
                    if (hasErrors) {
                        statusMessage += `。以下文件上传失败：${errors.join('；')}`;
                    }
                    uploadStatus.textContent = statusMessage;
                    setTimeout(function() {
                        window.location.reload();
                    }, hasErrors ? 2500 : 1200);
                    return;
                }

                if (errors && errors.length > 0) {
                    uploadStatus.textContent = '上传失败：' + errors.join('；');
                } else {
                    uploadStatus.textContent = '上传失败，请重试';
                }

                resetUploadState();
            });

            xhr.addEventListener('error', function() {
                uploadStatus.textContent = '上传出错，请重试';
                resetUploadState();
            });

            cancelButton.onclick = function() {
                xhr.abort();
                uploadStatus.textContent = '上传已取消';
                resetUploadState();
                setTimeout(function() {
                    progressContainer.style.display = 'none';
                }, 2000);
            };

            xhr.open('POST', '/upload');
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            xhr.send(formData);
        }

        function resetUploadState() {
            uploadButton.disabled = false;
            uploadButton.value = '上传';
            cancelButton.style.display = 'none';
            fileInput.value = '';
        }
        
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
        
        // 拖拽上传功能
        // 阻止浏览器默认的拖拽行为
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
            document.body.addEventListener(eventName, preventDefaults, false);
        });
        
        // 添加拖拽高亮效果
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, highlight, false);
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, unhighlight, false);
        });
        
        // 处理文件拖拽放下事件
        dropZone.addEventListener('drop', handleDrop, false);
        
        // 点击拖拽区域时触发文件选择
        dropZone.addEventListener('click', () => {
            fileInput.click();
        });
        
        // 文件输入框变化时触发上传
        fileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                startUpload(Array.from(this.files));
            }
        });
        
        // 阻止默认行为的函数
        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }
        
        // 添加高亮效果
        function highlight() {
            dropZone.classList.add('dragover');
        }
        
        // 移除高亮效果
        function unhighlight() {
            dropZone.classList.remove('dragover');
        }
        
        // 处理拖拽放下的文件
        function handleDrop(e) {
            const files = Array.from(e.dataTransfer.files || []);

            if (files.length > 0) {
                const dataTransfer = new DataTransfer();
                files.forEach(file => dataTransfer.items.add(file));
                fileInput.files = dataTransfer.files;
                startUpload(files);
            }
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
        * { box-sizing: border-box; }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(120deg, #eff6ff, #f8fafc);
            color: #0f172a;
        }
        a { text-decoration: none; }
        .page-wrapper {
            max-width: 1080px;
            margin: 48px auto;
            padding: 0 24px 48px;
            display: flex;
            flex-direction: column;
            gap: 32px;
        }
        .card {
            background: #ffffff;
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 24px 48px rgba(15, 23, 42, 0.08);
            border: 1px solid rgba(148, 163, 184, 0.16);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 24px;
        }
        .header h1 {
            margin: 0;
            font-size: 30px;
            font-weight: 700;
            color: #0f172a;
        }
        .header .subtitle {
            margin-top: 6px;
            font-size: 15px;
            color: #475569;
        }
        .nav-actions {
            display: flex;
            gap: 12px;
            align-items: center;
            flex-wrap: wrap;
        }
        .nav-actions a { color: #1d4ed8; font-weight: 600; }
        .nav-actions a:hover { color: #1e3a8a; }
        .tag {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 999px;
            background: rgba(37, 99, 235, 0.1);
            color: #1d4ed8;
            font-size: 13px;
            font-weight: 600;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 10px 18px;
            border-radius: 999px;
            font-size: 14px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.2s ease;
        }
        .btn:focus { outline: none; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.35); }
        .btn-primary {
            background: linear-gradient(90deg, #2563eb, #1d4ed8);
            color: #ffffff;
            box-shadow: 0 12px 24px rgba(29, 78, 216, 0.28);
        }
        .btn-primary:hover { background: linear-gradient(90deg, #1d4ed8, #1e40af); transform: translateY(-1px); }
        .btn-secondary {
            background: rgba(15, 23, 42, 0.08);
            color: #1f2937;
        }
        .btn-secondary:hover { background: rgba(15, 23, 42, 0.12); transform: translateY(-1px); }
        .btn-success {
            background: linear-gradient(90deg, #22c55e, #16a34a);
            color: #ffffff;
            box-shadow: 0 12px 24px rgba(34, 197, 94, 0.25);
        }
        .btn-success:hover { background: linear-gradient(90deg, #16a34a, #15803d); transform: translateY(-1px); }
        .btn-danger {
            background: linear-gradient(90deg, #ef4444, #dc2626);
            color: #ffffff;
            box-shadow: 0 12px 24px rgba(239, 68, 68, 0.25);
        }
        .btn-danger:hover { background: linear-gradient(90deg, #dc2626, #b91c1c); transform: translateY(-1px); }
        .form-card {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        .form-header {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .form-header h2 { margin: 0; font-size: 22px; color: #0f172a; }
        .helper-text { font-size: 13px; color: #64748b; }
        form { display: flex; flex-direction: column; gap: 18px; }
        textarea {
            width: 100%;
            min-height: 120px;
            padding: 16px;
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.6);
            background: rgba(248, 250, 252, 0.9);
            font-size: 15px;
            resize: vertical;
        }
        textarea:focus {
            outline: none;
            border-color: #2563eb;
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
        }
        .checkbox-row {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 14px;
            color: #1e293b;
        }
        .alert {
            padding: 14px 18px;
            border-radius: 14px;
            font-size: 14px;
            font-weight: 500;
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .alert::before { content: '⚠'; font-size: 18px; }
        .alert-error { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
        .table-card { padding: 0; }
        .table-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            padding: 26px 28px;
            border-bottom: 1px solid rgba(148, 163, 184, 0.16);
        }
        .table-header h2 { margin: 0; font-size: 22px; color: #0f172a; }
        .table-header-actions { display: flex; gap: 12px; flex-wrap: wrap; }
        .table-wrapper { overflow-x: auto; }
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 14px;
        }
        thead tr { background: rgba(248, 250, 252, 0.9); }
        th, td {
            padding: 16px 20px;
            border-bottom: 1px solid rgba(226, 232, 240, 0.9);
            text-align: left;
            color: #1f2937;
        }
        th:first-child, td:first-child { padding-left: 28px; }
        th:last-child, td:last-child { padding-right: 28px; }
        tbody tr:hover { background: rgba(59, 130, 246, 0.06); }
        .actions { display: flex; gap: 10px; flex-wrap: wrap; }
        .content-preview {
            max-width: 320px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            color: #0f172a;
        }
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 6px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge-public { background: rgba(34, 197, 94, 0.14); color: #15803d; }
        .badge-private { background: rgba(100, 116, 139, 0.15); color: #334155; }
        .empty-state {
            padding: 32px;
            text-align: center;
            font-size: 15px;
            color: #64748b;
        }
        @media (max-width: 768px) {
            .header { flex-direction: column; align-items: flex-start; }
            .nav-actions { width: 100%; }
            .table-header { flex-direction: column; align-items: flex-start; }
            th, td { white-space: nowrap; }
        }
    </style>
</head>
<body>
    <div class="page-wrapper">
        <header class="header card">
            <div>
                <h1>网络剪贴板</h1>
                <p class="subtitle">集中管理临时片段，支持公开分享或私密留存。</p>
            </div>
            <div class="nav-actions">
                <span class="tag">当前用户 {{ username }}</span>
                <a href="/">文件管理</a>
                <a href="/personal_clipboard">个人剪贴板</a>
                <a href="/logout" class="btn btn-danger">退出</a>
            </div>
        </header>

        <section class="card form-card">
            <div class="form-header">
                <h2>添加新内容</h2>
                <p class="helper-text">支持 5000 字符以内的文本，可勾选“公开”生成共享链接。</p>
            </div>
            {% if error %}
            <div class="alert alert-error">错误: {{ error }}</div>
            {% endif %}
            <form method="post">
                <div>
                    <label for="content" class="helper-text" style="font-size:14px;color:#1e293b;font-weight:600;">内容</label>
                    <textarea name="content" id="content" rows="5" placeholder="在此输入要保存到剪贴板的内容..." required></textarea>
                </div>
                <label class="checkbox-row">
                    <input type="checkbox" name="is_public" id="is_public" style="width:16px;height:16px;">
                    公开内容（其他用户可见）
                </label>
                <div>
                    <button type="submit" class="btn btn-primary">保存到剪贴板</button>
                </div>
            </form>
        </section>

        <section class="card table-card">
            <div class="table-header">
                <h2>剪贴板内容</h2>
                <div class="table-header-actions">
                    <span class="helper-text">支持直接复制链接或内容，默认按时间倒序排列。</span>
                </div>
            </div>
            {% if clipboard_items %}
            <div class="table-wrapper">
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
                            <td class="content-preview" title="{{ item.content }}">{{ item.content[:50] }}{% if item.content|length > 50 %}...{% endif %}</td>
                            <td>{{ item.owner }}</td>
                            <td>
                                {% if item.is_public %}
                                <span class="badge badge-public">公开</span>
                                {% else %}
                                <span class="badge badge-private">私有</span>
                                {% endif %}
                            </td>
                            <td>{{ item.created_at[:19].replace('T', ' ') }}</td>
                            <td class="actions">
                                {% if item.is_public %}
                                <a href="/clipboard/public/{{ item.id }}" class="btn btn-success copy" target="_blank">复制链接</a>
                                {% else %}
                                <a href="/clipboard/get/{{ item.id }}" class="btn btn-success copy" target="_blank">复制内容</a>
                                {% endif %}
                                {% if item.owner == username %}
                                <a href="/clipboard/delete/{{ item.id }}" class="btn btn-danger" onclick="return confirm('确定要删除此剪贴板内容吗？')">删除</a>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="empty-state">剪贴板中没有内容，先添加一条试试吧。</div>
            {% endif %}
        </section>
    </div>

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
        * { box-sizing: border-box; }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(120deg, #eff6ff, #f8fafc);
            color: #0f172a;
        }
        .page-wrapper {
            max-width: 1080px;
            margin: 48px auto;
            padding: 0 24px 48px;
            display: flex;
            flex-direction: column;
            gap: 32px;
        }
        a { text-decoration: none; }
        .card {
            background: #ffffff;
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 24px 48px rgba(15, 23, 42, 0.08);
            border: 1px solid rgba(148, 163, 184, 0.16);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 24px;
        }
        .header h1 {
            margin: 0;
            font-size: 30px;
            font-weight: 700;
            color: #0f172a;
        }
        .header .subtitle { margin-top: 6px; font-size: 15px; color: #475569; }
        .nav-actions { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
        .nav-actions a { color: #1d4ed8; font-weight: 600; }
        .nav-actions a:hover { color: #1e3a8a; }
        .tag {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 999px;
            background: rgba(37, 99, 235, 0.1);
            color: #1d4ed8;
            font-size: 13px;
            font-weight: 600;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 10px 18px;
            border-radius: 999px;
            font-size: 14px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.2s ease;
        }
        .btn:focus { outline: none; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.35); }
        .btn-primary {
            background: linear-gradient(90deg, #2563eb, #1d4ed8);
            color: #ffffff;
            box-shadow: 0 12px 24px rgba(29, 78, 216, 0.28);
        }
        .btn-primary:hover { background: linear-gradient(90deg, #1d4ed8, #1e40af); transform: translateY(-1px); }
        .btn-secondary {
            background: rgba(15, 23, 42, 0.08);
            color: #1f2937;
        }
        .btn-secondary:hover { background: rgba(15, 23, 42, 0.12); transform: translateY(-1px); }
        .btn-danger {
            background: linear-gradient(90deg, #ef4444, #dc2626);
            color: #ffffff;
            box-shadow: 0 12px 24px rgba(239, 68, 68, 0.25);
        }
        .btn-danger:hover { background: linear-gradient(90deg, #dc2626, #b91c1c); transform: translateY(-1px); }
        .btn-outline {
            background: transparent;
            border: 1px solid rgba(15, 23, 42, 0.12);
            color: #1f2937;
        }
        .btn-outline:hover { background: rgba(15, 23, 42, 0.05); transform: translateY(-1px); }
        .form-card { display: flex; flex-direction: column; gap: 20px; }
        .form-header { display: flex; flex-direction: column; gap: 6px; }
        .form-header h2 { margin: 0; font-size: 22px; color: #0f172a; }
        .helper-text { font-size: 13px; color: #64748b; }
        form { display: flex; flex-direction: column; gap: 18px; }
        input[type="text"], textarea {
            width: 100%;
            padding: 16px;
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.6);
            background: rgba(248, 250, 252, 0.9);
            font-size: 15px;
        }
        input[type="text"]:focus, textarea:focus {
            outline: none;
            border-color: #2563eb;
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
        }
        textarea { resize: vertical; min-height: 120px; }
        .table-card { padding: 0; }
        .table-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            padding: 26px 28px;
            border-bottom: 1px solid rgba(148, 163, 184, 0.16);
        }
        .table-header h2 { margin: 0; font-size: 22px; color: #0f172a; }
        .table-wrapper { overflow-x: auto; }
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 14px;
        }
        thead tr { background: rgba(248, 250, 252, 0.9); }
        th, td {
            padding: 16px 20px;
            text-align: left;
            border-bottom: 1px solid rgba(226, 232, 240, 0.9);
            color: #1f2937;
        }
        th:first-child, td:first-child { padding-left: 28px; }
        th:last-child, td:last-child { padding-right: 28px; }
        tbody tr:hover { background: rgba(59, 130, 246, 0.06); }
        .actions { display: flex; gap: 10px; flex-wrap: wrap; }
        .empty-state {
            padding: 32px;
            text-align: center;
            font-size: 15px;
            color: #64748b;
        }
        @media (max-width: 768px) {
            .header { flex-direction: column; align-items: flex-start; }
            .nav-actions { width: 100%; }
            .table-header { flex-direction: column; align-items: flex-start; }
            th, td { white-space: nowrap; }
        }
    </style>
</head>
<body>
    <div class="page-wrapper">
        <header class="header card">
            <div>
                <h1>个人剪贴板</h1>
                <p class="subtitle">创建多个私有笔记本，集中同步常用片段。</p>
            </div>
            <div class="nav-actions">
                <span class="tag">当前用户 {{ username }}</span>
                <a href="/clipboard">网络剪贴板</a>
                <a href="/">文件管理</a>
                <a href="/logout" class="btn btn-danger">退出</a>
            </div>
        </header>

        <section class="card form-card">
            <div class="form-header">
                <h2>创建新的个人剪贴板</h2>
                <p class="helper-text">用于保存私人敏感片段，默认仅自己可见。</p>
            </div>
            {% if error %}
            <div class="alert alert-error">错误: {{ error }}</div>
            {% endif %}
            <form method="post">
                <div>
                    <label for="name" class="helper-text" style="font-size:14px;color:#1e293b;font-weight:600;">名称</label>
                    <input type="text" name="name" id="name" placeholder="剪贴板名称" required>
                </div>
                <div>
                    <label for="content" class="helper-text" style="font-size:14px;color:#1e293b;font-weight:600;">初始内容</label>
                    <textarea name="content" id="content" rows="5" placeholder="可选，填写后会作为默认内容"></textarea>
                </div>
                <div>
                    <button type="submit" class="btn btn-primary">创建剪贴板</button>
                </div>
            </form>
        </section>

        <section class="card table-card">
            <div class="table-header">
                <h2>我的个人剪贴板</h2>
                <span class="helper-text">按更新时间排序，便于快速找到最近修改的记录。</span>
            </div>
            {% if personal_clipboards %}
            <div class="table-wrapper">
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
                                <a href="/personal_clipboard/{{ clipboard.id }}" class="btn btn-outline">查看/编辑</a>
                                <a href="/personal_clipboard/delete/{{ clipboard.id }}" class="btn btn-danger" onclick="return confirm('确定要删除 {{ clipboard.name }} 吗？')">删除</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="empty-state">没有个人剪贴板，立即创建一个专属存档吧。</div>
            {% endif %}
        </section>
    </div>
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
        * { box-sizing: border-box; }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(120deg, #eff6ff, #f8fafc);
            color: #0f172a;
        }
        a { text-decoration: none; }
        .page-wrapper {
            max-width: 960px;
            margin: 48px auto;
            padding: 0 24px 48px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }
        .card {
            background: #ffffff;
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 24px 48px rgba(15, 23, 42, 0.08);
            border: 1px solid rgba(148, 163, 184, 0.16);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 24px;
        }
        .header h1 {
            margin: 0;
            font-size: 28px;
            font-weight: 700;
            color: #0f172a;
        }
        .nav-actions { display: flex; gap: 12px; flex-wrap: wrap; }
        .nav-actions a { color: #1d4ed8; font-weight: 600; }
        .nav-actions a:hover { color: #1e3a8a; }
        .tag {
            display: inline-flex;
            align-items: center;
            padding: 6px 12px;
            border-radius: 999px;
            background: rgba(37, 99, 235, 0.1);
            color: #1d4ed8;
            font-size: 13px;
            font-weight: 600;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 10px 18px;
            border-radius: 999px;
            font-size: 14px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.2s ease;
        }
        .btn:focus { outline: none; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.35); }
        .btn-secondary {
            background: rgba(15, 23, 42, 0.08);
            color: #1f2937;
        }
        .btn-secondary:hover { background: rgba(15, 23, 42, 0.12); transform: translateY(-1px); }
        .btn-primary {
            background: linear-gradient(90deg, #2563eb, #1d4ed8);
            color: #ffffff;
            box-shadow: 0 12px 24px rgba(29, 78, 216, 0.28);
        }
        .btn-primary:hover { background: linear-gradient(90deg, #1d4ed8, #1e40af); transform: translateY(-1px); }
        .btn-danger {
            background: linear-gradient(90deg, #ef4444, #dc2626);
            color: #ffffff;
            box-shadow: 0 12px 24px rgba(239, 68, 68, 0.25);
        }
        .btn-danger:hover { background: linear-gradient(90deg, #dc2626, #b91c1c); transform: translateY(-1px); }
        .info-card {
            background: linear-gradient(135deg, #eef2ff, #ffffff);
            display: flex;
            flex-direction: column;
            gap: 6px;
            font-size: 15px;
            color: #1e293b;
        }
        .info-card strong { color: #0f172a; }
        .helper-text { font-size: 13px; color: #64748b; }
        form { display: flex; flex-direction: column; gap: 18px; }
        textarea {
            width: 100%;
            padding: 16px;
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.6);
            background: rgba(248, 250, 252, 0.9);
            font-size: 15px;
            min-height: 320px;
            resize: vertical;
        }
        textarea:focus {
            outline: none;
            border-color: #2563eb;
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
        }
        .alert {
            padding: 14px 18px;
            border-radius: 14px;
            font-size: 14px;
            font-weight: 500;
            display: flex;
            gap: 10px;
            align-items: center;
            background: #fee2e2;
            color: #991b1b;
            border: 1px solid #fca5a5;
        }
        .alert::before { content: '⚠'; font-size: 18px; }
        @media (max-width: 768px) {
            .header { flex-direction: column; align-items: flex-start; }
            .nav-actions { width: 100%; }
        }
    </style>
</head>
<body>
    <div class="page-wrapper">
        <header class="header card">
            <div>
                <h1>个人剪贴板 - {{ clipboard.name }}</h1>
                <p style="margin:6px 0 0;color:#475569;font-size:15px;">实时保存每次改动，适合维护个人配置片段。</p>
            </div>
            <div class="nav-actions">
                <span class="tag">当前用户 {{ username }}</span>
                <a href="/personal_clipboard">返回列表</a>
                <a href="/personal_clipboard/{{ clipboard.id }}">刷新</a>
                <a href="/logout" class="btn btn-danger">退出</a>
            </div>
        </header>

        <section class="card info-card">
            <div><strong>创建时间:</strong> {{ clipboard.created_at[:19].replace('T', ' ') }}</div>
            <div><strong>最后更新:</strong> {{ clipboard.updated_at[:19].replace('T', ' ') }}</div>
        </section>

        <section class="card">
            <h2 style="margin-top:0;font-size:22px;color:#0f172a;">编辑内容</h2>
            <p class="helper-text" style="margin-top:4px;margin-bottom:20px;">支持 Markdown 与代码片段，保存后立即生效。</p>
            {% if error %}
            <div class="alert">错误: {{ error }}</div>
            {% endif %}
            <form method="post">
                <textarea name="content" rows="15">{{ clipboard.content }}</textarea>
                <div style="display:flex;gap:12px;flex-wrap:wrap;">
                    <button type="submit" class="btn btn-primary">保存内容</button>
                    <a href="/personal_clipboard" class="btn btn-secondary">返回上一页</a>
                </div>
            </form>
        </section>
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
        * { box-sizing: border-box; }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(120deg, #eff6ff, #f8fafc);
            color: #0f172a;
        }
        a { text-decoration: none; }
        .page-wrapper {
            max-width: 1080px;
            margin: 48px auto;
            padding: 0 24px 48px;
            display: flex;
            flex-direction: column;
            gap: 32px;
        }
        .card {
            background: #ffffff;
            border-radius: 18px;
            padding: 28px;
            box-shadow: 0 24px 48px rgba(15, 23, 42, 0.08);
            border: 1px solid rgba(148, 163, 184, 0.16);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 24px;
        }
        .header h1 {
            margin: 0;
            font-size: 30px;
            font-weight: 700;
            color: #0f172a;
        }
        .header .subtitle { margin-top: 6px; font-size: 15px; color: #475569; }
        .nav-actions { display: flex; gap: 12px; flex-wrap: wrap; }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 10px 18px;
            border-radius: 999px;
            font-size: 14px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.2s ease;
        }
        .btn:focus { outline: none; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.35); }
        .btn-primary {
            background: linear-gradient(90deg, #2563eb, #1d4ed8);
            color: #ffffff;
            box-shadow: 0 12px 24px rgba(29, 78, 216, 0.28);
        }
        .btn-primary:hover { background: linear-gradient(90deg, #1d4ed8, #1e40af); transform: translateY(-1px); }
        .btn-secondary {
            background: rgba(15, 23, 42, 0.08);
            color: #1f2937;
        }
        .btn-secondary:hover { background: rgba(15, 23, 42, 0.12); transform: translateY(-1px); }
        .btn-outline {
            background: transparent;
            border: 1px solid rgba(15, 23, 42, 0.12);
            color: #1f2937;
        }
        .btn-outline:hover { background: rgba(15, 23, 42, 0.05); transform: translateY(-1px); }
        .meta-card {
            display: flex;
            flex-direction: column;
            gap: 16px;
            background: linear-gradient(135deg, #eef2ff, #ffffff);
        }
        .meta-grid { display: flex; flex-wrap: wrap; gap: 20px; }
        .meta-item { flex: 1 1 220px; display: flex; flex-direction: column; gap: 6px; }
        .meta-label { font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: #64748b; }
        .meta-value { font-size: 16px; font-weight: 600; color: #0f172a; word-break: break-all; }
        .preview-card { display: flex; flex-direction: column; gap: 20px; }
        .helper-text { font-size: 13px; color: #64748b; }
        .alert { padding: 16px 20px; border-radius: 14px; font-size: 14px; font-weight: 500; }
        .alert-error { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
        .preview-content {
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.35);
            background: rgba(255, 255, 255, 0.95);
            max-height: 70vh;
            overflow: auto;
        }
        pre {
            white-space: pre-wrap;
            word-wrap: break-word;
            margin: 0;
            padding: 18px 20px;
            font-family: 'JetBrains Mono', 'Courier New', monospace;
            font-size: 14px;
            color: #0f172a;
            background: transparent;
        }
        code { font-family: 'JetBrains Mono', 'Courier New', monospace; }
        pre code.hljs {
            padding: 0 !important;
            background: transparent !important;
            display: block;
            overflow-x: auto;
        }
        img { max-width: 100%; height: auto; display: block; border-radius: 14px; }
        .pdf-container { width: 100%; height: 70vh; border: none; border-radius: 12px; }
        .no-preview {
            border-radius: 16px;
            padding: 32px;
            text-align: center;
            color: #475569;
            background: rgba(59, 130, 246, 0.08);
        }
        .no-preview p { margin: 12px 0; }
        .preview-error { border-radius: 14px; padding: 18px 20px; background: #fee2e2; border: 1px solid #fca5a5; color: #991b1b; }
        .toggle-buttons { display: flex; gap: 12px; flex-wrap: wrap; }
        .toggle-btn {
            background: rgba(15, 23, 42, 0.08);
            color: #1f2937;
            border-radius: 999px;
            padding: 8px 18px;
            border: none;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.2s ease;
        }
        .toggle-btn:hover { background: rgba(37, 99, 235, 0.2); color: #1d4ed8; transform: translateY(-1px); }
        .toggle-btn.active { background: linear-gradient(90deg, #2563eb, #1d4ed8); color: #ffffff; box-shadow: 0 10px 20px rgba(29, 78, 216, 0.28); }
        .markdown-content { font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.65; padding: 20px; }
        .markdown-content h1 { color: #0f172a; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }
        .markdown-content h2 { color: #1e293b; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }
        .markdown-content h3 { color: #334155; }
        .markdown-content code { background-color: rgba(15, 23, 42, 0.08); padding: 2px 6px; border-radius: 6px; }
        .markdown-content pre { background-color: rgba(15, 23, 42, 0.08); padding: 16px; border-radius: 12px; overflow: auto; }
        .markdown-content blockquote { border-left: 4px solid #93c5fd; padding: 0 18px; color: #475569; }
        .markdown-content ul, .markdown-content ol { padding-left: 26px; }
        .markdown-content a { color: #1d4ed8; }
        .markdown-content table { border-collapse: collapse; width: 100%; margin: 16px 0; }
        .markdown-content th, .markdown-content td { border: 1px solid #e2e8f0; padding: 8px 12px; }
        .markdown-content th { background-color: rgba(59, 130, 246, 0.1); }
        .highlight .hll { background-color: #ffffcc }
        .highlight  { background: #f8f8f8; }
        .highlight .c { color: #408080; font-style: italic }
        .highlight .err { border: 1px solid #FF0000 }
        .highlight .k { color: #008000; font-weight: bold }
        .highlight .o { color: #666666 }
        .highlight .cm { color: #408080; font-style: italic }
        .highlight .cp { color: #BC7A00 }
        .highlight .c1 { color: #408080; font-style: italic }
        .highlight .cs { color: #408080; font-style: italic }
        .highlight .gd { color: #A00000 }
        .highlight .ge { font-style: italic }
        .highlight .gr { color: #FF0000 }
        .highlight .gh { color: #000080; font-weight: bold }
        .highlight .gi { color: #00A000 }
        .highlight .go { color: #888888 }
        .highlight .gp { color: #000080; font-weight: bold }
        .highlight .gs { font-weight: bold }
        .highlight .gu { color: #800080; font-weight: bold }
        .highlight .gt { color: #0044DD }
        .highlight .kc { color: #008000; font-weight: bold }
        .highlight .kd { color: #008000; font-weight: bold }
        .highlight .kn { color: #008000; font-weight: bold }
        .highlight .kp { color: #008000 }
        .highlight .kr { color: #008000; font-weight: bold }
        .highlight .kt { color: #B00040 }
        .highlight .m { color: #666666 }
        .highlight .s { color: #BA2121 }
        .highlight .na { color: #7D9029 }
        .highlight .nb { color: #008000 }
        .highlight .nc { color: #0000FF; font-weight: bold }
        .highlight .no { color: #880000 }
        .highlight .nd { color: #AA22FF }
        .highlight .ni { color: #999999; font-weight: bold }
        .highlight .ne { color: #D2413A; font-weight: bold }
        .highlight .nf { color: #0000FF }
        .highlight .nl { color: #A0A000 }
        .highlight .nn { color: #0000FF; font-weight: bold }
        .highlight .nt { color: #008000; font-weight: bold }
        .highlight .nv { color: #19177C }
        .highlight .ow { color: #AA22FF; font-weight: bold }
        .highlight .w { color: #bbbbbb }
        .highlight .mf { color: #666666 }
        .highlight .mh { color: #666666 }
        .highlight .mi { color: #666666 }
        .highlight .mo { color: #666666 }
        .highlight .sb { color: #BA2121 }
        .highlight .sc { color: #BA2121 }
        .highlight .sd { color: #BA2121; font-style: italic }
        .highlight .s2 { color: #BA2121 }
        .highlight .se { color: #BB6622; font-weight: bold }
        .highlight .sh { color: #BA2121 }
        .highlight .si { color: #BB6688; font-weight: bold }
        .highlight .sx { color: #008000 }
        .highlight .sr { color: #BB6688 }
        .highlight .s1 { color: #BA2121 }
        .highlight .ss { color: #19177C }
        .highlight .bp { color: #008000 }
        .highlight .vc { color: #19177C }
        .highlight .vg { color: #19177C }
        .highlight .vi { color: #19177C }
        .highlight .il { color: #666666 }
        @media (max-width: 768px) {
            .header { flex-direction: column; align-items: flex-start; }
            .nav-actions { width: 100%; }
            .meta-grid { flex-direction: column; }
            .preview-content { max-height: none; }
            .pdf-container { height: 60vh; }
        }
    </style>
</head>
<body>
    <div class="page-wrapper">
        <header class="header card">
            <div>
                <h1>文件预览</h1>
                <p class="subtitle">支持常见文本、图片与 PDF 的快速查看。</p>
            </div>
            <div class="nav-actions">
                <a href="/" class="btn btn-secondary">返回文件管理</a>
                <a href="/download/{{ filename }}" class="btn btn-primary">下载文件</a>
            </div>
        </header>

        <section class="card meta-card">
            <div class="meta-grid">
                <div class="meta-item">
                    <span class="meta-label">文件名</span>
                    <span class="meta-value">{{ filename }}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">文件大小</span>
                    <span class="meta-value">{{ file_size }}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">修改时间</span>
                    <span class="meta-value">{{ modified_time }}</span>
                </div>
            </div>
        </section>

        <section class="card preview-card">
            {% if error %}
            <div class="preview-error"><strong>预览错误:</strong> {{ error }}</div>
            {% elif preview_type == 'text' %}
            <div class="toggle-buttons">
                <button id="rawBtn" class="toggle-btn active" onclick="toggleView('raw')">纯文本</button>
                <button id="renderedBtn" class="toggle-btn" onclick="toggleView('rendered')">渲染显示</button>
            </div>
            <div class="preview-content">
                <pre id="rawContent" style="display: block;">{{ content }}</pre>
                <div id="renderedContent" style="display: none; padding: 20px;"></div>
            </div>
            {% elif preview_type == 'image' %}
            <div class="preview-content" style="padding: 20px;">
                <img src="/download/{{ filename }}" alt="{{ filename }}">
            </div>
            {% elif preview_type == 'pdf' %}
            <div class="preview-content" style="padding: 20px;">
                <embed src="/download/{{ filename }}" type="application/pdf" class="pdf-container">
                <p class="helper-text" style="margin-top:16px; color:#475569;">如果未能显示，请直接<a href="/download/{{ filename }}" style="color:#1d4ed8;">下载文件</a>。</p>
            </div>
            {% elif preview_type == 'archive' %}
            <div class="no-preview">
                <p>这是一个压缩包文件（{{ filename.split('.')[-1].lower()|upper }} 格式）。</p>
                <p><a href="/download/{{ filename }}" class="btn btn-primary">下载后解压查看内容</a></p>
            </div>
            {% else %}
            <div class="no-preview">
                <p>该文件类型暂不支持在线预览。</p>
                <p><a href="/download/{{ filename }}" class="btn btn-primary">点击下载到本地查看</a></p>
            </div>
            {% endif %}
        </section>
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
            const content = {{ content|tojson if content else '""' }};
            const renderedContent = document.getElementById('renderedContent');
            
            if (!content) {
                renderedContent.innerHTML = '<p>该文件类型不支持渲染显示。</p>';
                return;
            }
            
            if (extension === 'md') {
                const md = markdownit();
                renderedContent.innerHTML = '<div class=\"markdown-content\">' + md.render(content) + '</div>';
            } else if (['py', 'js', 'java', 'c', 'cpp', 'html', 'css', 'php', 'sql', 'xml', 'json', 'yaml', 'yml', 'ini', 'cfg', 'conf', 'sh', 'pl', 'rb', 'go'].includes(extension)) {
                const escapedContent = content
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#039;');
                renderedContent.innerHTML = '<pre><code class=\"language-' + extension + '\">' + escapedContent + '</code></pre>';
                if (typeof hljs !== 'undefined' && typeof hljs.highlightAll === 'function') {
                    hljs.highlightAll();
                }
            } else {
                const escapedContent = content
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#039;');
                renderedContent.innerHTML = '<pre>' + escapedContent + '</pre>';
            }
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            const rawBtn = document.getElementById('rawBtn');
            if (rawBtn) {
                rawBtn.classList.add('active');
            }
        });
    </script>
</body>
</html>
'''

# 验证码生成路由
@app.route('/captcha')
def captcha():
    """生成新的验证码"""
    captcha_text = generate_captcha_text()
    session['captcha'] = captcha_text
    captcha_image = generate_captcha_image(captcha_text)
    return {'captcha_image': captcha_image}

# 登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # 检查表单字段是否存在
        if 'username' not in request.form or 'password' not in request.form or 'captcha' not in request.form:
            # 生成新的验证码图片，使用session中的验证码文本
            current_captcha = session.get('captcha', generate_captcha_text())
            session['captcha'] = current_captcha  # 确保session中有验证码
            captcha_image = generate_captcha_image(current_captcha)
            return render_template_string(login_template, captcha_image=captcha_image, error='请填写完整的登录信息')

        username = request.form['username']
        password = request.form['password']
        captcha = request.form['captcha']

        logger.debug("Login attempt - Username: %s", username)
        logger.debug("Available users: %s", list(users.keys()))
        logger.debug("Session captcha: %s", session.get('captcha'))
        logger.debug("User input captcha: %s", captcha)

        # 验证验证码
        if not validate_captcha(captcha, session.get('captcha')):
            # 验证失败时，生成新的验证码
            captcha_text = generate_captcha_text()
            session['captcha'] = captcha_text
            captcha_image = generate_captcha_image(captcha_text)
            logger.debug("Captcha validation failed for user: %s", username)
            logger.debug("Generated new captcha: %s", captcha_text)
            return render_template_string(login_template, captcha_image=captcha_image, error='验证码错误，请重新输入')

        # 验证用户凭据
        if username in users and check_password_hash(users[username], password):
            logger.debug("Login successful for user: %s", username)
            session['username'] = username
            # 登录成功后清除验证码
            session.pop('captcha', None)
            return redirect(url_for('upload_file'))
        else:
            # 密码错误时，也生成新的验证码
            captcha_text = generate_captcha_text()
            session['captcha'] = captcha_text
            captcha_image = generate_captcha_image(captcha_text)
            logger.debug("Login failed for user: %s", username)
            return render_template_string(login_template, captcha_image=captcha_image, error='无效的用户名或密码')

    # GET请求 - 生成初始验证码
    captcha_text = generate_captcha_text()
    session['captcha'] = captcha_text
    captcha_image = generate_captcha_image(captcha_text)
    return render_template_string(login_template, captcha_image=captcha_image)

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
            return render_template_string(
                upload_template,
                username=session['username'],
                files=files,
                **storage_info,
                storage_full=True,
                storage_warning=storage_warning
            )

        # 收集所有上传的文件实例
        uploaded_files = [f for f in request.files.getlist('file') if f and f.filename]
        if not uploaded_files:
            files = get_file_list()
            return render_template_string(
                upload_template,
                username=session['username'],
                files=files,
                **storage_info,
                storage_full=storage_full,
                storage_warning=storage_warning,
                error='没有选择文件'
            )

        ajax_request = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        current_usage = storage_info['used_bytes']
        max_storage = storage_info['max_bytes']
        successful_uploads = []
        errors = []

        for file in uploaded_files:
            filename = file.filename

            if not is_safe_filename(filename):
                errors.append(
                    f'{filename}: 文件名包含非法字符或路径遍历字符（如../），请使用合法的文件名。文件名不应包含以下字符：/\\<>:"|?*以及控制字符。'
                )
                continue

            if not allowed_file(filename):
                file_type_desc = get_file_type_description(filename)
                errors.append(
                    f'{filename}: 出于安全考虑，系统不允许上传{file_type_desc}。请上传以下类型的文件：文本文件、图片、文档、压缩包、音频或视频文件。'
                )
                continue

            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)

            if current_usage + file_size > max_storage:
                errors.append(
                    f'{filename}: 上传此文件将超出存储限制，请删除一些文件后再试。'
                )
                continue

            file.save(filepath)
            current_usage += file_size
            successful_uploads.append({
                'name': filename,
                'size': format_file_size(file_size)
            })

        # AJAX 请求返回 JSON 响应
        if ajax_request:
            updated_storage = format_storage_info()
            response_data = {
                'success': bool(successful_uploads),
                'uploaded': successful_uploads,
                'errors': errors,
                'storage': {
                    'used_storage': updated_storage['used_storage'],
                    'usage_percentage': updated_storage['usage_percentage']
                }
            }
            return app.response_class(
                response=json.dumps(response_data, ensure_ascii=False),
                mimetype='application/json'
            )

        # 非 AJAX 请求：若有成功上传的文件则重定向，否则返回错误信息
        if successful_uploads:
            return redirect(url_for('upload_file'))

        files = get_file_list()
        return render_template_string(
            upload_template,
            username=session['username'],
            files=files,
            **storage_info,
            storage_full=storage_full,
            storage_warning=storage_warning,
            error='；'.join(errors) if errors else '上传失败，请重试。'
        )
    
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
        elif ext in ARCHIVE_EXTENSIONS:
            return 'archive'
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
    elif preview_type == 'archive':
        return render_template_string(preview_template, 
                                    filename=filename,
                                    file_size=file_size,
                                    modified_time=modified_time,
                                    preview_type='archive')
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
