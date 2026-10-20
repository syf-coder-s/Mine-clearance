"""单测包。

只依赖标准库。跑法（仓库根目录）：
    python -m unittest discover -s tests -t . -v

-t . 是必须的：顶层目录设成仓库根，测试才能以 tests.xxx 的形式导入，
src/ 也才会被加进搜索路径。每个测试文件自己也会补一次路径，方便单独跑单个文件。
"""
