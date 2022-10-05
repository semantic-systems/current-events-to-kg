# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from os import makedirs
from typing import Dict, List, Optional, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
from currenteventstokg import currenteventstokg_module_dir
from currenteventstokg.etc import month2int, months

from .current_events_graph import CurrentEventsGraphSplit, CurrentEventsGraphABC


class CurrentEventDiagram():
    def __init__(self, sub_dir_name:str, graph_names:List[str], graph_modules=["base"], graph_class:CurrentEventsGraphABC=CurrentEventsGraphSplit):
        self.graph_names = graph_names # need to be sorted with first one first!
    
        self.start_month = month2int[self.graph_names[0].split("_")[0]]
        self.end_month = month2int[self.graph_names[-1].split("_")[0]]
        self.start_year = int(self.graph_names[0].split("_")[1])
        self.end_year = int(self.graph_names[-1].split("_")[1])

        filename = ""
        for i,gn in enumerate(self.graph_names):
            if i>0:
                filename += "_"
            filename += gn
        self.filename = filename

        self.cache_dir = currenteventstokg_module_dir / "cache" / sub_dir_name
        makedirs(self.cache_dir, exist_ok=True)

        self.diagrams_dir = currenteventstokg_module_dir / "diagrams/" / sub_dir_name
        makedirs(self.diagrams_dir, exist_ok=True)

        self.graph = graph_class(graph_names=graph_names, graph_modules=graph_modules)
    


class CurrentEventBarChart(CurrentEventDiagram):
    def __init__(self, sub_dir_name:str, graph_names:List[str], graph_modules=["base"], graph_class:CurrentEventsGraphABC=CurrentEventsGraphSplit):
        super().__init__(sub_dir_name, graph_names, graph_modules, graph_class)

    def _create_bar_chart_per_month(self, data, title:str, x_label:str, y_label:str):
        fig, ax = plt.subplots()
        
        keys = sorted(list(data.keys()))
        y = []
        x = []
        tick_labels = []
        labels = [None, 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        for year in keys:
            for month in range(12):
                if not np.isnan(data[year][month]):
                    y.append(data[year][month])
                    x.append(f"{labels[month+1]}/{int(year)-2000}")
                    if month == 0 or len(x) == 0:
                        tick_labels.append(f"{int(year)-2000}")
                    elif month%2 == 0:
                        tick_labels.append(f"{labels[month+1]}")
                    else:
                        tick_labels.append(f"")
                    

        ax.bar(x, y, tick_label=tick_labels)
        ax.set_title(title)
        ax.set_ylabel(y_label)
        ax.set_xlabel(x_label)
        
        
        return fig
