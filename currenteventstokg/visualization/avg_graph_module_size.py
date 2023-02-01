# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import argparse
import locale
from atexit import register
from json import dump, dumps, load
from os.path import abspath, exists, split, getsize, basename
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


class AverageGraphModuleSize(CurrentEventDiagram):
    def __init__(self, graph_names:List[str], num_processes:int=1):
        super().__init__(basename(__file__).split(".")[0], graph_names, ["base"], CurrentEventsGraphSplit)
        self.num_processes = num_processes

    
    def create_triple_num_diagram(self, ax, force=False):
        data_cache_path = self.cache_dir / f"size.json"
        if exists(data_cache_path) and not force:
            data = self._load_json(data_cache_path)
        else:
            data = {}
            for graph_module in ["base", "ohg", "osm", "raw"]:
                self._load_graph(self.graph_names, [graph_module])

                data[graph_module] = 0

                q = """
                    SELECT (COUNT(*) as ?num) WHERE{
                        ?a ?b ?c.
                    }"""

                print(q)
                res_list = self.graph.query(q, self.num_processes)

                for res in res_list:
                    for row in res:
                        num = int(row["num"])
                        print(num)
                        data[graph_module] += num
                
                data[graph_module] /= len(res_list)
            
            self._dump_json(data_cache_path, data)
        
        self._create_bar_chart_from_data(
            ax, 
            data, 
            None, 
            "Graph modules", 
            "Average amount of triples"
        )


    def create_file_size_diagram(self, ax, force=False):
        data = {}
        for gm in ["base", "ohg", "osm", "raw"]:
            filenames = [ f"{gn}_{gm}.jsonld" for gn in self.graph_names]
            size_sum = 0
            for f in filenames:
                size_sum += getsize(str(currenteventstokg_dir / "dataset" / f))

            data[gm] = (size_sum / len(filenames)) / 1000000

        self._create_bar_chart_from_data(
            ax, 
            data, 
            None, 
            "Graph modules", 
            "Average file size in MB"
        )
    

    def createDiagram(self, force=True):
        fig, (ax1, ax2) = plt.subplots(1,2, layout="constrained", figsize=(6,3))

        ax1.tick_params(axis='x', which='minor', bottom=False)
        ax2.tick_params(axis='x', which='minor', bottom=False)

        self.create_triple_num_diagram(ax1, force)
        self.create_file_size_diagram(ax2, force)
        
        fig.savefig(
            self.diagrams_dir / f"{self.filename}.svg",
            #dpi=400,
        )
        plt.show()



if __name__ == "__main__":
    graphs = graph_name_list(202001, 202208)
    print(graphs)

    parser = argparse.ArgumentParser()
     
    parser.add_argument("-f", '--force',
        action='store_true', 
        help="force")

    parser.add_argument("-np", '--num_processes',
        action='store', 
        type=int,
        default=1,
        help="used processes")
    
    args = parser.parse_args()

    plt.style.use(currenteventstokg_dir / "resources" / "style.mplstyle")
    AverageGraphModuleSize(graphs, args.num_processes).createDiagram(args.force)
    


    