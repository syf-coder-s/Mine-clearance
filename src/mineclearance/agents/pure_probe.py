"""受限纯函数演示探针：固定测试、去凭据子进程、AST 限制、超时。

这是纯 Python 小题的限制执行器，不是运行任意不可信程序的通用安全沙箱。
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile

from .probe import ProbeResult

SAFE_BUILTINS = ("abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "int",
                 "isinstance", "len", "list", "map", "max", "min", "next", "range", "reversed",
                 "round", "set", "sorted", "str", "sum", "tuple", "zip", "ValueError", "IndexError")
SAFE_METHODS = {"append", "extend", "pop", "sort", "reverse", "index", "count", "copy", "get",
                "keys", "values", "items", "add", "discard", "remove", "clear", "setdefault"}


def validate(source: str, *, tests: bool = False):
    tree = ast.parse(source)
    if not tree.body or any(not isinstance(n, ast.FunctionDef) and not (
        isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
    ) for n in tree.body):
        raise ValueError("只允许函数定义与文档字符串")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.Global, ast.Nonlocal,
                             ast.With, ast.AsyncFunctionDef, ast.Delete)):
            raise ValueError("不支持的语法: " + type(node).__name__)
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("禁止反射")
        if isinstance(node, ast.Attribute) and node.attr not in SAFE_METHODS:
            raise ValueError("不支持的方法: " + node.attr)
        if isinstance(node, ast.FunctionDef):
            if node.decorator_list or node.args.defaults or node.args.kw_defaults:
                raise ValueError("演示探针不支持装饰器或默认参数")
            if node.name.startswith("__") or node.name in SAFE_BUILTINS:
                raise ValueError("函数名越域")
            if tests and (not node.name.startswith("test_") or node.args.args):
                raise ValueError("测试必须是无参 test_* 函数")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"open", "eval", "exec", "compile", "getattr", "setattr", "globals", "locals",
                                "vars", "input", "breakpoint", "help", "type", "super", "__import__"}:
                raise ValueError("禁止调用: " + node.func.id)
    if tests and sum(isinstance(n, ast.Assert) for n in ast.walk(tree)) < 3:
        raise ValueError("独立测试至少需要3个 assert")
    return tree


WORKER = r'''
import builtins, json, sys
try:
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
except ImportError:
    pass
data = json.load(sys.stdin)
scope = {"__builtins__": {k: getattr(builtins, k) for k in data["builtins"]}}
try:
    exec(compile(data["source"], "subject.py", "exec"), scope)
    exec(compile(data["tests"], "tests.py", "exec"), scope)
    tests = [v for k, v in scope.items() if k.startswith("test_") and callable(v)]
    passed, failures = 0, []
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as exc:
            failures.append({"test": test.__name__, "error": type(exc).__name__, "detail": str(exc)[:160]})
    print(json.dumps({"ok": bool(tests) and not failures, "passed": passed, "total": len(tests), "failures": failures}))
except Exception as exc:
    print(json.dumps({"ok": False, "setup_error": type(exc).__name__}))
'''


class PurePythonProbe:
    def __init__(self, timeout_s: float = 4.0):
        self.timeout_s = timeout_s

    def run(self, source: str) -> ProbeResult:
        return ProbeResult(False, "必须同时提供独立测试和原版/埋雷版")

    def verify_pair(self, original: str, planted: str, tests: str):
        try:
            trees = [validate(original), validate(planted), validate(tests, tests=True)]
            names = [{n.name for n in t.body if isinstance(n, ast.FunctionDef)} for t in trees]
            if names[0] != names[1] or names[0] & names[2]:
                raise ValueError("函数签名集合被修改或测试覆盖了被测函数")
            if any(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id in names[0]
                   for n in ast.walk(trees[2])):
                raise ValueError("测试不能改写被测函数")
        except (SyntaxError, ValueError, TypeError) as exc:
            invalid = ProbeResult(False, "验证拒绝: " + str(exc))
            return invalid, invalid
        return self._run(original, tests), self._run(planted, tests)

    def _run(self, source, tests):
        with tempfile.TemporaryDirectory(prefix="mc_pure_") as directory:
            # 不把模型/RAG 密钥传给执行生成代码的子进程。
            clean_env = {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR") if k in os.environ}
            try:
                result = subprocess.run([sys.executable, "-I", "-S", "-c", WORKER],
                    input=json.dumps({"source": source, "tests": tests, "builtins": SAFE_BUILTINS}),
                    text=True, capture_output=True, cwd=directory, env=clean_env, timeout=self.timeout_s)
                data = json.loads(result.stdout)
                if "setup_error" in data:
                    return ProbeResult(False, "执行初始化失败: " + data["setup_error"], timed_out=True)
                return ProbeResult(bool(data["ok"]), json.dumps(data, ensure_ascii=False))
            except (subprocess.TimeoutExpired, ValueError, OSError):
                return ProbeResult(False, "探针执行失败或超时，不能确认行为缺陷", timed_out=True)
