import unittest


class CrystalPort:
    def __init__(self, observations):
        self.events=[]
        self.observations=list(observations)
    def stage(self,label):self.events.append(label)
    def teleport_hub(self):self.events.append('teleport')
    def ring_bell(self):self.events.append('bell')
    def locate_crystals(self):self.events.append('locate');return self.observations.pop(0)
    def run_route(self,name):self.events.append(('route',name));return {'status':'succeeded','message':'已确认三份','materials':{'星光结晶':3}}


class StarseaCrystalTests(unittest.TestCase):
    def test_no_crystal_exit_clears_bell_context(self):
        from nuannuan.starsea_crystal import StarseaCrystalRunner
        port=CrystalPort([None,None])
        cleaned=[]
        port.finish=lambda:cleaned.append(True)
        StarseaCrystalRunner(port).run()
        self.assertEqual(cleaned,[True])

    def test_detected_location_selects_its_own_route_in_source_order(self):
        from nuannuan.starsea_crystal import StarseaCrystalRunner
        port=CrystalPort([(3082.,1893.)])
        result=StarseaCrystalRunner(port).run()
        self.assertEqual(result['status'],'succeeded')
        self.assertIn(('route','星海拾光_星光结晶收集_泡泡梦屿'),port.events)
        self.assertEqual([item for item in port.events if item in {'teleport','bell','locate'}],['teleport','bell','locate'])

    def test_no_markers_only_rings_once_more_and_never_runs_default_route(self):
        from nuannuan.starsea_crystal import StarseaCrystalRunner
        port=CrystalPort([None,None])
        result=StarseaCrystalRunner(port).run()
        self.assertEqual(result['status'],'skipped')
        self.assertEqual(port.events.count('bell'),2)
        self.assertFalse(any(isinstance(event,tuple) for event in port.events))

    def test_unknown_location_does_not_fall_back_to_hub_route(self):
        from nuannuan.starsea_crystal import StarseaCrystalRunner
        port=CrystalPort([(5000,5000)])
        result=StarseaCrystalRunner(port).run()
        self.assertEqual(result['status'],'partial')
        self.assertFalse(any(isinstance(event,tuple) for event in port.events))

    def test_route_zero_result_is_kept_as_partial(self):
        from nuannuan.starsea_crystal import StarseaCrystalRunner
        port=CrystalPort([(1679,2000)])
        port.run_route=lambda name:{'status':'partial','message':'零获得','materials':{'星光结晶':0}}
        self.assertEqual(StarseaCrystalRunner(port).run()['status'],'partial')

    def test_sprite_matching_suppresses_duplicate_responses(self):
        import cv2
        import numpy as np
        from nuannuan.tracking_vision import sprite_matches
        rng=np.random.default_rng(16)
        image=rng.integers(30,230,(20,20,3),np.uint8)
        frame=np.full((200,300,3),20,np.uint8)
        frame[30:50,50:70]=image
        frame[80:100,150:170]=image
        matches=sprite_matches(frame,image,threshold=.95,limit=5)
        self.assertEqual(len(matches),2)
