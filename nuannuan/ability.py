"""Route ability requirements and verified ability-page configuration."""
from nuannuan.routes import RouteError

ABILITY_ICONS = {
    '动物清洁': 'IconAbilityAnimal', '捕虫': 'IconAbilityInsect', '钓鱼': 'IconAbilityFish',
    '万物交响': 'IconAbilityRhythms', '滑翔': 'IconAbilityFly', '变小': 'IconAbilitySmall',
    '变大': 'IconAbilityBig', '黏黏爪': 'IconAbilityStick', '芳间巡游': 'IconAbilityFlourish',
    '化万相': 'IconAbilityShapeshifting', '采星': 'IconAbilityStarCollect', '械控': 'IconAbilityMachine',
}
JUMP_ICONS = {'漂浮': 'IconAbilityFloat', '悬羽': 'IconAbilityWing'}
ABILITY_DEFAULTS = {'跑图前自动配置能力': True, '能力方案': 3, '跳跃能力': '漂浮', '主能力': '自动'}


def required_abilities(route, options):
    required = list(getattr(route, 'abilities', ()))
    if any(point.action == 'CATCH_INSECT' for point in route.points) and '捕虫' not in required:
        required.append('捕虫')
    for action, ability in {'FISHING_STAR': '采星', 'FISHING': '钓鱼', 'CLEAN_ANIMAL': '动物清洁',
                            'FLOURISH': '芳间巡游', 'FLORAL_INSECT': '捕虫', 'MAGNET': '化万相',
                            'BIG': '变大', 'FAIRY_ANIMAL': '变小', 'MACHINE_INFUSE': '械控',
                            'MACHINE_EXTRACT': '械控'}.items():
        if any(point.action == action for point in route.points) and ability not in required:
            required.append(ability)
    active = getattr(route, 'active_ability', '自动')
    if active == '自动':
        active = options.get('主能力', '自动')
    if active == '自动':
        active = required[0] if required else None
    if active and active not in required:
        required.append(active)
    jump = getattr(route, 'jump_ability', '自动')
    if jump == '自动':
        jump = options.get('跳跃能力', '漂浮')
    if not any(point.move_mode == 'JUMP' for point in route.points):
        jump = None
    if any(name not in ABILITY_ICONS for name in required) or (jump and jump not in JUMP_ICONS):
        raise RouteError('路线能力设置无效')
    if len(required) > 8:
        raise RouteError('一条路线最多配置 8 个轮盘能力')
    return tuple(required), jump, active


def allocate_slots(current, required):
    assigned = {}
    for slot, name in current.items():
        if name in required and name not in assigned:
            assigned[name] = slot
    free = [slot for slot in range(1, 9) if slot not in assigned.values()]
    for name in required:
        if name not in assigned:
            if not free:
                raise RouteError('能力轮盘没有可用槽位')
            assigned[name] = free.pop(0)
    return assigned


class AbilityManager:
    def __init__(self, port):
        self.port = port
        self.slots = {}

    def prepare(self, route, options):
        required, jump, active = required_abilities(route, options)
        if not required and not jump:
            return {}
        plan = options.get('能力方案', 3)
        if type(plan) is not int or plan not in {1, 2, 3}:
            raise RouteError('能力方案必须为 1、2 或 3')
        self.port.open_ability_page()
        self.port.choose_ability_plan(plan)
        current = self.port.read_ability_slots()
        assignment = allocate_slots(current, required)
        changed = False
        for name, slot in assignment.items():
            if current.get(slot) != name:
                self.port.set_ability_slot(slot, name)
                changed = True
        if jump and self.port.read_jump_ability() != jump:
            self.port.set_ability_slot('jump', jump)
            changed = True
        if changed:
            self.port.save_abilities()
            # Reopen the page to verify persisted state rather than trusting a click.
            self.port.recover_home()
            self.port.open_ability_page()
            self.port.choose_ability_plan(plan)
        verified = self.port.read_ability_slots()
        for name, slot in assignment.items():
            if verified.get(slot) != name:
                raise RouteError(f'能力保存后复核失败：{name}，已停止跑图')
        if jump and self.port.read_jump_ability() != jump:
            raise RouteError(f'跳跃能力保存后复核失败：{jump}，已停止跑图')
        self.slots = assignment
        self.port.recover_home()
        if active:
            self.port.activate_ability(assignment[active], active)
        return dict(assignment)
