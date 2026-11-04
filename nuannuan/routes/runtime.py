"""ok-script input/capture adapter for validated route traversal and actions."""
import json
import math
import time

from nuannuan.config import ROOT
from nuannuan.daily.runner import DailyRunner
from nuannuan.map.vision import BIGMAP_SCALES, MapLocator
from nuannuan.routes.model import RouteError, game_to_map

KEY_SETTINGS = {'jump': ('跳跃', 'space'), 'falling': ('下坠', 'q'), 'forward': ('前进', 'w'),
                'interaction': ('交互', 'f'), 'item': ('道具', 'z'), 'bell': ('摇铃', 'x'),
                'back': ('返回', 'backspace'), 'sprint': ('冲刺', 'shift'), 'map': ('地图', 'm'),
                'daily_task': ('奇想日历', 'l'), 'take_photo': ('拍照', 'p'),
                'monthly_pass': ('奇迹之旅', 'j'), 'chat': ('聊天', 'enter')}
KEY_SETTINGS.update({'backward': ('后退', 's'), 'left': ('向左', 'a'), 'right': ('向右', 'd'),
                      'event': ('活动大厅', 'k'), 'dress': ('换装', 'c'),
                      'ability_derivation_world_1': ('大世界能力衍生', 'g'),
                      'ability_derivation_1': ('能力衍生', 'r')})


