import random
import math
import numpy
import pandas

from deap import tools
import scipy.signal
from scipy.spatial.distance import cdist
import operator
import functools
from collections import Sequence
from pathlib import Path

from addict import Dict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import tempfile
import os
from cadet import Cadet
import score
import subprocess
import sys
import json
import itertools

from scoop import futures

saltIsotherms = {b'STERIC_MASS_ACTION', b'SELF_ASSOCIATION', b'MULTISTATE_STERIC_MASS_ACTION', 
                 b'SIMPLE_MULTISTATE_STERIC_MASS_ACTION', b'BI_STERIC_MASS_ACTION'}

def smoothing_factor(y):
    return max(y)/1000000.0

def find_extreme(seq):
    try:
        return max(seq, key=lambda x: abs(x[1]))
    except ValueError:
        return [0,0]

def get_times_values(simulation, target, selected = None):

    times = simulation.root.output.solution.solution_times

    isotherm = target['isotherm']

    if isinstance(isotherm, list):
        values = numpy.sum([simulation[i] for i in isotherm],0)
    else:
        values = simulation[isotherm]
    
    if selected is None:
        selected = target['selected']

    return times[selected], values[selected]

def sse(data1, data2):
    return numpy.sum( (data1 - data2)**2 )

def find_peak(times, data):
    "Return tuples of (times,data) for the peak we need"
    #[highs, lows] = peakdetect.peakdetect(data, times, 1)

    #return find_extreme(highs), find_extreme(lows)

    minIdx = numpy.argmin(data)
    maxIdx = numpy.argmax(data)

    return (times[maxIdx], data[maxIdx]), (times[minIdx], data[minIdx])

def find_breakthrough(times, data):
    "return tupe of time,value for the start breakthrough and end breakthrough"
    selected = data > 0.999 * max(data)
    selected_times = times[selected]
    return (selected_times[0], max(data)), (selected_times[-1], max(data))

def generateIndividual(icls, size, imin, imax):
    while 1:
        #ind = icls(random.uniform(imin[idx], imax[idx]) for idx in range(size))
        ind = icls(numpy.random.uniform(imin, imax))
        if feasible(ind):
            return ind

def initIndividual(icls, content):
    return icls(content)

def feasible(individual):
    "evaluate if this individual is feasible"

    return True

print_log = 0

def log(*args):
    if print_log:
        print(args)

def product_score(values):
    values = numpy.array(values)
    if numpy.all(values >= 0.0):
        return numpy.prod(values)**(1.0/len(values))
    else:
        return -numpy.prod(numpy.abs(values))**(1.0/len(values))

def averageFitness(offspring):
    total = 0.0
    number = 0.0
    bestMin = -sys.float_info.max
    bestProd = -sys.float_info.max

    for i in offspring:
        total += sum(i.fitness.values)
        number += len(i.fitness.values)
        bestMin = max(bestMin, min(i.fitness.values))
        bestProd = max(bestProd, product_score(i.fitness.values))
    return total/number, bestMin, bestProd

def smoothing(times, values):
    #temporarily get rid of smoothing for debugging
    #return values
    #filter length must be odd, set to 10% of the feature size and then make it odd if necesary
    filter_length = int(.1 * len(values))
    if filter_length % 2 == 0:
        filter_length += 1
    return scipy.signal.savgol_filter(values, filter_length, 3)
    #return scipy.signal.hilbert(values)

