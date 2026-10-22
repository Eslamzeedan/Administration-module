"""Compare two JSON snapshots captured while application writes are paused."""
import json
from pathlib import Path
import sys


def load(filename):
    content = Path(filename).read_text(encoding='utf-8-sig')
    begin, end = content.find('{'), content.rfind('}')
    if begin < 0 or end < begin:
        raise ValueError('Snapshot output contains no JSON object')
    return json.loads(content[begin:end+1])


def compare(before, after):
    errors = []
    for dt, expected in before['legacy'].items():
        if after['legacy'].get(dt) != expected:
            errors.append(dt + ': count or original-field checksum changed')
    if before['permissions'] != after['permissions']:
        errors.append('Existing DocPerm/Custom DocPerm changed; investigate before release')
    old = before['workspace'].get('EuP Administration')
    if old:
        new = after['workspace'].get('EuP Administration')
        if not new or new['content_sha256'] != old['content_sha256'] or new['shortcuts'] != old['shortcuts']:
            errors.append('Original workspace content or shortcuts changed')
    if 'EuP Administration v2' not in after['workspace']:
        errors.append('Source-backed v2 workspace is missing')
    return errors

if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python tools/compare_snapshots.py before.json after.json')
    errors = compare(load(sys.argv[1]),load(sys.argv[2]))
    print('\n'.join(errors) if errors else 'PASS: legacy records, permissions and existing workspace preserved; v2 workspace present')
    raise SystemExit(1 if errors else 0)
