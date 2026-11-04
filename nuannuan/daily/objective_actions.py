"""Actions available to the automatic task planner, with explicit unsupported reasons."""
from dataclasses import replace

from nuannuan.daily.runner import DailyRunner
from nuannuan.routes.navigation import RouteRunner
from nuannuan.routes.runtime import RouteRuntime
from nuannuan.routes.model import RouteCatalog, RouteError, game_to_map

WISH_ROUTES = {'pickup': '朝夕心愿_采集', 'insect': '朝夕心愿_捕虫', 'fight': '朝夕心愿_战斗', 'minigame': '朝夕心愿_小游戏'}
STARSEA_ROUTES = {
    'place_item': '星海拾光_放置摆饰', 'music': '星海拾光_更改音乐', 'group_chat': '星海拾光_聚会聊天',
    'bubble_make': '星海拾光_制造泡泡', 'bottle_pickup': '星海拾光_拾取漂流瓶',
    'bottle_delivery': '星海拾光_投递漂流瓶', 'bottle_photo': '星海拾光_合影漂流瓶',
    'plane_photo': '星海拾光_合影星芒之翼', 'animal_one': '星海拾光_化身动物', 'animal_three': '星海拾光_化身动物',
    'crystal': '星海拾光_星光结晶收集_无界枢纽',
}


class ObjectiveActions:
    def __init__(self, port):
        self.port = port
        self.catalog = RouteCatalog()

    def reason(self, board, item):
        if item.kind == 'unknown':
            return '任务文字未识别或尚无匹配规则，请查看截图和原文'
        if item.kind in {'photo', 'dig'}:
            return ''
        if board == 'wish' and item.kind in {'energy', 'realm', 'bless', 'monster_realm'}:
            return ''
        if board == 'starsea' and item.kind == 'lookbook':
            return ''
        if board=='starsea' and item.kind=='crystal':
            return ''
        if item.kind == 'group_chat' and not self.port.allow_chat:
            return '聚会聊天发送默认关闭，可在任务选项中启用'
        routes = WISH_ROUTES if board == 'wish' else STARSEA_ROUTES
        name = routes.get(item.kind)
        if not name:
            return '原应用只有识别规则，尚无已接入执行流程；保留任务原文'
        try:
            route = self.catalog.get(name)
            RouteRuntime(self.port, allow_chat=self.port.allow_chat).preflight(route)
        except RouteError as error:
            return str(error)
        return ''

    def perform(self, board, item):
        if board=='starsea' and item.kind=='crystal':
            from nuannuan.daily.starsea_crystal import CrystalRuntime,StarseaCrystalRunner
            return StarseaCrystalRunner(CrystalRuntime(self.port)).run()
        if board == 'wish' and item.kind in {'energy', 'realm', 'bless', 'monster_realm'}:
            from nuannuan.daily.extra import ExtraDaily
            options = getattr(self.port, 'extra_options', {})
            action = {'realm': 'realm', 'bless': 'bless', 'monster_realm': 'monster'}.get(item.kind)
            if item.kind == 'energy':
                return ExtraDaily(self.port, options).spend_energy()
            return ExtraDaily(self.port, options).run(action)
        if board == 'starsea' and item.kind in {'photo', 'lookbook'}:
            hub = game_to_map((-35070.57421875, 44421.59765625), 'starsea')
            RouteRuntime(self.port, allow_chat=self.port.allow_chat).teleport(hub, 'starsea')
        if item.kind in {'photo', 'dig'}:
            keys = {'photo': self.port.settings.get('拍照', 'p')}
            return DailyRunner(self.port, keys).run_one(item.kind)
        if board == 'starsea' and item.kind == 'lookbook':
            DailyRunner(self.port).recover_home()
            self.port.key('esc')
            if not self.port.wait('menu_page') or not self.port.click_text('星绘图册', 'AreaEscEntrances', scroll=True):
                raise RouteError('未找到星绘图册入口')
            self.port.sleep(1)
            self.port.click_reference(960, 540)
            if not self.port.wait('ButtonXhsgBooklookLike'):
                raise RouteError('未找到星绘图册点赞按钮')
            self.port.click_feature('ButtonXhsgBooklookLike')
            DailyRunner(self.port).recover_home()
            return
        routes = WISH_ROUTES if board == 'wish' else STARSEA_ROUTES
        route = self.catalog.get(routes[item.kind])
        if item.kind == 'animal_one':
            route = replace(route, points=[replace(point, params='1') if point.action == 'TRANS_ANIMAL' else point
                                           for point in route.points])
        runtime = RouteRuntime(self.port, allow_chat=self.port.allow_chat)
        return RouteRunner(runtime, max_seconds=self.port.route_seconds).run(route)
