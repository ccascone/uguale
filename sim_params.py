from copy import copy

from misc import pdict_to_str
from source_conf import CONF_RANGE, rates_fan, CONF_WC, CONF_HALF
from switch import SW_TYPE_1FIFO, SW_TYPE_UGUALE
from uconf import DURATION

noexp = ['rate_conf', 'conn_conf', 'rtt_conf']


def explode_param_list(other_list, original_list, p_name=None):
    new_p_dicts = []
    for val in other_list:
        for p_dict in original_list:
            d = copy(p_dict)
            if p_name not in noexp and isinstance(val, dict):
                d.update(val)
            else:
                assert p_name is not None
                d[p_name] = val
            new_p_dicts.append(d)
    return new_p_dicts


def explode_lines(sim_lines):
    new_sim_lines = []
    for sim_line in sim_lines:
        p_dicts = [{}]
        for p_name in sim_line:
            p_value = sim_line[p_name]
            if isinstance(p_value, (list, tuple)):
                p_dicts = explode_param_list(original_list=p_dicts, other_list=p_value, p_name=p_name)
                p_dicts = explode_lines(p_dicts)
                continue
            if p_name not in noexp and isinstance(p_value, (dict,)):
                other_sim_lines = explode_lines([p_value])
                p_dicts = explode_param_list(original_list=p_dicts, other_list=other_sim_lines)
                continue
            for p_dict in p_dicts:
                p_dict[p_name] = p_value
        new_sim_lines.extend(p_dicts)
    return new_sim_lines


def generate_param_dicts():
    result = []
    for sim_name in sim_groups:
        sim_line = sim_groups[sim_name]
        sim_line['sim_group'] = sim_name
        # apply defaults
        sim_line.update(defaults)
        result.extend(explode_lines([sim_line]))
    return result


defaults = dict(duration=DURATION)
duration = 60
num_bands = 8

conf_range = (2, 20)
rtt_range = (1, 100)

rate_conf_dummy = dict(num_bands=num_bands, func=rates_fan, alpha=0.5)

rate_conf_8_fan = dict(num_bands=num_bands, func=rates_fan, alpha=[round(0.1 * i, 2) for i in range(1, 10)] + [0.99999])

conn_conf_range = dict(type=CONF_RANGE, range=conf_range)
rtt_conf_range = dict(type=CONF_RANGE, range=rtt_range)

conn_conf_wc = dict(type=CONF_WC, range=conf_range)
rtt_conf_wc = dict(type=CONF_WC, range=rtt_range)

conn_conf_half = dict(type=CONF_HALF, range=conf_range)
rtt_conf_half = dict(type=CONF_HALF, range=rtt_range)

conn_confs = [conn_conf_range, conn_conf_half, conn_conf_wc]
rtt_confs = [rtt_conf_range, rtt_conf_half, rtt_conf_wc]

spcs = spc = [1, 10]  # , 100]

sim_groups = {
    # Hazard Detector
    "baseline": dict(sw_type=SW_TYPE_1FIFO, spc=spcs, conn_conf=None, rtt_conf=None, rate_conf=rate_conf_dummy),
    "1fifo_tcp": dict(sw_type=SW_TYPE_1FIFO, spc=spcs, conn_conf=conn_conf_half, rtt_conf=None,
                      rate_conf=rate_conf_dummy),
    "1fifo_rtt": dict(sw_type=SW_TYPE_1FIFO, spc=spcs, conn_conf=None, rtt_conf=rtt_conf_half,
                      rate_conf=rate_conf_dummy),
    "uguale_tcp": dict(sw_type=SW_TYPE_UGUALE, spc=spcs, conn_conf=conn_conf_half, rtt_conf=rate_conf_dummy,
                       rate_conf=explode_lines([rate_conf_8_fan])),
    "uguale_rtt": dict(sw_type=SW_TYPE_UGUALE, spc=spcs, conn_conf=None, rtt_conf=rtt_conf_half,
                       rate_conf=explode_lines([rate_conf_8_fan]))
}

if __name__ == '__main__':

    param_dicts = generate_param_dicts()
    data = []
    for pd in param_dicts:
        print pdict_to_str(pd)
        # data.append(["%s=%s" % (n, v.__name__ if callable(v) else v) for n, v in pd.items()])
    exit()

    col_widths = [0] * max(len(row) for row in data)
    for i in range(len(col_widths)):
        col_widths[i] = max(len(row[i]) if len(row) > i else 0 for row in data)
    for row in data:
        print "".join(row[i].ljust(col_widths[i] + 4) for i in range(len(row)))

    print len(param_dicts)
