from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import pytest

from webgal_backend.asset_library import AssetLibrary, AssetLibraryError


class RecordingCursor:
    def __init__(self, fetches=None, rowcount=1) -> None:
        self.calls = []
        self.fetches = list(fetches or [])
        self.rowcount = rowcount

    def execute(self, query, params=()):
        self.calls.append((" ".join(str(query).split()), tuple(params)))

    def fetchone(self):
        return self.fetches.pop(0) if self.fetches else None

    def fetchall(self):
        return []


def library_with_cursor(cursor: RecordingCursor) -> AssetLibrary:
    library = object.__new__(AssetLibrary)

    @contextmanager
    def transaction():
        yield cursor

    library._transaction = transaction
    return library


def test_generated_asset_listing_is_public_not_owner_scoped():
    cursor = RecordingCursor()
    library = library_with_cursor(cursor)

    assert library.list_assets("viewer-user", kind="BACKGROUND", source_type="GENERATED") == []

    query, params = cursor.calls[-1]
    assert "a.source_type='GENERATED'" in query
    assert "a.owner_user_id=%s" not in query
    assert params == ("BACKGROUND", 100)


def test_uploaded_asset_listing_remains_owner_scoped():
    cursor = RecordingCursor()
    library = library_with_cursor(cursor)

    assert library.list_assets("owner-user", kind="FIGURE", source_type="UPLOADED") == []

    query, params = cursor.calls[-1]
    assert "a.owner_user_id=%s" in query
    assert params == ("owner-user", "FIGURE", "UPLOADED", 100)


def test_personal_collection_combines_uploads_and_accessible_favorites_in_one_page():
    cursor = RecordingCursor()
    library = library_with_cursor(cursor)
    library.list_assets("viewer", collection="personal", original_only=True, limit=13, offset=12)
    query, params = cursor.calls[-1]
    assert "a.source_type='UPLOADED'" in query
    assert "EXISTS (SELECT 1 FROM asset_favorites" in query
    assert "a.owner_user_id=%s OR a.source_type='GENERATED'" in query
    assert "f.variant='original'" in query
    assert params == ("viewer", "viewer", "viewer", 13, 12)


def test_category_filter_is_bound_with_server_side_pagination():
    cursor = RecordingCursor()
    library_with_cursor(cursor).list_assets("viewer", source_type="GENERATED", category="ancient", limit=13, offset=12)
    query, params = cursor.calls[-1]
    assert "'$.category'))=%s" in query
    assert params == ("ancient", 13, 12)


def test_public_generated_asset_is_accessible_to_another_user():
    record = {"id": "f" * 32, "source_type": "GENERATED", "visibility": "PUBLIC"}
    cursor = RecordingCursor([record])
    library = library_with_cursor(cursor)

    assert library.get_accessible_file("viewer-user", "f" * 32) == record

    query, params = cursor.calls[-1]
    assert "a.owner_user_id=%s OR a.source_type='GENERATED'" in query
    assert params == ("f" * 32, "viewer-user")


def test_publish_file_rejects_unused_imported_source(tmp_path: Path):
    library = object.__new__(AssetLibrary)
    source = tmp_path / "asset.webp"
    source.write_bytes(b"asset")

    with pytest.raises(AssetLibraryError, match="Unsupported asset source type"):
        library.publish_file(
            user_id="user-1",
            job_id="a" * 32,
            path=source,
            logical_path="background/asset.webp",
            kind="BACKGROUND",
            source_type="IMPORTED",
            name="asset",
            usage_role="background",
            source_key="job:key",
        )


