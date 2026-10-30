"""Validated JSON library operations with history, aliases, and non-destructive imports."""
import copy
import json
import os
import uuid
from pathlib import Path

from nuannuan.config import ROOT
from nuannuan.routes import Route, RouteCatalog, RouteError, validate_macro


class RouteStore:
    def __init__(self, root=None):
        self.root = Path(root or ROOT / 'routes').resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta = self.root / '.library'
        if self.meta.is_symlink():
            raise RouteError('路线管理目录不能是符号链接')
        self.meta.mkdir(exist_ok=True)

    def state(self):
        path = self.meta / 'state.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
            'aliases': {}, 'deleted_sources': [], 'managed_files': []}

    @staticmethod
    def encode(data):
        try:
            return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
        except (TypeError, ValueError) as error:
            raise RouteError('路线包含无法保存的数值或结构') from error

    def write(self, path, payload):
        path = Path(path)
        if not path.resolve().is_relative_to(self.root) or path.is_symlink():
            raise RouteError('写入路径必须位于本地路线库内')
        temporary = path.with_name(f'.{uuid.uuid4().hex}.tmp')
        temporary.write_bytes(payload)
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _save_state(self, state):
        self.write(self.meta / 'state.json', self.encode(state))

    def _path(self, name):
        catalog = RouteCatalog(self.root)
        resolved = catalog.resolve_name(name)
        path = catalog.paths.get(resolved)
        if path is None:
            raise RouteError(f'路线或宏不存在：{name}')
        if path.is_symlink() or path.resolve().parent != self.root:
            raise RouteError('不能修改路线库外的文件')
        return path, resolved, catalog

    def get_data(self, name):
        path, _, _ = self._path(name)
        return json.loads(path.read_text(encoding='utf-8'))

    @staticmethod
    def _unique(name, names):
        candidate, index = name, 2
        while candidate in names:
            candidate = f'{name}（导入{index}）'
            index += 1
        names.add(candidate)
        return candidate

    def import_files(self, paths):
        records = []
        for path in paths:
            try:
                data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
            except (OSError, ValueError) as error:
                raise RouteError(f'无法读取导入文件：{Path(path).name}') from error
            if isinstance(data, dict) and 'routes' in data:
                if not isinstance(data['routes'], list) or not isinstance(data.get('macros', []), list):
                    raise RouteError('导入包需要 routes 和 macros 列表')
                records.extend(data.get('macros', []))
                records.extend(data['routes'])
            else:
                records.append(data)
        return self.import_records(records)

    def import_records(self, records):
        if not records or len(records) > 200:
            raise RouteError('一次可导入 1 至 200 条路线 / 宏')
        records = copy.deepcopy(records)
        catalog = RouteCatalog(self.root)
        state = self.state()
        names = set(catalog.records) | set(catalog.macros) | set(catalog.aliases)
        existing = {**catalog.records, **catalog.macros}
        prepared, imported, renamed_macros = [], [], {}
        for data in records:
            if not isinstance(data, dict) or not isinstance(data.get('info'), dict):
                raise RouteError('导入文件缺少基本信息')
            name = data['info'].get('name')
            if not isinstance(name, str) or not name.strip():
                raise RouteError('导入路线 / 宏名称不能为空')
        for macro in [data for data in records if 'points' not in data]:
            validate_macro(macro)
            name = macro['info']['name']
            if existing.get(name) == macro:
                renamed_macros[name] = name
                imported.append(name)
                continue
            new_name = self._unique(name, names)
            renamed_macros[name] = new_name
            macro['info']['name'] = new_name
            prepared.append(macro)
            imported.append(new_name)
        macros = {**catalog.macros, **{data['info']['name']: data for data in prepared}}
        for data in [data for data in records if 'points' in data]:
            for point in data.get('points', []) if isinstance(data.get('points'), list) else []:
                if isinstance(point, dict) and point.get('action') in {'MACRO', 'MINIGAME'}:
                    point['action_params'] = renamed_macros.get(point.get('action_params'), point.get('action_params'))
            name = data['info']['name']
            if existing.get(name) == data:
                imported.append(name)
                continue
            data['info']['name'] = self._unique(name, names)
            try:
                Route.from_dict(data, macros)
            except (TypeError, ValueError, KeyError, AttributeError) as error:
                raise RouteError(f'导入路线结构无效：{name}') from error
            prepared.append(data)
            imported.append(data['info']['name'])
        # Validate the entire batch and encode everything before creating any route files.
        outputs = [(self.root / f'local-{uuid.uuid4().hex}.json', self.encode(data)) for data in prepared]
        created = []
        try:
            for path, payload in outputs:
                self.write(path, payload)
                created.append(path)
            state['managed_files'] = list(set(state.get('managed_files', [])) | {p.name for p in created})
            self._save_state(state)
        except BaseException:
            for path in created:
                path.unlink(missing_ok=True)
            raise
        return imported

    def _archive(self, path):
        history = self.meta / 'history'
        if history.is_symlink():
            raise RouteError('路线历史目录不能是符号链接')
        history.mkdir(exist_ok=True)
        target = history / f'{uuid.uuid4().hex}-{path.name}'
        self.write(target, path.read_bytes())
        return target

    def update(self, name, data):
        path, resolved, catalog = self._path(name)
        data = copy.deepcopy(data)
        if not isinstance(data, dict) or not isinstance(data.get('info'), dict):
            raise RouteError('路线结构无效')
        new_name = data['info'].get('name')
        if not isinstance(new_name, str) or not new_name.strip():
            raise RouteError('路线名称不能为空')
        if new_name != resolved and new_name in (set(catalog.records) | set(catalog.macros) | set(catalog.aliases)):
            raise RouteError('该路线名称已被使用')
        if 'points' not in data:
            raise RouteError('此编辑入口只修改跑图路线，不能修改依赖宏')
        data['info']['origin_name'] = catalog.records[resolved]['info'].get('origin_name', resolved)
        try:
            Route.from_dict(data, catalog.macros)
        except (TypeError, ValueError, KeyError, AttributeError) as error:
            raise RouteError('路线结构无效') from error
        payload = self.encode(data)
        old = path.read_bytes()
        self._archive(path)
        state = self.state()
        if new_name != resolved:
            state['aliases'][resolved] = new_name
        state['managed_files'] = list(set(state.get('managed_files', [])) | {path.name})
        try:
            self.write(path, payload)
            self._save_state(state)
        except BaseException:
            self.write(path, old)
            raise
        return new_name

    def delete(self, name):
        path, resolved, catalog = self._path(name)
        if resolved in catalog.macros:
            users = [route_name for route_name, data in catalog.records.items()
                     if any(point.get('action') in {'MACRO', 'MINIGAME'} and point.get('action_params') == resolved
                            for point in data.get('points', []) if isinstance(point, dict))]
            if users:
                raise RouteError('此宏仍被路线引用，不能删除：' + '、'.join(users))
        self._archive(path)
        old_state = self.state()
        state = copy.deepcopy(old_state)
        state['deleted_sources'] = list(set(state.get('deleted_sources', [])) | {path.name})
        self._save_state(state)
        try:
            path.unlink()
        except BaseException:
            self._save_state(old_state)
            raise
