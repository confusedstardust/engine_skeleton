"""V2 Forge planning regressions (no DB, no network, no billing)."""
from webgal_backend.nar_intent_v2 import build_context_packet, plan_v2

A, B, CID = "a" * 32, "b" * 32, "c" * 32


def context(selected=None):
    return build_context_packet(
        "调整作品", CID,
        [{"role": "user", "content": "先做马达动画"},
         {"role": "assistant", "content": "已经完成"}],
        [{"artifactId": A, "kind": "animation", "title": "马达动画"},
         {"artifactId": B, "kind": "html", "title": "函数网页"}],
        selected_artifact_id=selected,
    )


def decision(action, relation, output, candidate=None, step="execute"):
    return {"schema_version": "2.0", "next_step": step, "uncertainty": "none",
            "tasks": [{"action": action, "target_relation": relation,
                       "candidate_artifact_id": candidate,
                       "desired_output": output, "goal": "任务", "requirements": []}],
            "clarification": None}


def test_new_independent_html_never_inherits_previous_animation():
    p = plan_v2(decision("create", "new", "html"), context(A))
    assert p["mode"] == "html" and p["parent_artifact_id"] is None
    blocked = plan_v2(decision("create", "new", "html", A), context(A))
    assert blocked["mode"] is None


def test_revision_respects_owner_scoped_target_and_generator_kind():
    p = plan_v2(decision("revise", "referenced", "animation", A), context())
    assert (p["mode"], p["parent_artifact_id"]) == ("animation", A)
    p2 = plan_v2(decision("revise", "referenced", "html", B), context())
    assert (p2["mode"], p2["parent_artifact_id"]) == ("edit", B)
    assert plan_v2(decision("revise", "referenced", "animation", "f" * 32), context())["mode"] is None


def test_ambiguous_target_no_auto_selection_of_recent():
    p = plan_v2(decision("revise", "ambiguous", "unspecified"), context())
    assert p["next_step"] == "clarify" and p["parent_artifact_id"] is None
    p = plan_v2(decision("revise", "selected", "animation"), context())
    assert p["next_step"] == "clarify"
    explicit = plan_v2(decision("revise", "selected", "animation"), context(A))
    assert explicit["parent_artifact_id"] == A


def test_cross_generator_must_not_silently_rebuild():
    p = plan_v2(decision("revise", "referenced", "html", A), context())
    assert p["next_step"] == "capability_review"
    assert p["mode"] is None
    assert plan_v2(decision("convert", "referenced", "html", A), context())["mode"] is None


def test_teaching_evaluation_is_not_generation_and_hybrid_is_reviewed():
    assert plan_v2(decision("evaluate", "referenced", "text", A), context())["mode"] == "chat"
    assert plan_v2(decision("create", "new", "hybrid"), context())["next_step"] == "capability_review"


def test_model_does_not_override_owner_capabilities():
    ctx = context(A)
    ctx["capabilities"]["animation"] = ["create"]
    p = plan_v2(decision("revise", "selected", "animation", A), ctx)
    assert p["mode"] is None
