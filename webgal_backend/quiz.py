from __future__ import annotations

import json
from typing import Any


def quiz_prompt(job: dict[str, Any], narrative_plan: dict[str, Any]) -> str:
    options = job.get("options") if isinstance(job.get("options"), dict) else {}
    source = str(job.get("source_material") or "").strip()
    narrative_json = json.dumps(narrative_plan, ensure_ascii=False, indent=2)
    return f"""你是一名有课堂经验的教师，请根据教学材料和已经生成的叙事课堂设计一套课后讲评练。

目标：
- 生成 4-8 道题，必须同时包含 single_choice（单选题）和 judgement（判断/辨析题）。
- 题目用于教师课后讲评，不要考察游戏界面操作，不要依赖学生记忆无关紧要的情节细节。
- 每题只有一个正确选项。single_choice 使用 4 个选项；judgement 使用 2 个选项，文本为“正确”和“错误”。
- 干扰项要有诊断价值，能够暴露常见误解，不能使用“以上都对/都不对”。
- explanation 要说明答案依据；teaching_tip 要告诉教师如何追问或纠正误区。
- 知识表述必须来自提供的教学材料和叙事计划，不得补造事实。

课堂信息：
- 主题：{options.get('classroom_topic') or '未指定'}
- 年级/学科：{options.get('grade') or '未指定'}
- 难度：{options.get('difficulty') or '未指定'}
- 教学目标：{options.get('teacher_goal') or '未指定'}
- 学生目标：{options.get('student_goal') or '未指定'}

教学材料：
{source[:24000]}

叙事计划：
{narrative_json[:24000]}

返回 quiz_plan，严格符合给定 JSON Schema。"""
