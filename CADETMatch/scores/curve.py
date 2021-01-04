import numpy
import scipy.stats
from addict import Dict

import CADETMatch.score as score
import CADETMatch.util as util
import CADETMatch.smoothing as smoothing

name = "curve"


def get_settings(feature):
    settings = Dict()
    settings.adaptive = True
    settings.badScore = 0
    settings.meta_mask = True
    settings.count = 1
    return settings


def run(sim_data, feature):
    "similarity, value, start stop"
    sim_time_values, sim_data_values = util.get_times_values(
        sim_data["simulation"], feature
    )
    selected = feature["selected"]

    exp_data_values = feature["value"][selected]

    temp = [
        score.pear_corr(
            scipy.stats.pearsonr(sim_data_values, feature["smooth_value"])[0]
        )
    ]

    return (
        temp,
        util.sse(sim_data_values, exp_data_values),
        len(sim_data_values),
        sim_time_values,
        sim_data_values,
        exp_data_values,
        [1.0 - i for i in temp],
    )


def setup(sim, feature, selectedTimes, selectedValues, CV_time, abstol, cache):
    name = "%s_%s" % (sim.root.experiment_name, feature["name"])
    s, crit_fs, crit_fs_der = smoothing.find_smoothing_factors(
        selectedTimes, selectedValues, name, cache
    )

    temp = {}
    temp["peak_max"] = max(selectedValues)
    temp["smoothing_factor"] = s
    temp["critical_frequency"] = crit_fs
    temp["critical_frequency_der"] = crit_fs_der
    temp["smooth_value"] = smoothing.smooth_data(
        selectedTimes, selectedValues, crit_fs, s
    )
    return temp


def headers(experimentName, feature):
    name = "%s_%s" % (experimentName, feature["name"])
    temp = ["%s_Similarity" % name]
    return temp
