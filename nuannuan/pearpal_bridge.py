"""Thin conversion boundary; loading, authentication and filtering stay upstream."""
import json
from urllib.parse import urlsplit
from nuannuan._pearpal.pearpal_auth import parse_login_storage
from nuannuan._pearpal.pearpal_regions import get_pearpal_region
from nuannuan.map_mask import MaskPoint

LABELS = {'pearpal_star': '奇想星', 'pearpal_dewdrop': '灵感露珠', 'pearpal_box': '宝箱', 'pearpal_read': '阅读物'}


def adapt_points(points):
    return [MaskPoint(point.id, point.name, LABELS.get(point.label_id, point.label_id),
                      point.map_name, point.image_x, point.image_y) for point in points]


def credentials_from_page(region, origin, payload):
    expected = urlsplit(get_pearpal_region(region).page_url)
    actual = urlsplit(origin)
    if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
        raise ValueError('登录结果不是所选官方地图来源')
    if isinstance(payload, str):
        try: payload = json.loads(payload)
        except (ValueError, TypeError): raise ValueError('官方页面尚未返回有效登录状态') from None
    if not isinstance(payload, dict): raise ValueError('官方页面尚未登录')
    return parse_login_storage(payload.get('momoToken'), payload.get('momoNid'))