@pytest.mark.parametrize(("source_type", "expected_visibility"), [("GENERATED", "PUBLIC"), ("UPLOADED", "PRIVATE")])
def test_publish_file_sets_visibility_from_origin(tmp_path: Path, source_type: str, expected_visibility: str):
    cursor = RecordingCursor([{"id": "job"}, None, {"next_revision": 1}])
    library = library_with_cursor(cursor)

    class FakeBucket:
        def put_object(self, *_args, **_kwargs):
            return type("Result", (), {"etag": "etag"})()

        def delete_object(self, *_args, **_kwargs):
            raise AssertionError("successful publish must not delete the object")

    library._bucket = lambda: FakeBucket()
    source = tmp_path / "asset.webp"
    source.write_bytes(b"asset bytes")

    library.publish_file(
        user_id="user-1",
        job_id="a" * 32,
        path=source,
        logical_path="background/asset.webp",
        kind="BACKGROUND",
        source_type=source_type,
        name="asset",
        usage_role="background",
        source_key="job:key",
    )

    _, params = next(call for call in cursor.calls if "INSERT INTO assets" in call[0])
    assert expected_visibility in params


def test_visibility_migration_never_blocks_or_rewrites_generated_files():
    migration = (Path(__file__).parents[1] / "docs" / "database-plan" / "06_generated_asset_visibility.sql").read_text(encoding="utf-8")

    assert "SET visibility = 'PUBLIC'" in migration
    assert "UPDATE asset_files" not in migration
    assert "SET asset.status" not in migration


def test_rename_asset_is_owner_scoped():
    cursor = RecordingCursor([{"id": "a" * 32, "name": "新名称", "kind": "FIGURE", "source_type": "UPLOADED"}])
    library = library_with_cursor(cursor)

    result = library.rename_asset("owner-user", "a" * 32, "  新名称  ")

    assert result["name"] == "新名称"
    update_query, update_params = cursor.calls[0]
    assert "owner_user_id=%s" in update_query
    assert update_params == ("新名称", "a" * 32, "owner-user")


def test_delete_asset_soft_deletes_owner_asset_without_touching_files():
    cursor = RecordingCursor()
    library = library_with_cursor(cursor)

    library.delete_asset("owner-user", "a" * 32)

    query, params = cursor.calls[0]
    assert "UPDATE assets SET status='DELETED'" in query
    assert "owner_user_id=%s" in query
    assert params == ("a" * 32, "owner-user")
    assert "asset_files" not in query


def test_delete_asset_rejects_missing_or_foreign_asset():
    library = library_with_cursor(RecordingCursor(rowcount=0))

    with pytest.raises(AssetLibraryError, match="Asset not found"):
        library.delete_asset("owner-user", "a" * 32)


def test_favorites_are_user_scoped_and_check_access():
    cursor = RecordingCursor()
    library_with_cursor(cursor).list_assets("viewer", collection="favorites")
    query, params = cursor.calls[-1]
    assert "af.user_id=%s" in query
    assert "a.owner_user_id=%s OR a.source_type='GENERATED'" in query
    assert params == ("viewer", "viewer", 100)


def test_cannot_favorite_inaccessible_asset():
    cursor = RecordingCursor([None])
    with pytest.raises(AssetLibraryError):
        library_with_cursor(cursor).set_favorite("viewer", "asset", True)
    assert len(cursor.calls) == 1


def test_favorite_is_idempotent_and_unfavorite_only_affects_viewer():
    cursor = RecordingCursor([{"id": "asset"}])
    library = library_with_cursor(cursor)
    library.set_favorite("viewer", "asset", True)
    assert "ON DUPLICATE KEY UPDATE" in cursor.calls[-1][0]
    library.set_favorite("viewer", "asset", False)
    assert cursor.calls[-1][1] == ("viewer", "asset")
    assert "WHERE user_id=%s AND asset_id=%s" in cursor.calls[-1][0]


def test_upload_collection_excludes_generated_assets():
    cursor = RecordingCursor()
    library_with_cursor(cursor).list_assets("viewer", collection="uploads")
    query, params = cursor.calls[-1]
    assert "a.owner_user_id=%s" in query
    assert "a.source_type='UPLOADED'" in query
    assert params == ("viewer", 100)
