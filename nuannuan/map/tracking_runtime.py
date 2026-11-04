"""ok-script adapter for Whimbox's ordered material tracking operations."""
import json
import math

import cv2
import numpy as np

from nuannuan.config import ROOT
from nuannuan.map.material_tracking import material_info
from nuannuan.routes.model import RouteError
from nuannuan.map.tracking_vision import TrackingVision, sprite_matches


class TrackingRuntime:
    def __init__(self, runtime, map_name):
        self.runtime, self.port, self.map_name = runtime, runtime.port, map_name
        self.vision = TrackingVision()
        self._forward = None
        self._stuck = 0

    def stage(self, name):
        self.runtime.task.info_set('采集阶段',name)
        journal=getattr(self.port,'workflow_progress',None)
        if journal: journal(name,'running','')

    def select_ability(self, name): self.port.select_ability(name)

    @staticmethod
    def sprite(name):
        info=json.loads((ROOT/'assets/manifest.json').read_text(encoding='utf-8')).get('game_icons',{}).get(name)
        if not info: raise RouteError(f'缺少追踪图标：{name}')
        image=cv2.imdecode(np.frombuffer((ROOT/info['local_icon']).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        if image is None: raise RouteError('追踪图标无法读取')
        return image

    def select_sprite(self, image, region_name, scale, threshold, attempts=12):
        for index in range(attempts):
            frame=self.port.fresh()
            box=self.port.region(region_name,frame)
            crop=frame[box.y:box.y+box.height,box.x:box.x+box.width]
            matches=sprite_matches(crop,image,scale=scale*frame.shape[0]/1080,threshold=threshold,limit=1)
            if matches:
                x,y,_=matches[0]
                self.runtime.task.click(box.x+round(x),box.y+round(y),after_sleep=.4)
                return True
            if index+1 < attempts:
                self.runtime.task.scroll(box.x+box.width//2,box.y+box.height//2,10 if index==0 else -4)
                self.port.sleep(.25)
        return False

    def find_type(self, kind):
        return self.select_sprite(self.sprite('IconMaterialTypeInsect' if kind=='insect' else 'IconMaterialTypeAnimal'),
                                  'AreaBigMapMaterialTypeSelect',1,.75,attempts=8)

    def find_material(self, name):
        info=material_info(name)
        image=cv2.imdecode(np.frombuffer((ROOT/info['local_icon']).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        return self.select_sprite(image,'AreaBigMapMaterialSelect',.45,.8)

    def enable_tracking(self, name):
        info=material_info(name)
        if self.runtime.tracking_material==name:
            return
        self.port.goto_page('地图')
        if not self.port.wait('IconUIBigmap'): raise RouteError('未找到材料追踪入口')
        self.port.click_feature('IconUIBigmap')
        self.port.sleep(.3)
        if not self.find_type(info['type']): raise RouteError('材料追踪类别选择失败')
        if not self.find_material(name): raise RouteError(f'追踪材料选择失败：{name}')
        self.port.sleep(.5)
        text=self.port.text('AreaBigMapMaterialTrackConfirm').strip()
        if text=='精确追踪':
            if not self.port.click_text(text,'AreaBigMapMaterialTrackConfirm'): raise RouteError('精确追踪确认消失，未执行')
        elif text=='取消追踪':
            self.port.key('esc')
        else:
            raise RouteError('该材料未开启精确追踪，或追踪状态未识别')
        self.port.goto_page('主界面')
        self.runtime.tracking_material=name

    def begin_capture(self):
        frame=self.port.fresh()
        if not self.port.match('IconPageMainFeature',frame): raise RouteError('采集前未确认大世界界面')
        self.runtime.held_mouse.add('right')
        self.runtime.task.executor.interaction.mouse_down(frame.shape[1]//2,frame.shape[0]//2,key='right')

    def observe(self):
        frame=self.port.fresh()
        if not self.port.match('IconPageMainFeature',frame):
            raise RouteError('材料追踪过程中离开大世界，已释放输入')
        return {'active':self.vision.ability_ready(frame),'marker':self.vision.marker(frame)}

    def approach(self, marker):
        hint=getattr(self.runtime,'last_position',None)
        if hint is None: raise RouteError('材料追踪缺少可信路线位置，未移动')
        before=self.runtime.locate(self.map_name,hint)
        dx,dy=marker
        if self._forward is None:
            key='w'
        else:
            fx,fy=self._forward
            forward,right=dx*fx+dy*fy,dx*-fy+dy*fx
            key=('w' if forward>=0 else 's') if abs(forward)>=abs(right) else ('d' if right>=0 else 'a')
        self.runtime.pulse(key,.12)
        after=self.runtime.locate(self.map_name,before)
        x,y=after[0]-before[0],after[1]-before[1]
        moved=math.hypot(x,y)
        if moved < .1:
            self._stuck+=1
            if self._stuck>=8: raise RouteError('追踪目标时移动无反馈，停止当前点采集')
        else:
            if moved > 25: raise RouteError('追踪时位置异常跳变，已停止')
            self._stuck=0
            vx,vy={'w':(x,y),'s':(-x,-y),'d':(y,-x),'a':(-y,x)}[key]
            self._forward=(vx/moved,vy/moved)

    def stop_forward(self):
        for key in list(self.runtime.held_keys): self.runtime._key_up(key)

    def release_capture(self):
        self.runtime.task.executor.interaction.mouse_up(key='right')
        self.runtime.held_mouse.discard('right')

    def finish_capture(self):
        for _ in range(25):
            if self.port.exists('IconSkip'):
                self.port.key(self.port.settings.get('交互','f'))
            elif self.port.exists('IconPageMainFeature'):
                return
            self.port.sleep(.2)
        raise RouteError('采集动作后未返回主界面，未继续采集')

    def reward_text(self): return self.port.text('AreaMaterialGetText')
    def clear_marker(self): self.vision.previous=None
    def sleep(self, seconds): self.port.sleep(seconds)
    def release_all(self): self.runtime.release_all()
    def evidence(self,name): self.port.evidence(name)
