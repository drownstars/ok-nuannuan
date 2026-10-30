"""Retry observed page transitions without replaying reward or spending actions."""
from nuannuan.daily import AutomationError, DailyRunner


def open_confirmed_page(port, label, state, opener, *, timeout=12):
    error = AutomationError(f'未确认进入{label}')
    for attempt in range(2):
        # A late frame may already show the target: do not toggle it closed.
        if port.exists(state):
            return
        DailyRunner(port).recover_home()
        try:
            opener()
            if port.wait(state, timeout=timeout):
                return
            if port.exists(state):
                return
            error = AutomationError(f'未确认进入{label}')
        except AutomationError as observed_error:
            error = observed_error
        port.evidence(f'page_{state}_attempt_{attempt + 1}_failed')
        if attempt == 0:
            notify = getattr(port, 'workflow_progress', None)
            if notify:
                notify(f'打开{label}', 'running', '首次页面切换未确认，重新观察后再尝试一次')
    # Preserve the original failure, including a missing intermediate page.
    raise AutomationError(f'{label}两次页面切换均未确认：{error}') from error
