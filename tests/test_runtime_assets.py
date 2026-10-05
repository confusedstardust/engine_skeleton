from webgal_backend.runtime_assets import rewrite_webgal_asset_urls


def test_rewrites_runtime_images_and_voice_to_oss_urls() -> None:
    urls = {
        "background/bg_room.webp": "https://bucket.example/library/bg-room.webp",
        "figure/figure_teacher.webp": "https://bucket.example/library/teacher.webp",
        "figure/miniavatar_teacher.webp": "https://bucket.example/library/avatar.webp",
        "vocal/start_001_teacher.wav": "https://bucket.example/library/voice.wav",
    }
    source = """changeBg:bg_room.webp -next;
changeFigure:figure_teacher.webp -left -next;
miniAvatar:miniavatar_teacher.webp;
老师:你好 -start_001_teacher.wav;
playEffect:./game/vocal/start_001_teacher.wav -volume=50 -next;
"""
    rewritten = rewrite_webgal_asset_urls(source, urls)
    assert "changeBg:https://bucket.example/library/bg-room.webp -next;" in rewritten
    assert "changeFigure:https://bucket.example/library/teacher.webp -left -next;" in rewritten
    assert "miniAvatar:https://bucket.example/library/avatar.webp;" in rewritten
    assert "老师:你好 -vocal=https://bucket.example/library/voice.wav;" in rewritten
    assert "playEffect:https://bucket.example/library/voice.wav -volume=50 -next;" in rewritten


def test_keeps_external_and_unregistered_assets_unchanged() -> None:
    source = "changeBg:https://cdn.example/bg.webp -next;\nbgm:built_in.mp3;\nchangeFigure:none;\n"
    assert rewrite_webgal_asset_urls(source, {}) == source
