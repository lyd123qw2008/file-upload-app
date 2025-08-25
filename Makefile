# Makefile for File Upload Service

.PHONY: help build start stop restart logs test clean

# 显示帮助信息
help:
	@echo "File Upload Service - Makefile Commands"
	@echo ""
	@echo "Usage:"
	@echo "  make build     - 构建Docker镜像"
	@echo "  make start     - 启动服务"
	@echo "  make stop      - 停止服务"
	@echo "  make restart   - 重启服务"
	@echo "  make logs      - 查看服务日志"
	@echo "  make test      - 运行测试"
	@echo "  make clean     - 清理构建文件"
	@echo "  make init      - 初始化项目"

# 初始化项目
init:
	./init.sh

# 构建Docker镜像
build:
	docker-compose build

# 启动服务
start:
	docker-compose up -d

# 停止服务
stop:
	docker-compose down

# 重启服务
restart:
	docker-compose down && docker-compose up -d

# 查看服务日志
logs:
	docker-compose logs -f

# 运行测试
test:
	./tests/test_upload_process.sh

# 清理构建文件
clean:
	docker-compose down -v --remove-orphans
	docker rmi file-upload-app 2>/dev/null || true

# 快速重启
quick-restart:
	./quick_restart.sh