from collections import deque
from random import shuffle

import scripter
from misc import hnum
from switch import SW_TYPE_1FIFO
from uconf import BN_BITRATE, CLIENTS

CONF_RANGE = 'range'
CONF_WC = 'wc'
CONF_HALF = 'half'


def main():
    num_rates = 3
    rates = [i * BN_BITRATE / num_rates for i in range(1, num_rates)]
    defaults = dict(marking_rates=rates, rtt=40, num_conn=2)
    source_confs = [defaults for _ in range(len(CLIENTS) * 2)]
    scripter.gen_scripts(source_confs=source_confs, sw_type=SW_TYPE_1FIFO)


def rates_fan(num_sources, num_bands, alpha):
    """
    Dispose rates all around the source_cap. Alpha controls the distance between source_cap and the first/last rate.
    With alpha->1, distance->source_cap
    """
    source_cap = BN_BITRATE / num_sources
    assert 0 < alpha < 1, 'must be 0 < alpha < 1'
    min_rate = source_cap * (1 - alpha)
    num_rates = num_bands - 1
    # print "source cap: %s" % hnum(source_cap)
    if num_bands % 2 == 0:
        rate_step = (source_cap - min_rate) / (num_rates / 2)
    else:
        rate_step = (source_cap - min_rate) / (((num_rates - 1) / 2) + 0.5)
    # print "rate step: %s" % hnum(rate_step)
    return [min_rate + (rate_step * i) for i in range(num_rates)]


def rates_min1st(num_sources, num_bands, alpha):
    """
    Dispose rates on top of source_cap. Alpha controls the distance from source cap to the last rate.
    With alpha->+inf, distance->min(source_cap * alpha, BN_BITRATE - source_cap)
    """
    source_cap = BN_BITRATE / num_sources
    num_rates = num_bands - 1
    assert alpha > 0, 'must be alpha > 0'
    rate_range = min(source_cap * alpha, BN_BITRATE - source_cap)
    rate_step = rate_range / num_rates
    return [source_cap + (rate_step * i) for i in range(num_rates)]


def gen_source_confs(spc, conn_conf, rtt_conf, rate_conf):
    source_confs = [None] * spc * len(CLIENTS)
    num_sources = len(source_confs)

    # Assign number of connections to each one
    if not conn_conf:
        conns = [2 for _ in range(num_sources)]
    elif conn_conf['type'] == CONF_RANGE:
        conn_range = conn_conf['range']
        conn_width = conn_range[1] - conn_range[0]
        if conn_width > num_sources:
            conn_step = conn_width / (num_sources - 1)
            conns = [conn_range[0] + x * conn_step for x in range(num_sources)]
        else:
            num_conns = range(conn_range[0], conn_range[1] + 1)
            conns = [num_conns[x % len(num_conns)] for x in range(num_sources)]
    elif conn_conf['type'] == CONF_WC:
        min_conn = min(conn_conf['range'])
        max_conn = max(conn_conf['range'])
        conns = [max_conn for _ in range(num_sources)]
        conns[0] = min_conn
    elif conn_conf['type'] == CONF_HALF:
        conns = [conn_conf['range'][i % 2] for i in range(num_sources)]
    else:
        raise UgException('Unknown conn_conf type %s' % conn_conf['type'])

    assert min(conns) > 1, "Minimum number of connections per source is 2"

    shuffle(conns)

    # Assign RTTs
    if not rtt_conf:
        rtts = [0 for _ in range(num_sources)]
    elif rtt_conf['type'] == CONF_RANGE:
        rtt_range = rtt_conf['range']
        rtt_step = (rtt_range[1] - rtt_range[0]) / float(num_sources - 1)
        rtts = [rtt_range[0] + rtt_step * x for x in range(num_sources)]
    elif rtt_conf['type'] == CONF_WC:
        min_rtt = min(rtt_conf['range'])
        max_rtt = max(rtt_conf['range'])
        rtts = [min_rtt for _ in range(num_sources)]
        rtts[0] = max_rtt
    elif rtt_conf['type'] == CONF_HALF:
        rtts = [rtt_conf['range'][i % 2] for i in range(num_sources)]
    else:
        raise UgException('Unknown rtt_conf type %s' % conn_conf['type'])

    shuffle(rtts)

    info = dict()
    # Rate bands
    source_cap = BN_BITRATE / num_sources
    info['source_cap'] = source_cap
    if rate_conf:
        num_bands = rate_conf['num_bands']
        if num_bands > 2:
            rates = rate_conf['func'](num_sources=num_sources, num_bands=num_bands, alpha=rate_conf['alpha'])
        elif num_bands == 2:
            rates = [source_cap]
        else:
            raise UgException("Invalid num_bands %s" % num_bands)
        assert len(rates) == num_bands - 1
    else:
        rates = None

    for i in range(num_sources):
        source_confs[i] = dict(source_cap=source_cap, marking_rates=rates, num_conn=int(conns[i]),
                               rtt=int(round(rtts[i])))

    return source_confs, info


class UgException(Exception):
    pass


if __name__ == '__main__':
    rate_conf = dict(num_bands=4, func=rates_fan, alpha=0.5)
    source_confs, info = gen_source_confs(spc=10, rate_conf=rate_conf,
                                          conn_conf=dict(type=CONF_HALF, range=(2, 20)),
                                          rtt_conf=dict(type=CONF_HALF, range=(1, 100)))

    print info

    print (len(source_confs))

    for conf in source_confs:
        print "%s conn x RTT %s ms -> rates %s" % (conf['num_conn'], conf['rtt'], map(hnum, conf['marking_rates']))
