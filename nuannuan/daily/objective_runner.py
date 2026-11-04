from nuannuan.core.errors import AutomationError

# Whimbox 3.1.1: descending (priority, score), stable for equal cards.
PRIORITIES = {
    'wish': {
        'energy': (5, 200), 'realm': (5, 200), 'bless': (5, 200),
        'monster_realm': (5, 200), 'photo': (5, 100), 'pickup': (4, 200),
        'insect': (3, 200), 'fight': (2, 200), 'minigame': (0, 200),
        'dig': (0, 100), 'upgrade_bless': (0, 100), 'craft': (0, 100),
    },
    'starsea': {
        'animal_three': (5, 300), 'photo': (5, 200), 'place_item': (5, 200),
        'lookbook': (5, 200), 'music': (5, 100), 'group_chat': (5, 100),
        'animal_one': (5, 100), 'bottle_pickup': (4, 200),
        'bottle_photo': (4, 200), 'plane_photo': (4, 200),
        'bottle_delivery': (3, 200), 'bubble_make': (3, 200),
        'coco_pickup': (0, 300), 'fragment_delivery': (0, 300),
        'coco_photo': (0, 200), 'fragment_photo': (0, 200),
        'meteor': (0, 200), 'bubble_photo': (0, 200), 'crystal': (0, 100),
    },
}


def objective_order(board, item):
    priority, score = PRIORITIES[board].get(item.kind, (-1, 0))
    # Original planner keeps screen order when priority and reward are equal.
    return -priority, -score


class ObjectiveRunner:
    def __init__(self, port):
        self.port = port

    def progress(self, board, message, state='running'):
        notify = getattr(self.port, 'workflow_progress', None)
        if notify:
            notify('朝夕心愿' if board == 'wish' else '星海拾光', state, message)

    def run(self, board, *, execute=True):
        self.progress(board, '检查积分和任务完成情况')
        initial = self.port.scan_objectives(board)
        current = initial
        pending = [item.text for item in initial.objectives if not item.completed]
        self.progress(board, f'界面分数 {initial.score}/500；'
                      + ('未完成任务：' + '；'.join(pending) if pending else '无待执行任务或日常积分已达标'))
        attempts = []
        unsupported = []
        if execute:
            # Refresh after each action: one route may satisfy several cards,
            # and reaching the observed score goal ends the remaining actions.
            ordered = sorted(initial.objectives, key=lambda item: objective_order(board, item))
            for item in ordered:
                current_item = next((observed for observed in current.objectives if observed.slot == item.slot), item)
                if current.score >= 500:
                    break
                if current_item.completed:
                    continue
                reason = self.port.supports_objective(board, item)
                if reason:
                    unsupported.append({'slot': item.slot, 'text': item.text, 'reason': reason})
                    self.progress(board, f'跳过 {item.text or "文字未识别"}：{reason}')
                    continue
                try:
                    self.progress(board, f'开始执行：{item.text}；当前 {current.score}/500')
                    self.port.perform_objective(board, item)
                    observed = self.port.scan_objectives(board)
                    card = next((card for card in observed.objectives if card.slot == item.slot), None)
                    current = observed
                    # A successful action call is not evidence that the game accepted it.
                    if observed.score < 500 and (card is None or not card.completed):
                        raise AutomationError('执行后任务卡仍未显示完成，未计入完成项目')
                    attempts.append({'slot': item.slot, 'text': item.text, 'status': 'succeeded',
                                     'confirmation': 'card' if card is not None and card.completed else 'daily_score'})
                    self.progress(board, (f'已确认日常积分 {current.score}/500，停止其余任务'
                                          if current.score >= 500 else f'任务卡已确认完成：{item.text}；当前 {current.score}/500'))
                except AutomationError as error:
                    self.port.evidence(f'{board}_objective_{item.slot}_failed')
                    attempts.append({'slot': item.slot, 'text': item.text, 'status': 'failed', 'message': str(error)})
                    self.progress(board, f'未确认 {item.text}：{error}')
            if current.score < 500:
                current = self.port.scan_objectives(board)
            self.progress(board, '检查并领取已有心愿奖励')
            claimed = self.port.claim_objective_rewards(board)
        else:
            claimed = 0
        result = {
            'status': 'succeeded' if not execute or current.score >= 500 else 'partial',
            'message': f'{"朝夕心愿" if board == "wish" else "星海拾光"}：'
                       + ('日常积分已达标，' if current.score >= 500 else f'识别 {len(current.objectives)} 项，')
                       + f'界面分数 {current.score}/500，确认领取奖励 {claimed} 次',
            'initial': initial.as_dict(), 'snapshot': current.as_dict(),
            'attempts': attempts, 'unsupported': unsupported, 'claimed': claimed,
            'identified_only': not execute,
        }
        self.progress(board, result['message'], result['status'])
        return result
