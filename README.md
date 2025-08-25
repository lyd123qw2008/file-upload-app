# 文件上传服务

这是一个基于 Flask 的文件上传和下载服务，具有用户认证功能。

## 项目结构

```
.
├── src/              # 源代码目录
│   ├── app.py        # Flask应用主文件
│   └── requirements.txt    # Python依赖
├── tests/            # 测试脚本目录
├── docs/             # 文档目录
├── uploads/          # 文件上传存储目录
├── Dockerfile        # Docker镜像定义
├── docker-compose.yml  # Docker编排文件
├── quick_restart.sh    # 快速重启脚本
├── README.md         # 项目说明文档
├── CLAUDE.md         # Claude相关的说明文档
├── CHANGELOG.md      # 变更日志
├── .env.example      # 环境配置示例文件
├── .env              # 环境配置文件（需手动创建）
├── .gitignore        # Git忽略文件
├── Makefile          # 构建脚本
└── init.sh           # 项目初始化脚本
```

## 使用说明

### 目录结构说明
- `src/`: 包含所有源代码和Docker配置文件
- `uploads/`: 文件上传存储目录（与Docker容器中的/uploads目录挂载）
- `tests/`: 包含测试脚本
- `docs/`: 包含文档文件

### 启动服务

```bash
# 在项目根目录启动服务
docker-compose up -d

# 或使用项目根目录的脚本
./init.sh

# 使用快速重启脚本
./quick_restart.sh
```

### 配置环境变量

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑.env文件设置您的配置
vim .env
```

### Docker挂载说明

docker-compose.yml中配置了以下挂载：
- `./uploads:/uploads`: 将项目根目录的uploads目录挂载到容器的/uploads目录
- `./app:/app`: 将源代码挂载到容器中，便于开发时实时更新

### 开发和部署

1. **开发环境**: 代码挂载到容器中，修改后快速重启即可生效
2. **生产环境**: 构建Docker镜像，不挂载本地代码
3. **数据持久化**: uploads目录挂载确保文件持久化存储

## 更多信息

查看 [完整文档](README.md) 获取详细的使用说明。