def graph_simulation(simulation, graph):
    ncomp = int(simulation.root.input.model.unit_001.ncomp)
    isotherm = bytes(simulation.root.input.model.unit_001.adsorption_model)

    hasSalt = isotherm in saltIsotherms

    solution_times = simulation.root.output.solution.solution_times

    comps = []

    hasColumn = isinstance(simulation.root.output.solution.unit_001.solution_outlet_comp_000, Dict)

    if hasColumn:
        for i in range(ncomp):
            comps.append(simulation.root.output.solution.unit_001['solution_column_outlet_comp_%03d' % i])
    else:
        for i in range(ncomp):
            comps.append(simulation.root.output.solution.unit_001['solution_outlet_comp_%03d' % i])

    if hasSalt:
        graph.set_title("Output")
        graph.plot(solution_times, comps[0], 'b-', label="Salt")
        graph.set_xlabel('time (s)')
        
        # Make the y-axis label, ticks and tick labels match the line color.
        graph.set_ylabel('mMol Salt', color='b')
        graph.tick_params('y', colors='b')

        colors = ['r', 'g', 'c', 'm', 'y', 'k']
        axis2 = graph.twinx()
        for idx, comp in enumerate(comps[1:]):
            axis2.plot(solution_times, comp, '%s-' % colors[idx], label="P%s" % idx)
        axis2.set_ylabel('mMol Protein', color='r')
        axis2.tick_params('y', colors='r')


        lines, labels = graph.get_legend_handles_labels()
        lines2, labels2 = axis2.get_legend_handles_labels()
        axis2.legend(lines + lines2, labels + labels2, loc=0)
    else:
        graph.set_title("Output")
        
        colors = ['r', 'g', 'c', 'm', 'y', 'k']
        for idx, comp in enumerate(comps):
            graph.plot(solution_times, comp, '%s-' % colors[idx], label="P%s" % idx)
        graph.set_ylabel('mMol Protein', color='r')
        graph.tick_params('y', colors='r')
        graph.set_xlabel('time (s)')

        lines, labels = graph.get_legend_handles_labels()
        graph.legend(lines, labels, loc=0)


def mutPolynomialBoundedAdaptive(individual, eta, low, up, indpb):
    """Adaptive eta for mutPolynomialBounded"""
    scores = individual.fitness.values
    prod = product_score(scores)
    eta = eta + prod * 100
    return tools.mutPolynomialBounded(individual, eta, low, up, indpb)

def plotExperiments(save_name_base, settings, target, results, directory, file_pattern):
    for experiment in settings['experiments']:
        experimentName = experiment['name']
        
        dst = Path(directory, file_pattern % (save_name_base, experimentName))

        numPlots = len(experiment['features']) + 1  #1 additional plot added as an overview for the simulation

        exp_time = target[experimentName]['time']
        exp_value = target[experimentName]['value']

        fig = plt.figure(figsize=[10, numPlots*10])

        graph_simulation(results[experimentName]['simulation'], fig.add_subplot(numPlots, 1, 1))

        for idx,feature in enumerate(experiment['features']):
            graph = fig.add_subplot(numPlots, 1, idx+1+1) #additional +1 added due to the overview plot
            
            featureName = feature['name']
            featureType = feature['type']

            feat = target[experimentName][featureName]

            selected = feat['selected']
            exp_time = feat['time'][selected]
            exp_value = feat['value'][selected]

            sim_time, sim_value = get_times_values(results[experimentName]['simulation'],target[experimentName][featureName])

            if featureType in ('similarity', 'similarityDecay', 'similarityHybrid', 'similarityHybridDecay','curve', 'breakthrough', 'dextran', 'dextranHybrid', 
                               'similarityCross', 'similarityCrossDecay', 'breakthroughCross', 'SSE', 'LogSSE'):
                graph.plot(sim_time, sim_value, 'r--', label='Simulation')
                graph.plot(exp_time, exp_value, 'g:', label='Experiment')
            elif featureType in ('derivative_similarity', 'derivative_similarity_hybrid', 'derivative_similarity_cross', 'derivative_similarity_cross_alt'):
                try:
                    sim_spline = scipy.interpolate.UnivariateSpline(sim_time, smoothing(sim_time, sim_value), s=smoothing_factor(sim_value)).derivative(1)
                    exp_spline = scipy.interpolate.UnivariateSpline(exp_time, smoothing(exp_time, exp_value), s=smoothing_factor(exp_value)).derivative(1)

                    graph.plot(sim_time, sim_spline(sim_time), 'r--', label='Simulation')
                    graph.plot(exp_time, exp_spline(exp_time), 'g:', label='Experiment')
                except:
                    pass
            elif featureType in ('fractionation', 'fractionationCombine'):
                graph_exp = results[experimentName]['graph_exp']
                graph_sim = results[experimentName]['graph_sim']

                colors = ['r', 'g', 'b', 'c', 'm', 'y', 'k']

                for idx,(key,value) in enumerate(graph_sim.items()):
                    (time, values) = zip(*value)
                    graph.plot(time, values, '%s--' % colors[idx], label='Simulation Comp: %s' % key)

                for idx,(key,value) in enumerate(graph_exp.items()):
                    (time, values) = zip(*value)
                    graph.plot(time, values, '%s:' % colors[idx], label='Experiment Comp: %s' % key)
            graph.legend()

        plt.savefig(bytes(dst), dpi=100)
        plt.close()

