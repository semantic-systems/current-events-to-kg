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
from .current_events_graph import CurrentEventsGraph
from ..etc import graph_name_list
from currenteventstokg import currenteventstokg_dir

class NumEventsPerMonthAverageDiagram(CurrentEventDiagram):
    def __init__(self, basedir, graph_names:List[str]):
        super().__init__(basedir, "event_num_ua_per_month_avg", graph_names)

    def createDiagram(self, force=True):
        q = """
            PREFIX coy: <https://schema.coypu.org/global#>
            PREFIX gn: <https://www.geonames.org/ontology#>
            PREFIX nif: <http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#>
            SELECT DISTINCT ?month (COUNT(?e) as ?num) WHERE{
                ?e  (coy:isOccuringDuring)*/gn:wikipediaArticle <https://en.wikipedia.org/wiki/2022_Russian_invasion_of_Ukraine>;
                    a coy:WikiNews;
                    coy:isIdentifiedBy ?c;
                    coy:hasMentionDate ?date.
                ?c a nif:Context.
                BIND(MONTH(?date) as ?month).
            } GROUP BY ?month"""

        print(q)
        n = CurrentEventsGraph()
        res = n.query(q)

        data = np.zeros(12)
        n = np.zeros(12)

        for row in res:
            num = int(row.num)
            month = int(row.month)

            data[month-1] += num
            n[month-1] += 1
        
        fig = self.createAveragePlot(data, n)
        plt.show()
        
    
    def createAveragePlot(self, data, n):
        y = []
        for i in range(12):
            if n[i] > 0:
                y.append(data[i]/n[i])
            else:
                y.append(0)
        print(y)

        # plot
        fig, ax = plt.subplots()

        x = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'June', 'July', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        ax.bar(x, y)
        
        return fig


class NumEventsPerMonthDiagram(CurrentEventDiagram):
    def __init__(self, basedir, graph_names:List[str]):
        super().__init__("event_num_ua_per_month", graph_names)

    def createDiagram(self, force=True):
        cache_path = self.cache_dir / f"{self.filename}.json"
        if exists(cache_path) and not force:
            data = self.__load_json(cache_path)
        else:
            q = """
                PREFIX coy: <https://schema.coypu.org/global#>
                PREFIX gn: <https://www.geonames.org/ontology#>
                PREFIX nif: <http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#>

                SELECT DISTINCT ?year ?month (COUNT(?e) as ?num) WHERE{
                    ?e  (coy:isOccuringDuring)*/gn:wikipediaArticle <https://en.wikipedia.org/wiki/2022_Russian_invasion_of_Ukraine>;
                        a coy:WikiNews;
                        coy:isIdentifiedBy ?c;
                        coy:hasMentionDate ?date.
                    ?c a nif:Context.
                    BIND(MONTH(?date) as ?month).
                    BIND(YEAR(?date) as ?year).
                } GROUP BY ?year ?month"""

            print(q)
            # fpaths = [basedir / f"{gn}_base.jsonld" for gn in self.graph_names]
            # fpaths = [
            #     Path("../current-events-to-kg/dataset/February_2022_base.jsonld"), 
            #     Path("../current-events-to-kg/dataset/March_2022_base.jsonld")
            # ]
            # n = CurrentEventsGraph(filepaths=fpaths)
            # res = n.query(q)
            res_list = self.graph.query(q)

            data = {}
            for res in res_list:
                for row in res:
                    month = int(row["month"])
                    year = int(row["year"])
                    num = int(row["num"])

                    if year not in data:
                        data[year] = np.full(12, np.nan)
                    data[year][month-1] = num
        
        print(data)
        
        fig = self._create_bar_chart_per_month(
            data, 
            None, 
            "Month",
            "Number of events",
        )
        fig.savefig(
            self.diagrams_dir / f"{self.filename}.svg",
            #dpi=400,
            bbox_inches="tight",
        )
        plt.show()


if __name__ == "__main__":
    graphs = graph_name_list(202202, 202208)
    print(graphs)

    parser = argparse.ArgumentParser()
     
    parser.add_argument("-f", '--force',
        action='store_true', 
        help="force")
    
    args = parser.parse_args()

    plt.style.use(currenteventstokg_dir / "resources" / "style.mplstyle")

    # NumEventsPerMonthAverageDiagram(currenteventstokg_dir, graphs).createDiagram()
    NumEventsPerMonthDiagram(currenteventstokg_dir, graphs).createDiagram(args.force)
