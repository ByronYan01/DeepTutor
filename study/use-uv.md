# 切换版本（优先级：本地项目 > 全局）
# 全局（系统默认）
pyenv global 3.11.8
# 本地项目（进入项目目录执行，会生成 .python-version 文件）
pyenv local 3.11.8

# 验证当前 Python 版本
python --version

# 初始化项目（生成 pyproject.toml，可选 --pytest/--fastapi 等模板）
uv init my-python-project  # 会创建项目文件夹，或直接 uv init 初始化当前目录

# 创建虚拟环境（自动关联 pyenv 的 Python 版本）
uv venv

# 激活虚拟环境
# Mac/Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1


# 安装包（比如 requests，会自动锁定版本到 uv.lock）
uv add requests  # 等价于 pip install requests，但更快
uv add fastapi==0.104.1  # 指定版本
uv add "pytest>=7.0,<8.0"  # 版本范围

# 安装开发依赖（仅开发环境用，比如 pytest、black）
uv add --dev pytest black

# 从 pyproject.toml 安装所有依赖（比如克隆项目后）
uv sync  # 等价于 pip install -r requirements.txt，但更严格（按 uv.lock 安装）

# 升级包
uv upgrade requests

# 卸载包
uv remove requests

# 导出依赖到 requirements.txt（兼容旧项目）
uv pip freeze > requirements.txtc


赖管理还停留在传统的 requirements.txt 方式，没有完全迁移到 pyproject.toml 的现代标准。
所以以后如果需要重新安装依赖，直接用
uv pip install -r requirements.txt
# 安装包
uv pip install <package_name>

# 然后手动把它加到 requirements.txt 里