"""四个角色 + 两个离线工具。

builder   出题（离线，0 次在线）
planter   埋雷（离线，0 次在线），出厂前必须过 probe 复核
adversary 对抗（在线，6–9 次）
judge     结算（在线，1 次决策 + 最多 1 次升级）
reporter  复盘（在线，1 次）
"""

from .adversary import Adversary
from .builder import Builder, BuilderError
from .judge import Judge, citation_report, extract_row
from .planter import PlantOutcome, Planter, PlanterError
from .probe import PYTEST_PROBE, CommandProbe, MarkerProbe, Probe, ProbeResult
from .report import Reporter

__all__ = [
    "Builder",
    "BuilderError",
    "Planter",
    "PlanterError",
    "PlantOutcome",
    "Probe",
    "ProbeResult",
    "MarkerProbe",
    "CommandProbe",
    "PYTEST_PROBE",
    "Adversary",
    "Judge",
    "extract_row",
    "citation_report",
    "Reporter",
]
