"""Bounded, structure-only history traversal with explicit boundary evidence."""
import asyncio
import time


def message_key(message):
    return tuple(message.get(k) for k in ('side', 'time', 'text', 'kind'))


def window_key(page):
    # Keep occurrence order and multiplicity. Recycled element IDs alone are
    # not proof of a scroll or of a message's identity.
    return tuple(page.get('bubble_anchors', ()))


def join_adjacent(previous, incoming):
    left, right = list(map(message_key, previous)), list(map(message_key, incoming))
    matches = [n for n in range(1, min(len(left), len(right)) + 1) if left[-n:] == right[:n]]
    if len(matches) != 1:
        return None  # No overlap, or repeated messages make the overlap ambiguous.
    return previous + incoming[matches[0]:]


async def collect_history(read_page, scroll, *, seconds=120, max_up=30, max_down=100,
                          stable_required=3, pause=1.0, slow_pause=2.0,
                          clock=time.monotonic, sleep=asyncio.sleep):
    started = clock()
    pages = []
    number = None
    title = None
    stable = 0
    top = False
    bottom = False
    aligned = True
    reason = 'top_not_confirmed'
    progress = {'up_scrolls': 0, 'down_scrolls': 0, 'top_confirmations': 0, 'bottom_confirmations': 0}

    def check(page):
        nonlocal number, title
        if not page.get('scan_complete'):
            raise ValueError('界面遍历未完整确认，不能据此判断历史边界')
        current = page.get('phone_number')
        current_title = page.get('contact')
        if number and current and current != number:
            raise ValueError('读取期间完整手机号发生变化，已停止，未合并其他会话')
        if title and current_title and current_title != title:
            raise ValueError('读取期间会话标题发生变化，已停止')
        number = number or current
        title = title or current_title
        pages.append(page)

    async def next_page():
        remaining = seconds - (clock() - started)
        if remaining <= 0:
            raise TimeoutError()
        page = await asyncio.wait_for(read_page(), timeout=remaining)
        check(page)
        return page

    def boundary_equal(a, b):
        return (bool(window_key(a)) and window_key(a) == window_key(b)
                and not a.get('loading') and not b.get('loading'))

    current = None
    collected = []
    try:
        current = await next_page()
        for attempt in range(max_up):
            await scroll(True, stable > 0)
            progress['up_scrolls'] += 1
            await sleep(slow_pause if stable else pause)
            newer = await next_page()
            # A missing number requests further upward navigation. It does not
            # establish either the recipient or the historical boundary.
            equal = boundary_equal(current, newer) and bool(newer.get('phone_number'))
            stable = stable + 1 if equal else 0
            progress['top_confirmations'] = stable
            current = newer
            if stable >= stable_required:
                top = True
                break
        if not top:
            reason = 'phone_number_not_confirmed' if not number else 'top_scroll_limit'
        else:
            collected = list(current.get('messages', ()))
            aligned = not bool(current.get('unclassified'))
            stable = 0
            reason = 'bottom_not_confirmed'
            for attempt in range(max_down):
                await scroll(False, stable > 0)
                progress['down_scrolls'] += 1
                await sleep(slow_pause if stable else pause)
                newer = await next_page()
                if boundary_equal(current, newer):
                    stable += 1
                else:
                    stable = 0
                    merged = join_adjacent(collected, list(newer.get('messages', ())))
                    if merged is None:
                        aligned = False
                        reason = 'ambiguous_or_missing_overlap'
                        # Keep individual windows as evidence; never invent an
                        # ordered, deduplicated history across this gap.
                        break
                    collected = merged
                aligned = aligned and not bool(newer.get('unclassified'))
                current = newer
                progress['bottom_confirmations'] = stable
                if stable >= stable_required:
                    bottom = True
                    reason = 'ui_boundaries_confirmed' if aligned else 'unparsed_bubbles'
                    break
            else:
                reason = 'bottom_scroll_limit'
    except TimeoutError:
        reason = 'time_limit'
    except ValueError as exc:
        # Identity changes must never be archived as the selected conversation.
        if '发生变化' in str(exc):
            raise
        reason = 'scan_incomplete: ' + str(exc)

    if not pages:
        raise ValueError('读取失败：未取得完整的界面结构')
    if not number:
        raise ValueError('读取不完整：未确认手机号和历史起点，请保持短信会话打开后重试')
    best = max(pages, key=lambda p: len(p.get('messages', ())))
    messages = collected if top else list(best.get('messages', ()))
    if not messages:
        raise ValueError('读取不完整：没有读到可确认的短信气泡')
    messages = [dict(m, sequence=i+1) for i, m in enumerate(messages)]
    complete = top and bottom and aligned
    scope = ('已确认界面历史起点和终点，逐屏衔接通过；数据库历史完整性未核对' if complete else
             f'读取不完整：{reason}；界面起点{"已确认" if top else "未确认"}，终点{"已确认" if bottom else "未确认"}')
    return {**best, 'phone_number': number, 'contact': title or number, 'messages': messages,
            'ui_start_confirmed': top, 'ui_end_confirmed': bottom, 'ui_history_complete': complete,
            'history_alignment': aligned, 'history_complete': False, 'scope': scope,
            'history_stop_reason': reason, 'history_pages': len(pages), 'boundary_evidence': progress,
            'history_windows': [{'messages': p.get('messages', []), 'loading': p.get('loading', False)} for p in pages],
            'elapsed_seconds': round(clock() - started, 2)}