def saveExperiments(save_name_base, settings,target, results, directory, file_pattern):
    for experiment in settings['experiments']:
        experimentName = experiment['name']

        dst = Path(directory, file_pattern % (save_name_base, experimentName))

        if dst.is_file():  #File already exists don't try to write over it
            return False
        else:
            simulation = results[experimentName]['simulation']
            simulation.filename = bytes(dst)

            for (header, score) in zip(experiment['headers'], results[experimentName]['scores']):
                simulation.root.score[header] = score
            simulation.save()
    return True

def set_simulation(individual, simulation, settings):
    log("individual", individual)

    cadetValues = []
    cadetValuesKEQ = []

    idx = 0
    for parameter in settings['parameters']:
        location = parameter['location']
        transform = parameter['transform']

        try:
            comp = parameter['component']
            bound = parameter['bound']
            indexes = []
        except KeyError:
            indexes = parameter['indexes']
            bound = []

        if bound:
            if transform == 'keq':
                unit = location[0].split('/')[3]
            elif transform == 'log':
                unit = location.split('/')[3]

            if simulation.root.input.model[unit].unit_type == b'CSTR':
                NBOUND = simulation.root.input.model[unit].nbound
            else:
                NBOUND = simulation.root.input.model[unit].discretization.nbound

            boundOffset = numpy.cumsum(numpy.concatenate([[0,], NBOUND]))

        if transform == 'keq':
            for bnd in bound:
                position = boundOffset[comp] + bnd
                simulation[location[0].lower()][position] = math.exp(individual[idx])
                simulation[location[1].lower()][position] = math.exp(individual[idx])/(math.exp(individual[idx+1]))

                cadetValues.append(simulation[location[0]][position])
                cadetValues.append(simulation[location[1]][position])

                cadetValuesKEQ.append(simulation[location[0]][position])
                cadetValuesKEQ.append(simulation[location[1]][position])
                cadetValuesKEQ.append(simulation[location[0]][position]/simulation[location[1]][position])

                idx += 2

        elif transform == "log":
            for bnd in bound:
                if comp == -1:
                    position = ()
                    simulation[location.lower()] = math.exp(individual[idx])
                    cadetValues.append(simulation[location])
                    cadetValuesKEQ.append(simulation[location])
                else:
                    position = boundOffset[comp] + bnd
                    simulation[location.lower()][position] = math.exp(individual[idx])
                    cadetValues.append(simulation[location][position])
                    cadetValuesKEQ.append(simulation[location][position])

                idx += 1

            for index in indexes:
                simulation[location.lower()][index] = math.exp(individual[idx])
                cadetValues.append(simulation[location][index])
                cadetValuesKEQ.append(simulation[location][index])

                idx+=1

    log("finished setting hdf5")
    return cadetValues, cadetValuesKEQ

