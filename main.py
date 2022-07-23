import argparse 
import string
from src.inputHtml import InputHtml
from src.outputRdf import OutputRdf
from src.outputJson import OutputJson
from src.extraction import Extraction
from src.analytics import Analytics
from src.nominatimService import NominatimService
from src.wikidataService import WikidataService
from rdflib import Graph
from os import makedirs
from os.path import split, abspath
from pprint import pprint

import logging
from pathlib import Path


if __name__ == '__main__':
    __progName__ = "current-events-to-kg"
    __progVersion__ = "1.0"
    __progGitRepo__ = "https://github.com/larsmic/current-events-to-kg"

    basedir, _ = split(abspath(__file__))
    basedir = Path(basedir)

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    # store_true
    parser.add_argument('-fp', '--force_parse', 
        action='store_true', 
        help="Parse again even if graph for this month exists in cache")
    
    parser.add_argument('-ihc', '--ignore_http_cache', 
        action='store_true', 
        help="GET every website")
    
    parser.add_argument('-iwoec', '--ignore_wikidata_osm_entity_cache', 
        action='store_true', 
        help="Query again even if exists in cache")

    parser.add_argument('-iwhllc', '--ignore_wikidata_higher_level_location_cache', 
        action='store_true', 
        help="Query again even if exists in cache")
    
    parser.add_argument('-iwlc', '--ignore_wikidata_label_cache', 
        action='store_true', 
        help="Query again even if exists in cache")

    parser.add_argument('-iwohgc', '--ignore_wikidata_one_hop_graph_cache', 
        action='store_true', 
        help="Query again even if exists in cache")

    parser.add_argument('-sm', '--sample_mode', 
        action='store_true', 
        help="Only include Boulder County Fires Topic from 1.1.2022 with Event")
    
    parser.add_argument('-da', '--development_analytics', 
        action='store_true', 
        help="Enable analytics which were useful during development, which normally would use unnessesary resources.")
    
    parser.add_argument('-nmd', '--no_merged_dataset', 
        action='store_true', 
        help="Disable the creation of a merged Dataset of all months (saves RAM).")
    
    parser.add_argument('-cca', '--create_combined_analytics', 
        action='store_true', 
        help="Only creates analytics report for monthly analytics between start and end argument.")
    
    # store
    parser.add_argument('-msd', '--monthly_start_day', 
        action='store', 
        help="Start day to parse in each month (inclusive)", 
        type=int, 
        default=1)
    
    parser.add_argument('-med', '--monthly_end_day', 
        action='store', 
        help="Last day to parse in each month (inclusive)", 
        type=int, 
        default=31)
    
    parser.add_argument('-s', '--start', 
        action='store', 
        help="Start month to parse (inclusive) format: month/year", 
        type=str, 
        default="1/2022")
    
    parser.add_argument('-e', '--end', 
        action='store', 
        help="Last month to parse (inclusive) format: month/year", 
        type=str, 
        default="1/2022")
    
    parser.add_argument('-cd', '--cache_dir', 
        action='store', 
        help="Cache directory (relative to directory of main.py)", 
        default="./cache/")
    
    parser.add_argument('-dd', '--dataset_dir', 
        action='store', 
        help="Dataset output directory (relative to directory of main.py)", 
        default="./dataset/")
    
    parser.add_argument('-ad', '--analytics_dir', 
        action='store', 
        help="Analytics output directory (relative to directory of main.py)", 
        default="./analytics/")
    
    parser.add_argument('-we', '--wikidata_endpoint', 
        action='store', 
        help="Sets the wikidata sparql endpoint for querying", 
        default="https://query.wikidata.org/sparql")
    
    parser.add_argument("-wrs", '--wikidata_request_spacing',
        action='store',
        type=int,
        help="Minimum seconds between requests to the wikidata endpoint (only change to values allowed by your endpoint!)", 
        default=2)
    
    parser.add_argument('-ne', '--nominatim_endpoint', 
        action='store', 
        help="Sets the nominatim endpoint for querying", 
        default='https://nominatim.openstreetmap.org/')
    
    parser.add_argument("-nrs", '--nominatim_request_spacing',
        action='store', 
        type=int,
        help="Minimum seconds between requests to the nominatim endpoint (only change to values allowed by your endpoint!)", 
        default=2)
    
    
    args = parser.parse_args()

    if args.sample_mode:
        args.start = "1/2022"
        args.end = "1/2022"
        args.monthly_start_day = 1
        args.monthly_end_day = 1

    standard_start_end_days = args.monthly_start_day == 1 and args.monthly_end_day == 31
    
    if args.monthly_start_day > args.monthly_end_day:
        print("monthly_start_day must be smaller than monthly_end_day!")
        quit(1)
    
    
    combined = Analytics(basedir, args, str(Path(args.analytics_dir) / "combined_analytics"))
    
    a = Analytics(basedir, args, args.analytics_dir)
    i = InputHtml(basedir, args, a)
    o = OutputRdf(basedir, args, a, args.dataset_dir)
    n = NominatimService(basedir, args, a, __progName__, __progVersion__, __progGitRepo__, 
        args.nominatim_endpoint, waitBetweenQueries=args.nominatim_request_spacing)
    w = WikidataService(basedir, args, a, __progName__, __progVersion__, __progGitRepo__, 
        args.wikidata_endpoint, minSecondsBetweenQueries=args.wikidata_request_spacing)
    e = Extraction(basedir, i, o, a, n, w, args)

    months = ["January","February","March","April","May","June","July","August","September","October","November","December"]
    
    # start date (inclusive)
    start = args.start.split("/")
    year = int(start[1])
    month = int(start[0])

    # end date (inclusive)
    end = args.end.split("/")
    endYear = int(end[1])
    endMonth = int(end[0])

    graphsNames = ["base", "osm", "raw"]
    monthGraphs = {}
    monthGraphs["base"] = None
    monthGraphs["osm"] = None
    monthGraphs["raw"] = None
    monthGraphs["ohg"] = None

    if not args.no_merged_dataset:
        dataset = {g: Graph() for g in monthGraphs.keys()}

    while(year*100+month <= endYear*100+endMonth):
        
        suffix = months[month-1] + "_" + str(year)
        
        monthAnalyticsAvailable = True

        if not args.create_combined_analytics:
            a.monthStart()

            sourceUrl, page = i.fetchCurrentEventsPage(suffix)
            
            # loading cached graph
            if standard_start_end_days and not args.force_parse:
                print("Trying to load cached graphs for", str(year) + "_" + months[month-1], end="...", flush=True)
                for name in monthGraphs.keys():
                    monthGraphs[name] = o.loadGraph(suffix + "_" + name + ".jsonld")

                month_graphs_exists = all([monthGraphs[x] != None for x in monthGraphs.keys()])
                if month_graphs_exists:
                    print("Done")
                else:
                    print("None found")
            else:
                monthGraphs = {g: None for g in monthGraphs.keys()}
                month_graphs_exists = False
            
            

            # parsing
            if not month_graphs_exists or args.force_parse:                
                monthGraphs = {g: Graph() for g in monthGraphs.keys()}
                e.parsePage(sourceUrl, page, year, months[month-1], monthGraphs)

                if standard_start_end_days:
                    # save monthly analytics
                    a.save(suffix)
            else:
                print("Fetching analytics of", str(year) + "_" + months[month-1], end="...", flush=True)
                try:
                    a.load(suffix)
                    print("Done")
                except:
                    print("Went wrong")
                    monthAnalyticsAvailable = False
            
            # saving cached graph
            for name in monthGraphs.keys():
                if standard_start_end_days:
                    if not month_graphs_exists or args.force_parse:
                        filename = suffix + "_" + name + ".jsonld"
                    else:
                        # skip saving loop
                        break
                else:
                    # month only partially parsed
                    daySpanStr = str(args.monthly_start_day) + "_" + str(args.monthly_end_day)
                    filename = daySpanStr + "_" + suffix + "_" + name + ".jsonld"
                o.saveGraph(monthGraphs[name], filename)

            
            
            if not args.no_merged_dataset:
                # add month to resulting dataset
                print("Merging month in dataset...", end="", flush=True)
                for name in dataset.keys():
                    dataset[name] = dataset[name] + monthGraphs[name]
                print("Done")
            
            a.monthEnd()
        else:
            # Just load analytics
            print("Fetching analytics of", str(year) + "_" + months[month-1], end="...", flush=True)
            try:
                a.load(suffix)
                print("Done")
            except:
                print("Went wrong")
                monthAnalyticsAvailable = False


        # combine monthly analytics
        if monthAnalyticsAvailable:
            combined += a
            a.printAnalytics(title=suffix + " Analytics")

        a.reset()        

        if(month >= 12):
            month = 1
            year += 1
        else:
            month += 1
    
    combined.printAnalytics(title="Combined Analytics")
        
    
    if not args.no_merged_dataset:
        # save dataset
        for name in dataset.keys():
            o.saveGraph(dataset[name], "dataset_" + name + ".jsonld")


    
    
    
        
        


