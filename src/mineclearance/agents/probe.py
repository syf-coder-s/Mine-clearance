"""埋雷后的自动复核。

规矩是「原版通过、埋雷版失败」。这一条必须在封印之前跑，理由很简单：
    雷没埋上，或者埋完之后原版也挂了，那这道题本身是坏的。
    坏题拿去判学生，学生答对了也会被判错，这是产品最不可原谅的错。
宁可这道题不进本场，也不能带着坏题往下走。

探针有两种：
    MarkerProbe   —— 确定性替身，冒烟与单测用。按源码里有没有健康标记判定。
    CommandProbe  —— 生产用。把源码写进临时目录，跑一条带超时的命令（pytest 等）。
                     默认不启用：执行模型生成的代码是有风险的，必须由部署方显式打开。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    detail: str = ""
    timed_out: bool = False


@runtime_checkable
class Probe(Protocol):
    def run(self, source: str) -> ProbeResult:
        """返回源码是否「行为正确」。"""


class MarkerProbe:
    """按健康标记判定。故意做得很笨，免得有人以为它在做语义校验。"""

    def __init__(self, healthy_marker: str = "# OK") -> None:
        if not healthy_marker:
            raise ValueError("healthy_marker 不能为空")
        self.healthy_marker = healthy_marker

    def run(self, source: str) -> ProbeResult:
        ok = self.healthy_marker in source
        return ProbeResult(ok=ok, detail="健康标记%s" % ("存在" if ok else "缺失"))


class CommandProbe:
    """在临时目录里跑一条命令。{file} 会被替换成源码文件路径。

    使用前提：调用方自己的沙箱策略（容器、只读挂载、去掉网络）。
    这里只保证「单次执行不超时、不留工作目录之外的东西」。
    """

    def __init__(self, argv: Sequence[str], *, timeout_s: float = 5.0, suffix: str = ".py") -> None:
        if not argv:
            raise ValueError("argv 不能为空")
        self.argv = list(argv)
        self.timeout_s = timeout_s
        self.suffix = suffix

    def run(self, source: str) -> ProbeResult:
        with tempfile.TemporaryDirectory(prefix="mc_probe_") as workdir:
            target = Path(workdir) / ("subject" + self.suffix)
            target.write_text(source, encoding="utf-8")
            argv = [part.replace("{file}", str(target)) for part in self.argv]
            try:
                completed = subprocess.run(
                    argv,
                    cwd=workdir,
                    capture_output=True,
                    timeout=self.timeout_s,
                    text=True,
                )
            except subprocess.TimeoutExpired:
                return ProbeResult(ok=False, detail="探针超时 %.1fs" % self.timeout_s, timed_out=True)
            except OSError as exc:
                return ProbeResult(ok=False, detail="探针无法执行: %s" % exc)
        detail = (completed.stdout + completed.stderr).strip()[-300:]
        return ProbeResult(ok=completed.returncode == 0, detail=detail or "exit=%d" % completed.returncode)


PYTEST_PROBE = CommandProbe([sys.executable, "-m", "pytest", "-q", "--no-header", "{file}"], timeout_s=8.0)
