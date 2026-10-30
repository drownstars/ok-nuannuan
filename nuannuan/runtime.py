import json
import re
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from ok import Box

from nuannuan.config import ROOT
from nuannuan.daily import AutomationError
from nuannuan.extra_runtime import ExtraRuntimeMixin


def validate_frame(frame):
    if frame is None or frame.ndim != 3 or frame.shape[2] < 3:
        raise AutomationError('未获得游戏画面，请在连接页面选择无限暖暖窗口')
    height, width = frame.shape[:2]
    if width < 1280 or height < 720 or abs(width / height - 16 / 9) > 0.02:
        raise AutomationError('首版识别需要至少 1280×720 的 16:9 游戏窗口')
    if float(np.mean(frame)) < 2:
        raise AutomationError('捕获画面为黑屏，请检查游戏窗口并切换 WGC / BitBlt')


class RuntimePort(ExtraRuntimeMixin):
    def __init__(self, task, artifact_directory: Path, settings: dict):
        self.task = task
        self.artifacts = Path(artifact_directory)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.settings = settings
        self.allow_chat = False
        self.route_seconds = 1200
        self.manifest = json.loads((ROOT / 'assets/manifest.json').read_text(encoding='utf-8'))

    def workflow_progress(self, label, state, message=''):
        captions={'running':'执行中','succeeded':'已确认','skipped':'已跳过','failed':'失败',
                  'partial':'未完全确认','cancelled':'已停止'}
        self.task.info_set('当前步骤',label)
        self.task.info_set(label,captions.get(state,state)+(f' · {message}' if message else ''))
        row={'time':datetime.now().astimezone().isoformat(),'label':label,'state':state,'message':message}
        control = getattr(getattr(self.task, 'executor', None), '_nuannuan_run_control', None)
        if control is not None: control.record(label, state, message)
        with (self.artifacts/'workflow.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')

    def fresh(self):
        frame = self.task.next_frame()
        validate_frame(frame)
        return frame

    def region(self, name, frame):
        x, y, width, height = self.manifest['regions'][name]['bbox']
        sx, sy = frame.shape[1] / 1920, frame.shape[0] / 1080
        return Box(round(x * sx), round(y * sy), max(1, round(width * sx)), max(1, round(height * sy)), name=name)

    def match(self, name, frame):
        options = {'frame': frame, 'use_gray_scale': True,
                   'threshold': 0.88 if name in {'IconPickupFeature', 'IconSkipDialog'} else 0.92}
        if name in {'IconPickupFeature', 'IconSetdownFeature', 'IconTalkFeature'}:
            options['box'] = self.region('AreaPickup', frame)
        if name == 'IconAbilityInsect':
            options['box'] = self.region('AreaAbilityButton', frame)
        return self.task.find_one(name, **options)

    def exists(self, name):
        frame = self.fresh()
        if name in self.manifest['features']:
            return bool(self.match(name, frame))
        if name == 'game_loading':
            if self.match('IconUILoading', frame):
                return True
            # Login and initial loading share the sound icon. Require the
            # recorded loading caption before treating that scene as a wait.
            if not self.match('IconPageLoginFeature', frame):
                return False
            h, w = frame.shape[:2]
            box = Box(round(w*.25), round(h*.82), round(w*.60), round(h*.10), name='游戏加载提示')
            text = ''.join(item.name for item in self.task.ocr(box=box, frame=frame, threshold=.8))
            return '正在进入奇迹大陆' in re.sub(r'\s+', '', text)
        if name == 'reward_popup':
            return bool(self.match('IconClickSkip', frame))
        if name == 'calendar_page':
            return (bool(self.match('ButtonZxxyEntrance', frame))
                    or re.sub(r'\s+', '', self.text('AreaPageTitleFeature', frame)) == '奇想日历')
        if name == 'bigmap_page':
            return bool(self.match('IconUIBigmap', frame) or self.match('IconUIBigmapJoystick', frame))
        if name == 'menu_page':
            return '美鸭梨' in self.text('AreaPageTitleFeature', frame)
        if name == 'dig_page':
            return (bool(self.match('ButtonDigGather', frame))
                    or bool(re.search(r'\d+\s*/\s*\d+', self.text('AreaDigingNumText', frame))))
        if name == 'dig_active':
            if self.match('ButtonDigAgain', frame) or self.match('ButtonDigGather', frame):
                return False
            match = re.search(r'(\d+)\s*/\s*(\d+)', self.text('AreaDigingNumText', frame))
            return bool(match and 0 < int(match[1]) <= int(match[2]))
        if name == 'pass_page':
            return not self.match('IconClickSkip', frame) and '奇迹之旅' in self.text('AreaPageTitleFeature', frame)
        raise ValueError(f'Unknown visual state: {name}')

    def wait(self, name, timeout=6):
        return bool(self.task.wait_until(lambda: self.exists(name), time_out=timeout, settle_time=0.2))

    def key(self, value):
        # Validate a current capture before every input; framework sleep/input also
        # enforce cooperative cancellation and pause handling.
        self.fresh()
        self.task.send_key(value, after_sleep=0.35)

    def click_feature(self, name):
        target = self.match(name, self.fresh())
        if not target:
            raise AutomationError(f'操作前标识消失：{name}')
        self.task.click_box(target, after_sleep=0.4)

    def text(self, region, frame=None):
        frame = self.fresh() if frame is None else frame
        box = self.region(region, frame)
        single_lines = {'AreaPageTitleFeature','AreaZxxyEnergy','AreaWeeklyCountText',
                        'AreaMiraCrownOverview','AreaBigMapMaterialTrackConfirm'}
        factory=getattr(getattr(self.task,'executor',None),'ocr_lib',None)
        if region in single_lines and callable(factory):
            crop=frame[box.y:box.y+box.height,box.x:box.x+box.width]
            if region=='AreaWeeklyCountText':
                crop=crop[:,:max(1,round(crop.shape[1]*.5))]
            result=factory('default')(crop,use_det=False,use_cls=False,use_rec=True)
            return ''.join(text for text,score in zip(result.txts or [],result.scores or []) if score>=.8)
        boxes = self.task.ocr(box=box, frame=frame, threshold=0.65)
        return ''.join(box.name for box in boxes)

    def continue_prompt_visible(self):
        frame=self.fresh()
        h,w=frame.shape[:2]
        box=Box(round(w*.78),round(h*.92),round(w*.22),round(h*.08),name='继续提示')
        return any('空白区域继续' in re.sub(r'\s+','',item.name) for item in self.task.ocr(box=box,frame=frame,threshold=.8))

    def click_text(self, value, region=None, scroll=False):
        for attempt in range(7 if scroll else 3):
            frame = self.fresh()
            box = self.region(region, frame) if region else None
            boxes = self.task.ocr(box=box, frame=frame, threshold=0.7)
            target = next((item for item in boxes if value in re.sub(r'\s+', '', item.name)), None)
            if target:
                self.task.click_box(target, after_sleep=0.5)
                return True
            if scroll and attempt < 6:
                self.task.scroll(box.x + box.width // 2, box.y + box.height // 2, -3 if attempt >= 1 else 8)
            self.sleep(0.4)
        return False

    def claim_wish_rewards(self):
        return self._claim_rewards('wish')

    def _claim_rewards(self, board):
        feature = 'IconZxxyFeature' if board == 'wish' else 'IconXhsgFeature'
        rewards = 'AreaZxxyRewards' if board == 'wish' else 'AreaXhsgRewards'
        count = 0
        for _ in range(5):
            frame = self.fresh()
            if not self.match(feature, frame):
                raise AutomationError('领取奖励前已离开目标任务界面')
            box = self.region(rewards, frame)
            roi = frame[box.y:box.y + box.height, box.x:box.x + box.width]
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, np.array([0, 0, 125]), np.array([30, 255, 255]))
            scale = frame.shape[0] / 1080
            circles = cv2.HoughCircles(mask, cv2.HOUGH_GRADIENT, dp=1, minDist=100 * scale,
                                       param1=60, param2=10, minRadius=max(1, round(30 * scale)),
                                       maxRadius=max(2, round(35 * scale)))
            if circles is None:
                break
            x, y, _ = circles[0, 0]
            self.task.click(round(box.x + x), round(box.y + y), after_sleep=0.5)
            if not self.wait('reward_popup', timeout=4):
                raise AutomationError('点击心愿奖励后未出现奖励结果，已停止领取')
            self.key(self.settings.get('交互', 'f'))
            if not self.wait(feature):
                raise AutomationError('领取奖励后未返回目标任务界面')
            count += 1
        return count

    def click_reference(self, x, y):
        frame = self.fresh()
        self.task.click(round(x * frame.shape[1] / 1920), round(y * frame.shape[0] / 1080), after_sleep=0.35)

    def click_region(self, name):
        frame = self.fresh()
        self.task.click_box(self.region(name, frame), after_sleep=0.4)

    def drag_reference(self, start, end):
        frame = self.fresh()
        sx, sy = frame.shape[1] / 1920, frame.shape[0] / 1080
        self.task.swipe(round(start[0] * sx), round(start[1] * sy), round(end[0] * sx), round(end[1] * sy),
                        duration=0.4, after_sleep=0.35)

    def text_contains(self, value, region):
        return bool(self.task.wait_until(lambda: value in self.text(region), time_out=5, settle_time=0.2))

    def open_objective_board(self, board):
        from nuannuan.page_navigation import open_confirmed_page
        if board not in {'wish', 'starsea'}:
            raise AutomationError(f'未知任务面板：{board}')
        label = '朝夕心愿' if board == 'wish' else '星海拾光'
        entrance = 'ButtonZxxyEntrance' if board == 'wish' else 'ButtonXhsgEntrance'
        feature = 'IconZxxyFeature' if board == 'wish' else 'IconXhsgFeature'
        def open_page():
            self.key(self.settings.get('奇想日历', 'l'))
            if not self.wait('calendar_page'):
                raise AutomationError('未进入奇想日历')
            if self.wait(entrance, timeout=1):
                self.click_feature(entrance)
            elif not self.click_text(label):
                raise AutomationError('当前账号尚未找到目标任务入口')
        open_confirmed_page(self, label, feature, open_page)

    def _objective_score(self, prefix):
        from nuannuan.objectives import parse_score
        first = parse_score(self.text(f'Area{prefix}Score'))
        self.sleep(.2)
        second = parse_score(self.text(f'Area{prefix}Score'))
        if first != second:
            raise AutomationError('任务积分读数不稳定，未使用该分数执行或跳过任务')
        return second

    def scan_objectives(self, board):
        from nuannuan.daily import DailyRunner
        from nuannuan.objectives import Objective, Snapshot, WISH_CENTERS, STARSEA_CENTERS, classify
        self.open_objective_board(board)
        prefix = 'Zxxy' if board == 'wish' else 'Xhsg'
        centers = WISH_CENTERS if board == 'wish' else STARSEA_CENTERS
        items = []
        score = self._objective_score(prefix)
        # The daily goal is already confirmed. Claiming pending rewards is a
        # separate operation; opening all five cards cannot improve this result.
        for slot, (x, y) in enumerate(centers if score < 500 else []):
            if not self.exists(f'Icon{prefix}Feature'):
                raise AutomationError('读取任务卡时已离开目标任务页')
            self.click_reference(x, y)
            self.sleep(0.35)
            frame = self.fresh()
            completed = bool(self.match(f'Icon{prefix}TaskFinished', frame))
            text = self.text(f'Area{prefix}TaskText', frame)
            items.append(Objective(slot, text, classify(board, text), completed))
            self.evidence(f'{board}_card_{slot + 1}')
        if items:
            score = self._objective_score(prefix)
        snapshot = Snapshot(board, score, items)
        (self.artifacts / f'{board}_snapshot.json').write_text(json.dumps(snapshot.as_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
        DailyRunner(self).recover_home()
        return snapshot

    def supports_objective(self, board, item):
        from nuannuan.objective_actions import ObjectiveActions
        return ObjectiveActions(self).reason(board, item)

    def perform_objective(self, board, item):
        from nuannuan.objective_actions import ObjectiveActions
        return ObjectiveActions(self).perform(board, item)

    def claim_objective_rewards(self, board):
        from nuannuan.daily import DailyRunner
        self.open_objective_board(board)
        count = self._claim_rewards(board)
        DailyRunner(self).recover_home()
        return count

    def sleep(self, seconds):
        self.task.sleep(seconds)

    def evidence(self, name):
        executor = getattr(self.task, 'executor', None)
        frame = executor.nullable_frame() if executor is not None else self.task.frame
        if frame is None:
            return
        name = re.sub(r'[^\w-]', '_', name)
        path = self.artifacts / f'{name}_{time.time_ns()}.png'
        ok, encoded = cv2.imencode('.png', frame)
        if not ok:
            raise RuntimeError('无法编码诊断截图')
        path.write_bytes(encoded.tobytes())
