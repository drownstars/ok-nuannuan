"""Recognized game pages, login and explicit game lifecycle tools."""
import time
from pathlib import Path

from nuannuan.daily import DailyRunner, AutomationError
from nuannuan.extra_daily import require

REALM_AREAS = {'素材激化幻境': 'AreaHuanjingJihuaEntrace', '祝福闪光幻境': 'AreaHuanjingBlessEntrace',
               '魔物试炼幻境': 'AreaHuanjingMonsterEntrace', '心之突破幻境': 'AreaHuanjingBossEntrace'}
PAGES = ['主界面', '美鸭梨', '奇想日历', '朝夕心愿', '星海拾光', '地图', '换装', '能力配置',
         '拍照', '奇迹之旅', '活动大厅', '设置', '幻境挑战', *REALM_AREAS, '商城', '共鸣', '演奏']


class GameTools:
    def __init__(self, port):
        self.port = port
        if not getattr(port,'_known_launcher_root',None):
            task=getattr(port,'task',None)
            manager=getattr(getattr(task,'executor',None),'device_manager',None)
            game_path=getattr(getattr(manager,'hwnd_window',None),'exe_full_path',None)
            if game_path:
                for parent in Path(game_path).parents:
                    if (parent/'launcher.exe').is_file() and (parent/'game').is_dir():
                        port._known_launcher_root=parent.resolve()
                        break

    def close_launcher(self):
        import psutil
        from ok.util.window import find_all_visible_windows
        from ok.device.interaction import PostMessageInteraction
        import win32con
        root=getattr(self.port,'_known_launcher_root',None)
        if root is None:
            return {'status':'skipped','message':'没有已验证的同目录启动器，未关闭其他程序'}
        targets={}
        for process in psutil.process_iter(['pid','name','exe']):
            path=process.info['exe']
            if path and (process.info['name'] or '').lower() in {'launcher.exe','xstarter.exe'} and Path(path).resolve().is_relative_to(root):
                targets[process.pid]=Path(path).resolve()
        if not targets:
            return {'status':'succeeded','message':'官方启动器已关闭'}
        approved=set(targets.values())
        sent=0
        for hwnd,title,name,path in find_all_visible_windows():
            if path and Path(path).resolve() in approved:
                PostMessageInteraction(None,None).post(win32con.WM_CLOSE,0,0,hwnd=hwnd)
                sent+=1
        for _ in range(20):
            if not any(psutil.pid_exists(pid) for pid in targets):
                return {'status':'succeeded','message':'已确认官方启动器退出'}
            self.port.sleep(.1)
        return {'status':'partial','message':'请求关闭后启动器进程仍在运行，未计入关闭成功'}

    def visible(self, page):
        features = {'主界面': 'IconPageMainFeature', '美鸭梨': 'menu_page', '奇想日历': 'calendar_page',
                     '朝夕心愿': 'IconZxxyFeature', '星海拾光': 'IconXhsgFeature', '地图': 'bigmap_page',
                     '换装': 'IconWardrobeFeature', '能力配置': 'IconAbilityFeature', '拍照': 'IconPhotoFeature',
                     '奇迹之旅': 'pass_page'}
        if page in features: return self.port.exists(features[page])
        return page in self.port.text('AreaPageTitleFeature')

    def goto(self, page):
        require(page in PAGES, f'不支持的页面：{page}')
        if self.visible(page): return
        if page in {'朝夕心愿', '星海拾光'}:
            self.port.open_objective_board('wish' if page == '朝夕心愿' else 'starsea')
            return
        if page == '主界面':
            DailyRunner(self.port).recover_home()
            return
        keys = {'美鸭梨': ('esc', 'menu_page'), '奇想日历': (self.port.settings.get('奇想日历', 'l'), 'calendar_page'),
                '地图': (self.port.settings.get('地图', 'm'), 'bigmap_page'),
                '换装': (self.port.settings.get('换装', 'c'), 'IconWardrobeFeature'),
                '拍照': (self.port.settings.get('拍照', 'p'), 'IconPhotoFeature'),
                '奇迹之旅': (self.port.settings.get('奇迹之旅', 'j'), 'pass_page')}
        if page in keys:
            from nuannuan.page_navigation import open_confirmed_page
            key, state = keys[page]
            open_confirmed_page(self.port, page, state, lambda: self.port.key(key))
        elif page == '能力配置':
            from nuannuan.ability_runtime import AbilityRuntime
            AbilityRuntime(self.port).open_ability_page()
        elif page == '幻境挑战' or page in REALM_AREAS:
            DailyRunner(self.port).recover_home()
            self.goto('奇想日历')
            require(self.port.wait('ButtonHuanjingGo'), '未找到幻境挑战入口')
            self.port.click_feature('ButtonHuanjingGo')
            require(self.port.text_contains('幻境挑战', 'AreaPageTitleFeature'), '未进入幻境挑战')
            if page in REALM_AREAS:
                require(self.port.click_text(page, REALM_AREAS[page]), f'未找到{page}入口')
                require(self.port.text_contains(page, 'AreaPageTitleFeature'), f'未确认进入{page}')
        else:
            DailyRunner(self.port).recover_home()
            if page == '活动大厅':
                self.port.key(self.port.settings.get('活动大厅', 'k'))
            else:
                self.goto('美鸭梨')
                require(self.port.click_text(page, 'AreaEscEntrances', scroll=True), f'菜单没有{page}入口')
            require(self.port.text_contains(page, 'AreaPageTitleFeature'), f'未确认进入{page}')
        self.port.evidence('goto_page')

    def enter(self, timeout=600):
        deadline, confirmed, login_clicks = time.monotonic() + timeout, 0, 0
        unknown_since, last_stage = None, None
        def stage(message):
            nonlocal last_stage
            if message != last_stage:
                notify = getattr(self.port, 'workflow_progress', None)
                if notify:
                    notify('进入游戏', 'running', message)
                last_stage = message
        while time.monotonic() < deadline:
            known = True
            # Reward panels can leave the world HUD visible underneath.
            if self.port.exists('IconDailyRewardFeature1') or self.port.exists('IconDailyRewardFeature2') or (
                    hasattr(self.port,'continue_prompt_visible') and self.port.continue_prompt_visible()):
                confirmed=0
                stage('确认月卡或继续提示，返回大世界')
                self.port.key(self.port.settings.get('交互', 'f'))
            elif self.port.exists('IconPageMainFeature'):
                stage('已出现大世界，连续确认界面')
                confirmed += 1
                if confirmed >= 3:
                    return {'status': 'succeeded', 'message': '已连续确认游戏大世界'}
            else:
                confirmed = 0
                if self.port.exists('game_loading'):
                    stage('游戏加载中，等待登录或大世界；不重复点击')
                elif self.port.exists('IconPageLoginFeature'):
                    stage('已确认登录入口，等待进入游戏')
                    require(login_clicks<3,'登录页点击后未观察到变化，请检查输入权限或切换前台交互')
                    require(self.port.click_text('点击进入游戏', 'AreaLoginOCR'), '请先手动完成登录验证')
                    login_clicks+=1
                elif self.port.exists('reward_popup'):
                    stage('关闭已识别的奖励结果')
                    self.port.key(self.port.settings.get('交互', 'f'))
                else:
                    known = False
                    if unknown_since is None:
                        unknown_since = time.monotonic()
                    stage('页面切换中，短暂等待识别；不操作未知弹窗')
                    require(time.monotonic() - unknown_since < 15,
                            '持续未识别到登录、加载或月卡页面，请先手动处理弹窗')
            if known:
                unknown_since = None
            self.port.sleep(1)
        raise AutomationError('进入游戏超时')

    def change_account(self, name):
        name = str(name).strip()
        require(bool(name), '请填写游戏登录列表中的完整账号显示名称')
        self.goto('美鸭梨')
        require(self.port.wait('ButtonExit'), '未找到退出菜单')
        self.port.click_feature('ButtonExit')
        require(self.port.click_text('返回登录', 'AreaExitBackLoginButton'), '未找到返回登录')
        require(self.port.wait('ButtonExitLogout', timeout=20), '未返回登录页')
        require(self.port.click_text('登录', 'AreaRegisterLoginButton'), '请手动打开账号列表')
        require(self.port.click_exact_text(name, 'AreaLoginAccountList', scroll=True), '未唯一识别到指定账号，不自动选择其他账号')
        require(self.port.click_text('登录', 'AreaLoginOCR'), '未找到账号登录按钮')
        return self.enter()

    def close(self):
        self.goto('美鸭梨')
        require(self.port.wait('ButtonExit'), '未找到退出游戏菜单')
        self.port.click_feature('ButtonExit')
        require(self.port.click_text('退出游戏', 'AreaDialog'), '未找到退出游戏选项')
        require(self.port.click_text('确认', 'AreaDialog'), '未确认退出游戏')
        import psutil
        for _ in range(20):
            if not any((p.info['name'] or '').lower() == 'x6game-win64-shipping.exe' for p in psutil.process_iter(['name'])):
                return {'status': 'succeeded', 'message': '已确认游戏进程退出'}
            self.port.sleep(.5)
        raise AutomationError('退出后游戏进程仍在运行')
