"""Pin original Whimbox map data implementation; keep changes explicit and auditable."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT/'references/whimbox-upstream/whimbox/map/mask'
    target = ROOT/'nuannuan/pearpal/_pearpal'
    target.mkdir(exist_ok=True)
    (target/'__init__.py').write_text('"""Whimbox 3.1.1 PearPal provider, GPL-3.0; see SOURCE.json."""\n', encoding='utf-8')
    records = []
    for name in ['models.py', 'pearpal_auth.py', 'pearpal_regions.py', 'pearpal_provider.py', 'pearpal_debug.py']:
        raw = (source/name).read_bytes()
        text = raw.decode('utf-8')
        changes = []
        if name == 'pearpal_provider.py':
            text = text.replace('from whimbox.common.logger import logger', 'import logging\nlogger = logging.getLogger(__name__)')
            changes.append('Use local Python logging instead of Whimbox runtime logger')
        if name == 'pearpal_debug.py':
            start = text.index('def default_cache_dir()')
            end = text.index('\ndef decode_snappy_json', start)
            text = text[:start]+"def default_cache_dir() -> Path:\n    from nuannuan.config import ROOT\n    return ROOT / '.cache/pearpal'\n\n"+text[end:]
            changes.append('Store public response cache in project .cache/pearpal')
        (target/name).write_text(text, encoding='utf-8', newline='')
        records.append({'file': name, 'source_sha256': hashlib.sha256(raw).hexdigest(),
                        'adapted_sha256': hashlib.sha256((target/name).read_bytes()).hexdigest(), 'changes': changes})
    (target/'SOURCE.json').write_text(json.dumps({'repository': 'https://github.com/nikkigallery/Whimbox',
        'commit': '2a75df818c28e9f4af2b3e81c0db12d7694a20d1', 'license': 'GPL-3.0', 'files': records}, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__': main()
