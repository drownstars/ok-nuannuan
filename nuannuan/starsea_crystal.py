"""Reference hub/bell/map/route sequence for the day's observed star crystals."""
import math

from nuannuan.routes import RouteCatalog, game_to_map

CRYSTAL_ROUTES = {
    '星海拾光_星光结晶收集_星梦群屿': (2865.,2155.),
    '星海拾光_星光结晶收集_泡泡梦屿': (3082.,1893.),
    '星海拾光_星光结晶收集_泡泡梦屿2': (3140.,1960.),
    '星海拾光_星光结晶收集_无界枢纽': (1679.,2000.),
    '星海拾光_星光结晶收集_晶簇之谷': (2250.,1475.),
    '星海拾光_星光结晶收集_大舞台': (3282.8,2437.6),
    '星海拾光_星光结晶收集_繁星之滨': (2434.4,1659.2),
    '星海拾光_星光结晶收集_繁星之滨2': (2375.,1605.),
}


class StarseaCrystalRunner:
    def __init__(self, port, catalog=None):
        self.port,self.catalog=port,catalog or RouteCatalog()

    def run(self):
        try:
            return self._run()
        finally:
            finish=getattr(self.port,'finish',None)
            if finish: finish()

    def _run(self):
        self.port.stage('传送到星海无界枢纽')
        self.port.teleport_hub()
        target=None
        for attempt in range(2):
            self.port.stage('摇铃')
            self.port.ring_bell()
            self.port.stage('查看星光结晶位置')
            target=self.port.locate_crystals()
            if target is not None: break
        if target is None:
            return {'status':'skipped','message':'摇铃复查后未发现当前星光结晶，未运行固定路线'}
        name=min(CRYSTAL_ROUTES,key=lambda name:math.dist(target,CRYSTAL_ROUTES[name]))
        if math.dist(target,CRYSTAL_ROUTES[name])>=50:
            return {'status':'partial','location':list(target),'message':'已识别结晶位置，但没有匹配的收集路线'}
        self.catalog.get(name)
        self.port.stage('开始跑图收集星光结晶')
        return {**self.port.run_route(name),'crystal_location':list(target),'crystal_route':self.catalog.resolve_name(name)}


class CrystalRuntime:
    def __init__(self, port):
        from nuannuan.route_runtime import RouteRuntime
        self.port,self.navigation=port,RouteRuntime(port,allow_chat=port.allow_chat)

    def stage(self,label):
        self.port.task.info_set('结晶收集阶段',label)
        progress=getattr(self.port,'workflow_progress',None)
        if progress: progress(label,'running','')

    def finish(self): self.port._crystal_bell_done=False

    def teleport_hub(self):
        self.navigation.teleport(game_to_map((-35070.57421875,44421.59765625),'starsea'),'starsea')

    def ring_bell(self):
        from nuannuan.daily import DailyRunner
        from nuannuan.routes import RouteError
        DailyRunner(self.port).recover_home()
        if not self.navigation.hold(self.navigation.game_key('bell'),4): raise RouteError('摇铃被中断')
        if not self.port.wait('IconPageMainFeature',timeout=12): raise RouteError('摇铃后未返回主界面')
        self.port._crystal_bell_done=True

    def locate_crystals(self):
        import cv2
        from nuannuan.map_vision import BIGMAP_SCALES, MapLocator
        from nuannuan.tracking_runtime import TrackingRuntime
        from nuannuan.tracking_vision import sprite_matches
        self.port.goto_page('地图')
        self.navigation.maximize_map()
        icon=TrackingRuntime.sprite('StarCrystal')
        for attempt in range(3):
            frame=self.port.fresh()
            matches=sprite_matches(frame,icon,scale=frame.shape[0]/1080,threshold=.7,limit=3)
            if not matches: return None
            width,height=frame.shape[1],frame.shape[0]
            x=sum(point[0] for point in matches)/len(matches)*1920/width
            y=sum(point[1] for point in matches)/len(matches)*1080/height
            if 320<x<1600 and 156<y<924:
                center=self.navigation.locator.bigmap(frame,'starsea')
                return center[0]+(x-960)*BIGMAP_SCALES['starsea'],center[1]+(y-540)*BIGMAP_SCALES['starsea']
            # An off-screen indicator is clicked once, then observed again.
            self.port.click_reference(x,y)
            self.port.sleep(.4)
        return None

    def run_route(self,name):
        from nuannuan.tasks import execute_route
        try: return execute_route(self.port,name)
        finally: self.port._crystal_bell_done=False
