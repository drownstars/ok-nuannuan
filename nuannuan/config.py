from pathlib import Path

from nuannuan import __version__

ROOT = Path(__file__).resolve().parents[1]
KEYS_NAME = '游戏按键'
KEY_DEFAULTS = {'交互': 'f', '拍照': 'p', '奇想日历': 'l', '奇迹之旅': 'j', '地图': 'm',
                '前进': 'w', '后退': 's', '向左': 'a', '向右': 'd', '跳跃': 'space',
                '下坠': 'q', '冲刺': 'shift', '道具': 'z', '摇铃': 'x', '返回': 'backspace',
                '聊天': 'enter', '捕虫能力': '2', '换装': 'c', '能力配置': 'e',
                '活动大厅': 'k', '大世界能力衍生': 'g', '能力衍生': 'r'}
ROUTE_OPTIONS_NAME = '跑图设置'


def make_config():
    from ok import ConfigOption
    from nuannuan.core.interaction import WhimboxInteraction
    from nuannuan.daily.extra import EXTRA_DEFAULTS, EXTRA_SETTINGS
    from nuannuan.map.mask import MAP_NAMES, MASK_DEFAULTS, MASK_SETTINGS
    from nuannuan.routes.ability import ABILITY_DEFAULTS, ABILITY_ICONS, JUMP_ICONS
    import json
    options_path = ROOT/'assets/setting_options.json'
    options = json.loads(options_path.read_text(encoding='utf-8')) if options_path.exists() else {}

    return {
        'version': __version__,
        'gui_title': '暖暖小助手 · 无限暖暖',
        'gui_icon': str(ROOT / 'assets/app-momo.ico'),
        'gui': {'type': 'qt', 'window_size': {'width': 1200, 'height': 820, 'min_width': 1100, 'min_height': 760}},
        'debug': False,
        'locale': 'zh_CN',
        'config_folder': str(ROOT / 'configs'),
        'screenshots_folder': str(ROOT / 'screenshots'),
        'windows': {
            'exe': ['X6Game-Win64-Shipping.exe'],
            'capture_method': ['WGC', 'BitBlt'],
            'interaction': [WhimboxInteraction],
            'start_exe': False,
        },
        'supported_resolution': {'ratio': '16:9', 'min_size': (1280, 720)},
        'template_matching': {
            'template_folder': str(ROOT / 'assets/templates'),
            'default_horizontal_variance': 0.015,
            'default_vertical_variance': 0.015,
            'default_threshold': 0.9,
        },
        'ocr': {
            'lib': 'rapidocr',
            'params': {
                'Det.model_path': str(ROOT / 'assets/ocr/ch_PP-OCRv5_mobile_det.onnx'),
                'Rec.model_path': str(ROOT / 'assets/ocr/ch_PP-OCRv5_rec_mobile_infer.onnx'),
                'Rec.rec_keys_path': str(ROOT / 'assets/ocr/ppocrv5_dict.txt'),
                'Cls.model_path': str(ROOT / 'assets/ocr/ch_ppocr_mobile_v2.0_cls_infer.onnx'),
                'Global.font_path': str(ROOT / 'assets/ocr/FZYTK.TTF'),
                'Global.use_cls': False,
                'Global.text_score': 0.75,
                'EngineConfig.onnxruntime.intra_op_num_threads': 2,
                'EngineConfig.onnxruntime.inter_op_num_threads': 1,
                'EngineConfig.onnxruntime.use_dml': False,
            },
        },
        'global_configs': [ConfigOption(
            KEYS_NAME, KEY_DEFAULTS, description='与游戏设置中的实际键位保持一致。',
            config_description={key: '填写小写键名，例如 f、p、l、j。' for key in KEY_DEFAULTS},
        ), ConfigOption(ROUTE_OPTIONS_NAME, ABILITY_DEFAULTS,
                        description='跑图前根据路线动作与所选能力配置轮盘，保存并复核后开始移动。',
                        config_type={'能力方案': {'min': 1, 'max': 3},
                                     '跳跃能力': {'type': 'drop_down', 'options': list(JUMP_ICONS)},
                                     '主能力': {'type': 'drop_down', 'options': ['自动', *ABILITY_ICONS]}}),
                           ConfigOption(EXTRA_SETTINGS, EXTRA_DEFAULTS,
                                        description='每日自动检测日常进度；心愿指定的幻境优先执行。剩余能量默认素材激化，逐份确认并复查，大于 100 时继续。',
                                        config_type={'快速挑战次数': {'min': 1, 'max': 10},
                                                     '奇迹之冠最多挑战': {'min': 1, 'max': 30},
                                                     '钓鱼抛竿次数': {'min': 1, 'max': 20},
                                                     '小游戏最多重试': {'min': 0, 'max': 3},
                                                     '每日结束操作': {'type':'drop_down','options':['保持游戏','关闭游戏','关闭游戏和助手']},
                                                     '活跃能量用途': {'type': 'drop_down', 'options': ['素材激化', '祝福闪光幻境', '魔物试炼']},
                                                     '激化产物': {'type': 'drop_down', 'options': ['噗灵', '丝线', '闪亮泡泡']},
                                                     '祝福关卡': {'type': 'drop_down', 'options': [v for v in options.get('bless_target', ['古铸剑遗址']) if not v.startswith('不做')]},
                                                     '魔物关卡': {'type': 'drop_down', 'options': [v.split('|')[0].strip() for v in options.get('monster_target', ['攀越']) if not v.startswith('不做')]}}),
                           ConfigOption(MASK_SETTINGS, MASK_DEFAULTS,
                                        description='显示官方点位与本地路线；登录官方地图可同步收集进度。每次启动需手动开启。',
                                        config_type={'透明度': {'min': 20, 'max': 100},
                                                     '地图': {'type': 'drop_down', 'options': ['自动识别', *MAP_NAMES.values()]},
                                                     '预览地图': {'type': 'drop_down', 'options': list(MAP_NAMES.values())}})],
        'custom_tabs': [['nuannuan.ui.home', 'HomeTab'], ['nuannuan.map.tab', 'MapMaskTab'],
                        ['nuannuan.ui.feature_tab', 'FeatureTab'], ['nuannuan.ui.script_tab', 'ScriptTab'], ['nuannuan.routes.tab', 'RouteTab']],
        'onetime_tasks': [['nuannuan.tasks.daily_tasks', name] for name in
                          ['DailyTask', 'RouteTask', 'CaptureCheckTask', 'OperationTask']],
        'trigger_tasks': [['nuannuan.tasks.daily_tasks', 'AutoPickupTask'], ['nuannuan.tasks.daily_tasks', 'AutoDialogueTask'],
                          ['nuannuan.tasks.extra_tasks', 'AutoFishingTask'], ['nuannuan.tasks.extra_tasks', 'AutoCleanTask'],
                          ['nuannuan.tasks.extra_tasks', 'AutoFlourishTask'], ['nuannuan.tasks.extra_tasks', 'AutoFloralTask']],
    }
