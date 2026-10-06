"""Where each pane goes for a terminal of a given size.

    wide (>= WIDE columns)            narrow
    +-------------------------------+ +-----------------+
    | header: title · chapter · room| | header          |
    +--------------------+----------+ +-----------------+
    | story              | menu     | | story           |
    |                    |          | |                 |
    |                    +----------+ +-----------------+
    |                    | here     | | menu            |
    +--------------------+----------+ +-----------------+
    | status: message, or what Enter would do            |
    | footer: the keys                                   |

The sidebar ("here": the room, who and what is in it, what you carry)
shows only when wide and there is room; Tab hides or shows it. A pane
added later is one more entry here and one more widget.
"""

from collections import namedtuple

Rect = namedtuple('Rect', 'y x h w')

MIN_H, MIN_W = 14, 48
WIDE = 90


def layout(h, w, sidebar=True):
    if h < MIN_H or w < MIN_W:
        return {'too_small': True, 'h': h, 'w': w}
    header, status, footer = Rect(0, 0, 1, w), Rect(h - 2, 0, 1, w), Rect(h - 1, 0, 1, w)
    top, body = 1, h - 3
    if w >= WIDE:
        right = max(34, min(52, w * 2 // 5))
        story = Rect(top, 0, body, w - right)
        menu_h = max(8, body * 3 // 5) if sidebar else body
        menu = Rect(top, w - right, menu_h, right)
        side = Rect(top + menu_h, w - right, body - menu_h, right) if sidebar and body - menu_h >= 5 else None
        if side is None:
            menu = Rect(top, w - right, body, right)
    else:
        menu_h = max(7, body * 2 // 5)
        story = Rect(top, 0, body - menu_h, w)
        menu = Rect(top + body - menu_h, 0, menu_h, w)
        side = None
    return {'too_small': False, 'header': header, 'story': story, 'menu': menu, 'side': side,
            'status': status, 'footer': footer, 'overlay': overlay_rect(h, w), 'wide': w >= WIDE}


def overlay_rect(h, w, height=None, width=None):
    oh = min(h - 2, height or h - 4)
    ow = min(w - 2, width or min(100, w - 6))
    return Rect((h - oh) // 2, (w - ow) // 2, oh, ow)
