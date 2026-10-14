"""Import the reviewed catalog into OSS/MySQL; dry run unless --apply is given."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from webgal_backend.asset_library import AssetLibrary, _location_hash
from webgal_backend.config import settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--database', required=True, help='Expected database, checked before writes')
    parser.add_argument('--owner', required=True, help='Existing catalog administrator user ID')
    args = parser.parse_args()
    lib = AssetLibrary()
    if lib.config.database != args.database:
        raise RuntimeError('Database does not match the explicitly selected target')
    review = ROOT / 'exports/public_asset_review_2026-10-07'
    base = (ROOT / 'exports/jobs_assets_flat_2026-10-07').resolve()
    entries = json.loads((review / 'asset_manifest.json').read_text(encoding='utf-8-sig'))
    for entry in entries:
        path = (base / entry['relative_path']).resolve()
        if not path.is_relative_to(base) or entry['review_status'] != 'READY':
            raise RuntimeError('Unapproved entry or unsafe catalog path')
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise RuntimeError(f"Catalog file changed: {entry['filename']}")
    with lib._transaction() as cursor:
        cursor.execute('SELECT id FROM users WHERE id=%s', (args.owner,))
        if cursor.fetchone() is None:
            raise RuntimeError('Catalog administrator does not exist')
    print(json.dumps({'count': len(entries), 'database': args.database,
                      'bucket': settings.oss_bucket, 'apply': args.apply}), flush=True)
    if not args.apply:
        return
    bucket = lib._bucket()
    report = []
    for entry in entries:
        aid = entry['asset_id']
        fid = hashlib.sha256(f"catalog:{aid}:original:1".encode()).hexdigest()[:32]
        key = f"{settings.oss_prefix.rstrip('/')}/catalog/{aid}/{entry['filename']}"
        with lib._transaction() as cursor:
            cursor.execute('SELECT a.owner_user_id, f.sha256 FROM assets a LEFT JOIN asset_files f ON f.asset_id=a.id WHERE a.id=%s', (aid,))
            existing = cursor.fetchall()
        if existing:
            if any(row['owner_user_id'] != args.owner or row['sha256'] != entry['sha256'] for row in existing):
                raise RuntimeError('Existing asset identity conflicts with catalog')
            report.append({'asset_id': aid, 'file_id': fid, 'status': 'existing', 'object_key': key})
            continue
        content = (base / entry['relative_path']).read_bytes()
        if bucket.object_exists(key):
            if hashlib.sha256(bucket.get_object(key).read()).hexdigest() != entry['sha256']:
                raise RuntimeError('Existing OSS object conflicts with catalog')
            etag = bucket.head_object(key).etag
        else:
            etag = bucket.put_object(key, content, headers={'Content-Type': 'image/webp'}).etag
        metadata = {k: entry[k] for k in ('type', 'category', 'category_label', 'tags', 'old_filename')}
        metadata['library_scope'] = 'PLATFORM'
        metadata['catalog'] = 'jobs-reviewed-2026-10-07'
        with lib._transaction() as cursor:
            cursor.execute("INSERT INTO assets (id,owner_user_id,name,kind,source_type,visibility,status,generation_metadata,source_key) VALUES (%s,%s,%s,%s,'GENERATED','PUBLIC','ACTIVE',%s,%s)",
                           (aid, args.owner, entry.get('display_name') or Path(entry['filename']).stem, 'FIGURE' if entry['type'] == 'figure' else 'BACKGROUND', json.dumps(metadata, ensure_ascii=False), f'platform-catalog:{aid}'))
            cursor.execute("INSERT INTO asset_files (id,asset_id,revision,variant,storage_provider,bucket,region,object_key,location_hash,sha256,etag,mime_type,size_bytes,width_px,height_px,status,uploaded_at) VALUES (%s,%s,1,'original','OSS',%s,'oss-cn-hangzhou',%s,%s,%s,%s,'image/webp',%s,%s,%s,'READY',CURRENT_TIMESTAMP(3))",
                           (fid, aid, settings.oss_bucket, key, _location_hash('OSS', settings.oss_bucket, key), entry['sha256'], etag, len(content), entry['width'], entry['height']))
        report.append({'asset_id': aid, 'file_id': fid, 'status': 'registered', 'object_key': key})
        (review / 'upload_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'{len(report)}/{len(entries)} registered', flush=True)
    (review / 'upload_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
