from flask import Flask, request, send_from_directory, redirect, url_for, render_template, render_template_string, session, abort, make_response
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
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def load_dotenv(env_file: str = '.env') -> None:
    """Load key=value pairs from .env without overriding existing env vars."""
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / env_file
    if not env_path.exists():
        return

    with env_path.open('r', encoding='utf-8') as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            if not key:
                continue
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_dotenv()

STATIC_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static')

# 配置日志
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)
logger.info('Serving static files from: %s', STATIC_FOLDER)

app = Flask(__name__, static_folder=STATIC_FOLDER, static_url_path='/static')
# 从环境变量读取密钥，如果没有设置则使用默认值
secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')  # 在生产环境中应该使用更安全的密钥
app.secret_key = secret_key
logger.debug("Secret key loaded: %s", secret_key[:10] + "..." if len(secret_key) > 10 else secret_key)  # 只显示前10个字符以保护安全

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads')
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
            return render_template(
                'upload.html',
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
            return render_template(
                'upload.html',
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
        return render_template(
            'upload.html',
            username=session['username'],
            files=files,
            **storage_info,
            storage_full=storage_full,
            storage_warning=storage_warning,
            error='；'.join(errors) if errors else '上传失败，请重试。'
        )
    
    # GET请求 - 显示文件列表和上传表单
    files = get_file_list()
    return render_template('upload.html', 
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
        return render_template('preview.html', 
                                    filename=filename,
                                    error="文件名不安全，无法预览")
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    # 检查文件是否存在
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        return render_template('preview.html', 
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
            return render_template('preview.html', 
                                        filename=filename,
                                        file_size=file_size,
                                        modified_time=modified_time,
                                        error=error)
        return render_template('preview.html', 
                                    filename=filename,
                                    file_size=file_size,
                                    modified_time=modified_time,
                                    preview_type='text',
                                    content=content)
    elif preview_type == 'image':
        return render_template('preview.html', 
                                    filename=filename,
                                    file_size=file_size,
                                    modified_time=modified_time,
                                    preview_type='image',
                                    content='')
    elif preview_type == 'pdf':
        return render_template('preview.html', 
                                    filename=filename,
                                    file_size=file_size,
                                    modified_time=modified_time,
                                    preview_type='pdf')
    elif preview_type == 'archive':
        return render_template('preview.html', 
                                    filename=filename,
                                    file_size=file_size,
                                    modified_time=modified_time,
                                    preview_type='archive')
    else:
        return render_template('preview.html', 
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
    
    return render_template('clipboard.html', 
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
    
    return render_template('personal_clipboard.html', 
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
    
    return render_template('personal_clipboard_detail.html', 
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
    host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_RUN_PORT', '5000'))
    app.run(host=host, port=port, debug=debug_mode)
