"""Qt equivalent of the isolated official PearPal login window."""
import json
from urllib.parse import urlsplit
from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout
from qfluentwidgets import BodyLabel, PushButton, isDarkTheme
from nuannuan.config import ROOT
from nuannuan.pearpal_bridge import credentials_from_page
from nuannuan._pearpal.pearpal_regions import get_pearpal_region


class PearPalLogin(QDialog):
    def __init__(self, provider, region, parent=None):
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView
        # Keep Chromium's native surface out of FluentWindow's translucent
        # parent/child composition chain. Ownership is handled on app shutdown.
        super().__init__(None, Qt.Window)
        self._owner = parent
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        self.setObjectName('officialMapLogin')
        self.setStyleSheet('QDialog#officialMapLogin { background: '+('#202020' if isDarkTheme() else '#f3f3f3')+'; }')
        self.provider, self.region = provider, region
        self._submitted = None
        self._clearing = False
        self._loading = True
        self.setWindowTitle('登录官方美鸭梨地图' if region == 'cn' else 'Log in to official PearPal')
        self.resize(1024, 760)
        layout = QVBoxLayout(self)
        self.status = BodyLabel('请在下方官方页面登录，完成后自动同步收集进度。', self)
        layout.addWidget(self.status)
        folder = ROOT/'configs/pearpal-browser'/region
        folder.mkdir(parents=True, exist_ok=True)
        self.profile = QWebEngineProfile('nuannuan-pearpal-'+region, self)
        self.profile.setPersistentStoragePath(str(folder/'storage'))
        self.profile.setCachePath(str(ROOT/'.cache/pearpal-browser'/region))
        self.web = QWebEngineView(self)
        self.web.setPage(QWebEnginePage(self.profile, self.web))
        layout.addWidget(self.web, 1)
        self.submit_button = PushButton('完成登录并同步', self)
        self.submit_button.clicked.connect(lambda: self.inspect_storage(force=True))
        layout.addWidget(self.submit_button)
        self.reload_button = PushButton('重新加载官方页面', self)
        self.reload_button.clicked.connect(self.web.reload)
        layout.addWidget(self.reload_button)
        self.web.loadStarted.connect(self.on_load_started)
        self.web.loadFinished.connect(self.on_load_finished)
        self.web.page().renderProcessTerminated.connect(self.on_render_terminated)
        self.web.setUrl(QUrl(get_pearpal_region(region).page_url))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(1000)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().aboutToQuit.connect(self.dispose)

    def inspect_storage(self, *, force=False):
        if self._clearing or not self.isVisible(): return
        if getattr(self, '_loading', False):
            if force: self.status.setText('官方页面正在加载，请稍候；长时间无画面可点击重新加载。')
            return
        region = get_pearpal_region(self.region)
        expected = urlsplit(region.page_url)
        origin = expected.scheme+'://'+expected.netloc
        current = urlsplit(self.web.url().toString())
        if (current.scheme, current.netloc) != (expected.scheme, expected.netloc):
            if force: self.status.setText('尚未返回官方地图页面，请先完成官方登录 / 授权。')
            return
        if self.provider.get_user_status()['auth_state'] == 'authenticating':
            if force: self.status.setText('正在核验登录并同步，请稍候。')
            return
        script = '(function(){if(location.origin!=='+json.dumps(origin)+')return null;return JSON.stringify({momoToken:localStorage.getItem("momoToken"),momoNid:localStorage.getItem("momoNid")});})()'
        self.web.page().runJavaScript(script, lambda value: self.accept_storage(origin, value, force))

    def accept_storage(self, origin, payload, force=False):
        if self._clearing or not self.isVisible() or self.provider.get_user_status()['region'] != self.region: return
        try:
            credentials = credentials_from_page(self.region, origin, payload)
        except (ValueError, RuntimeError):
            if force: self.status.setText('未检测到有效登录信息，请在官方页面完成登录后再点击同步。')
            return
        identity = (credentials.token, credentials.openid)
        if identity == self._submitted and not force: return
        self._submitted = identity
        self.provider.authenticate(credentials)
        self.status.setText('已取得官方登录结果，正在核验并同步收集进度…')

    def on_load_started(self):
        self._loading = True
        self.status.setText('正在加载官方地图页面…')

    def on_load_finished(self, ok):
        self._loading = False
        if self._clearing: return
        if not ok:
            self.status.setText('官方页面加载失败，请检查网络后点击“重新加载官方页面”。')
            return
        self.status.setText('官方页面已加载。请完成登录，随后点击“完成登录并同步”。')
        self.inspect_storage()

    def on_render_terminated(self, status, code):
        self._loading = False
        self.status.setText('登录页面渲染进程已退出，请点击“重新加载官方页面”。')

    def poll(self):
        if self._clearing or not self.isVisible(): return
        state = self.provider.get_user_status()
        if state['authenticated']:
            self.status.setText('登录核验与收集进度同步成功，可关闭此窗口返回地图遮罩。')
        elif state.get('auth_error'):
            self.status.setText('登录核验失败。请重新完成官方登录后点击同步；详细状态见地图页。')
        elif state['auth_state'] == 'authenticating':
            self.status.setText('正在核验登录并同步收集进度，请稍候…')
        else: self.inspect_storage()

    def clear_login(self):
        self._clearing = True
        self._submitted = None
        self.provider.clear_login_information()
        self.profile.cookieStore().deleteAllCookies()
        target = get_pearpal_region(self.region).page_url
        def clear(ok):
            self.web.loadFinished.disconnect(clear)
            if not ok:
                self._clearing = False
                self.status.setText('官方页面未能加载，登录清理尚未完成；请重新加载后重试。')
                return
            origin = urlsplit(target)
            expected = origin.scheme+'://'+origin.netloc
            script = '(function(){if(location.origin!=='+json.dumps(expected)+')return false;localStorage.removeItem("momoToken");localStorage.removeItem("momoNid");return true;})()'
            def completed(ok):
                if ok: self._cleared()
                else:
                    self._clearing = False
                    self.status.setText('尚未返回官方地图，未确认登录信息已清除，请重试。')
            self.web.page().runJavaScript(script, completed)
        self.web.loadFinished.connect(clear)
        self.web.setUrl(QUrl(target))

    def _cleared(self):
        self._clearing = False
        self.status.setText('已清除本助手中该区服的登录信息，请重新登录。')

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def dispose(self):
        if getattr(self, '_disposed', False): return
        self._disposed = True
        self._clearing = True
        self.timer.stop()
        self.hide()
        self.web.page().deleteLater()
        self.web.deleteLater()
        self.profile.deleteLater()
        self.deleteLater()
