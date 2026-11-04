import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from PySide6.QtCore import QUrl


class LoginFixTests(unittest.TestCase):
    def test_qt_string_callback_is_decoded_before_original_auth_validation(self):
        from nuannuan.pearpal.bridge import credentials_from_page
        payload = json.dumps({'momoToken': '{"token":"abcDEF0123456789"}', 'momoNid': '"12405094"'})
        result = credentials_from_page('cn', 'https://myl.nuanpaper.com', payload)
        self.assertEqual(result.openid, '12405094')

    def test_manual_submit_reports_missing_login_instead_of_silently_returning(self):
        from nuannuan.pearpal.login import PearPalLogin
        provider = SimpleNamespace(get_user_status=lambda: {'region':'cn'}, authenticate=Mock())
        dialog = SimpleNamespace(_clearing=False, isVisible=lambda:True, provider=provider, region='cn',
                                 status=SimpleNamespace(setText=Mock()))
        PearPalLogin.accept_storage(dialog, 'https://myl.nuanpaper.com', '', True)
        provider.authenticate.assert_not_called()
        dialog.status.setText.assert_called_once()

    def test_script_serializes_login_fields_for_qt_callback(self):
        from nuannuan.pearpal.login import PearPalLogin
        page = SimpleNamespace(runJavaScript=Mock())
        dialog = SimpleNamespace(_clearing=False, isVisible=lambda:True, region='cn',
            provider=SimpleNamespace(get_user_status=lambda:{'auth_state':'anonymous'}),
            web=SimpleNamespace(url=lambda:QUrl('https://myl.nuanpaper.com/tools/map'), page=lambda:page),
            accept_storage=Mock())
        PearPalLogin.inspect_storage(dialog, force=True)
        self.assertIn('JSON.stringify', page.runJavaScript.call_args.args[0])
