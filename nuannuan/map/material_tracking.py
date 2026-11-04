"""Whimbox's ordered ability/tracking/capture flow, with observed loot counts."""
import json
import re
import time

from nuannuan.config import ROOT
from nuannuan.core.text import count_option, require


def material_info(name):
    entries = json.loads((ROOT/'assets/materials.json').read_text(encoding='utf-8'))
    entry = entries.get(name)
    require(entry is not None and entry.get('track'), f'材料不支持精确追踪：{name}')
    require(entry['type'] in {'insect', 'animal'}, '此追踪流程仅支持捕虫和动物清洁')
    return entry


def observed_quantity(name, text, before=''):
    compact = re.sub(r'\s+', '', text or '')
    if not compact or compact == re.sub(r'\s+', '', before or ''):
        return 0
    match = re.search(re.escape(name)+r'(?:[×xX*](\d+))?', compact)
    return int(match[1]) if match and match[1] is not None else (1 if match else 0)


class MaterialTracker:
    def __init__(self, port, *, max_seconds=60):
        self.port, self.max_seconds = port, max_seconds

    def run(self, name, ability, expected_count=1):
        expected_count = count_option(expected_count, '当前采集点目标数量', 100)
        info = material_info(name)
        require(ability == {'insect': '捕虫', 'animal': '动物清洁'}[info['type']], '材料与能力不匹配')
        quantity, missing, active = 0, 0, 0
        status, reason = 'partial', '采集达到本次时间上限'
        try:
            self.port.stage('切换能力')
            self.port.select_ability(ability)
            self.port.stage('开启材料追踪')
            self.port.enable_tracking(name)
            self.port.stage('开始前往采集')
            deadline = time.monotonic()+self.max_seconds
            before = self.port.reward_text()
            self.port.begin_capture()
            for _ in range(600):
                if time.monotonic() >= deadline:
                    break
                observation = self.port.observe()
                if observation['active']:
                    missing = 0
                    self.port.stop_forward()
                    active += 1
                    if active >= 2:
                        self.port.release_capture()
                        self.port.finish_capture()
                        self.port.sleep(.5)
                        text = self.port.reward_text()
                        gained = observed_quantity(name, text, before)
                        if not gained:
                            reason = '采集动作结束，但未确认新的目标材料获得文本'
                            break
                        quantity += gained
                        self.port.evidence('material_reward')
                        self.port.clear_marker()
                        if quantity >= expected_count:
                            status, reason = 'succeeded', '已确认目标数量'
                            break
                        before = text
                        active = 0
                        self.port.sleep(.8)
                        self.port.begin_capture()
                else:
                    active = 0
                    marker = observation['marker']
                    if marker is None:
                        self.port.stop_forward()
                        missing += 1
                        if missing >= 6:
                            status = 'skipped' if not quantity else 'partial'
                            reason = '附近已经没有追踪的材料了'
                            self.port.stage(reason)
                            break
                    else:
                        missing = 0
                        self.port.approach(marker)
                self.port.sleep(.1)
            return {'status': status, 'materials': {name: quantity}, 'missing_frames': missing,
                    'message': f'{reason}；已确认获得{name} × {quantity}'}
        finally:
            self.port.release_all()
