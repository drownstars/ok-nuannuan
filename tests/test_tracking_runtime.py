import unittest
from types import SimpleNamespace

from nuannuan.routes.model import RouteError


class TrackUI:
    def __init__(self, confirm='精确追踪'):
        self.events=[]
        self.confirm=confirm
        self.task=SimpleNamespace(info_set=lambda *args:None)
    def goto_page(self, name):self.events.append(('page',name))
    def wait(self,name,timeout=6):return True
    def click_feature(self,name):self.events.append(('feature',name))
    def text(self,name):return self.confirm
    def key(self,key):self.events.append(('key',key))
    def select_ability(self,name):self.events.append(('ability',name))
    def click_text(self,text,region=None,scroll=False):self.events.append(('text_confirm',text));return True
    def sleep(self,seconds):pass


class TrackingRuntimeTests(unittest.TestCase):
    def adapter(self, confirm='精确追踪'):
        from nuannuan.map.tracking_runtime import TrackingRuntime
        port=TrackUI(confirm)
        runtime=SimpleNamespace(port=port,task=port.task,tracking_material=None,release_all=lambda:None)
        adapter=TrackingRuntime(runtime,'miraland')
        adapter.find_type=lambda kind:port.events.append(('type',kind)) or True
        adapter.find_material=lambda name:port.events.append(('material',name)) or True
        return adapter,port

    def test_tracking_ui_order_and_confirm_before_cache(self):
        adapter,port=self.adapter()
        adapter.enable_tracking('珠链蝶')
        self.assertEqual(port.events[:4],[('page','地图'),('feature','IconUIBigmap'),('type','insect'),('material','珠链蝶')])
        self.assertIn(('text_confirm','精确追踪'),port.events)
        self.assertEqual(adapter.runtime.tracking_material,'珠链蝶')
        previous=len(port.events)
        adapter.enable_tracking('珠链蝶')
        self.assertEqual(len(port.events),previous)

    def test_unknown_tracking_state_does_not_click_or_cache(self):
        adapter,port=self.adapter('未解锁')
        with self.assertRaisesRegex(RouteError,'追踪'):
            adapter.enable_tracking('珠链蝶')
        self.assertIsNone(adapter.runtime.tracking_material)
        self.assertFalse(any(event[0]=='text_confirm' for event in port.events))
