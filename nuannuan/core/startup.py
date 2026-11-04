"""Official-launcher preparation before the framework connects a daily task."""
import os
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from nuannuan.config import ROOT
from nuannuan.core.errors import AutomationError


class GameLaunchSequence:
    def __init__(self, port, *, timeout=60, clock=time.monotonic):
        self.port,self.timeout,self.clock=port,timeout,clock

    def run(self):
        try:
            if self.port.game_ready():
                return {'status':'skipped','message':'游戏窗口已运行，直接连接'}
            path=self.port.resolve_path()
            if path is None: raise AutomationError('未设置官方启动器；请在常用操作中选择游戏启动程序')
            self.port.stage('自动启动游戏')
            self.port.launch(path)
            deadline=self.clock()+self.timeout
            clicked=False
            while self.clock()<deadline:
                if self.port.game_ready():
                    return {'status':'succeeded','message':'已确认无限暖暖窗口，继续进入游戏'}
                if not clicked:
                    clicked=self.port.click_launch()
                self.port.sleep(.5)
            raise AutomationError('等待游戏启动超时；请检查官方启动器的更新、登录或系统提示')
        finally:
            self.port.close()


class LaunchRuntime:
    def __init__(self, app, task):
        self.app,self.task=app,task
        self.path=None
        self.capture=self.window=None
        self.stop=threading.Event()
        self.folder=ROOT/'logs/runs'/f'startup_{uuid.uuid4().hex[:12]}'

    def stage(self,label):
        from ok.core.events import communicate
        self.task.info_set('当前步骤',label)
        self.task.info_set('启动状态',label)
        control = getattr(self.app, 'run_control', None)
        if control is not None: control.record(label, 'running')
        communicate.starting_emulator.emit(False,label,60)

    @staticmethod
    def check_privilege(hwnd):
        import win32api,win32con,win32process,win32security
        from ok.util.process import is_admin
        if is_admin(): return
        pid=win32process.GetWindowThreadProcessId(hwnd)[1]
        try:
            process=win32api.OpenProcess(0x1000,False,pid)
            token=win32security.OpenProcessToken(process,win32con.TOKEN_QUERY)
            elevated=bool(win32security.GetTokenInformation(token,win32security.TokenElevation))
        except Exception as error:
            raise AutomationError('无法确认游戏 / 启动器输入权限，未发送模拟操作') from error
        if elevated:
            raise AutomationError('游戏或启动器以管理员权限运行；请以管理员身份运行助手后重试')

    def game_ready(self):
        self.check_cancelled()
        import win32gui
        from ok.util.window import find_all_visible_windows
        for hwnd,title,name,path in find_all_visible_windows():
            if name.lower()!='x6game-win64-shipping.exe': continue
            rect=win32gui.GetClientRect(hwnd)
            if rect[2]>=1280 and rect[3]>=720:
                self.check_privilege(hwnd)
                return True
        return False

    def resolve_path(self):
        from nuannuan.tasks.daily_tasks import OperationTask
        operation=self.app.task_executor.get_task_by_class(OperationTask)
        selected=operation.config.get('启动程序路径','')
        if selected and Path(selected).is_file():
            self.path=Path(selected).resolve()
            return self.path
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            shell=win32com.client.Dispatch('WScript.Shell')
            for special in ['Desktop','AllUsersDesktop']:
                desktop=Path(shell.SpecialFolders(special))
                for shortcut in desktop.glob('*.lnk'):
                    if not any(word in shortcut.stem.lower() for word in ['无限暖暖','infinitynikki','infinity nikki']): continue
                    target=Path(shell.CreateShortcut(str(shortcut)).TargetPath)
                    if target.is_file() and target.suffix.lower()=='.exe':
                        self.path=target.resolve()
                        operation.config['启动程序路径']=str(self.path)
                        return self.path
        finally:
            pythoncom.CoUninitialize()
        return None

    def launcher_windows(self):
        from ok.util.window import find_all_visible_windows
        if self.path is None: return []
        return [item for item in find_all_visible_windows()
                if item[3] and Path(item[3]).resolve().is_relative_to(self.path.parent)
                and item[2].lower() in {'launcher.exe','xstarter.exe','infinitynikki.exe'}
                and any(word in item[1].lower() for word in ['暖暖','nikki'])]

    def launch(self,path):
        if not self.launcher_windows(): os.startfile(str(path))

    def click_launch(self):
        self.check_cancelled()
        windows=self.launcher_windows()
        if not windows: return False
        hwnd,title,name,path=windows[0]
        self.check_privilege(hwnd)
        if self.window is None:
            from ok.device.capture import HwndWindow,update_capture_method
            class Options(dict): pass
            options=Options({'Mute Game while in Background':False,'Auto Resize Game Window':False})
            global_config=SimpleNamespace(get_config=lambda name:options)
            manager=SimpleNamespace(config={'selected_exe':path,'selected_hwnd':hwnd},capture_method=None,
                                    executor=None,get_preferred_device=lambda:None)
            self.window=HwndWindow(self.stop,None,path,global_config=global_config,device_manager=manager)
            self.capture=update_capture_method({'capture_method':['WGC','BitBlt']},None,self.window,self.stop)
            manager.capture_method=self.capture
        if self.capture is None: return False
        frame=self.capture.get_frame(busy_wait=.1)
        if frame is None: return False
        result=self.app.task_executor.ocr_lib('default')(frame,use_det=True,use_cls=False,use_rec=True)
        targets=[box for box,text,score in zip(result.boxes if result.boxes is not None else [],result.txts or [],result.scores or [])
                 if ''.join(text.split())=='启动游戏' and score>=.85]
        if len(targets)!=1: return False
        import cv2
        from nuannuan.core.interaction import WhimboxInteraction
        self.folder.mkdir(parents=True,exist_ok=True)
        cv2.imwrite(str(self.folder/'launcher-before.png'),frame)
        points=targets[0]
        x=sum(point[0] for point in points)/len(points)
        y=sum(point[1] for point in points)/len(points)
        self.stage('点击官方启动器的启动游戏，等待游戏窗口')
        self.check_cancelled()
        interaction = WhimboxInteraction(self.capture, self.window)
        try:
            interaction.on_run()
            self.check_cancelled()
            interaction.click(round(x),round(y),down_time=.1)
        finally: interaction.on_destroy()
        return True

    def check_cancelled(self):
        control = getattr(self.app, 'run_control', None)
        if control is not None and control.cancel_event.is_set():
            raise AutomationError('任务已停止，启动流程已取消')

    def sleep(self,seconds):
        self.check_cancelled()
        control = getattr(self.app, 'run_control', None)
        if control is not None:
            control.cancel_event.wait(seconds)
            self.check_cancelled()
        elif self.app.exit_event.wait(seconds):
            raise AutomationError('助手正在退出，启动流程已停止')
        if self.app.exit_event.is_set(): raise AutomationError('助手正在退出，启动流程已停止')
    def close(self):
        self.stop.set()
        if self.capture is not None: self.capture.close()
        if self.window is not None: self.window.stop()


