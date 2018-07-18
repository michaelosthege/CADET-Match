import numpy
import util

import time

from pathlib import Path

from deap import creator
from deap import tools

import os

from cadet import Cadet

import cache

ERROR = {'scores': None,
         'path': None,
         'simulation' : None,
         'error': None,
         'cadetValues':None,
         'cadetValuesKEQ': None}

def fitness(individual, json_path):
    if json_path != cache.cache.json_path:
        cache.cache.setup(json_path)

    scores = []
    error = 0.0

    results = {}
    for experiment in cache.cache.settings['experiments']:
        result = runExperiment(individual, experiment, cache.cache.settings, cache.cache.target, cache.cache)
        if result is not None:
            results[experiment['name']] = result
            scores.extend(results[experiment['name']]['scores'])
            error += results[experiment['name']]['error']
        else:
            return cache.cache.WORST, [], None

    #need
    if cache.cache.roundScores is not None:
        scores = util.RoundToSigFigs(scores, cache.cache.roundScores)
    else:
        scores = scores

    #human scores
    humanScores = numpy.array( [util.product_score(scores), 
                                min(scores), sum(scores)/len(scores), 
                                numpy.linalg.norm(scores)/numpy.sqrt(len(scores)), 
                                error] )

    if cache.cache.roundScores is not None:
        humanScores = util.RoundToSigFigs(humanScores, cache.cache.roundScores)
    else:
        humanScores = humanScores

    for result in results.values():
        if result['cadetValuesKEQ']:
            cadetValuesKEQ = result['cadetValuesKEQ']
            break

    #generate csv
    csv_record = []
    csv_record.extend(['EVO', 'NA'])
    csv_record.extend(["%.5g" % i for i in cadetValuesKEQ])
    csv_record.extend(["%.5g" % i for i in scores])
    csv_record.extend(["%.5g" % i for i in humanScores])
      
    return scores, csv_record, results

def saveExperiments(save_name_base, settings, target, results):
    return util.saveExperiments(save_name_base, settings, target, results, settings['resultsDirEvo'], '%s_%s_EVO.h5')

def plotExperiments(save_name_base, settings, target, results):
    util.plotExperiments(save_name_base, settings, target, results, settings['resultsDirEvo'], '%s_%s_EVO.png')

def runExperiment(individual, experiment, settings, target, cache):
    if 'simulation' not in experiment:
        templatePath = Path(settings['resultsDirMisc'], "template_%s.h5" % experiment['name'])
        templateSim = Cadet()
        templateSim.filename = templatePath
        templateSim.load()
        experiment['simulation'] = templateSim

    return util.runExperiment(individual, experiment, settings, target, experiment['simulation'], float(experiment['timeout']), cache)

def run(cache):
    "run the parameter estimation"
    searchMethod = cache.settings.get('searchMethod', 'SPEA2')
    return cache.search[searchMethod].run(cache, tools, creator)
