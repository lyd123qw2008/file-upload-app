# 部署说明

## 生产环境部署指南

### 环境要求
- Docker 18.06.0+
- Docker Compose 1.22.0+

### 部署步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd file-upload-app
```

2. **配置环境变量**
```bash
# 复制示例配置文件
cp .env.example .env

# 编辑.env文件，设置生产环境配置
vim .env
```

3. **构建和启动服务**
```bash
# 使用Makefile
make init

# 或手动执行
cd src && docker-compose up -d
```

4. **访问应用**
打开浏览器访问 `http://your-server-ip:5000`

### 环境变量配置

在 `.env` 文件中配置以下变量：

```bash
# 管理员凭据
ADMIN_USERNAME=your_admin_username
ADMIN_PASSWORD=your_secure_password

# 存储限制 (字节)
MAX_STORAGE_BYTES=1073741824

# Flask密钥 (必须更改)
SECRET_KEY=your_very_secure_secret_key_here

# 调试模式 (生产环境应为False)
FLASK_DEBUG=False
```

> ⚠️ **安全提醒**: 请务必将 `.env` 文件添加到 `.gitignore` 中，不要提交到版本控制系统。

### 安全建议

1. **更改默认凭据**
   - 修改ADMIN_USERNAME和ADMIN_PASSWORD
   - 使用强密码

2. **生成安全的SECRET_KEY**
   ```python
   import secrets
   print(secrets.token_hex(32))
   ```

3. **配置HTTPS**
   - 在生产环境中使用HTTPS
   - 配置反向代理（如Nginx）

4. **定期备份**
   - 定期备份uploads目录
   - 备份数据库（如果使用）

### 监控和维护

1. **查看日志**
```bash
make logs
# 或
cd src && docker-compose logs -f
```

2. **重启服务**
```bash
make restart
# 或
cd src && docker-compose restart
```

3. **更新应用**
```bash
# 拉取最新代码
git pull

# 重新构建镜像
make build

# 重启服务
make restart
```

### 故障排除

1. **服务无法启动**
   - 检查端口是否被占用
   - 检查Docker和Docker Compose是否正常运行
   - 查看日志获取详细错误信息

2. **上传失败**
   - 检查存储空间是否已满
   - 检查文件类型是否被允许
   - 查看应用日志

3. **认证问题**
   - 确认凭据正确
   - 检查SECRET_KEY是否正确配置