"""Copy supplied route/map data with provenance, without executing reference code."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from nuannuan.routes.model import RouteCatalog

    assets_source = ROOT / 'whimbox_app/python-embedded/Lib/site-packages/whimbox/assets'
    route_root = ROOT / 'routes'
    map_root = ROOT / 'assets/maps'
    route_root.mkdir(exist_ok=True)
    map_root.mkdir(parents=True, exist_ok=True)
    manifest = {'sources': []}
    library_state_path = route_root / '.library/state.json'
    library_state = json.loads(library_state_path.read_text(encoding='utf-8')) if library_state_path.exists() else {}

    def copy(source, target, payload=None, notes=None):
        original = source.read_bytes()
        output = original if payload is None else payload
        if target.parent == route_root and target.name in library_state.get('managed_files', []) and target.exists():
            output = target.read_bytes()
            notes = [*(notes or []), 'Preserved user-managed route changes']
        if target.exists() and target.read_bytes() not in (original, output):
            raise ValueError(f'Refusing to overwrite changed local data: {target}')
        target.write_bytes(output)
        manifest['sources'].append({'source': source.relative_to(ROOT).as_posix(),
                                    'target': target.relative_to(ROOT).as_posix(),
                                    'sha256': hashlib.sha256(original).hexdigest(),
                                    'target_sha256': hashlib.sha256(output).hexdigest(), 'notes': notes or []})

    for source in (ROOT / 'whimbox_app/scripts').glob('*.json'):
        if source.name in library_state.get('deleted_sources', []):
            continue
        data = json.loads(source.read_text(encoding='utf-8'))
        notes = []
        if data['info']['name'] == '星海拾光_化身动物' and not data.get('loops'):
            for identity, point in enumerate(data['points']):
                point['id'] = identity
            data['points'][-1].update({'action': 'TRANS_ANIMAL', 'action_params': '3'})
            notes = ['Renumber duplicate point IDs in reference route',
                     'Perform three animal interactions at the reference destination']
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8') if notes else None
        copy(source, route_root / source.name, payload, notes)
    for prefix in ['w01_v12', 'w14000000_v2', 'w8000001_v1', 'w4020034']:
        for scale in ['05x', '0125x']:
            filename = f'{prefix}_luma_{scale}.png'
            copy(assets_source / 'imgs/Maps' / filename, map_root / filename)
    copy(assets_source / 'checkpoints.json', map_root / 'checkpoints.json')
    catalog = RouteCatalog(route_root)
    manifest['inventory'] = catalog.inventory()
    manifest['macros'] = list(catalog.macros)
    (route_root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Imported {len(catalog.records)} routes and {len(catalog.macros)} macros; '
          f'{sum(row["ready"] for row in manifest["inventory"])} routes pass validation.')


if __name__ == '__main__':
    main()
