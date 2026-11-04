"""Shared text and number validation helpers used by every flow."""
import re

from nuannuan.core.errors import AutomationError


def require(condition, message):
    if not condition:
        raise AutomationError(message)


def read_fraction(text):
    text = re.sub(r'[vV√★☆\s]', '', text or '')
    match = re.fullmatch(r'(\d{1,5})/(\d{1,5})', text)
    require(match is not None, f'数量识别不可靠：{text!r}')
    current, total = map(int, match.groups())
    require(0 <= current <= total and total > 0, f'数量范围无效：{text!r}')
    return current, total


def count_option(value, label, maximum=10):
    require(type(value) is int and 1 <= value <= maximum, f'{label}需要 1 至 {maximum} 的整数')
    return value