def runExperiment(individual, experiment, settings, target, template_sim, timeout):
    handle, path = tempfile.mkstemp(suffix='.h5')
    os.close(handle)

    simulation = Cadet(template_sim.root)
    simulation.filename = path

    simulation.root.input.solver.nthreads = int(settings.get('nThreads',1))
    cadetValues, cadetValuesKEQ = set_simulation(individual, simulation, settings)

    simulation.save()

    def leave():
        os.remove(path)
        return None

    try:
        simulation.run(timeout = timeout)
    except subprocess.TimeoutExpired:
        print("Simulation Timed Out")
        return leave()

    #read sim data
    simulation.load()

    simulationFailed = isinstance(simulation.root.output.solution.solution_times, Dict)
    if simulationFailed:
        log(individual, "sim must have failed", path)
        return leave()
    log("Everything ran fine")


    temp = {}
    temp['simulation'] = simulation
    temp['path'] = path
    temp['scores'] = []
    temp['error'] = 0.0
    temp['cadetValues'] = cadetValues
    temp['cadetValuesKEQ'] = cadetValuesKEQ

    for feature in experiment['features']:
        start = float(feature['start'])
        stop = float(feature['stop'])
        featureType = feature['type']
        featureName = feature['name']

        if featureType in ('similarity', 'similarityDecay'):
            scores, sse = score.scoreSimilarity(temp, target[experiment['name']][featureName])
        elif featureType in ('similarityHybrid', 'similarityHybridDecay'):
            scores, sse = score.scoreSimilarityHybrid(temp, target[experiment['name']][featureName])
        elif featureType in ('similarityCross', 'similarityCrossDecay'):
            scores, sse = score.scoreSimilarityCrossCorrelate(temp, target[experiment['name']][featureName])
        elif featureType == 'derivative_similarity':
            scores, sse = score.scoreDerivativeSimilarity(temp, target[experiment['name']][featureName])
        elif featureType == 'derivative_similarity_cross':
            scores, sse = score.scoreDerivativeSimilarityCross(temp, target[experiment['name']][featureName])
        elif featureType == 'derivative_similarity_cross_alt':
            scores, sse = score.scoreDerivativeSimilarityCrossAlt(temp, target[experiment['name']][featureName])
        elif featureType == 'derivative_similarity_hybrid':
            scores, sse = score.scoreDerivativeSimilarityHybrid(temp, target[experiment['name']][featureName]) 
        elif featureType == 'curve':
            scores, sse = score.scoreCurve(temp, target[experiment['name']][featureName])
        elif featureType == 'breakthrough':
            scores, sse = score.scoreBreakthrough(temp, target[experiment['name']][featureName])
        elif featureType == 'breakthroughCross':
            scores, sse = score.scoreBreakthroughCross(temp, target[experiment['name']][featureName])
        elif featureType == 'breakthroughHybrid':
            scores, sse = score.scoreBreakthroughHybrid(temp, target[experiment['name']][featureName])
        elif featureType == 'dextran':
            scores, sse = score.scoreDextran(temp, target[experiment['name']][featureName])
        elif featureType == 'dextranHybrid':
            scores, sse = score.scoreDextranHybrid(temp, target[experiment['name']][featureName])
        elif featureType == 'fractionation':
            scores, sse = score.scoreFractionation(temp, target[experiment['name']][featureName])
        elif featureType == 'fractionationCombine':
            scores, sse = score.scoreFractionationCombine(temp, target[experiment['name']][featureName])
        elif featureType == 'SSE':
            scores, sse = score.scoreSSE(temp, target[experiment['name']][featureName])
        elif featureType == 'LogSSE':
            scores, sse = score.scoreLogSSE(temp, target[experiment['name']][featureName])
        temp['scores'].extend(scores)
        temp['error'] += sse

    return temp

def copyCSVWithNoise(idx, center, noise):
    "read the original json file and create a new set of simulation data and simulation file in a subdirectory with noise"
    settings_file = Path(sys.argv[1])
    with settings_file.open() as json_data:
        settings = json.load(json_data)

        baseDir = Path(settings['resultsDir']) / str(idx)
        baseDir.mkdir(parents=True, exist_ok=True)

        settings['resultsDir'] = str(baseDir)

        del settings['bootstrap']

        #find CSV files
        for experiment in settings['experiments']:
            if 'CSV' in experiment:
                data = numpy.genfromtxt(experiment['CSV'], delimiter=',')
                addNoise(data, center, noise)
                csv_path = Path(experiment['CSV'])
                new_csv_path = baseDir / csv_path.name
                numpy.savetxt(str(new_csv_path), data, delimiter=',')
                experiment['CSV'] = str(new_csv_path)
            for feature in experiment['features']:
                if 'CSV' in feature:
                    data = numpy.genfromtxt(feature['CSV'], delimiter=',')
                    addNoise(data, center, noise)
                    csv_path = Path(feature['CSV'])
                    new_csv_path = baseDir / csv_path.name
                    numpy.savetxt(str(new_csv_path), data, delimiter=',')
                    feature['CSV'] = str(new_csv_path)

        new_settings_file = baseDir / settings_file.name
        with new_settings_file.open(mode="w") as json_data:
            json.dump(settings, json_data)
        return new_settings_file
        

