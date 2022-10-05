# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import argparse
from atexit import register
from json import dump, dumps, load
from os.path import abspath, exists, split
from pathlib import Path
from time import sleep, time
from typing import Dict, List, Optional, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
from currenteventstokg import currenteventstokg_module_dir
from ..etc import months, graph_name_list

from .current_events_diagram import CurrentEventBarChart
from .current_events_graph import CurrentEventsGraphSplit, SPARQLEndpoint
from..sleeper import Sleeper


class NumCompanyEventsPerMonthDiagram(CurrentEventBarChart, Sleeper):
    def __init__(self, graph_names:List[str], wikidata_endpoint:str, wd_sleep_time:float=2.0, num_processes:int=1):
        CurrentEventBarChart.__init__(self, "company_events_per_month", graph_names, ["base", "ohg"], CurrentEventsGraphSplit)
        Sleeper.__init__(self)

        self.wikidata = SPARQLEndpoint(wikidata_endpoint)
        self.wd_sleep_time = wd_sleep_time
        self.num_processes = num_processes

        self.is_class_company_subclass_cache_path = currenteventstokg_module_dir / "cache" / "is_class_company_subclass.json"
        self.is_class_company_subclass_cache = self.__loadJsonDict(self.is_class_company_subclass_cache_path)

        # save caches after termination
        register(self.__saveCaches)
    
    def __saveCaches(self):
        self.__saveJsonDict(self.is_class_company_subclass_cache_path, self.is_class_company_subclass_cache)

    def __loadJsonDict(self, file_path):
        if(exists(file_path)):
            with open(file_path, mode='r', encoding="utf-8") as f:
                return load(f)
        else:
            return {}
    
    def __saveJsonDict(self, file_path, dic):
        with open(file_path, mode='w', encoding="utf-8") as f:
            dump(dic, f)


    def createDiagram(self, force=True):
        cache_path = self.cache_dir / f"{self.filename}.json"
        if exists(cache_path) and not force:
            data = self.__loadJsonDict(cache_path)
        else:
            q = """
                PREFIX coy: <https://schema.coypu.org/global#>
                PREFIX wdt: <http://www.wikidata.org/prop/direct/>
                SELECT DISTINCT ?year ?month ?wd ?type ?e WHERE{
                    ?e  a coy:Event;
                        coy:hasDate ?date;
                        coy:hasSentence/coy:hasLink/coy:hasReference ?a.
                    ?a  a coy:WikipediaArticle;
                        owl:sameAs ?wd.
                    ?wd wdt:P31 ?type.
                    BIND(MONTH(?date) as ?month).
                    BIND(YEAR(?date) as ?year).
                } ORDER BY ?e"""

            print(q)
            res_list = self.graph.query(q, self.num_processes)

            data = {}
            companies = set()
            for res in res_list:
                last_company_event = None
                
                for row in res:
                    month = int(row["month"])
                    year = int(row["year"])
                    event = str(row["e"])
                    entity = str(row["wd"])
                    entity_type = str(row["type"])
                    #print(year, month, entity, entity_type)

                    companies.add(entity)

                    if last_company_event and event == last_company_event:
                        continue

                    if self._is_company_subclass(entity_type):
                        if year not in data:
                            data[year] = [np.nan]*12

                        if np.isnan(data[year][month-1]):
                            data[year][month-1] = 0

                        data[year][month-1] += 1

                        last_company_event = event
            
            print(f"Number of Entites (Company or subclass/similar)  = {len(companies)}")
            
            # cache
            self.__saveJsonDict(cache_path, data)
        
        print(data)

        fig = self._create_bar_chart_per_month(
            data, 
            "Number of Events with Link to Company Per Month",
            "Month",
            "Number of Events",
        )
        fig.savefig(
            self.diagrams_dir / f"{self.filename}.png",
            dpi=400,
        )
        plt.show()
    
    def _is_company_subclass(self, entity_type:str):
        if entity_type in self.is_class_company_subclass_cache:
            return self.is_class_company_subclass_cache[entity_type]
        else:
            q = f"""
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd: <http://www.wikidata.org/entity/>
ASK{{
    <{entity_type}> wdt:P279*/wdt:P460? wd:Q783794.
}}"""
            res = self.wikidata.query(q)
            isCompany = res["boolean"]
            self.is_class_company_subclass_cache[entity_type] = isCompany
            self.sleepUntilNewRequestLegal(self.wd_sleep_time)
            return isCompany

if __name__ == "__main__":
    graphs = graph_name_list(202001, 202208)
    print(graphs)

    parser = argparse.ArgumentParser()
    
    parser.add_argument("-wde", '--wikidata_endpoint',
        action='store', 
        required=True,
        help="wikidata endpoint url")
    
    parser.add_argument("-f", '--force',
        action='store_true', 
        help="force")
    
    parser.add_argument("-qst", '--query_sleep_time',
        action='store',
        type=float,  
        required=True,
        help="wikidata endpoint min query sleep time")
    
    parser.add_argument("-np", '--num_processes',
        action='store', 
        type=int,
        default=1,
        help="used processes")
    
    args = parser.parse_args()

    NumCompanyEventsPerMonthDiagram(graphs, args.wikidata_endpoint, args.query_sleep_time, args.num_processes).createDiagram(args.force)
