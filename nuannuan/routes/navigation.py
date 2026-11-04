"""Closed-loop route following; measured displacement calibrates WASD directions."""
import math
import time

from nuannuan.routes.model import RouteError, game_to_map


class RouteRunner:
    def __init__(self, port, *, tolerance=3, max_seconds=1200):
        self.port = port
        self.tolerance = tolerance
        self.max_seconds = max_seconds
        self._forward = None
        self._speed = 20.

    def run(self, route):
        self._forward = None
        started = time.monotonic()
        points = list(route.expanded())
        hint = None
        visited = []
        expected_reached = False
        self._checkpoint = None
        try:
            if hasattr(self.port, 'preflight'):
                self.port.preflight(route)
            if hasattr(self.port, 'prepare_abilities'):
                self.port.prepare_abilities(route)
            if hasattr(self.port,'initialize_map'):
                self.port.initialize_map(route)
            for index, point in enumerate(points):
                if time.monotonic() - started > self.max_seconds:
                    raise RouteError('跑图超过本次最大运行时间')
                target = game_to_map(point.position, route.map_name)
                self.port.progress(index + 1, len(points), point)
                if point.action == 'TELEPORT':
                    self.port.teleport(target, route.map_name)
                    hint = self.port.locate(route.map_name, target)
                    self._forward = None
                    self._checkpoint = target
                    if hasattr(self.port, 'after_teleport'):
                        self.port.after_teleport(route, point)
                else:
                    hint = self._move_to(route, point, target, hint, started)
                    if point.action:
                        self.port.action(point, route)
                visited.append(point.id)
                materials = getattr(self.port, 'material_counts', {})
                if route.material_target and route.expected_count and materials.get(route.material_target, 0) >= route.expected_count:
                    expected_reached = True
                    break
            self.port.evidence('route_finished')
            materials = dict(getattr(self.port, 'material_counts', {}))
            collecting = route.material_target and any(p.action in {'PICK_UP', 'CATCH_INSECT', 'CLEAN_ANIMAL', 'FISHING', 'FISHING_STAR'} for p in points)
            zero = collecting and not materials.get(route.material_target, 0)
            reached = len(visited) == len(points)
            message = f'路线 {route.name} 已确认到达 {len(visited)} 个点位'
            if collecting:
                message += f'；已确认获得{route.material_target} × {materials.get(route.material_target, 0)}'
                if zero: message += '，未确认采集成功'
            if expected_reached: message += '；已达到目标数量，结束跑图'
            return {'status': 'partial' if zero else 'succeeded', 'reached_end': reached, 'route': route.name,
                    'visited': visited, 'materials': materials, 'expected_count_reached': expected_reached, 'message': message}
        except BaseException:
            try:
                self.port.evidence('route_stopped')
            except Exception:
                pass
            raise
        finally:
            self.port.release_all()

    def _move_to(self, route, point, target, hint, started):
        position = self.port.locate(route.map_name, hint)
        stuck = 0
        unstuck_used = False
        for _ in range(300):
            if time.monotonic() - started > self.max_seconds:
                raise RouteError('跑图超过本次最大运行时间')
            check=getattr(self.port,'check_interruption',None)
            recovered=check(route,position,self._checkpoint) if check else None
            if recovered is not None:
                position=recovered
                self._forward=None
                stuck=0
            distance = math.dist(position, target)
            if distance <= self.tolerance:
                confirmed = self.port.locate(route.map_name, position)
                if math.dist(confirmed, target) <= self.tolerance:
                    return confirmed
                position = confirmed
                continue
            if self._forward is None:
                key, duration = 'w', 0.25
            else:
                fx, fy = self._forward
                dx, dy = target[0] - position[0], target[1] - position[1]
                forward, right = dx * fx + dy * fy, dx * -fy + dy * fx
                key = ('w' if forward >= 0 else 's') if abs(forward) >= abs(right) else ('d' if right >= 0 else 'a')
                duration = max(0.06, min(0.5, max(abs(forward), abs(right)) / self._speed * 0.7))
            self.port.pulse(key, duration, jump=point.move_mode == 'JUMP')
            observed = self.port.locate(route.map_name, position)
            dx, dy = observed[0] - position[0], observed[1] - position[1]
            movement = math.hypot(dx, dy)
            if movement < 0.2:
                stuck += 1
                if stuck >= 5:
                    if not unstuck_used and hasattr(self.port,'unstuck'):
                        self.port.unstuck()
                        unstuck_used=True
                        self._forward=None
                        stuck=0
                        position=self.port.locate(route.map_name,position)
                        continue
                    raise RouteError(f'点位 {point.id} 附近移动无反馈或卡住，已停止')
            else:
                if movement > 120 * duration + 10:
                    raise RouteError('位置发生不合理跳变，已停止移动')
                stuck = 0
                observed_forward = {'w': (dx, dy), 's': (-dx, -dy), 'd': (dy, -dx), 'a': (-dy, dx)}[key]
                self._forward = (observed_forward[0] / movement, observed_forward[1] / movement)
                self._speed = min(100, max(1, movement / duration))
                if point.point_type in {'PATH','WAY','PASS'} and not point.action:
                    vx,vy=observed[0]-position[0],observed[1]-position[1]
                    length=vx*vx+vy*vy
                    t=max(0,min(1,((target[0]-position[0])*vx+(target[1]-position[1])*vy)/length)) if length else 0
                    closest=(position[0]+vx*t,position[1]+vy*t)
                    if math.dist(target,closest)<=self.tolerance:
                        return observed
            position = observed
        raise RouteError(f'点位 {point.id} 到达超时')
