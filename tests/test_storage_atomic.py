from pathlib import Path

import pytest

from webgal_backend import storage


def test_reader_sees_complete_old_document_until_replacement(tmp_path, monkeypatch):
    target = tmp_path / "job.json"
    storage.write_json(target, {"title": "原作品"})
    replace = storage.os.replace

    def inspect_replace(source, destination):
        assert Path(source).parent == target.parent
        assert storage.read_json(target) == {"title": "原作品"}
        assert storage.read_json(Path(source)) == {"title": "新作品"}
        replace(source, destination)

    monkeypatch.setattr(storage.os, "replace", inspect_replace)
    storage.write_json(target, {"title": "新作品"})
    assert storage.read_json(target) == {"title": "新作品"}
    assert list(tmp_path.iterdir()) == [target]


def test_failed_replacement_preserves_original_and_cleans_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "job.json"
    storage.write_json(target, {"status": "DONE"})

    def fail_replace(*args):
        raise OSError("replacement failed")

    monkeypatch.setattr(storage.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failed"):
        storage.write_json(target, {"status": "RUNNING"})
    assert storage.read_json(target) == {"status": "DONE"}
    assert list(tmp_path.iterdir()) == [target]
