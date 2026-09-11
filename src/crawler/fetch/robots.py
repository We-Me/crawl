"""robots.txt 规则解析与判定（FR-001：遵守来源访问规则）。

按 RFC 9309 的可用子集实现：User-agent 组匹配、Allow/Disallow 最长匹配优先、
同长度时 Allow 优先、空 Disallow 表示放行；`*` 与 `$` 按通行扩展支持。
本模块只做纯解析与判定，不发网络请求；获取、缓存与拒绝抛错在 http_client 中。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

WILDCARD_AGENT = "*"


@lru_cache(maxsize=512)
def _compile_pattern(pattern: str) -> "re.Pattern[str]":
    """把 robots 路径模式编译为正则：`*` 任意串，结尾 `$` 锚定，其余按字面量。"""
    anchored = pattern.endswith("$")
    core = pattern[:-1] if anchored else pattern
    body = "".join(".*" if char == "*" else re.escape(char) for char in core)
    return re.compile("^" + body + ("$" if anchored else ""))


@dataclass(frozen=True)
class RobotRule:
    """一条 Allow/Disallow 规则；pattern 为空表示不限制。"""

    allow: bool
    pattern: str

    @property
    def length(self) -> int:
        return len(self.pattern)

    def matches(self, path: str) -> bool:
        return bool(self.pattern) and _compile_pattern(self.pattern).match(path) is not None


@dataclass(frozen=True)
class RobotsGroup:
    """一组 User-agent 及其规则。"""

    agents: Tuple[str, ...]
    rules: Tuple[RobotRule, ...]


@dataclass(frozen=True)
class RobotsRules:
    """单个主机的 robots 规则；blocked 表示规则不可用时保守拒绝。"""

    groups: Tuple[RobotsGroup, ...] = ()
    reason: str = ""
    blocked: bool = False

    @classmethod
    def allow_all(cls, reason: str) -> "RobotsRules":
        return cls((), reason=reason)

    @classmethod
    def deny_all(cls, reason: str) -> "RobotsRules":
        return cls((), reason=reason, blocked=True)

    def match_group(self, user_agent: str) -> Optional[RobotsGroup]:
        """返回最匹配的组：具体 token 优先，其次 `*`；大小写不敏感。"""
        ua = (user_agent or "").lower()
        wildcard: Optional[RobotsGroup] = None
        best: Optional[RobotsGroup] = None
        best_length = -1
        for group in self.groups:
            for agent in group.agents:
                if agent == WILDCARD_AGENT:
                    if wildcard is None:
                        wildcard = group
                    continue
                if agent and agent in ua and len(agent) > best_length:
                    best, best_length = group, len(agent)
        return best or wildcard

    def decision(self, path: str, user_agent: str) -> Tuple[bool, str]:
        """返回 (是否允许, 原因)。无规则、无匹配或空规则都放行。"""
        if self.blocked:
            return False, self.reason or "规则不可用，保守拒绝"
        group = self.match_group(user_agent)
        if group is None:
            return True, self.reason or "没有匹配的 User-agent 组"
        target = path or "/"
        best: Optional[RobotRule] = None
        for rule in group.rules:
            if not rule.matches(target):
                continue
            if (
                best is None
                or rule.length > best.length
                or (rule.length == best.length and rule.allow and not best.allow)
            ):
                best = rule
        if best is None:
            return True, "没有匹配的 Allow/Disallow 规则"
        label = "Allow" if best.allow else "Disallow"
        return best.allow, f"{label} {best.pattern}"


def rules_for_unavailable(status: Optional[int]) -> RobotsRules:
    """robots.txt 不可用时的策略：4xx 视为无规则放行，5xx/网络失败保守拒绝。"""
    if status is None:
        return RobotsRules.deny_all("robots.txt 获取失败，保守拒绝")
    if 400 <= status < 500:
        return RobotsRules.allow_all(f"robots.txt 返回 {status}，视为无规则")
    return RobotsRules.deny_all(f"robots.txt 返回 {status}，保守拒绝")


def parse_robots(text: str) -> RobotsRules:
    """解析 robots.txt 文本；忽略 Crawl-delay/Sitemap 等非 Allow/Disallow 指令。"""
    groups: List[RobotsGroup] = []
    agents: List[str] = []
    rules: List[RobotRule] = []

    def flush() -> None:
        nonlocal agents, rules
        if agents:
            groups.append(RobotsGroup(tuple(agents), tuple(rules)))
        agents, rules = [], []

    for raw_line in (text or "").lstrip("\ufeff").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            if rules:  # 规则之后的新 UA 行开始新组
                flush()
            if value:
                agents.append(value.lower())
        elif field in ("allow", "disallow"):
            if not agents:
                continue  # 出现在任何 User-agent 之前的规则不属于任何组
            if not value:
                continue  # 空 Disallow/Allow 不构成限制
            rules.append(RobotRule(field == "allow", value))
    flush()
    return RobotsRules(tuple(groups), reason="按 robots.txt 解析")


def group_summary(rules: RobotsRules) -> Dict[str, int]:
    """可读的规则统计，用于日志与证据。"""
    return {
        "groups": len(rules.groups),
        "rules": sum(len(group.rules) for group in rules.groups),
        "agents": sum(len(group.agents) for group in rules.groups),
    }
