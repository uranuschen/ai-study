import sys
from pathlib import Path


# 兼容 IDE 直接运行此文件时的包查找路径。
SRC_DIR = Path(__file__).resolve().parents[1]
# agent_learning 的父目录是 src，需要把它加入导入路径。
sys.path.insert(0, str(SRC_DIR))

from agent_learning.cli import main


# 旧入口只提示运行根目录 main_api.py。
if __name__ == "__main__":
    # 不在旧入口启动另一份 API 服务。
    main()
