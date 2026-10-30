import json
import math
import time
import uuid
from datetime import datetime
from pathlib import Path

from ok import BaseTask, TriggerTask

from nuannuan.assist import AssistGate
from nuannuan.config import KEYS_NAME, ROUTE_OPTIONS_NAME, ROOT
from nuannuan.daily import AutomationError, DailyRunner
from nuannuan.runtime import RuntimePort


def report_folder():
    return ROOT / 'logs/runs' / f'{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}'


def settings(task):
    return dict(task.get_global_config(KEYS_NAME))


def write_report(task, folder, started, results, scope):
    report = {'started_at': started, 'finished_at': datetime.now().astimezone().isoformat(),
              'results': results,
              'all_succeeded': bool(results) and all(r['status'] not in {'failed', 'partial'} for r in results),
              'scope': scope}
    path = folder / 'report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    task.info_set('运行报告', str(path))
    (ROOT / 'logs/latest_run.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def execute_route(port, name):
    from nuannuan.navigation import RouteRunner
    from nuannuan.route_runtime import RouteRuntime
    from nuannuan.routes import RouteCatalog
    route = RouteCatalog().get(name)
    runtime = RouteRuntime(port, allow_chat=port.allow_chat)
    result = RouteRunner(runtime, max_seconds=port.route_seconds).run(route)
    return {'name': route.name, 'status': 'succeeded', **result}


class DailyTask(BaseTask):
    action = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from nuannuan.daily_workflow import DAILY_DEFAULTS
        from nuannuan.routes import RouteCatalog
        self.name = '每日任务'
        self.description = ('按奇想盒顺序：挖掘 → 家园 → 周本 → 心愿 → 结晶 → 星海 → 奇迹之冠 → 奇迹之旅；'
                            '可接续跑图，最后执行所选收尾操作。')
        self.default_config = dict(DAILY_DEFAULTS)
        choices = [row['name'] for row in RouteCatalog().inventory() if row['ready']]
        self.config_type = {'运行模式': {'type': 'drop_down', 'options': ['自动执行', '只识别']},
                            '接续跑图路线': {'type': 'drop_down', 'options': choices}}
        self.config_description = {'每日结束后跑图': '每日正常结束后运行所选路线；只识别、取消或执行失败时不接续。',
                                   '奇迹之旅奖励': '先检查旅行任务和旅行秘宝，仅领取有待领取奖励的页面；无奖励或状态不明时跳过。',
                                   '朝夕心愿': '识别任务卡后执行，只有未完成的拍照任务才会拍照。'}
        self.support_schedule_task = True
        from nuannuan.extra_daily import EXTRA_SETTINGS
        self.global_config_names = [KEYS_NAME, ROUTE_OPTIONS_NAME, EXTRA_SETTINGS]

    def load_config(self):
        if self.__class__ is DailyTask:
            from ok.util.config import Config
            from nuannuan.daily_workflow import migrate_daily_file
            migrate_daily_file(Path(Config.config_folder) / 'DailyTask.json')
        super().load_config()

    def _port(self, folder=None):
        port = RuntimePort(self, folder or report_folder(), settings(self))
        config = self.config or self.default_config
        port.allow_chat = config.get('允许聚会聊天', False)
        port.route_seconds = float(config.get('单条路线最大分钟', 20)) * 60
        port.execute_objectives = config.get('运行模式', '自动执行') != '只识别'
        port.route_options = dict(self.get_global_config(ROUTE_OPTIONS_NAME))
        from nuannuan.extra_daily import EXTRA_SETTINGS
        port.extra_options = dict(self.get_global_config(EXTRA_SETTINGS))
        return port

    def validate_config(self, key, value):
        if key == '单条路线最大分钟':
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 1 <= value <= 120:
                return '请输入 1 至 120 分钟'

    def reset_to_start(self):
        # Reuse the same recovery baseline for repeated task runs.
        port = self._port(getattr(self, 'artifact_directory', None))
        DailyRunner(port).recover_home()

    def verify_start_state(self):
        if not self._port(getattr(self, 'artifact_directory', None)).exists('IconPageMainFeature'):
            raise AutomationError('未确认游戏大世界主界面')
        return True

    def run(self):
        self.info.clear()
        folder = report_folder()
        port = self._port(folder)
        key_values = settings(self)
        keys = {'photo': key_values['拍照'], 'calendar': key_values['奇想日历'],
                'pass': key_values['奇迹之旅'], 'interaction': key_values['交互']}
        from nuannuan.daily_workflow import DailyWorkflow
        from nuannuan.extra_daily import ExtraDaily
        port.run_daily_action = lambda action: (DailyRunner(port, keys).run_one(action) if action in DailyRunner.LABELS
                                                else ExtraDaily(port, port.extra_options).run(action))
        def validate_follow_route(name):
            from nuannuan.route_runtime import RouteRuntime
            from nuannuan.routes import RouteCatalog
            RouteRuntime(port, allow_chat=port.allow_chat).preflight(RouteCatalog().get(name))
        port.validate_follow_route = validate_follow_route
        port.run_route = lambda name: execute_route(port, name)
        workflow = DailyWorkflow(port)
        started = datetime.now().astimezone().isoformat()
        results = []
        try:
            results = workflow.run(self.config)
            for result in results:
                self.info_set(result['name'], result['message'])
                for item in result.get('unsupported', []):
                    self.info_set(f'{result["name"]} · 未执行 {item["slot"] + 1}',
                                  f'{item["text"] or "文字未识别"}：{item["reason"]}')
                for item in result.get('attempts', []):
                    if item['status'] == 'failed':
                        self.info_set(f'{result["name"]} · 未确认 {item["slot"] + 1}', item['message'])
            failures = [r for r in results if r['status'] in {'failed', 'partial'}]
            if failures:
                raise AutomationError(f'{len(failures)} 个项目未完成，详情见任务信息和运行报告')
        finally:
            port.release_inputs()
            write_report(self, folder, started, workflow.results,
                         '每日统一流程：按识别结果执行；满足接续条件时运行所选路线')
            if getattr(port,'request_exit_after_report',False):
                from ok.core.events import communicate
                communicate.quit.emit()


class RouteTask(DailyTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from nuannuan.routes import RouteCatalog
        self.name = '选择路线自动跑图'
        self.description = '传送至路线起点，通过小地图视觉定位逐点移动；卡住、低置信度或超时会停止。'
        choices = [row['name'] for row in RouteCatalog().inventory() if row['ready']]
        self.default_config = {'路线名称': '星海拾光_更改音乐' if '星海拾光_更改音乐' in choices else next(iter(choices), ''),
                               '允许聚会聊天': False, '单条路线最大分钟': 20}
        self.config_type = {'路线名称': {'type': 'drop_down', 'options': choices}}

    def run(self):
        self.info.clear()
        folder = report_folder()
        port = self._port(folder)
        started = datetime.now().astimezone().isoformat()
        results = []
        try:
            result = execute_route(port, self.config['路线名称'])
            results.append(result)
            self.info_set('跑图结果', result['message'])
            if result.get('status') in {'partial','failed'}:
                raise AutomationError(result['message'])
        except AutomationError as error:
            if not results: results.append({'name': self.name, 'status': 'failed', 'message': str(error)})
            raise
        finally:
            write_report(self, folder, started, results, '以视觉位置确认路线点位；资源任务以任务卡复核为准')


class OperationTask(DailyTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from nuannuan.tool_runner import TOOLS
        from nuannuan.game_tools import PAGES
        from nuannuan.routes import RouteCatalog
        catalog = RouteCatalog()
        self.name = '操作执行器'
        self.description = '承接常用操作和脚本管理页面的动作。'
        self.visible = False
        self.support_schedule_task = False
        self.default_config = {'工具功能': '检查活跃能量', '宏名称': next(iter(catalog.macros), ''),
                               '流程JSON': '[]', '录制秒数': 20, '录制名称': '我的录制',
                               '录制参考路线': '星海拾光_更改音乐', '目标页面': '主界面', '账号显示名称': '', '启动程序路径': ''}
        self.config_type = {'工具功能': {'type': 'drop_down', 'options': TOOLS},
                            '宏名称': {'type': 'drop_down', 'options': list(catalog.macros)},
                            '录制秒数': {'min': 1, 'max': 120},
                            '录制参考路线': {'type': 'drop_down', 'options': list(catalog.records)},
                            '目标页面': {'type': 'drop_down', 'options': PAGES}}

    def load_config(self):
        from ok.util.config import Config
        old = Path(Config.config_folder)/'ToolsTask.json'
        new = Path(Config.config_folder)/'OperationTask.json'
        if old.exists() and not new.exists():
            new.write_bytes(old.read_bytes())
        super().load_config()

    def reset_to_start(self):
        if self.config['工具功能'] in {'进入游戏', '切换账号'}:
            return  # Main run observes the recognized login state itself.
        super().reset_to_start()

    def verify_start_state(self):
        if self.config['工具功能'] in {'进入游戏', '切换账号'}:
            self._port(getattr(self, 'artifact_directory', None)).fresh()
            return True
        return super().verify_start_state()

    def run(self):
        from nuannuan.tool_runner import run_tool
        self.info.clear()
        folder = report_folder()
        port = self._port(folder)
        started = datetime.now().astimezone().isoformat()
        results = []
        options = getattr(self, '_pending_options', None) or dict(self.config)
        self._pending_options = None
        self.info_set('当前操作', options['工具功能'])
        self.info_set('运行状态', '执行中')
        try:
            result = run_tool(port, options)
            results.append({'name': options['工具功能'], **result})
            self.info_set('操作结果', result['message'])
            if result['status'] in {'failed', 'partial'}:
                raise AutomationError(result['message'])
            self.info_set('运行状态', '已完成')
        except (AutomationError, ValueError, OSError) as error:
            self.info_set('运行状态', '失败')
            self.info_set('操作结果', str(error))
            if not results:
                results.append({'name': options['工具功能'], 'status': 'failed', 'message': str(error)})
            port.evidence('tool_failed')
            raise
        finally:
            if self.info.get('运行状态') == '执行中': self.info_set('运行状态', '已停止')
            port.release_inputs()
            write_report(self, folder, started, results, '原应用功能迁移；以可见页面、奖励与任务进度确认结果')


class CaptureCheckTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = '检查游戏画面'
        self.description = '保存当前游戏截图，检查分辨率、黑屏以及主界面识别；此任务不发送游戏按键。'

    def run(self):
        self.info.clear()
        folder = report_folder()
        port = RuntimePort(self, folder, {})
        frame = port.fresh()
        port.evidence('game_capture')
        self.info_set('画面尺寸', f'{frame.shape[1]}×{frame.shape[0]}')
        self.info_set('主界面识别', '通过' if port.match('IconPageMainFeature', frame) else '当前未识别到主界面')
        self.info_set('截图目录', str(folder))


class AssistTask(TriggerTask):
    mode = 'pickup'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_config.update({'操作间隔（秒）': 0.6})
        self.config_description = {'操作间隔（秒）': '两次交互之间至少间隔的秒数，最小 0.25 秒。'}
        self.global_config_names = [KEYS_NAME]
        self.trigger_interval = 0.15
        self._gate = None
        self._last_observed = 0
        self._pending = None

    def validate_config(self, key, value):
        if key == '操作间隔（秒）':
            try:
                number = float(value)
                if not math.isfinite(number) or not 0.25 <= number <= 10:
                    return '请输入 0.25 到 10 秒之间的间隔'
            except (TypeError, ValueError):
                return '请输入有效数字'

    def trigger(self):
        self._pending = None
        from nuannuan.run_control import assist_allowed
        if not assist_allowed(self.executor): return False
        cooldown = float(self.config['操作间隔（秒）'])
        now = time.monotonic()
        if self._gate is None or self._gate.cooldown != cooldown:
            self._gate = AssistGate(cooldown, pickup_enabled=self.mode == 'pickup', dialogue_enabled=self.mode == 'dialogue')
        if now - self._last_observed > 1.5:
            self._gate.reset()
        self._last_observed = now
        try:
            port = RuntimePort(self, ROOT / 'logs/assist', settings(self))
            frame = port.fresh()
            dialogue = bool(port.match('IconSkipDialog', frame))
            home = bool(port.match('IconPageMainFeature', frame))
            pickup = bool(port.match('IconPickupFeature', frame)) if home and not dialogue else False
            self._pending = self._gate.decide(home, pickup, dialogue, now)
        except AutomationError:
            self._gate.reset()
        return self._pending is not None

    def run(self):
        action, self._pending = self._pending, None
        from nuannuan.run_control import assist_allowed
        if not assist_allowed(self.executor): return
        backend = self.executor.interaction
        if hasattr(backend, 'resume_helpers'): backend.resume_helpers()
        if action != self.mode:
            return
        port = RuntimePort(self, ROOT / 'logs/assist', settings(self))
        frame = port.fresh()
        dialogue = bool(port.match('IconSkipDialog', frame))
        if action == 'dialogue' and not dialogue:
            return
        if action == 'pickup' and (dialogue or not port.match('IconPageMainFeature', frame)
                                   or not port.match('IconPickupFeature', frame)):
            return
        self.send_key(settings(self)['交互'], after_sleep=0.1)
        self.info_add('交互次数')
        self.info_set('最近触发', datetime.now().strftime('%H:%M:%S'))

    def disable(self):
        if self._gate:
            self._gate.reset()
        self._pending = None
        super().disable()


class AutoPickupTask(AssistTask):
    mode = 'pickup'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = '自动拾取'
        self.description = '在大世界主界面连续确认拾取标识后按交互键；不会自动移动或选择 NPC 对话。'


class AutoDialogueTask(AssistTask):
    mode = 'dialogue'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = '对话跳过'
        self.description = '连续确认跳过标识后按交互键，推进可跳过对话；选项需手动选择。'
