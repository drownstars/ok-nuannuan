"""Dispatch the unified tools task to shared implementations."""
import json

from nuannuan.daily.runner import DailyRunner
from nuannuan.core.text import require
from nuannuan.daily.extra import ExtraDaily
from nuannuan.routes.scripts import ScriptRunner, record_macro, record_route

EXTRA_ACTIONS = {'检查活跃能量': 'energy_check', '每周幻境': 'weekly', '素材激化': 'realm',
                 '祝福闪光幻境': 'bless', '魔物试炼': 'monster', '奇迹之冠': 'crown', '家园日常': 'home_daily'}
ABILITY_ACTIONS = ['清洁动物', '花套捕虫', '芳间巡游', '变大', '变小', '开启化万相', '械控注入', '械控抽取', '万物交响']
TOOLS = [*EXTRA_ACTIONS, '钓鱼', '家园钓星', '宏 / 乐谱', '自定义流程', '录制宏', '录制路线',
         '页面跳转', '进入游戏', '切换账号', '关闭游戏', *ABILITY_ACTIONS]


def run_tool(port, options):
    action = options['工具功能']
    require(action in TOOLS, '未知工具功能')
    if action in EXTRA_ACTIONS:
        return ExtraDaily(port, port.extra_options).run(EXTRA_ACTIONS[action])
    if action in {'进入游戏', '切换账号', '关闭游戏', '页面跳转'}:
        from nuannuan.daily.game_tools import GameTools
        tools = GameTools(port)
        if action == '进入游戏': return tools.enter()
        if action == '切换账号': return tools.change_account(options['账号显示名称'])
        if action == '关闭游戏': return tools.close()
        tools.goto(options['目标页面'])
        return {'status': 'succeeded', 'message': f'已确认页面：{options["目标页面"]}'}
    if action == '自定义流程':
        items = json.loads(options['流程JSON'])
        return ScriptRunner(port).flow(items)
    if action in {'录制宏', '录制路线'}:
        duration = options['录制秒数']
        require(type(duration) is int and 1 <= duration <= 120, '录制秒数需为 1 至 120 的整数')
        name = options['录制名称'].strip()
        require(bool(name), '请填写录制名称')
        if action == '录制宏':
            return record_macro(port, duration, name)
        DailyRunner(port).recover_home()
        return record_route(port, options['录制参考路线'], duration, name)
    if action == '宏 / 乐谱':
        return ScriptRunner(port).macro(options['宏名称'])
    DailyRunner(port).recover_home()
    if action in {'钓鱼', '家园钓星'}:
        from nuannuan.daily.gathering import FishingRunner, ability_action
        if action == '钓鱼' and port.extra_options.get('钓鱼前万物交响'):
            ability_action(port, '万物交响')
        return FishingRunner(port).run(casts=port.extra_options['钓鱼抛竿次数'], home=action == '家园钓星')
    from nuannuan.daily.gathering import ability_action
    return ability_action(port, action)
