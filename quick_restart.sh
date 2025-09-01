#!/bin/bash

# 快速重启脚本
# 用于在开发过程中快速重启服务，而不需要重新构建镜像

echo "停止服务..."
docker-compose stop

echo "启动服务..."
docker-compose start

echo "服务已重启完成"