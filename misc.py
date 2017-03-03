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
