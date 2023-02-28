# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import datetime
import json
from os.path import abspath, exists, split
from pathlib import Path
from pprint import pprint
from string import Template
from typing import Dict, List, Optional, Tuple, Union
import argparse

import matplotlib.pyplot as plt
import numpy as np
from tqdm import tqdm

from .current_events_diagram import CurrentEventDiagram
from ..etc import graph_name_list
from currenteventstokg import currenteventstokg_dir


class NumEventsPerYearDiagram(CurrentEventDiagram):
    def __init__(self, basedir, graph_names:List[str]):
        super().__init__("event_per_year", graph_names)

    def count_event_summaries(self, force=True):
        cache_path = self.cache_dir / f"num_event_summaries_per_year_{self.filename}.json"

        if exists(cache_path) and not force:
            num_event_summaries_per_year = self._load_json(cache_path)
        else:
            q = """
                PREFIX coy: <https://schema.coypu.org/global#>
                PREFIX gn: <https://www.geonames.org/ontology#>
                PREFIX dcterms: <http://purl.org/dc/terms/>

                SELECT DISTINCT ?year (COUNT(?e) as ?num) WHERE{
                    ?e  a coy:NewsSummary;
                        coy:hasMentionDate ?date.
                    BIND(YEAR(?date) as ?year).
                } GROUP BY ?year"""

            print(q)
            res_list = self.graph.query(q)

            num_event_summaries_per_year = {}
            for res in res_list:
                for row in res:
                    year = int(row["year"])
                    num = int(row["num"])

                    if year not in num_event_summaries_per_year:
                        num_event_summaries_per_year[year] = 0
                    
                    num_event_summaries_per_year[year] += num
            
            self._dump_json(cache_path, num_event_summaries_per_year)
        
        return num_event_summaries_per_year
    

    def count_topics(self, force=True):
        cache_path = self.cache_dir / f"num_topics_per_year_{self.filename}.json"
        
        if exists(cache_path) and not force:
            num_topic_per_year = self._load_json(cache_path)
        else:
            q = """
                PREFIX coy: <https://schema.coypu.org/global#>
                PREFIX gn: <https://www.geonames.org/ontology#>
                PREFIX dcterms: <http://purl.org/dc/terms/>

                SELECT DISTINCT ?year ?e WHERE{
                    ?e  a coy:TextTopic;
                        coy:hasMentionDate ?date.
                    BIND(YEAR(?date) as ?year).
                }"""

            print(q)
            res_list = self.graph.query(q)
            
            # add topic uris to set per year
            topic_uris_per_year = {}
            for res in res_list:
                for row in res:
                    year = int(row["year"])
                    topic = row["e"]

                    if year not in topic_uris_per_year:
                        topic_uris_per_year[year] = set()
                    
                    topic_uris_per_year[year].add(topic)

            # count topics per year
            num_topic_per_year = { year: len(topics) 
                for year, topics in topic_uris_per_year.items() 
            }
            
            self._dump_json(cache_path, num_topic_per_year)
        
        return num_topic_per_year


    def createDiagram(self, force=True):
        num_topic_per_year = self.count_topics(force)
        num_event_summaries_per_year = self.count_event_summaries(force)

        x_labels = [ str(year) for year in sorted(list(num_topic_per_year.keys())) ]
        
        new_x_labels = []
        for i,x_label in enumerate(x_labels):
            if i%4 == 0:
                l = x_label
            else:
                l = ""
            new_x_labels.append(l)
        x_labels = new_x_labels
        
        data = {
            "Topics": [ num_topic_per_year[y] for y in sorted(list(num_topic_per_year.keys())) ],
            "Event summaries": [ num_event_summaries_per_year[y] for y in sorted(list(num_event_summaries_per_year.keys())) ],
        }
        
        fig, ax = plt.subplots(constrained_layout=True)

        self._create_multi_attr_bar_chart(
            ax, 
            data, 
            x_labels,
            None, 
            "Year",
            "Amount of Events",
        )
        fig.set_figheight(3)
        fig.set_figwidth(4)
        fig.savefig(
            self.diagrams_dir / f"{self.filename}.svg",
            #dpi=400,
            bbox_inches="tight",
        )
        plt.show()


if __name__ == "__main__":
    graphs = graph_name_list(200201, 202212)
    print(graphs)

    parser = argparse.ArgumentParser()
     
    parser.add_argument("-f", '--force',
        action='store_true', 
        help="force")
    
    args = parser.parse_args()

    plt.style.use(currenteventstokg_dir / "resources" / "style.mplstyle")

    NumEventsPerYearDiagram(currenteventstokg_dir, graphs).createDiagram(args.force)
