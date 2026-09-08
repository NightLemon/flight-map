"""Small viewport intersection helper; segments crossing the dateline follow the short arc."""

import json


def _segment(a, b, west, south, east, north):
    low, high = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in [(-dx, a[0] - west), (dx, east - a[0]), (-dy, a[1] - south), (dy, north - a[1])]:
        if p == 0:
            if q < 0:
                return False
            continue
        ratio = q / p
        if p < 0:
            low = max(low, ratio)
        else:
            high = min(high, ratio)
        if low > high:
            return False
    return True


def line_intersects(encoded, west, south, east, north):
    geometry = json.loads(encoded) if isinstance(encoded, str) else encoded
    points = geometry.get("coordinates", [])
    intervals = [(west, east)] if west <= east else [(west, 180), (-180, east)]
    for a, b in zip(points, points[1:], strict=False):
        bx = b[0]
        if bx - a[0] > 180:
            bx -= 360
        elif bx - a[0] < -180:
            bx += 360
        for left, right in intervals:
            for shift in (-360, 0, 360):
                if _segment(a, [bx, b[1]], left + shift, south, right + shift, north):
                    return True
    return False
