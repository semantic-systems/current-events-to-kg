# Copyright: (c) 2022-2023, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import argparse
import logging
import string
from os import makedirs
from os.path import abspath, split, exists
from pathlib import Path
from pprint import pprint
from typing import List
from rdflib import Graph

from .analytics import Analytics
from .extraction import Extraction
from .inputHtml import InputHtml
from .nominatimService import NominatimService
from .outputJson import OutputJson
from .outputRdf import OutputRdf
from .wikidataService import WikidataService
from .falcon2Service import Falcon2Service
from .placeTemplatesExtractor import PlacesTemplatesExtractor
from .etc import months
from .articleExtractor import ArticleExtractor
from .graphConsistencyKeeper import add_dataset_endpoint_args

def print_months(months:List[str]):
    for m in months:
        print(m)

def print_unparsed_months(months:List[str]):
    if months:
        print("These months were skipped due to Exceptions:")
        print_months(months)

def print_missing_analytics_months(months:List[str]):
    if months:
        print("Analytics of these months are NOT included:")
        print_months(months)

if __name__ == '__main__':
    __progName__ = "current-events-to-kg"
    __progVersion__ = "1.0"
    __progGitRepo__ = "https://github.com/larsmic/current-events-to-kg"

    basedir, _ = split(abspath(__file__))
    basedir = Path(basedir)

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter, fromfile_prefix_chars='!')
    # store_true
    parser.add_argument('-fp', '--force_parse', 
        action='store_true', 
        help="Parse again even if graph for this month exists in cache")
    
    parser.add_argument('-iwc', '--ignore_wiki_cache', 
        action='store_true', 
        help="Ignore cache of Wikipedia wiki pages")
    
    parser.add_argument('-icepc', '--ignore_current_events_page_cache', 
        action='store_true', 
        help="Query current events page again even if exists in cache")
    
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

    parser.add_argument('-iwwc', '--ignore_wikidata2wikipedia_cache', 
        action='store_true', 
        help="Query again even if exists in cache")

    parser.add_argument('-ifc', '--ignore_falcon2_cache', 
        action='store_true', 
        help="Query again even if exists in cache")

    parser.add_argument('-sm', '--sample_mode', 
        action='store_true', 
        help="Only include Boulder County Fires Topic from 1.1.2022 with Event")
    
    parser.add_argument('-dsm', '--double_sample_mode', 
        action='store_true', 
        help="Runs a second time on -sm to test caching.")
    
    parser.add_argument('-da', '--development_analytics', 
        action='store_true', 
        help="Enable analytics which were useful during development, which normally would use unnessesary resources.")
    
    parser.add_argument('-md', '--merged_dataset', 
        action='store_true', 
        help="Creation a merged dataset of already parsed months.")
    
    parser.add_argument('-cca', '--create_combined_analytics', 
        action='store_true', 
        help="Only creates analytics report for monthly analytics between start and end argument.")

    parser.add_argument('-coe', '--crash_on_exceptions', 
        action='store_true', 
        help="Program crashes on Exceptions, instead of skipping month.")

    parser.add_argument('-um', '--update_mode', 
        action='store_true', 
        help="If used will update the specified files while only ignoring wikipedia and wikidata caches.")
    
    parser.add_argument('-doe', '--delete_old_entities', 
        action='store_true', 
        help="Will delete old entity versions of currently extracted entities in the graph of the dataset endpoint.")
    
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
    
    # add args required for the graph consitency keeper
    add_dataset_endpoint_args(parser)
    
    args = parser.parse_args()

    # override args in certain modes
    if args.sample_mode or args.double_sample_mode:
        args.start = "1/2022"
        args.end = "1/2022"
        args.monthly_start_day = 1
        args.monthly_end_day = 1
    
    if args.double_sample_mode:
        args.sample_mode = True
    
    if args.update_mode:
        # updating => parse all everything again
        args.force_parse = True
        # Dont update falcon and osm related caches assuming they dont update based on daily events.
        # update wikipedia caches
        args.ignore_current_events_page_cache = True
        args.ignore_wiki_cache = True
        # update wikidata caches
        args.ignore_wikidata_osm_entity_cache = True
        args.ignore_wikidata_label_cache = True
        args.ignore_wikidata_one_hop_graph_cache = True
        args.ignore_wikidata_higher_level_location_cache = True


    standard_start_end_days = args.monthly_start_day == 1 and args.monthly_end_day == 31
    
    if args.monthly_start_day > args.monthly_end_day:
        print("monthly_start_day must be smaller than monthly_end_day!")
        quit(1)
    
    day_span = str(args.monthly_start_day) + "_" + str(args.monthly_end_day)
    
    combined = Analytics(basedir, args, str(Path(args.analytics_dir) / "combined_analytics"))

    parser = "lxml" # "lxml" faster than "html.parser"
    
    a = Analytics(basedir, args, args.analytics_dir)
    i = InputHtml(a, basedir / args.cache_dir, args.ignore_wiki_cache, args.ignore_current_events_page_cache)
    p = PlacesTemplatesExtractor(basedir, args, i, parser)
    o = OutputRdf(basedir, args, a, args.dataset_dir)
    n = NominatimService(basedir, args, a, __progName__, __progVersion__, __progGitRepo__, 
        args.nominatim_endpoint, waitBetweenQueries=args.nominatim_request_spacing)
    w = WikidataService(basedir, args, a, __progName__, __progVersion__, __progGitRepo__, 
        args.wikidata_endpoint, minSecondsBetweenQueries=args.wikidata_request_spacing)
    f = Falcon2Service(basedir, args, a)
    ae = ArticleExtractor(i, a, n, w, f, p, args, parser)
    e = Extraction(basedir, i, o, a, ae, args, parser)

    # start date (inclusive)
    start = args.start.split("/")
    year = int(start[1])
    month = int(start[0])

    # end date (inclusive)
    end = args.end.split("/")
    endYear = int(end[1])
    endMonth = int(end[0])

    monthGraphs = {}
    monthGraphs["base"] = None
    monthGraphs["osm"] = None
    monthGraphs["raw"] = None
    monthGraphs["ohg"] = None
    
    unparsed_months = []
    missing_analytics = []

    while(year*100+month <= endYear*100+endMonth):
        
        month_year = months[month-1] + "_" + str(year)

        # define file prefix e.g. January_2022
        if standard_start_end_days:
            file_prefix = month_year
        else:
            file_prefix = day_span + "_" + month_year
        
        if args.sample_mode:
            file_prefix = "sample"

        # execute in different operation modes        
        if args.create_combined_analytics:
            a.load(file_prefix)
            combined += a
            
        elif args.merged_dataset:
            o.load(file_prefix)

            a.load(file_prefix)
            a.printAnalytics(title=file_prefix + " Analytics")

            combined += a

        else:
            a.monthStart()

            # get current events page
            sourceUrl, page = i.fetchCurrentEventsPage(month_year)
            
            # parse if graphs do not exist
            if not o.exists(file_prefix) or args.force_parse:
                parsing_successful = False
                try:
                    # parse page
                    e.parsePage(sourceUrl, page, year, months[month-1])
                    parsing_successful = True

                except KeyboardInterrupt as ki:
                    print_unparsed_months(unparsed_months)
                    raise ki

                except BaseException as be:
                    if args.crash_on_exceptions:
                        # let program crash
                        raise be
                    else:
                        print("Exception!", be)
                        print("Parsing this month will be skipped!")
                
                a.monthEnd()
                
                # save
                if parsing_successful:
                    # save graphs
                    o.save(file_prefix)

                    # save monthly analytics
                    a.save(file_prefix)
                else:
                    # remember month
                    unparsed_months.append(month_year)
                    missing_analytics.append(month_year)

                # clear graphs for next month
                o.reset()

            else: # == month exists already

                # load analytics for combining
                try:
                    a.load(file_prefix)
                except Exception as e:
                    print(f"Loading analytics from {file_prefix} failed:", e)
                    missing_analytics.append(month_year)

            if month_year not in missing_analytics:
                a.printAnalytics(title=file_prefix + " Analytics")

                # add to combined analytics
                combined += a

            # reset analytics for next month
            a.reset()

        # advance month for next iteration
        if(month >= 12):
            month = 1
            year += 1
        else:
            month += 1
    
    if args.merged_dataset:
        print("Saving merged dataset...")
        o.save("dataset")
    
    # show combined analytics for all month
    print_missing_analytics_months(missing_analytics)
    combined.printAnalytics(title="Combined Analytics")
    
    if unparsed_months:
        print("These months were skipped due to Exceptions:")
        print_months(unparsed_months)
    

    # second run on already cached data to test the cached data integrity
    if args.double_sample_mode:
        print("Run second time on sample mode:")
        sourceUrl, page = i.fetchCurrentEventsPage("January_2022")
        e.parsePage(sourceUrl, page, 2022, "January")
        o.save("sample2")



    
    
    
        
        


