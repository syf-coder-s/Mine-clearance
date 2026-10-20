"""Web 层。

store.py  会话状态机（纯标准库）：open / submit / settle，以及 RAG 代理。
main.py   FastAPI 薄壳，把 JSON 翻译成 store 的调用，再翻译回来。

这一层不实现任何业务判断。判级、引用核验、预算守卫都在 core 里，
Web 层只做两件事：**别泄漏答案**、**别把异常变成 500**。
"""
