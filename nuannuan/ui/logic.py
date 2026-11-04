"""Operation grouping and editable flow data for the desktop pages."""
import copy

from nuannuan.routes.model import RouteError

OPERATION_GROUPS = {
    '幻境与奖励': ['检查活跃能量', '每周幻境', '素材激化', '祝福闪光幻境', '魔物试炼', '奇迹之冠', '家园日常'],
    '采集与能力': ['钓鱼', '家园钓星', '清洁动物', '花套捕虫', '芳间巡游', '变大', '变小', '开启化万相',
                  '械控注入', '械控抽取', '万物交响'],
    '游戏与界面': ['页面跳转', '进入游戏', '切换账号', '关闭游戏'],
}


def operation_fields(name):
    return {'页面跳转': ('目标页面',), '切换账号': ('账号显示名称',)}.get(name, ())


class FlowSteps:
    def __init__(self, items=None):
        if not isinstance(items or [], list): raise RouteError('流程需要步骤列表')
        self.items = []
        for item in items or []:
            if not isinstance(item, dict) or item.get('type') not in {'path', 'macro'} or not isinstance(item.get('script_name'), str):
                raise RouteError('流程步骤类型或名称无效')
            self.items.append({**copy.deepcopy(item), 'enabled': bool(item.get('enabled', True))})

    def add(self, kind, name):
        if kind not in {'path', 'macro'} or not name: raise RouteError('请选择有效的路线或宏')
        if len(self.items) >= 100: raise RouteError('一个流程最多 100 步')
        self.items.append({'type': kind, 'script_name': name, 'enabled': True})

    def move(self, row, delta):
        target = row+delta
        if 0 <= row < len(self.items) and 0 <= target < len(self.items):
            self.items[row], self.items[target] = self.items[target], self.items[row]

    def remove(self, rows):
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self.items): self.items.pop(row)

    def validate(self, allow_empty=False):
        from nuannuan.routes.scripts import ScriptRunner
        if not self.items and allow_empty: return []
        ScriptRunner(None).validate_flow(self.items)
        return copy.deepcopy(self.items)
