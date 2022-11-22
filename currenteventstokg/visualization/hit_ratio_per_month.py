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
import datetime

import matplotlib.pyplot as plt
import numpy as np
from wordcloud import WordCloud

from .. import currenteventstokg_dir
from ..etc import graph_name_list, months, month2int
from .current_events_diagram import Diagram
from .current_events_graph import CurrentEventsGraphSplit

from..sleeper import Sleeper



class HitRatioPerMonth(Diagram):
    def __init__(self, graph_names:List[str], num_processes:int=1):
        super().__init__(basename(__file__).split(".")[0], "diagram")
        self.num_processes = num_processes

        self.graph_names = graph_names

    
    def _plot(self, ax:plt.Axes):
        data = {}
        cumu_data = {}
        total_hits = 0
        total_misses = 0
        for gn in self.graph_names:
            print(gn)

            analytics = self._load_json(currenteventstokg_dir / "analytics" / f"{gn}_analytics.json")

            hits = analytics["numArticleCacheHits"]
            misses = analytics["numArticleCacheMisses"]

            month = month2int[gn.split("_")[0]]-1
            year = int(gn.split("_")[1])

            if year not in data:
                data[year] = np.full(12, np.nan)
            
            if year not in cumu_data:
                cumu_data[year] = np.full(12, np.nan)

            total_hits += hits
            total_misses += misses
            
            cumu_data[year][month] = total_hits/(total_hits+total_misses)
            data[year][month] = hits/(hits+misses)
        
        print(data)
        print(cumu_data)

        self._create_plot_per_month(
            [data, cumu_data], 
            None, 
            "Month", 
            "Cache hit ratio",
            ax,
            legend_labels=["per month", "cumulative"]
        )


    def create_diagram(self, force=False):
        fig, ax = plt.subplots()

        self._plot(ax)

        fig.savefig(
            self.diagrams_dir / f"{self.filename}.svg",
            #dpi=400,
            bbox_inches="tight",
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
    HitRatioPerMonth(graphs, args.num_processes).create_diagram(args.force)
    


    