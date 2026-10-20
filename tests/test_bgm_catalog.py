from contextlib import contextmanager
from webgal_backend.asset_library import AssetLibrary
from webgal_backend.pipeline import WebGALPipeline


def track(name, moods):
    return dict(filename=name, moods=moods, asset_id=name, file_id=name)


def test_all_scenes_match_moods_and_manual_selection_wins():
    catalog = [track('calm.mp3', ['平静']), track('tense.mp3', ['紧张']), track('sad.mp3', ['悲伤'])]
    scenes = {'scenes': [{'scene_file': 'start.txt', 'music_mood': 'peace'},
                         {'scene_file': 'branch.txt', 'music_mood': 'tense'}],
              'endings': [{'scene_file': 'ending.txt', 'music_mood': 'sad'}]}
    assets = {'dialog': [t['filename'] for t in catalog] + ['private.mp3']}
    pipeline = WebGALPipeline()
    script = 'Scene:start.txt\nScene:branch.txt\nEnding:ending.txt'
    plan = pipeline._build_bgm_plan(script, assets, scenes, {}, catalog)
    assert [t['asset'] for t in plan] == ['calm.mp3', 'tense.mp3', 'sad.mp3']
    manual = pipeline._build_bgm_plan(script, assets, scenes, {'branch.txt': 'private.mp3'}, catalog)
    assert manual[1]['asset'] == 'private.mp3'
    assert manual[1]['system_asset'] == 'tense.mp3'
    assert 'asset_file_id' not in manual[1]


def test_empty_public_catalog_never_auto_selects_local_files():
    pipeline = WebGALPipeline()
    assets = {'dialog': ['local.mp3']}
    assert pipeline._build_bgm_plan('Scene:start.txt', assets, {}, {}, []) == []
    plan = pipeline._build_bgm_plan('Scene:start.txt', assets, {}, {'start.txt': 'local.mp3'}, [])
    assert plan[0]['asset'] == 'local.mp3'


def test_unknown_mood_falls_back_to_neutral_and_rotates_matches():
    catalog = [track('a.mp3', ['平静']), track('b.mp3', ['平静']), track('c.mp3', ['紧张'])]
    plan = WebGALPipeline()._build_bgm_plan('Scene:a.txt\nScene:b.txt', {'dialog': [t['filename'] for t in catalog]},
        {'scenes': [{'scene_file': 'a.txt', 'music_mood': 'unknown'}, {'scene_file': 'b.txt', 'music_mood': 'peace'}]}, {}, catalog)
    assert [item['asset'] for item in plan] == ['a.mp3', 'b.mp3']
    assert plan[0]['fallback'] is True


def test_public_catalog_filters_and_pins_latest_original_file():
    calls = []
    class Cursor:
        def execute(self, sql):
            calls.append(sql)
        def fetchall(self):
            return [dict(asset_id='asset', name='Music', generation_metadata='{"attributes":{"mood":["warm"]}}',
                         file_id=file, revision=rev, mime_type='audio/mpeg') for file, rev in [('new', 2), ('old', 1)]]
    @contextmanager
    def transaction():
        yield Cursor()
    library = object.__new__(AssetLibrary)
    library._transaction = transaction
    result = library.list_public_bgm()
    assert len(result) == 1 and result[0]['file_id'] == 'new'
    assert result[0]['moods'] == ['warm']
    for clause in ("a.kind='BGM'", "a.visibility='PUBLIC'", "a.status='ACTIVE'", "f.status='READY'", "f.variant='original'"):
        assert clause in calls[0]
