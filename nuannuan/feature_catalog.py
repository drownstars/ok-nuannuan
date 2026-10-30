"""User-facing migration inventory; no source configuration or credentials."""

# name, destination, boundary, original implementation
FEATURES = [
    ('朝夕心愿 / 星海识别执行', '每日任务', '自动 / 只识别；任务卡复核', 'task/daily_task/zhaoxi_task.py'),
    ('每日拍照', '每日任务', '仅未完成拍照任务触发', 'task/photo_task/daily_photo_task.py'),
    ('挖掘 / 奇迹之旅', '每日任务', '已收获结果与再次派遣复核', 'task/daily_task/dig_task_v2.py'),
    ('活跃能量检查', '每日 / 工具', '读取当前值与容量', 'task/daily_task/check_energy_task.py'),
    ('素材激化', '每日 / 工具 / 心愿', '默认能量用途；逐份兑换并复查，剩余大于 100 时继续', 'task/daily_task/jihua_task.py'),
    ('祝福闪光 / 魔物试炼', '每日 / 工具 / 心愿', '需解锁快速挑战；逐次确认，不点最大', 'task/daily_task/bless_task.py'),
    ('每周幻境', '每日 / 工具', '进度检查、选择目标、完成后复核', 'task/daily_task/weekly_realm_task.py'),
    ('奇迹之冠巅峰赛', '每日 / 工具', '推荐搭配、次数上限、进度复核', 'task/mira_crown_task/mira_crown_task.py'),
    ('巅峰赛领取 / 兑换', '扩展功能设置', '兑换列表默认空，每项只兑一份', 'task/mira_crown_task/mira_crown_task.py'),
    ('家园日常 / 采星', '每日 / 工具 / 路线', '自动检测家园入口；按路线执行，获得文本确认', 'task/daily_task/all_in_one_task.py'),
    ('巨陨星检测', '家园日常结果', '读取地图提示并记录', 'task/daily_task/all_in_one_task.py'),
    ('星光结晶收集', '路线与跑图', '路线选择；可在收集前开启化万相', 'task/daily_task/xinghai_run_task.py'),
    ('小游戏', '心愿 / 路线', '需启用支付噗灵，宏与奖励检查', 'task/minigame_task/minigame_task.py'),
    ('钓鱼 / 家园钓星', '工具 / 路线', '抛竿次数上限、视觉状态、获得文本', 'action/fishing.py'),
    ('自动钓鱼辅助', '辅助开关', '手动抛竿后接管当前一竿', 'task/background_task/background_task.py'),
    ('动物清洁 / 动画跳过', '工具 / 辅助开关', '附近清洁；确认能力与跳过标识', 'action/clean_animal.py'),
    ('芳间巡游 / 花套捕虫', '工具 / 辅助开关', '能力已选中时按间隔使用', 'action/flourish.py'),
    ('变大 / 变小 / 化万相 / 械控', '工具 / 路线', '配置能力后使用；械控模式复核', 'action/machine.py'),
    ('宏 / 乐谱执行', '脚本管理', '导入校验后执行；乐谱需演奏界面', 'task/macro_task/run_macro_task.py'),
    ('宏录制', '脚本管理', '仅录游戏前台输入；固定时长，取消不保存', 'task/macro_task/record_macro_task.py'),
    ('路线录制', '脚本管理', '从参考路线流转之柱附近开始；可继续编辑', 'task/navigation_task/record_path_task.py'),
    ('自定义流程', '脚本管理', '路线 / 宏排序；整批预检，失败停止', 'task/custom_flow_task.py'),
    ('页面跳转 / 进入游戏', '常用操作', '只处理已识别页面；登录验证需手动', 'task/common_task/goto_ui_task.py'),
    ('启动 / 关闭游戏', '常用操作', '启动路径由用户选择；退出通过游戏菜单', 'task/common_task/start_game_task.py'),
    ('切换已保存账号', '工具', '需完整显示名称，不导入密码或登录资料', 'task/common_task/change_account_task.py'),
]
LIMITS = [
    ('升级祝福闪光 / 制作服装', '原应用未实现', '有识别规则，没有可迁移的执行流程'),
    ('流星 / 椰果 / 碎片 / 泡泡合影', '原应用未实现', '有识别规则，原任务执行表未接入'),
    ('1.11 大富翁活动', '旧版活动未启用', '保留原始代码；当前没有对应活动画面和入口可验证'),
    ('多账号一条龙 / 关机', '未迁移', '当前仅支持显式切换一个已保存账号；不自动关机'),
]
