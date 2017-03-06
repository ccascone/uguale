powers = [(9, 'G', 'n'), (6, 'M', 'u'), (3, 'K', 'm')]


def hnum(value):
    value = float(value)
    if value == 0:
        return '0'
    for (p, b, s) in powers:
        if value > 10 ** p:
            return ("%.1f" % (value / 10 ** p)).rstrip('0').rstrip('.') + b
        if p != 3 and value < 10 ** -(p - 3):
            return ("%.1f" % (value * 10 ** p)).rstrip('0').rstrip('.') + s
    return ("%.2f" % value).rstrip('0').rstrip('.')


def pdict_to_str(val):
    if callable(val):
        val = val.__name__
    elif isinstance(val, dict):
        pieces = []
        for key in sorted(val.keys()):
            subval = pdict_to_str(val[key])
            pieces.append('%s=%s' % (key, subval))
        val = '{%s}' % ','.join(pieces)
    elif isinstance(val, (tuple, list)):
        val = "(%s)" % ','.join(map(pdict_to_str, val))
    else:
        val = str(val)
    return val


def filter_callables(val):
    if callable(val):
        return val.__name__
    elif isinstance(val, dict):
        new_val = dict()
        for key in val.keys():
            new_val[key] = filter_callables(val[key])
        return new_val
    elif isinstance(val, (tuple, list)):
        return map(filter_callables, val)
    else:
        return val
