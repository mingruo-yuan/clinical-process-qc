# -*- coding: utf-8 -*-
"""
Agent Skill 基类 - 结构化Skill定义
每个Skill包含: 触发规则、核心能力、执行步骤、约束、输出模板
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

from utils.llm_client import build_patient_context


class SkillStatus(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    NEED_MORE_DATA = "need_more_data"
    NOT_TRIGGERED = "not_triggered"


@dataclass
class SkillResult:
    skill_id: str
    skill_name: str
    status: SkillStatus
    总结: str
    详情: Dict[str, Any] = field(default_factory=dict)
    建议: List[str] = field(default_factory=list)
    警告: List[str] = field(default_factory=list)
    置信度: float = 0.0
    参考: List[str] = field(default_factory=list)
    执行记录: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为可JSON存储的dict"""
        return {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "status": self.status.value,
            "总结": self.总结,
            "详情": self.详情,
            "建议": self.建议,
            "警告": self.警告,
            "置信度": self.置信度,
            "参考": self.参考,
            "执行记录": self.执行记录,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SkillResult":
        return cls(
            skill_id=d.get("skill_id", ""),
            skill_name=d.get("skill_name", ""),
            status=SkillStatus(d.get("status", "success")),
            总结=d.get("总结", ""),
            详情=d.get("详情", {}),
            建议=d.get("建议", []),
            警告=d.get("警告", []),
            置信度=d.get("置信度", 0.0),
            参考=d.get("参考", []),
            执行记录=d.get("执行记录", []),
        )


@dataclass
class SkillConfig:
    """Skill的结构化配置"""
    skill_id: str
    skill_name: str
    description: str

    # 触发规则描述 (给人看的文档)
    trigger_rules: List[str]

    # 触发条件 (代码可执行的判断函数)
    # 返回 (bool, str): (是否触发, 原因)
    trigger_check: Optional[Callable] = None

    # 核心能力
    capabilities: List[str] = field(default_factory=list)

    # 执行步骤
    execution_steps: List[str] = field(default_factory=list)

    # 约束规则
    constraints: List[str] = field(default_factory=list)

    # 输入要求
    required_fields: List[str] = field(default_factory=list)

    # 可选字段: 声明后若患者数据中存在且非空, 则自动纳入LLM上下文; 缺失不报错
    optional_fields: List[str] = field(default_factory=list)

    # 输出模板
    output_template: Dict[str, Any] = field(default_factory=dict)


class AgentSkill(ABC):
    """Agent Skill基类"""

    def __init__(self):
        self.config = self._define_config()

    @abstractmethod
    def _define_config(self) -> SkillConfig:
        """定义Skill的配置"""
        pass

    @abstractmethod
    def _execute_steps(self, patient_data: Dict, context: str) -> Dict:
        """按执行步骤执行分析"""
        pass

    @abstractmethod
    def _apply_constraints(self, raw_result: Dict, patient_data: Dict) -> Dict:
        """应用约束规则，修正结果"""
        pass

    @abstractmethod
    def _format_output(self, result: Dict) -> Dict:
        """按输出模板格式化结果"""
        pass

    def check_trigger(self, patient_data: Dict, **kwargs) -> tuple:
        """
        检查触发条件
        返回: (是否触发, 原因说明)
        """
        # 如果没有定义触发检查函数，检查必填字段是否存在
        if self.config.trigger_check:
            return self.config.trigger_check(patient_data, **kwargs)

        # 默认: 检查必填字段是否存在
        missing = self._validate_input(patient_data)
        if missing:
            return False, f"缺少必要数据: {', '.join(missing)}"
        return True, "条件满足"

    def analyze(self, patient_data: Dict[str, Any], **kwargs) -> SkillResult:
        """标准执行流程
        kwargs:
          context_data: 可选, 仅用该子集构建LLM上下文(按流程步骤裁剪输入), 校验仍基于完整patient_data
          on_chunk: 可选, 流式输出回调(text), 传给LLM调用
        """
        trace = []
        # 保存扩展参数(如图片路径), 供具体skill的_execute_steps使用
        self._kwargs = kwargs

        # Step 1: 检查触发条件
        triggered, reason = self.check_trigger(patient_data, **kwargs)
        if not triggered:
            trace.append({"step": "触发检查", "status": f"未触发: {reason}"})
            return SkillResult(
                skill_id=self.config.skill_id,
                skill_name=self.config.skill_name,
                status=SkillStatus.NOT_TRIGGERED,
                总结=f"未触发: {reason}",
                执行记录=trace,
            )
        trace.append({"step": "触发检查", "status": f"已触发: {reason}"})

        # Step 2: 验证输入(基于完整病历, 保证必填字段满足)
        missing = self._validate_input(patient_data)
        if missing:
            trace.append({"step": "输入验证", "status": f"缺失字段: {missing}"})
            return SkillResult(
                skill_id=self.config.skill_id,
                skill_name=self.config.skill_name,
                status=SkillStatus.NEED_MORE_DATA,
                总结=f"缺少必要数据: {', '.join(missing)}",
                执行记录=trace,
            )
        trace.append({"step": "输入验证", "status": "通过"})

        # Step 2.5: 检查可选字段
        available_optional = self._check_optional_fields(patient_data)
        if available_optional:
            trace.append({"step": "可选字段", "status": f"可用: {', '.join(available_optional)}"})
        elif self.config.optional_fields:
            trace.append({"step": "可选字段", "status": "无可用可选字段"})

        # Step 3: 构建上下文(默认全量; 传入context_data时按流程步骤裁剪)
        context_data = kwargs.get("context_data")
        if context_data is None:
            context_data = patient_data
        context = build_patient_context(context_data)
        scoped = context_data is not patient_data
        trace.append({"step": "构建上下文", "status": f"上下文长度: {len(context)}字" + ("(步骤输入裁剪)" if scoped else "")})

        # Step 4-6: 执行分析、约束、格式化 (异常时返回FAILED，避免崩溃)
        try:
            raw_result = self._execute_steps(patient_data, context)
            mock_mode = self._is_mock(raw_result)
            trace.append({"step": "执行分析", "status": "Mock模式(未配置LLM API)" if mock_mode else "完成"})

            constrained_result = self._apply_constraints(raw_result, patient_data)
            trace.append({"step": "约束检查", "status": "完成"})

            final_output = self._format_output(constrained_result)
            if mock_mode:
                final_output["_mock"] = True
            trace.append({"step": "格式化输出", "status": "完成"})
        except Exception as e:
            trace.append({"step": "执行分析", "status": f"异常: {e}"})
            return SkillResult(
                skill_id=self.config.skill_id,
                skill_name=self.config.skill_name,
                status=SkillStatus.FAILED,
                总结=f"技能执行失败: {e}",
                执行记录=trace,
            )

        return self._build_result(final_output, trace)

    @staticmethod
    def _is_mock(raw_result: Any) -> bool:
        """检测LLM是否返回了Mock/失败文本(未配置API或JSON解析失败)"""
        return isinstance(raw_result, dict) and isinstance(raw_result.get("raw_response"), str)

    def _validate_input(self, patient_data: Dict) -> List[str]:
        """验证输入字段 (键名做空白归一化匹配, 兼容带空格/不带空格两种写法)"""
        def norm(s: str) -> str:
            return "".join(s.split())
        missing = []
        for field_path in self.config.required_fields:
            parts = [norm(p) for p in field_path.split(".")]
            obj = patient_data
            ok = True
            for part in parts:
                if isinstance(obj, dict):
                    # 每层用当前 dict 的键做空白归一化匹配
                    nk = None
                    for k in obj:
                        if norm(k) == part:
                            nk = k
                            break
                    if nk is None:
                        ok = False
                        break
                    obj = obj[nk]
                else:
                    ok = False
                    break
            if not ok:
                missing.append(field_path)
        return missing

    def _check_optional_fields(self, patient_data: Dict) -> List[str]:
        """检查可选字段: 返回patient_data中存在且非空的optional_fields列表"""
        if not self.config.optional_fields:
            return []
        def norm(s: str) -> str:
            return "".join(s.split())
        available = []
        for field_path in self.config.optional_fields:
            parts = [norm(p) for p in field_path.split(".")]
            obj = patient_data
            ok = True
            for part in parts:
                if isinstance(obj, dict):
                    nk = None
                    for k in obj:
                        if norm(k) == part:
                            nk = k
                            break
                    if nk is None:
                        ok = False
                        break
                    obj = obj[nk]
                else:
                    ok = False
                    break
            if ok and obj:
                available.append(field_path)
        return available

    def _build_result(self, output: Dict, trace: List) -> SkillResult:
        """构建最终结果"""
        warnings = list(output.get("警告", []))
        suggestions = output.get("建议", [])
        summary = output.get("总结", "")
        confidence = output.get("置信度", 0.85)

        status = SkillStatus.SUCCESS
        if warnings:
            status = SkillStatus.PARTIAL

        if output.pop("_mock", False):
            status = SkillStatus.PARTIAL
            warnings.insert(0, "未配置LLM API密钥(Mock模式)，结果为空，请配置 OPENAI_API_KEY 后重新执行")
            summary = f"Mock模式：未配置LLM API，未能生成{self.config.skill_name}结果"

        return SkillResult(
            skill_id=self.config.skill_id,
            skill_name=self.config.skill_name,
            status=status,
            总结=summary,
            详情=output,
            建议=suggestions,
            警告=warnings,
            置信度=confidence,
            参考=output.get("参考") or [],
            执行记录=trace,
        )