def install_launch_support(app):
    """Extend only this app's controller; do not patch framework classes."""
    from types import MethodType
    from nuannuan.daily.extra import EXTRA_SETTINGS
    from ok.core.events import communicate
    for facade in [getattr(app,'_app',None),getattr(app,'_headless_app',None)]:
        if facade is None: continue
        controller=facade.start_controller
        if getattr(controller,'_nuannuan_launch_support',False): continue
        original=controller._do_start
        def start(self, task=None, exit_after=False, original=original):
            selected=(task is not None and task.__class__.__name__ in {'DailyTask','RouteTask'}) or (
                task is not None and task.__class__.__name__=='OperationTask' and task.config.get('工具功能')=='进入游戏')
            options=app.global_config.get_config(EXTRA_SETTINGS)
            if selected and options.get('自动启动游戏',True) and app.task_executor.current_task is None:
                try:
                    GameLaunchSequence(LaunchRuntime(app,task)).run()
                except (AutomationError,OSError,ValueError) as error:
                    task.info_set('启动状态',str(error))
                    communicate.starting_emulator.emit(True,str(error),0)
                    return False
            control = getattr(app, 'run_control', None)
            if control is not None and control.cancel_event.is_set(): return False
            return original(task,exit_after)
        controller._do_start=MethodType(start,controller)
        controller._nuannuan_launch_support=True
