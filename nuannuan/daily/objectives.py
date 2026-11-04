"""OCR task descriptions and UI completion observations (no predicted score)."""
import re
from dataclasses import asdict, dataclass

from nuannuan.core.errors import AutomationError

WISH_CENTERS = [(549, 595), (790, 337), (1112, 378), (1315, 607), (1532, 375)]
STARSEA_CENTERS = [(686, 479), (915, 384), (1138, 402), (1348, 510), (1572, 408)]
KIND_LABELS = {
    'photo': '拍照', 'dig': '美鸭梨挖掘', 'pickup': '植物采集', 'insect': '捕虫', 'fight': '战斗',
    'energy': '消耗活跃能量', 'realm': '素材激化', 'bless': '祝福闪光幻境', 'upgrade_bless': '升级祝福闪光',
    'monster_realm': '魔物试炼', 'craft': '制作服装', 'minigame': '小游戏', 'unknown': '未识别类型',
    'lookbook': '星绘图册点赞', 'bottle_pickup': '漂流瓶拾取', 'bottle_delivery': '漂流瓶投递',
    'bottle_photo': '漂流瓶合影', 'plane_photo': '星芒之翼合影', 'place_item': '放置摆饰',
    'music': '更改音乐', 'group_chat': '聚会聊天', 'animal_one': '化身动物', 'animal_three': '动物互动三次',
    'bubble_make': '制造泡泡', 'bubble_photo': '泡泡合影', 'crystal': '星光结晶', 'meteor': '流星',
    'coco_pickup': '椰果采摘', 'coco_photo': '椰果合影', 'fragment_photo': '星愿碎片合影',
    'fragment_delivery': '星愿碎片投递',
}

# Specific combinations precede general words such as “照片” and “幻境”.
RULES = {
    'wish': [
        ('upgrade_bless', ('升级', '祝福闪光')), ('bless', ('幻境', '祝福闪光')),
        ('realm', ('素材激化',)), ('monster_realm', ('魔物试炼',)),
        ('energy', ('活跃能量',)), ('pickup', ('植物',)), ('insect', ('昆虫',)),
        ('fight', ('魔气怪',)), ('minigame', ('小游戏',)), ('photo', ('照片',)),
        ('photo', ('拍照',)), ('dig', ('挖掘',)), ('craft', ('制作',)),
    ],
    'starsea': [
        ('lookbook', ('星绘图册', '点赞')), ('bottle_photo', ('漂流瓶', '合影')),
        ('bottle_photo', ('星愿瓶', '合影')), ('bottle_pickup', ('漂流瓶', '查看')),
        ('bottle_delivery', ('投递', '信笺')), ('plane_photo', ('星芒之翼', '合影')),
        ('coco_photo', ('举起椰', '照片')), ('coco_pickup', ('椰果采摘',)),
        ('fragment_photo', ('星愿碎片', '照片')), ('fragment_delivery', ('星愿碎片', '投递')),
        ('bubble_photo', ('泡泡', '合影')), ('bubble_make', ('制造', '泡泡')),
        ('animal_three', ('动物互动', '3次')), ('animal_three', ('3次', '动物')),
        ('animal_one', ('不同的动物',)), ('animal_one', ('化身', '动物')),
        ('photo', ('拍下', '你的存在')), ('place_item', ('摆饰',)),
        ('music', ('留声机',)), ('group_chat', ('聚会频道',)),
        ('crystal', ('星光结晶',)), ('meteor', ('流星',)),
    ],
}


def classify(board, text):
    normalized = re.sub(r'\s+', '', text or '').replace('３', '3').replace('三次', '3次')
    for kind, keywords in RULES[board]:
        if all(word in normalized for word in keywords):
            return kind
    return 'unknown'


def parse_score(text):
    match = re.fullmatch(r'\s*(\d{1,3})\s*(?:/\s*500)?\s*', text or '')
    if not match or int(match[1]) not in range(0, 501, 100):
        raise AutomationError(f'任务分数识别不可靠：{text!r}')
    return int(match[1])


@dataclass(frozen=True)
class Objective:
    slot: int
    text: str
    kind: str
    completed: bool


@dataclass(frozen=True)
class Snapshot:
    board: str
    score: int
    objectives: list[Objective]

    def as_dict(self):
        return asdict(self)
