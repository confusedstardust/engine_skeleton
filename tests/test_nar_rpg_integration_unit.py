"""Pure contract checks for NarAgent -> existing WebGAL Auto handoff.

No LLM, MySQL, background jobs, or real credit reservations are triggered here.
Model intent accuracy and real owner/CAS behavior require integration tests.
"""
from __future__ import annotations

import unittest

from webgal_backend.nar_intent_v2 import build_context_packet, plan_v2
from webgal_backend.nar_rpg_options import compile_webgal_request, draft_game_spec


CAPS = {
    "chat": ["answer", "discuss", "evaluate"],
    "html": ["create", "revise"],
    "animation": ["create", "revise"],
    "hybrid": ["plan_only"],
    "game": ["create", "edit_link"],
}
GAME_ID = "a" * 32


class WebGALAutoInputContractTests(unittest.TestCase):
    def test_preserves_all_creative_requirements_and_confirmed_media(self):
        prompt = "把《琵琶行》做成20分钟互动RPG，玩家扮演琵琶女，至少三个结局，不需要配音。"
        spec = draft_game_spec(prompt, {"goal": "琵琶行角色扮演游戏"})
        self.assertEqual(spec["topic"], "琵琶行")
        self.assertEqual(spec["duration_minutes"], 20)
        self.assertFalse(spec["enable_voice"])
        request = compile_webgal_request(
            spec, original_prompt=prompt, duration_minutes=20,
            generate_images=True, enable_voice=True,
        )
        self.assertIn("玩家扮演琵琶女", request["source_material"])
        self.assertIn("三个结局", request["source_material"])
        self.assertIn("配音=开启", request["source_material"])
        self.assertEqual(request["options"]["generation_mode"], "auto")
        self.assertTrue(request["options"]["voice_enabled"])
        self.assertTrue(request["options"]["generate_tts"])
        self.assertEqual(request["options"]["voice_preset"], "多角色配音")
        self.assertTrue(request["options"]["generate_assets"])

    def test_negative_media_choices(self):
        prompt = "制作《围城》剧情互动游戏，不要配图，也无需配音。"
        spec = draft_game_spec(prompt, {"goal": prompt})
        self.assertFalse(spec["generate_images"])
        self.assertFalse(spec["enable_voice"])
        request = compile_webgal_request(
            spec, original_prompt=prompt, duration_minutes=30,
            generate_images=False, enable_voice=False,
        )
        self.assertFalse(request["options"]["generate_assets"])
        self.assertFalse(request["options"]["voice_enabled"])
        self.assertFalse(request["options"]["generate_tts"])
        self.assertEqual(request["options"]["duration"], "30分钟")

    def test_duration_default_and_no_silent_clamp(self):
        self.assertEqual(draft_game_spec("做一个剧情游戏", {"goal": "旅行"})["duration_minutes"], 20)
        requested = draft_game_spec("做一个120分钟的RPG", {"goal": "剧情游戏"})
        self.assertEqual(requested["duration_minutes"], 120)
        with self.assertRaises(ValueError):
            compile_webgal_request(
                requested, original_prompt="做一个120分钟的RPG",
                duration_minutes=120, generate_images=True, enable_voice=False)

    def test_invalid_inputs_are_rejected(self):
        spec = draft_game_spec("做《赤壁赋》互动游戏", {"goal": "赤壁赋"})
        for invalid in (0, 4, 61, 120, True, "20"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                compile_webgal_request(
                    spec, original_prompt="做《赤壁赋》互动游戏",
                    duration_minutes=invalid, generate_images=True, enable_voice=False,
                )
        with self.assertRaises(ValueError):
            compile_webgal_request(
                spec, original_prompt=" ", duration_minutes=20,
                generate_images=True, enable_voice=False,
            )

    def test_no_untrusted_generated_options(self):
        spec = draft_game_spec("做一款 RPG", {"goal": "互动叙事"})
        result = compile_webgal_request(
            spec, original_prompt="做一款 RPG", duration_minutes=20,
            generate_images=False, enable_voice=False,
            derived={"model": "untrusted", "generation_mode": "advanced", "grade": "成人"},
        )
        self.assertEqual(result["options"]["grade"], "成人")
        self.assertEqual(result["options"]["generation_mode"], "auto")
        self.assertNotIn("model", result["options"])


class PlannerRouteContractTests(unittest.TestCase):
    def setUp(self):
        self.context = build_context_packet(
            "创作游戏", "b" * 32, [], [], capabilities=CAPS,
            owner_scoped_games=[{"id": GAME_ID, "title": "已创作游戏", "status": "STARTED"}],
        )

    def decision(self, action="create", desired_output="game", relation="new",
                 game_id=None, artifact_id=None, step="execute"):
        return {
            "schema_version": "2.0",
            "tasks": [{
                "action": action, "target_relation": relation,
                "desired_output": desired_output,
                "candidate_artifact_id": artifact_id,
                "candidate_game_job_id": game_id,
                "goal": "按用户要求创作", "requirements": [],
            }],
            "next_step": step,
            "uncertainty": "none",
        }

    def test_new_game_uses_prepare_not_html(self):
        plan = plan_v2(self.decision(), self.context)
        self.assertEqual(plan["mode"], "rpg.prepare")
        self.assertIsNone(plan["parent_artifact_id"])

    def test_existing_rpg_edit_is_link_only(self):
        plan = plan_v2(self.decision(
            action="revise", relation="referenced", game_id=GAME_ID), self.context)
        self.assertEqual(plan["mode"], "rpg.edit_link")
        self.assertEqual(plan["game_job_id"], GAME_ID)

    def test_unowned_and_ambiguous_game_edits_fail_closed(self):
        for bad_id, relation in ((None, "ambiguous"), ("c" * 32, "referenced"),
                                 (GAME_ID, "ambiguous")):
            with self.subTest(game_id=bad_id, relation=relation):
                plan = plan_v2(self.decision(
                    action="revise", relation=relation, game_id=bad_id), self.context)
                self.assertEqual(plan["next_step"], "clarify")
                self.assertIsNone(plan["mode"])

    def test_game_capability_off_fails_closed(self):
        context = {**self.context, "capabilities": {key: value for key, value in CAPS.items() if key != "game"}}
        plan = plan_v2(self.decision(), context)
        self.assertIsNone(plan["mode"])

    def test_fifty_annotated_planner_contract_examples(self):
        # These are fixed expected outputs given annotated semantic decisions.
        # They DO NOT test real model classification accuracy.
        examples = []
        examples += [("game", p) for p in [
            "做一款玩家扮演李白的分支剧情游戏",
            "设计《围城》三结局 RPG",
            "制作 WebGAL 多人物互动故事",
            "历史人物对话分支游戏",
            "沉浸式文字剧情多结局故事",
            "互动小说，玩家选择改变结局",
            "琵琶行角色扮演剧情游戏",
            "做一个以选择影响剧情的古诗 RPG",
            "安排可选择立场的历史叙事游戏",
            "制作侦探推理故事，选择不同线索",
            "古典文学人物与剧情抉择游戏",
            "创作三个不同结局的角色剧情体验",
            "模拟《我城》叙事分支体验",
            "做一个多角色的 WebGAL 游戏",
            "重新做一款全新的海上生存互动剧情",
            "做《楚辞》互动叙事与角色选择",
            "给成年人制作一个分支伦理模拟游戏",
            "新建一款两人对话驱动的文字 RPG",
            "生成有章节和对话分支的历史剧情游戏",
            "把古诗理解变成有三条剧情路线的作品",
        ]]
        examples += [("html", p) for p in [
            "制作诗词拖拽排序小游戏",
            "做一个可以点击选答案的网页",
            "出五道判断题交互网页",
            "生成背诵抽查网页",
            "做词语卡片配对练习",
            "生成知识点点击翻牌小游戏",
            "制作生物细胞标注互动网页",
            "制作答对才进入下一关的选择题",
            "做历史时间轴拖拽练习",
            "制作一道数学交互滑块题",
            "做英文字母拼写游戏网页",
            "制作课堂奖励抽签器",
            "做填空题网页小测验",
            "制作儿童加减法练习小游戏",
            "做可交互的地理等高线演示网页",
        ]]
        examples += [("animation", p) for p in [
            "制作动画讲解三角函数",
            "用动画解释古代科举制度",
            "做一个诗词意象解说动画",
            "用运动图形展示圆周运动",
            "用动画演示火山喷发",
            "制作英语语法视频式动画",
            "展示句法树生长过程动画",
            "做一次光合作用步骤动画",
            "制作数学公式推导动画",
            "生成地球公转动画讲解",
        ]]
        examples += [("text", p) for p in [
            "评价我的 RPG 策划",
            "你觉得三结局合理吗",
            "分析这个游戏叙事结构",
            "给我的学习体验提建议",
            "讨论有没有必要加入配音",
        ]]
        self.assertEqual(len(examples), 50)
        expected = {"game": "rpg.prepare", "html": "html", "animation": "animation", "text": "chat"}
        for output, prompt in examples:
            with self.subTest(prompt=prompt):
                proposal = self.decision(
                    action="evaluate" if output == "text" else "create",
                    desired_output=output, relation="none" if output == "text" else "new",
                    step="respond" if output == "text" else "execute",
                )
                plan = plan_v2(proposal, self.context)
                self.assertEqual(plan["mode"], expected[output])


class ConfirmedFormatResumptionTests(unittest.TestCase):
    def setUp(self):
        self.original = {
            "schema_version": "2.0",
            "tasks": [{
                "action": "create", "target_relation": "new",
                "desired_output": "unspecified",
            }],
            "next_step": "clarify",
        }
        self.context = build_context_packet(
            "我选择：互动剧情游戏", "c" * 32, [], [],
            pending_task={"status": "pending", "proposal": self.original},
            pending_clarification={"current_answer": {
                "selected_option_ids": ["o1"], "selected_labels": ["互动剧情游戏"],
                "custom_text": ""
            }},
            capabilities=CAPS,
        )

    def proposal(self, *, action="continue", output="game", step="capability_review"):
        return {"schema_version": "2.0", "tasks": [{
            "action": action, "target_relation": "none",
            "candidate_artifact_id": None, "candidate_game_job_id": None,
            "desired_output": output, "goal": "继续制作互动游戏",
            "requirements": [],
        }], "next_step": step}

    def test_formal_game_choice_restores_create_even_if_model_calls_conversion(self):
        for action in ("continue", "convert"):
            with self.subTest(action=action):
                plan = plan_v2(self.proposal(action=action), self.context)
                self.assertEqual(plan["mode"], "rpg.prepare")
                self.assertEqual(plan["reason"], "new_game")

    def test_formal_html_choice_restores_html_builder(self):
        plan = plan_v2(self.proposal(output="html"), self.context)
        self.assertEqual(plan["mode"], "html")

    def test_no_answer_or_free_text_never_invents_a_creative_execution(self):
        for edit in (
            {"conversation": {**self.context["conversation"],
                              "pending_clarification": {"current_answer": {}}}},
            {"conversation": {**self.context["conversation"],
                              "pending_clarification": {"current_answer": {
                                  "selected_option_ids": ["o1"],
                                  "custom_text": "先不要做，谈一下3D玩法"
                              }}}},
        ):
            with self.subTest(edit=edit):
                plan = plan_v2(self.proposal(), {**self.context, **edit})
                self.assertEqual(plan["next_step"], "capability_review")
                self.assertIsNone(plan["mode"])

    def test_no_game_callback_capability_never_prepares_game(self):
        unavailable = {**self.context, "capabilities": {
            key: value for key, value in CAPS.items() if key != "game",
        }}
        plan = plan_v2(self.proposal(), unavailable)
        self.assertEqual(plan["next_step"], "capability_review")
        self.assertIsNone(plan["mode"])


if __name__ == "__main__":
    unittest.main()