class RouteRuntime:
    def __init__(self, port, *, allow_chat=False):
        self.port = port
        self.task = port.task
        self.allow_chat = allow_chat
        self.locator = MapLocator()
        self.held_keys = set()
        self.held_mouse = set()
        self.last_jump = 0
        self.collected = 0
        self.material_counts = {}
        self.action_results = []
        self.tracking_material = None
        self.last_position = None
        self._recovery_count = 0
        self.ability_manager = None
        self.checkpoints = json.loads((ROOT / 'assets/maps/checkpoints.json').read_text(encoding='utf-8'))

    def game_key(self, name):
        if name == 'fishing_reel_in': return 'mouse_right'
        if name.startswith('ability_'):
            return name.split('_')[-1]
        label, default = KEY_SETTINGS[name]
        return self.port.settings.get(label, default)

    def require(self, condition, message):
        if not condition:
            raise RouteError(message)

    def nearest_checkpoint(self, target, map_name):
        candidates = self.checkpoints.get(map_name, [])
        self.require(candidates, f'缺少 {map_name} 的传送点数据')
        point = min(candidates, key=lambda row: math.dist(target, game_to_map(row['position'], map_name)))
        position = game_to_map(point['position'], map_name)
        self.require(math.dist(target, position) < 80, '路线传送点距离已知流转之柱过远，请检查路线坐标')
        return point, position

    def preflight(self, route):
        from nuannuan.routes.ability import required_abilities
        required_abilities(route, getattr(self.port, 'route_options', {}))
        for point in route.points:
            if point.action in {'CATCH_INSECT','CLEAN_ANIMAL'}:
                from nuannuan.map.material_tracking import material_info
                info=material_info(route.material_target)
                self.require(info['type']==('insect' if point.action=='CATCH_INSECT' else 'animal'),'路线材料类别与采集动作不匹配')
            if point.action == 'TELEPORT':
                self.nearest_checkpoint(game_to_map(point.position, route.map_name), route.map_name)
            if point.action == 'GROUP_CHAT' and not self.allow_chat:
                raise RouteError('该路线包含聚会聊天；请在任务选项中启用“允许聚会聊天”后运行')
            if point.action == 'MINIGAME' and not getattr(self.port, 'extra_options', {}).get('允许小游戏支付噗灵', False):
                raise RouteError('该路线需要支付小游戏噗灵，请先在扩展功能设置中启用')

    def prepare_abilities(self, route):
        from nuannuan.routes.ability import AbilityManager, ABILITY_DEFAULTS
        from nuannuan.routes.ability_runtime import AbilityRuntime
        options = {**ABILITY_DEFAULTS, **getattr(self.port, 'route_options', {})}
        if not options['跑图前自动配置能力']:
            return
        self.task.info_set('能力配置', '正在检查路线所需能力')
        self.ability_manager = AbilityManager(AbilityRuntime(self.port))
        assigned = self.ability_manager.prepare(route, options)
        self.port._ability_manager = self.ability_manager
        if '捕虫' in assigned:
            self.port.settings['捕虫能力'] = str(assigned['捕虫'])
        self.task.info_set('能力配置', '已验证' if assigned or any(p.move_mode == 'JUMP' for p in route.points)
                           else '本路线无需切换能力')

    def initialize_map(self,route):
        self.task.info_set('跑图状态','初始化地图信息')
        self.locator.atlas(route.map_name,'05x')

    def evidence(self, name):
        self.port.evidence(name)
        (self.port.artifacts / 'navigation.json').write_text(json.dumps(
            {'last_observation': self.locator.last_observation, 'collected': self.collected,
             'materials':self.material_counts,'action_results':self.action_results},
            ensure_ascii=False, indent=2), encoding='utf-8')

    def progress(self, index, total, point):
        self.task.info_set('跑图进度', f'{index}/{total} · 点位 {point.id} · {point.action or point.move_mode}')

    def after_teleport(self, route, point):
        if (route.origin_name or route.name).startswith('星海拾光_星光结晶收集'):
            if getattr(self.port, 'extra_options', {}).get('结晶收集前化万相', False):
                from nuannuan.daily.gathering import ability_action
                ability_action(self.port, '开启化万相')
            if not getattr(self.port,'_crystal_bell_done',False):
                self.require(self.hold(self.game_key('bell'), 4), '星海摇铃被中断')
                self.require(self.port.wait('IconPageMainFeature', timeout=12), '摇铃后未返回星海主界面')

    def _key_down(self, key):
        self.task.executor.check_enabled(check_pause=False)
        if self.task.executor.paused:
            raise RouteError('输入前任务已暂停')
        key = self.task.validate_key(key)
        self.held_keys.add(key)
        self.task.executor.interaction.send_key_down(key)

    def _key_up(self, key):
        # Bypass pause-aware scene reset so cleanup can always release an input.
        self.task.executor.interaction.send_key_up(key)
        self.held_keys.discard(key)

    def release_all(self):
        for key in list(self.held_keys):
            try:
                self._key_up(key)
            except Exception:
                self.held_keys.discard(key)
        for key in list(self.held_mouse):
            try:
                self.task.executor.interaction.mouse_up(key=key)
            finally:
                self.held_mouse.discard(key)

    def _wait_holding(self, duration):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.task.executor.check_enabled(check_pause=False)
            current = self.task.executor.current_task
            if self.task.executor.paused or (current is not None and current.paused):
                return False
            time.sleep(min(0.02, max(0, deadline - time.monotonic())))
        return True

    def hold(self, key, duration):
        self.port.fresh()
        self._key_down(key)
        try:
            completed = self._wait_holding(duration)
        finally:
            self._key_up(key)
        self.port.sleep(0.05)
        return completed

    def pulse(self, key, duration, jump=False):
        frame = self.port.fresh()
        self.require(self.port.match('IconPageMainFeature', frame), '移动前未确认大世界主界面')
        actual_key = self.port.settings.get({'w': '前进', 'a': '向左', 's': '后退', 'd': '向右'}[key], key)
        self._key_down(actual_key)
        try:
            if jump and time.monotonic() - self.last_jump > 0.8:
                jump_key = self.game_key('jump')
                self._key_down(jump_key)
                try:
                    self._wait_holding(0.03)
                finally:
                    self._key_up(jump_key)
                self.last_jump = time.monotonic()
            self._wait_holding(duration)
        finally:
            self._key_up(actual_key)
        self.port.sleep(0.12)

    def locate(self, map_name, hint):
        frame = self.port.fresh()
        self.require(self.port.match('IconPageMainFeature', frame), '小地图定位前未确认大世界界面')
        location = self.locator.minimap(frame, map_name, hint)
        self.task.info_set('视觉位置', f'{location[0]:.1f}, {location[1]:.1f}')
        self.task.info_set('定位置信度', f'{self.locator.last_observation["confidence"]:.3f}')
        self.last_position=location
        return location

    def check_interruption(self, route, hint, checkpoint=None):
        if self.port.exists('IconPageMainFeature'):
            return None
        self.release_all()
        self.require(self._recovery_count<2,'本次跑图中断恢复次数已达上限')
        self.task.info_set('跑图状态','意外中断，等待回到主界面…')
        stable=0
        for _ in range(30):
            stable=stable+1 if self.port.exists('IconPageMainFeature') else 0
            if stable>=2: break
            self.port.sleep(1)
        self.require(stable>=2,'中断后等待主界面超时，未点击未知弹窗')
        self._recovery_count+=1
        self.tracking_material=None
        self.task.info_set('跑图状态','已回到主界面，重新定位坐标')
        if hint is None:
            return None
        try:
            return self.locate(route.map_name,hint)
        except RouteError:
            self.require(checkpoint is not None,'无法重新定位且没有可信传送点，已停止')
            self.task.info_set('跑图状态','重新定位失败，返回最近可信流转之柱')
            self.teleport(checkpoint,route.map_name)
            return self.locate(route.map_name,checkpoint)

    def unstuck(self):
        self.release_all()
        self.require(self.port.exists('IconPageMainFeature'),'脱困前不在主界面，未发送跳跃')
        self.task.info_set('跑图状态','移动无反馈，尝试一次跳跃脱困')
        self.pulse('w',.6,jump=True)

    def maximize_map(self):
        for _ in range(4):
            frame = self.port.fresh()
            if self.port.match('IconBigMapMaxScale', frame) or self.port.match('IconBigMapMaxScaleJoyStick', frame):
                return
            self.port.click_feature('ButtonBigMapZoom')
            self.port.sleep(0.4)
        raise RouteError('未确认大地图最大缩放级别')

    def teleport(self, target, map_name):
        checkpoint, destination = self.nearest_checkpoint(target, map_name)
        DailyRunner(self.port).recover_home()
        self.port.key(self.game_key('map'))
        self.require(self.port.wait('bigmap_page'), '未进入大地图')
        region = self.port.text('AreaBigMapRegionName')
        if checkpoint['region'] not in region:
            self.port.click_region('AreaBigMapRegionName')
            if map_name == 'home':
                self.port.click_feature('IconBigMapHomeFeature')
            else:
                self.require(self.port.click_text(checkpoint['province'], 'AreaBigMapRegionSelect', scroll=True),
                             f'地图中未找到区域：{checkpoint["province"]}')
                if checkpoint['province'] != '星海':
                    self.require(self.port.click_text(checkpoint['region'], 'AreaBigMapRegionSelect', scroll=True),
                                 f'地图中未找到区域：{checkpoint["region"]}')
            self.port.sleep(0.7)
            region = self.port.text('AreaBigMapRegionName')
            self.require(map_name == 'home' or checkpoint['region'] in region, '地图区域切换后未确认目标区域')
        self.maximize_map()
        for _ in range(24):
            frame = self.port.fresh()
            center = self.locator.bigmap(frame, map_name)
            dx = (destination[0] - center[0]) / BIGMAP_SCALES[map_name]
            dy = (destination[1] - center[1]) / BIGMAP_SCALES[map_name]
            if abs(dx) < 450 and abs(dy) < 260:
                self.port.click_reference(960 + dx, 540 + dy)
                break
            # Drag a bounded distance and re-localize; never assume a drag worked.
            shift_x, shift_y = max(-350, min(350, -dx * 0.7)), max(-250, min(250, -dy * 0.7))
            self.port.drag_reference((960, 540), (960 + shift_x, 540 + shift_y))
        else:
            raise RouteError('大地图移动超时，未找到目标传送点')
        if not self.port.click_text('传送', 'AreaBigMapTeleportButton'):
            self.require(self.port.click_text(checkpoint['name'], 'AreaBigMapTeleporterSelect', scroll=True),
                         '未找到传送点选项，可能尚未解锁')
            self.require(self.port.click_text('传送', 'AreaBigMapTeleportButton'), '目标流转之柱尚未解锁或无法传送')
        self.require(self.port.wait('IconPageMainFeature', timeout=35), '传送后未返回大世界')
        self.port.sleep(1)
        actual = self.locate(map_name, destination)
        self.require(math.dist(actual, destination) < 50, '传送后小地图位置与目标不符')
        self.evidence('teleport_verified')

    def macro(self, data):
        from nuannuan.routes.model import validate_macro
        steps = validate_macro(data)
        self.port.fresh()
        try:
            for step in steps:
                kind = step['type']
                if kind == 'gap':
                    duration = float(step['duration'])
                    if self.held_keys or self.held_mouse:
                        self.require(self._wait_holding(duration), '宏已因暂停释放按键，请从该任务重新运行')
                    else:
                        self.port.sleep(duration)
                elif kind == 'goto_game_page':
                    self.port.goto_page(step['target_game_page'])
                elif kind in {'wait_game_page', 'wait_not_game_page'}:
                    want = kind == 'wait_game_page'
                    self.require(self.task.wait_until(lambda: self.port.page_visible(step['target_game_page']) == want,
                                                       time_out=20, settle_time=.3), '宏等待目标页面超时')
                elif kind in {'keyboard', 'game_key'}:
                    key = self.game_key(step['key']) if kind == 'game_key' else step['key']
                    if key in {'mouse_left', 'mouse_right'}:
                        button = 'left' if key == 'mouse_left' else 'right'
                        if step['action'] == 'press':
                            frame = self.task.executor.nullable_frame()
                            self.require(frame is not None, '宏缺少鼠标操作画面')
                            self.held_mouse.add(button)
                            self.task.executor.interaction.mouse_down(frame.shape[1]//2, frame.shape[0]//2, key=button)
                        else:
                            self.task.executor.interaction.mouse_up(key=button)
                            self.held_mouse.discard(button)
                    elif step['action'] == 'press':
                        self._key_down(key)
                    else:
                        self._key_up(key)
                elif kind == 'mouse':
                    key = 'left' if step['key'] == 'mouse_left' else 'right'
                    if step['action'] == 'press':
                        frame = self.task.executor.nullable_frame()
                        self.require(frame is not None, '宏操作缺少可用的游戏画面')
                        x, y = step['position']
                        self.held_mouse.add(key)
                        self.task.executor.interaction.mouse_down(round(x * frame.shape[1] / 1920),
                                                                  round(y * frame.shape[0] / 1080), key=key)
                    else:
                        frame = self.task.executor.nullable_frame()
                        self.require(frame is not None, '宏释放鼠标缺少可用画面')
                        x, y = step['position']
                        self.task.executor.interaction.move(round(x*frame.shape[1]/1920), round(y*frame.shape[0]/1080))
                        self.task.executor.interaction.mouse_up(key=key)
                        self.held_mouse.discard(key)
                self.task.executor.check_enabled(check_pause=False)
                if self.task.executor.paused:
                    raise RouteError('宏已因暂停释放输入，请重新运行该任务')
        finally:
            self.release_all()

    def action(self, point, route):
        action = point.action
        if action in {'CATCH_INSECT','CLEAN_ANIMAL'}:
            from nuannuan.map.material_tracking import MaterialTracker
            from nuannuan.map.tracking_runtime import TrackingRuntime
            result=MaterialTracker(TrackingRuntime(self,route.map_name)).run(
                route.material_target,'捕虫' if action=='CATCH_INSECT' else '动物清洁',expected_count=int(point.params or 1))
            for name,count in result['materials'].items():
                self.material_counts[name]=self.material_counts.get(name,0)+count
                self.collected+=count
            self.action_results.append({'point':point.id,**result})
            self.task.info_set('采集结果',result['message'])
            return result
        if action in {'FISHING', 'FISHING_STAR'}:
            from nuannuan.daily.gathering import FishingRunner, ability_action
            options = getattr(self.port, 'extra_options', {})
            if action == 'FISHING' and options.get('钓鱼前万物交响', False):
                ability_action(self.port, '万物交响')
            result=FishingRunner(self.port).run(casts=options.get('钓鱼抛竿次数', 3), home=action == 'FISHING_STAR')
            if route.material_target:
                from nuannuan.map.material_tracking import observed_quantity
                count=sum(observed_quantity(route.material_target,text) for text in result['materials'])
                self.material_counts[route.material_target]=self.material_counts.get(route.material_target,0)+count
                self.collected+=count
            self.action_results.append({'point':point.id,**result})
        elif action == 'MINIGAME':
            from nuannuan.daily.minigame import MinigameRunner
            MinigameRunner(self.port).run(route.macros[point.params])
        elif action in {'CLEAN_ANIMAL', 'FLOURISH', 'FLORAL_INSECT', 'MAGNET', 'BIG', 'FAIRY_ANIMAL',
                        'MACHINE_INFUSE', 'MACHINE_EXTRACT'}:
            from nuannuan.daily.gathering import ability_action
            ability_action(self.port, {'CLEAN_ANIMAL': '清洁动物', 'FLOURISH': '芳间巡游', 'FLORAL_INSECT': '花套捕虫',
                                      'MAGNET': '开启化万相', 'BIG': '变大', 'FAIRY_ANIMAL': '变小',
                                      'MACHINE_INFUSE': '械控注入', 'MACHINE_EXTRACT': '械控抽取'}[action])
        elif action == 'WAIT':
            self.port.sleep(float(point.params or 0.2))
        elif action in {'KEY_CLICK', 'GAME_KEY_CLICK'}:
            self.port.key(self.game_key(point.params) if action == 'GAME_KEY_CLICK' else point.params)
        elif action == 'MACRO':
            self.macro(route.macros[point.params])
        elif action == 'TAKE_PHOTO':
            DailyRunner(self.port, {'photo': self.game_key('take_photo')}).run_one('photo')
        elif action == 'PICK_UP':
            from nuannuan.map.material_tracking import observed_quantity
            for _ in range(8):
                if not self.port.exists('IconPickupFeature'):
                    break
                before=self.port.text('AreaMaterialGetText')
                self.port.key(self.game_key('interaction'))
                self.port.sleep(.2)
                count=observed_quantity(route.material_target,self.port.text('AreaMaterialGetText'),before) if route.material_target else 0
                if route.material_target:
                    self.material_counts[route.material_target]=self.material_counts.get(route.material_target,0)+count
                self.collected+=count
        elif action == 'PICKUP_BOTTLE':
            if self.port.exists('IconPickupFeature'):
                self.port.key(self.game_key('interaction'))
                self.require(self.port.wait('ButtonXhsgBottleClose'), '未出现漂流瓶内容')
                self.port.click_feature('ButtonXhsgBottleClose')
                self.collected += 1
        elif action == 'CHANGE_MUSIC':
            self.require(self.port.text_contains('更改音乐', 'AreaPickup'), '当前位置没有更改音乐提示')
            self.port.key(self.game_key('interaction'))
            self.port.sleep(1)
            # Selecting an available play action, when the menu exposes it.
            self.port.click_text('播放', 'AreaDialog')
            DailyRunner(self.port).recover_home()
        elif action == 'TRANS_ANIMAL':
            for _ in range(int(point.params or 1)):
                self.require(self.port.text_contains('变身', 'AreaPickup'), '当前位置未识别到变身提示')
                self.port.key(self.game_key('interaction'))
                self.port.sleep(2)
            self.port.key(self.game_key('back'))
            self.require(self.port.click_text('确认', 'AreaDialog'), '未识别到结束化身确认')
            DailyRunner(self.port).recover_home()
        elif action == 'DELIVERY_BOTTLE':
            self.require(self.port.text_contains('投递', 'AreaPickup'), '当前位置没有投递提示')
            self.port.key(self.game_key('interaction'))
            self.require(self.port.click_text('确认投递', 'AreaDialog'), '未找到确认投递按钮')
            self.require(self.port.click_text('确认', 'AreaDialog'), '未找到投递确认按钮')
            DailyRunner(self.port).recover_home()
        elif action == 'GROUP_CHAT':
            self.require(self.allow_chat, '聚会聊天尚未启用')
            self.require(self.port.exists('IconSetdownFeature'), '未找到坐下提示')
            self.port.key(self.game_key('interaction'))
            self.port.sleep(2)
            self.port.key(self.game_key('chat'))
            self.require(self.port.wait('IconXhsgGroupChatFeature'), '未进入聚会聊天频道')
            self.port.key('1')
            self.port.key('enter')
            DailyRunner(self.port).recover_home()
            self.port.key(self.game_key('interaction'))
        elif action == 'PLACE_ITEM':
            self.place_item()
        else:
            raise RouteError(f'未实现的路线动作：{action}')

    def place_item(self):
        self.require(self.hold(self.game_key('item'), 3), '道具长按被中断')
        for name in ['ButtonItemSetting', 'ButtonItemFinishSetting', 'ButtonItemPlaceableItem']:
            self.require(self.port.wait(name), f'未找到摆饰界面标识：{name}')
            self.port.click_feature(name)
        self.port.click_region('AreaItemFirstItem')
        if self.port.wait('ButtonItemLanternConfirm', timeout=1):
            self.port.click_feature('ButtonItemLanternConfirm')
            self.require(self.port.click_text('确认', 'AreaDialog'), '河灯确认界面未识别')
        self.port.sleep(0.6)
        for _ in range(6):
            self.task.click_relative(0.5, 0.5, after_sleep=0.6)
            if not self.port.exists('IconItemCantPlace'):
                break
        else:
            raise RouteError('摆饰当前位置无法放置')
        if not self.port.exists('IconPageMainFeature'):
            self.task.click_relative(0.5, 0.5, key='right', after_sleep=0.3)
        DailyRunner(self.port).recover_home()
