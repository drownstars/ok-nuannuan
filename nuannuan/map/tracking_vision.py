"""Reference minimap tracking circles and ability highlight observations."""
import json
import math

import cv2
import numpy as np

from nuannuan.config import ROOT
from nuannuan.map.vision import MapLocator


class TrackingVision:
    def __init__(self):
        self.previous = None
        self.ability_box = json.loads((ROOT/'assets/manifest.json').read_text(encoding='utf-8'))['regions']['AreaAbilityButton']['bbox']

    def marker(self, frame):
        image = MapLocator.reference(frame)[22:222, 81:281]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([13, 90, 160]), np.array([15, 200, 255]))
        cv2.circle(mask, (100, 100), 10, 0, -1)
        circles = cv2.HoughCircles(cv2.GaussianBlur(mask, (3, 3), 1), cv2.HOUGH_GRADIENT,
                                   dp=1, minDist=10, param1=60, param2=8, minRadius=14, maxRadius=18)
        if circles is None:
            return None
        anchor = self.previous or (100, 100)
        candidates = [tuple(map(float, circle[:2])) for circle in circles[0]]
        chosen = min(candidates, key=lambda point: math.dist(anchor, point))
        if math.dist((100, 100), chosen) > 30:
            self.previous = None
            return None
        self.previous = chosen
        return chosen[0]-100, chosen[1]-100

    def ability_ready(self, frame):
        x,y,w,h = self.ability_box
        image = MapLocator.reference(frame)[y:y+h,x:x+w]
        mask = cv2.inRange(cv2.cvtColor(image,cv2.COLOR_BGR2HSV),np.array([0,80,200]),np.array([30,110,255]))
        return np.count_nonzero(mask) > 200


def sprite_matches(frame, image, *, scale=1, threshold=.8, limit=3):
    """Find distinct sprite centers; suppress duplicate template responses."""
    if image is None or frame is None:
        return []
    template = cv2.resize(image[:,:,:3],None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
    h,w=template.shape[:2]
    if frame.shape[0] < h or frame.shape[1] < w or template.std() < 1:
        return []
    scores=cv2.matchTemplate(frame[:,:,:3],template,cv2.TM_CCOEFF_NORMED)
    np.nan_to_num(scores,copy=False,nan=-1,posinf=-1,neginf=-1)
    matches=[]
    for _ in range(limit):
        _,confidence,_,(x,y)=cv2.minMaxLoc(scores)
        if confidence < threshold: break
        matches.append((x+w/2,y+h/2,confidence))
        scores[max(0,y-h//2):min(scores.shape[0],y+h//2+1),max(0,x-w//2):min(scores.shape[1],x+w//2+1)]=-1
    return matches
