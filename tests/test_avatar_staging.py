import importlib
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from webgal_backend.pipeline import WebGALPipeline
from webgal_backend.storage import read_json


backend = importlib.import_module("webgal_backend.app")


@pytest.mark.parametrize("published", [False, True])
@pytest.mark.parametrize("draft_replacement", [False, True])
def test_crop_stages_complete_figure_and_publishes(tmp_path, published, draft_replacement):
    job = {"id": "crop-job", "has_published_build": published}
    public = tmp_path / "public/game/figure/figure_cen_xun.webp"
    draft = tmp_path / "draft/game/figure/figure_cen_xun.webp"
    public.parent.mkdir(parents=True)
    Image.new("RGBA", (40, 80), "red").save(public, "WEBP", lossless=True)
    original_public = public.read_bytes()
    if draft_replacement:
        draft.parent.mkdir(parents=True)
        Image.new("RGBA", (40, 80), "blue").save(draft, "WEBP", lossless=True)
    expected = (draft if draft_replacement else public).read_bytes()
    with (
        patch.object(backend, "_get_owned_job_or_404", return_value=job),
        patch.object(backend, "_require_job_editable"),
        patch.object(backend, "_job_dir_or_404", return_value=tmp_path),
        patch.object(backend, "store", Mock()),
    ):
        payload = backend.AvatarCropRequest(filename="figure_cen_xun.webp")
        backend.crop_asset_avatar("crop-job", payload, Mock())
        # Saving twice must also work when the source is already staged.
        backend.crop_asset_avatar("crop-job", payload, Mock())

    assert draft.read_bytes() == expected
    assert public.read_bytes() == original_public
    avatar = draft.parent / "miniavatar_cen_xun.webp"
    assert Image.open(avatar).size == (400, 400)
    records = read_json(tmp_path / "state/uploaded_assets.json")["items"]
    assert len(records) == 1
    assert records[0]["status"] == "staged"
    with patch("webgal_backend.pipeline.upload_public_asset", return_value=("key", "https://example.test/asset")) as upload:
        WebGALPipeline(store=Mock())._publish_uploaded_assets_to_oss(tmp_path, "crop-job")
    assert upload.call_count == 2
    assert upload.call_args_list[0].args[3] == expected
    assert read_json(tmp_path / "state/uploaded_assets.json")["items"][0]["status"] == "published"


def test_missing_figure_still_fails_without_creating_staged_record(tmp_path):
    with (
        patch.object(backend, "_get_owned_job_or_404", return_value={"id": "crop-job"}),
        patch.object(backend, "_require_job_editable"),
        patch.object(backend, "_job_dir_or_404", return_value=tmp_path),
    ):
        with pytest.raises(backend.HTTPException) as exc:
            backend.crop_asset_avatar("crop-job", backend.AvatarCropRequest(filename="missing.webp"), Mock())
    assert exc.value.status_code == 404
    assert not (tmp_path / "state/uploaded_assets.json").exists()
