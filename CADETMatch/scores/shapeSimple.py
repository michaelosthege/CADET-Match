import CADETMatch.util as util
import CADETMatch.score as score
import scipy.stats
import scipy.interpolate
import numpy
from addict import Dict

name = "ShapeSimple"
settings = Dict()
settings.adaptive = True
settings.badScore = 0
settings.meta_mask = True
settings.count = 3
settings.failure = [0.0] * settings.count, 1e6, 1, numpy.array([0.0]), numpy.array([0.0]), numpy.array([1e6]), [1.0] * settings.count

def run(sim_data, feature):
    "similarity, value, start stop"
    sim_time_values, sim_data_values = util.get_times_values(sim_data['simulation'], feature)
    selected = feature['selected']

    exp_data_values = feature['value'][selected]
    exp_time_values = feature['time'][selected]

    sim_spline = util.create_spline(exp_time_values, sim_data_values, feature['smoothing_factor']).derivative(1)
    exp_spline = util.create_spline(exp_time_values, exp_data_values, feature['smoothing_factor']).derivative(1)
     
    [high, low] = util.find_peak(exp_time_values, sim_data_values)

    time_high, value_high = high

    pearson, diff_time = score.pearson_spline(exp_time_values, sim_data_values, exp_data_values)

    exp_data_values_spline = exp_spline(exp_time_values)
    sim_data_values_spline = sim_spline(exp_time_values)

    pearson_der, diff_time_der = score.pearson_spline(exp_time_values, sim_data_values_spline, exp_data_values_spline)

    temp = [pearson, 
            feature['time_function'](numpy.abs(diff_time)),
            pearson_der]
    return (temp, util.sse(sim_data_values, exp_data_values), len(sim_data_values), 
            sim_time_values, sim_data_values, exp_data_values, [1.0 - i for i in temp])

def setup(sim, feature, selectedTimes, selectedValues, CV_time, abstol, cache):
    name = '%s_%s' % (sim.root.experiment_name,   feature['name'])
    s = util.find_smoothing_factor(selectedTimes, selectedValues, name, cache)

    temp = {}
    temp['peak'] = util.find_peak(selectedTimes, selectedValues)[0]
    temp['time_function'] = score.time_function_cv(CV_time, selectedTimes, temp['peak'][0])
    temp['peak_max'] = max(selectedValues)
    temp['smoothing_factor'] = s
    return temp

def headers(experimentName, feature):
    name = "%s_%s" % (experimentName, feature['name'])
    temp = ["%s_Similarity" % name, "%s_Time" % name,
            "%s_Derivative_Similarity" % name]
    return temp



