# Repository Guidelines

## 项目结构与模块组织
Flask 后端集中在 `src/app.py`，其中封装认证、上传校验、剪贴板管理以及日志配置等主干逻辑；拓展蓝图或 API 时在该模块旁新增文件并更新导入表。`static/` 存放 favicon 与前端静态资源，`uploads/` 作为容器挂载目录保存运行期文件，不应提交至版本库。`tests/` 汇集 Shell 自动化脚本与 HTML 快照，可复用其中的请求模式扩展新场景。根目录保留 `Makefile`、`init.sh`、`quick_restart.sh` 等运维脚本；长篇说明与变更记录位于 `docs/` 与 `CHANGELOG.md`。
- Key directories: `src/` (source code), `tests/` (automation), `static/` (assets), `uploads/` (runtime artifacts)
- Docs hub: `docs/index.md`, `README.md`, `CHANGELOG.md` for release notes

## 构建、测试与开发命令
在 `src/` 执行 `pip install -r requirements.txt` 安装本地依赖，必要时通过 `python -m flask run --debug` 快速启动开发服务。容器化工作流使用 `docker-compose up -d` 启动、`docker-compose down` 清理，`quick_restart.sh` 可在调试时热重启。`make help` 概览常用动作，`make start` / `make stop` 管理服务生命周期，`make build` 重建镜像，`make logs` 跟踪运行日志，并通过 `make clean` 移除悬挂卷。端到端测试可运行 `make test` 或直接调用 `./tests/test_upload_process.sh`。
- `make start`: boot container stack in detached mode
- `make logs`: stream service output for debugging upload issues
- `docker-compose down -v`: remove stopped containers and volumes when resetting state

## 编码风格与命名约定
Python 代码遵循 PEP 8，统一四空格缩进、snake_case 函数与变量命名，配置常量保持全大写。视图函数应包含简洁 docstring，响应文案需明确说明安全后果。`logging` 已预置级别读取逻辑，新增模块时沿用该模式。Shell 脚本坚持 POSIX 兼容写法，变量大写，检测失败后使用 `exit 1`；脚本顶部加入用途注释。处理用户界面文案时使用 UTF-8，内部标识与路径保持 ASCII 以兼容跨平台部署。
- Preferred imports: standard library → third-party → local modules
- Formatting: run `python -m compileall src` before release if unsure about syntax errors
- Shell style: `set -euo pipefail` when scripts need stricter error handling

## 测试指南
现有脚本主要基于 `curl` 对上传、验证码与错误分支进行回归测试；运行前确保服务监听 `localhost:5000`，并在结束时清理解密、上传与 `/tmp` 临时文件。新增脚本延续 `test_*.sh` 命名并记录关键响应输出，若涉及模板或前端改动，请在 `tests/` 追加对应 HTML 快照。对剪贴板或安全限制的调整需补充步骤验证边界值和异常路径，并在 PR 中说明覆盖范围。
- Baseline command: `./tests/test_upload_process.sh` (happy path + malicious upload rejection)
- Snapshot updates: commit paired `.html` fixtures to keep UI messaging traceable
- Coverage focus: login flow, captcha validation, file-type filtering, clipboard CRUD

## 提交与 Pull Request 指南
历史提交信息采用中文祈使句，动词开头、突出用户价值，例如“优化上传校验提示”。继续保持一次提交只解决一个问题，必要时在正文中列出备注或 BREAKING 标记。提交 PR 时附上三部分内容：变更摘要、手工验证步骤（含命令或截图）、关联 Issue 或工单编号；界面调整需提供前后对比图。若改动涉及配置、权限或安全策略，请在说明中提示部署者所需动作。
- Commit style: `增加`, `修复`, `优化` + concise object, no punctuation
- PR checklist: description, tests, screenshots (if UI), deployment notes
- Review tips: call out new env vars, migrations, or dependency upgrades explicitly

## 安全与配置提示
首次部署请复制 `.env.example` 为 `.env`，并旋转 `SECRET_KEY`、`ADMIN_*` 凭据。利用 `MAX_STORAGE_BYTES` 限制仓库容量，新增环境变量后同步记录至 `docs/` 与示例文件。生产环境应关闭 Flask Debug、限制 `docker-compose` 端口暴露，并定期清理 `uploads/` 中的过期资料。`uploads/`、`cookies.txt` 等敏感目录已被忽略，切勿将真实用户数据提交到仓库。
- Environment hygiene: rotate secrets regularly, store them via Docker secrets or vaults in production
- Access control: restrict admin credentials to strong passwords and enable HTTPS termination upstream
- Data retention: schedule cron jobs to purge stale uploads and audit clipboard artifacts
