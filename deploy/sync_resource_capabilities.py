"""Re-read one uploaded manifest; dry-run by default, backed-up atomic apply."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from webgal_backend.html_resources import get_resource, publication_lock, resource_capabilities
from webgal_backend.storage import read_json, write_json

parser = argparse.ArgumentParser()
parser.add_argument('identifier')
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
root, _ = get_resource(args.identifier)
with publication_lock(root):
    path = root / 'metadata.json'
    before = path.read_bytes()
    metadata = read_json(path)
    files = (root / metadata.get('files_dir', 'files')).resolve()
    if not files.is_relative_to(root.resolve()):
        raise ValueError('files_dir escapes resource')
    manifest = files / 'narrativeos-resource.json'
    if not manifest.is_file():
        raise ValueError('No manifest: refusing to infer capabilities')
    desired = resource_capabilities(files)
    print(json.dumps({'id': args.identifier, 'before': metadata.get('capabilities', []),
                      'after': desired, 'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
                      'apply': args.apply}))
    if args.apply and metadata.get('capabilities') != desired:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = root / ('metadata.capabilities-backup-' + stamp + '.json')
        with backup.open('xb') as output:
            output.write(before)
        if path.read_bytes() != before:
            raise RuntimeError('Metadata changed; refusing to overwrite')
        metadata['capabilities'] = desired
        write_json(path, metadata)
        assert read_json(path) == metadata
        print('APPLIED; backup=' + backup.name)
    else:
        print('UNCHANGED')
