import pytest

from webgal_backend.scene_headers import scene_header_matches, scene_header_match, scene_header_kind, format_scene_header, scene_sections
from webgal_backend.game_design import scene_header_matches as design_headers
from webgal_backend.pipeline import WebGALPipeline
from webgal_backend.tts_pipeline import _scene_sections


@pytest.mark.parametrize("header, filename, kind", [
    ("Scene:start.txt", "start.txt", "Scene"),
    ("Ending：ending_good.txt", "ending_good.txt", "Ending"),
    ("scene : chapter_2.txt", "chapter_2.txt", "scene"),
    ("## Scene:start.txt", "start.txt", "Scene"),
    ("[chapter_2.txt]", "chapter_2.txt", "Scene"),
    ("【ending_good.txt】", "ending_good.txt", "Ending"),
    ("文件：chapter_2.txt", "chapter_2.txt", "Scene"),
    ("file chapter_2.txt:", "chapter_2.txt", "Scene"),
    ("ending_good.txt", "ending_good.txt", "Ending"),
])
def test_design_pipeline_and_tts_share_the_same_header_grammar(header, filename, kind):
    pipeline = object.__new__(WebGALPipeline)
    text = f"{header}\n旁白:作者原文;\n"
    match = scene_header_match(header)
    assert match.group("filename") == filename
    assert scene_header_kind(match) == kind
    assert pipeline._is_scene_header(header)
    assert pipeline._scene_header_match(header).group("filename") == filename
    assert [item.group("filename") for item in pipeline._scene_header_matches(text)] == [filename]
    assert [item.group("filename") for item in design_headers(text)] == [filename]
    assert _scene_sections(text) == [(filename, "旁白:作者原文;")]


@pytest.mark.parametrize("line", ["changeScene:start.txt;", "角色:start.txt", "Scene:../start.txt", "Scene:a/b.txt", "Scene:start.txt 旁白", "choose:继续:start.txt;", "Scene:start.json"])
def test_dialogue_commands_paths_and_invalid_extensions_are_not_headers(line):
    assert scene_header_match(line) is None
    assert scene_header_matches(line) == []


def test_section_offsets_preserve_body_and_scene_order():
    text = "# Scene:start.txt\n旁白:第一段;\n\n[chapter_2.txt]\n角色:第二段;\nEnding:ending_good.txt\nend;"
    assert scene_sections(text) == [("start.txt", "旁白:第一段;"), ("chapter_2.txt", "角色:第二段;"), ("ending_good.txt", "end;")]
    for match in scene_header_matches(text):
        assert text[match.start():match.end()].strip()


def test_explicit_marker_wins_and_canonical_format_remains_compatible():
    assert scene_header_kind(scene_header_match("Scene:ending_custom.txt")) == "Scene"
    assert format_scene_header("ending_custom.txt") == "Ending:ending_custom.txt"
    assert format_scene_header("folder/start.txt") == "Scene:folder/start.txt"
    assert format_scene_header("ENDING_custom.txt") == "Scene:ENDING_custom.txt"


def test_pipeline_scene_output_and_bgm_accept_the_same_authored_headers(tmp_path):
    pipeline = WebGALPipeline()
    text = "# Scene:start.txt\n旁白:第一段;\n【ending_good.txt】\nend;"
    paths = pipeline._split_game_design_completed_to_scene_files(tmp_path, text)
    assert paths == ["public/game/scene/start.txt", "public/game/scene/ending_good.txt"]
    assert (tmp_path / paths[0]).read_text(encoding="utf-8") == "旁白:第一段;\n"
    plan = pipeline._build_bgm_plan(text, {"opening": ["opening.mp3"], "dialog": [], "ending": ["ending.mp3"]})
    assert {item["scene_file"] for item in plan} == {"start.txt", "ending_good.txt"}