def addNoise(array, center, noise):
    "add noise to an array"
    maxValue = numpy.max(array[:,1])
    randomNoise = numpy.random.normal(center, noise*maxValue, len(array))
    array[:,1] += randomNoise

def bestMinScore(hof):
    "find the best score based on the minimum of the scores"
    idxMax = numpy.argmax([min(i.fitness.values) for i in hof])
    return hof[idxMax]

def similar(a,b):
    "we only need a parameter to 4 digits of accuracy so have the pareto front only keep up to 5 digits for members of the front"
    a = numpy.array(a)
    b = numpy.array(b)
    diff = numpy.abs((a-b)/a)
    return numpy.all(diff < 1e-6)

def gen_plots(directory_path, csv_path, parameter_indexes, scores_indexes):
    comp_two = list(itertools.combinations(parameter_indexes, 2))
    comp_one = list(itertools.combinations(parameter_indexes, 1))

    #3d plots
    prod = list(itertools.product(comp_two, scores_indexes))
    seq = [(directory_path, csv_path, i[0][0], i[0][1], i[1]) for i in prod]
    list(futures.map(plot_3d, seq))
    
    #2d plots
    prod = list(itertools.product(comp_one, scores_indexes))
    seq = [(directory_path, csv_path, i[0][0], i[1]) for i in prod]
    list(futures.map(plot_2d, seq))


def plot_3d(arg):
    directory_path, csv_path, c1, c2, score = arg
    dataframe = pandas.read_csv(csv_path)
    directory = Path(directory_path)

    headers = dataframe.columns.values.tolist()
    #print('3d', headers[c1], headers[c2], headers[score])

    scores = dataframe.iloc[:,score]
    scoreName = headers[score]
    if headers[score] == 'SSE':
        scores = -numpy.log(scores)
        scoreName = '-log(%s)' % headers[score]
    
    fig = plt.figure()
    ax = Axes3D(fig)
    ax.scatter(numpy.log(dataframe.iloc[:,c1]), numpy.log(dataframe.iloc[:,c2]), scores, c=scores, cmap=plt.get_cmap('winter'))
    ax.set_xlabel('log(%s)' % headers[c1])
    ax.set_ylabel('log(%s)' % headers[c2])
    ax.set_zlabel(scoreName)
    filename = "%s_%s_%s.png" % (c1, c2, score)
    plt.savefig(str(directory / filename), bbox_inches='tight')
    plt.close()

def plot_2d(arg):
    directory_path, csv_path, c1, score = arg
    dataframe = pandas.read_csv(csv_path)
    directory = Path(directory_path)
    headers = dataframe.columns.values.tolist()
    #print('2d', headers[c1], headers[score])

    fig = plt.figure()

    scores = dataframe.iloc[:,score]
    scoreName = headers[score]
    if headers[score] == 'SSE':
        scores = -numpy.log(scores)
        scoreName = '-log(%s)' % headers[score]

    plt.scatter(numpy.log(dataframe.iloc[:,c1]), scores, c=scores, cmap=plt.get_cmap('winter'))
    plt.xlabel('log(%s)' % headers[c1])
    plt.ylabel(scoreName)
    filename = "%s_%s.png" % (c1, score)
    plt.savefig(str(directory / filename), bbox_inches='tight')
    plt.close()

def space_plots(cache):
    csv_path = Path(cache.settings['resultsDirBase'], cache.settings['CSV'])
    output = cache.settings['resultsDirSpace']
    
    gen_plots(str(output), str(csv_path), cache.parameter_indexes, cache.score_indexes)