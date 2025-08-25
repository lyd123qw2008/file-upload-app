#!/bin/bash

# 项目初始化脚本

echo "=== 文件上传服务项目初始化 ==="

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装，请先安装Docker"
    exit 1
fi

# 检查Docker Compose是否安装
if ! command -v docker-compose &> /dev/null; then
    echo "错误: Docker Compose未安装，请先安装Docker Compose"
    exit 1
fi

# 设置执行权限
echo "设置脚本执行权限..."
chmod +x quick_restart.sh
chmod +x tests/*.sh

# 构建Docker镜像
echo "构建Docker镜像..."
docker-compose build

if [ $? -eq 0 ]; then
    echo "✓ Docker镜像构建成功"
else
    echo "✗ Docker镜像构建失败"
    exit 1
fi

# 启动服务
echo "启动服务..."
docker-compose up -d

if [ $? -eq 0 ]; then
    echo "✓ 服务启动成功"
    echo "请在浏览器中访问 http://localhost:5000"
    echo "请使用您在.env文件中配置的凭据登录"
else
    echo "✗ 服务启动失败"
    exit 1
fi

echo "=== 初始化完成 ==="