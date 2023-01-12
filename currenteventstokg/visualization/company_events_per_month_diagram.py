# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import argparse
import locale
from atexit import register
from json import dump, dumps, load
from os.path import abspath, exists, split
from pathlib import Path
from time import sleep, time
from typing import Dict, List, Optional, Tuple, Union
from pprint import pprint

import matplotlib.pyplot as plt
import numpy as np
from wordcloud import WordCloud

from .. import currenteventstokg_dir
from ..etc import graph_name_list, months
from .current_events_diagram import CurrentEventDiagram
from .current_events_graph import CurrentEventsGraphSplit, SPARQLEndpoint, SPARQLEndpoint

from..sleeper import Sleeper



class NumCompanyEventsPerMonthDiagram(CurrentEventDiagram, Sleeper):
    def __init__(self, graph_names:List[str], wikidata_endpoint:str, wd_sleep_time:float=2.0, num_processes:int=1):
        CurrentEventDiagram.__init__(self, "company_events_per_month", graph_names, ["base", "ohg"], CurrentEventsGraphSplit)
        Sleeper.__init__(self)

        self.wikidata = SPARQLEndpoint(wikidata_endpoint)
        self.wd_sleep_time = wd_sleep_time
        self.num_processes = num_processes

        self.is_class_company_subclass_cache_path = currenteventstokg_dir / "cache" / "is_class_company_subclass.json"
        self.is_class_company_subclass_cache = self._load_json(self.is_class_company_subclass_cache_path)

        # save caches after termination
        register(self.__saveCaches)
    

    def __saveCaches(self):
        self._dump_json(self.is_class_company_subclass_cache_path, self.is_class_company_subclass_cache)


    def createDiagram(self, force=True):
        qres_cache_path = self.cache_dir / f"{self.filename}_qres.json"
        if exists(qres_cache_path) and not force:
            res_list = self._load_json(qres_cache_path)
        else:
            q = """
                PREFIX coy: <https://schema.coypu.org/global#>
                PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    
                SELECT DISTINCT ?year ?month ?wd ?type ?e ?text ?link_text WHERE{
                    ?e  a coy:NewsSummary;
                        coy:hasMentionDate ?date;
                        coy:isIdentifiedBy ?c.
 
                    ?c  a nif:Context;
                        nif:isString ?text;
                        nif:subString/nif:subString ?l.

                    ?l  nif:anchorOf ?link_text;
                        gn:wikipediaArticle ?a.

                    ?a  owl:sameAs ?wd.
                    
                    ?wd wdt:P31 ?type.

                    BIND(MONTH(?date) as ?month).
                    BIND(YEAR(?date) as ?year).
                } ORDER BY ?e"""

            print(q)
            res_list = self.graph.query(q, self.num_processes)
            self._dump_json(qres_cache_path, res_list)

        data = {}
        event_texts = set()
        companies = set()
        for res in res_list:
            last_company_event = None
            
            for row in res:
                month = int(row["month"])
                year = int(row["year"])
                event = str(row["e"])
                entity = str(row["wd"])
                entity_type = str(row["type"])
                text = str(row["text"])
                link_text = str(row["link_text"])

                if last_company_event and event == last_company_event:
                    continue

                if self._is_company_subclass(entity_type):
                    if year not in data:
                        data[year] = [np.nan]*12

                    if np.isnan(data[year][month-1]):
                        data[year][month-1] = 0

                    data[year][month-1] += 1

                    last_company_event = event
                    event_texts.add(text)
                    companies.add(link_text)

        event_texts = list(event_texts)
        
        print(f"Number of company event texts  = {len(event_texts)}")
        pprint(companies)
        
        print(data)

        fig = self._create_bar_chart_per_month(
            data, 
            None,
            "Month",
            "Number of events",
        )
        fig.set_figheight(3)
        fig.set_figwidth(4)
        fig.savefig(
            self.diagrams_dir / f"{self.filename}.svg",
            bbox_inches="tight",
        )
        plt.show()

        # wordcloud
        wordcloud = WordCloud(background_color=None, mode="RGBA", height=1000, width=1000).generate(" ".join(event_texts))
        plt.imshow(wordcloud, interpolation='bilinear')
        plt.axis("off")
        plt.savefig(
            self.diagrams_dir / f"{self.filename}_wordcloud.png",
            dpi=400,
        )
        plt.show()


    def countCompanies(self, force=False):
        q = """
        PREFIX coy: <https://schema.coypu.org/global#>
        PREFIX gn: <https://www.geonames.org/ontology#>
        PREFIX nif: <http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>

        SELECT DISTINCT ?wd ?type WHERE{
            ?e  a coy:NewsSummary;
                coy:isIdentifiedBy ?c.
            ?c  a nif:Context;
                nif:subString/nif:subString/gn:wikipediaArticle ?a.
            ?a  a gn:WikipediaArticle;
                owl:sameAs ?wd.
            ?wd wdt:P31 ?type.
        }"""

        print(q)
        res_list = self.graph.query(q, self.num_processes)

        companies = set()
        for res in res_list:
            for row in res:
                entity = str(row["wd"])
                entity_type = str(row["type"])
                #print(year, month, entity, entity_type)

                if self._is_company_subclass(entity_type):
                    companies.add(entity)
        
        print(f"Number of Entites (Company or subclass/similar)  = {len(companies)}")
    

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

    locale.setlocale(locale.LC_ALL,'en_US.UTF-8')
    plt.rcParams['axes.formatter.use_locale'] = True
    plt.style.use(currenteventstokg_dir / "resources" / "style.mplstyle")

    NumCompanyEventsPerMonthDiagram(graphs, args.wikidata_endpoint, args.query_sleep_time, args.num_processes).createDiagram(args.force)
    #NumCompanyEventsPerMonthDiagram(graphs, args.wikidata_endpoint, args.query_sleep_time, args.num_processes).countCompanies(args.force)


    