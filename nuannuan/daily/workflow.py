"""One daily entry point; conditional photo remains inside recognized objectives."""
import json
import os
import uuid
from pathlib import Path

from nuannuan.core.errors import AutomationError

DAILY_DEFAULTS = {
    '朝夕心愿': True, '星海拾光': True, '美鸭梨挖掘': True, '奇迹之旅奖励': True,
    '运行模式': '自动执行', '允许聚会聊天': False, '单条路线最大分钟': 20,
    '每日结束后跑图': False, '接续跑图路线': '星海拾光_更改音乐',
}


def migrate_daily_options(old):
    result = {key: old.get(key, default) for key, default in DAILY_DEFAULTS.items()}
    if '朝夕心愿' not in old and '自动朝夕心愿' in old:
        result['朝夕心愿'] = old['自动朝夕心愿']
    if '奇迹之旅奖励' not in old and '奇迹之旅已有奖励' in old:
        result['奇迹之旅奖励'] = old['奇迹之旅已有奖励']
    return {**{key: value for key, value in old.items() if key.startswith('_')}, **result}


def migrate_daily_file(path):
    path = Path(path)
    if not path.exists():
        return
    old = json.loads(path.read_text(encoding='utf-8'))
    migrated = migrate_daily_options(old)
    if migrated == old:
        return
    backup = path.parent / 'migrations'
    backup.mkdir(parents=True, exist_ok=True)
    (backup / f'DailyTask-before-auto-daily-{uuid.uuid4().hex}.json').write_bytes(path.read_bytes())
    temporary = path.with_suffix('.migration.tmp')
    temporary.write_text(json.dumps(migrated, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


class DailyWorkflow:
    def __init__(self, port):
        self.port = port
        self.results = []

    def progress(self, label, state, message=''):
        notify = getattr(self.port, 'workflow_progress', None)
        if notify:
            notify(label, state, message)

    def step(self, label, callback):
        self.progress(label, 'running')
        try:
            result = {**callback(), 'name': label}
        except AutomationError as error:
            result = {'name': label, 'status': 'failed', 'message': str(error)}
        except BaseException:
            self.progress(label, 'cancelled', '执行已中断，未继续后续步骤')
            raise
        self.results.append(result)
        self.progress(label, result['status'], result['message'])
        return (result['status'] == 'failed' or (result['status'] == 'partial' and not result.get('unsupported'))
                or any(attempt['status'] == 'failed' for attempt in result.get('attempts', [])))

    def run(self, options):
        self.results = []
        identify = options.get('运行模式') == '只识别'
        automatic = {'enter_game', 'energy_check', 'auto_home', 'auto_weekly', 'auto_crown', 'auto_energy'}
        # Whimbox 3.1.1 DEFAULT_STEP_CONFIG; energy belongs to the wish stage.
        actions = [('进入游戏', 'enter_game'), ('检查活跃能量', 'energy_check'), ('美鸭梨挖掘', 'dig'),
                   ('家园日常', 'auto_home'), ('每周幻境', 'auto_weekly'), ('朝夕心愿', 'auto_wish'),
                   ('活跃能量处理', 'auto_energy'), ('星光结晶收集', 'auto_crystal'),
                   ('星海拾光', 'starsea'), ('奇迹之冠', 'auto_crown'), ('奇迹之旅奖励', 'pass')]
        actions = [(label, action) for label, action in actions
                   if (action in automatic or options.get(label, False) or (action == 'auto_crystal' and options.get('星海拾光')))
                   and (not identify or action in {'auto_wish', 'starsea'})]
        if not actions:
            raise AutomationError('请至少选择一个每日项目；只识别模式需要选择朝夕心愿或星海拾光')
        follow = bool(options.get('每日结束后跑图')) and not identify
        name = options.get('接续跑图路线', '')
        if follow:
            self.port.validate_follow_route(name)
        execution_failed = False
        for label, action in actions:
            failed = self.step(label, lambda action=action: self.port.run_daily_action(action))
            execution_failed |= failed
            if action == 'enter_game' and failed:
                break
        if follow:
            if execution_failed:
                self.results.append({'name': '每日后跑图', 'status': 'skipped', 'message': '每日存在执行失败，未接续跑图'})
            else:
                execution_failed |= self.step(f'每日后跑图 · {name}', lambda: self.port.run_route(name))
        if not identify:
            if execution_failed:
                result = {'name': '每日结束操作', 'status': 'skipped', 'message': '每日存在执行失败，保持游戏供检查'}
                self.results.append(result)
                self.progress(result['name'], result['status'], result['message'])
            else:
                self.step('每日结束操作', lambda: self.port.run_daily_action('finish_daily'))
        return self.results
