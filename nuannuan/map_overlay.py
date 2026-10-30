"""Read-only framework capture and click-through map point rendering."""
import threading
import time

from PySide6.QtCore import QObject, QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from nuannuan.map_mask import MapMaskEngine, logical_rect, project_points

COLORS = {'teleport': '#69d2ff', 'route': '#ffce76'}


class MapOverlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.markers = []
        self.names = True
        self.setWindowTitle('暖暖地图点位')

    def set_markers(self, markers, names=True):
        self.markers = list(markers)
        self.names = names
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(self.width()/1920, self.height()/1080)
        previous = None
        for point in self.markers:
            if point.label == 'route' and previous is not None and point.sequence == previous.sequence+1 and point.action != 'TELEPORT':
                painter.setPen(QPen(QColor('#dcb770'), 2))
                painter.drawLine(QPoint(round(previous.x), round(previous.y)), QPoint(round(point.x), round(point.y)))
            previous = point if point.label == 'route' else None
            color = QColor(COLORS.get(point.label, '#b6e79b'))
            painter.setPen(QPen(QColor('#263146'), 2))
            painter.setBrush(color)
            painter.drawEllipse(QPoint(round(point.x), round(point.y)), 5, 5)
            if self.names:
                text = point.name[:24]
                painter.setPen(QPen(QColor('#172434'), 3))
                painter.drawText(round(point.x)+9, round(point.y)+5, text)
                painter.setPen(QColor('#ffffff'))
                painter.drawText(round(point.x)+8, round(point.y)+4, text)


def game_context(executor):
    """Physical client rect only when the configured game owns the foreground."""
    import win32gui
    window = executor.device_manager.hwnd_window
    hwnd = getattr(window, 'hwnd', 0)
    if not hwnd or not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd): return None
    root = win32gui.GetAncestor(hwnd, 2)
    if win32gui.IsIconic(root) or win32gui.GetForegroundWindow() != root: return None
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width < 1280 or height < 720: return None
    return hwnd, (left, top, width, height)


def qt_geometry(hwnd, physical):
    import win32api
    info = win32api.GetMonitorInfo(win32api.MonitorFromWindow(hwnd))
    origin = info['Monitor'][:2]
    screens = QGuiApplication.screens()
    screen = next((screen for screen in screens if screen.name() == info.get('Device')), QGuiApplication.primaryScreen())
    return logical_rect(physical, origin, (screen.geometry().x(), screen.geometry().y()), screen.devicePixelRatio())


class OverlayController(QObject):
    observation_ready = Signal(object)
    status_changed = Signal(str)

    def __init__(self, executor, parent=None):
        super().__init__(parent)
        self.executor = executor
        self.overlay = MapOverlay()
        self.engine = MapMaskEngine()
        self.enabled = False
        self.closed = False
        self.busy = False
        self.generation = 0
        self.settings = {}
        self.points = []
        self.last_draw = 0.
        self.last_status = ''
        self.observation_ready.connect(self.accept_observation)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.last_attempt = 0.
        self.timer.timeout.connect(self.tick)
        QGuiApplication.instance().aboutToQuit.connect(self.close)

    def status(self, message):
        if message != self.last_status:
            self.last_status = message
            self.status_changed.emit(message)

    def configure(self, settings, points):
        if settings.get('地图') != self.settings.get('地图'):
            self.engine = MapMaskEngine()
        self.generation += 1
        self.settings = dict(settings)
        self.points = list(points)
        self.overlay.hide()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.generation += 1
        self.overlay.hide()
        if self.enabled:
            self.engine = MapMaskEngine()
            self.executor.enable_frame_snapshots()
            self.status('等待前台游戏与有效地图画面')
            self.timer.start()
            self.tick()
        else:
            self.timer.stop()
            self.status('地图遮罩已关闭')

    def tick(self):
        if not self.enabled or self.closed: return
        try:
            context = game_context(self.executor)
        except Exception:
            context = None
        if context is None:
            self.overlay.hide()
            self.status('等待游戏前台窗口；切回游戏后自动显示')
            return
        if time.monotonic()-self.last_draw > 1.2: self.overlay.hide()
        if self.busy: return
        if time.monotonic()-self.last_attempt < .4: return
        self.last_attempt = time.monotonic()
        self.busy = True
        generation, settings, points, engine = self.generation, dict(self.settings), list(self.points), self.engine
        threading.Thread(target=self.observe, args=(generation, context, settings, points, engine),
                         name='MapPointObservation', daemon=True).start()

    def observe(self, generation, context, settings, points, engine):
        packet = {'generation': generation, 'context': context, 'markers': [], 'mode': '', 'message': ''}
        try:
            if self.executor.current_task is not None and not self.executor.paused:
                snapshot = self.executor.get_frame_snapshot()
                if snapshot is None or time.time()-snapshot[1] > .8:
                    raise RuntimeError('等待任务提供新画面')
                frame = snapshot[0]
            else:
                capture = self.executor.device_manager.capture_method
                if capture is None or not capture.connected(): raise RuntimeError('请先在连接页选择游戏窗口')
                frame = capture.get_frame()
            if frame is None: raise RuntimeError('未获得有效游戏画面')
            features = self.executor.feature_set
            cache = {}
            def has_feature(name):
                if name not in cache:
                    cache[name] = bool(features.find_one_feature(frame, name, threshold=.92))
                return cache[name]
            observation = engine.observe(frame, has_feature, settings.get('地图', '自动识别'))
            packet['message'] = observation.message
            viewport = observation.viewport
            if viewport is not None:
                allowed = settings.get('显示大地图', True) if viewport.mode == 'bigmap' else settings.get('显示小地图', True)
                if allowed:
                    packet['markers'] = project_points(points, viewport)
                    packet['mode'] = viewport.mode
                    packet['message'] += f' · {len(packet["markers"])} 个可见点位'
                else: packet['message'] = '当前地图图层已关闭'
        except Exception as error:
            packet['message'] = str(error)
        try:
            self.observation_ready.emit(packet)
        except RuntimeError:
            pass  # Qt has already destroyed the window during shutdown.

    def accept_observation(self, packet):
        self.busy = False
        if self.closed or not self.enabled or packet['generation'] != self.generation: return
        try:
            context = game_context(self.executor)
        except Exception:
            context = None
        if context is None or context != packet['context']:
            self.overlay.hide()
            return
        self.status(packet['message'])
        if not packet['mode'] or not packet['markers']:
            self.overlay.hide()
            return
        self.overlay.setGeometry(*qt_geometry(*context))
        self.overlay.setWindowOpacity(max(.2, min(1., self.settings.get('透明度', 85)/100)))
        self.overlay.set_markers(packet['markers'], self.settings.get('显示名称', True))
        self.overlay.show()
        self.last_draw = time.monotonic()

    def close(self):
        self.closed = True
        self.enabled = False
        self.generation += 1
        self.timer.stop()
        self.overlay.close()
