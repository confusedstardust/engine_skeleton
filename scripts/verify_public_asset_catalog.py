"""Read-only public catalog checks plus a restored favorite round trip."""
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from webgal_backend.asset_library import AssetLibrary


def main():
    review = ROOT / 'exports/public_asset_review_2026-10-07'
    entries = json.loads((review / 'asset_manifest.json').read_text(encoding='utf-8-sig'))
    lib = AssetLibrary()
    viewer = 'catalog-verification-non-owner'
    rows = lib.list_assets(viewer, source_type='GENERATED', original_only=True, limit=200)
    by_id = {row['id']: row for row in rows}
    assert all(entry['asset_id'] in by_id for entry in entries), 'Missing public assets'

    def check(entry):
        row = by_id[entry['asset_id']]
        assert row['visibility'] == 'PUBLIC'
        assert row['name'] == entry.get('display_name', Path(entry['filename']).stem)
        assert row['category'] == entry['category']
        with urlopen(Request(row['url'], method='HEAD'), timeout=30) as response:
            assert response.status == 200
            assert int(response.headers['Content-Length']) == entry['size_bytes']
        return row['id']

    with ThreadPoolExecutor(max_workers=8) as pool:
        verified = list(pool.map(check, entries))
    samples = []
    for kind in ('bg', 'figure', 'cg'):
        entry = next(e for e in entries if e['type'] == kind)
        row = by_id[entry['asset_id']]
        record, content = lib.download_accessible_file(viewer, row['file_id'])
        assert hashlib.sha256(content).hexdigest() == entry['sha256']
        samples.append(kind)
    assert lib.list_assets(viewer, source_type='GENERATED', search='古代人物')
    with lib._transaction() as cursor:
        cursor.execute('SELECT id FROM users ORDER BY created_at LIMIT 1')
        user = cursor.fetchone()['id']
        cursor.execute('SELECT 1 FROM asset_favorites WHERE user_id=%s AND asset_id=%s', (user, entries[0]['asset_id']))
        had_favorite = cursor.fetchone() is not None
    try:
        lib.set_favorite(user, entries[0]['asset_id'], True)
        assert any(r['id'] == entries[0]['asset_id'] for r in lib.list_assets(user, collection='favorites', limit=200))
    finally:
        if not had_favorite:
            lib.set_favorite(user, entries[0]['asset_id'], False)
    report = {'public_urls_verified': len(verified), 'cross_owner_download_sha256_samples': samples,
              'chinese_category_search': 'passed', 'favorite_round_trip_restored': 'passed',
              'browser_selection_and_game_preview': 'pending_login'}
    (review / 'verification_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
