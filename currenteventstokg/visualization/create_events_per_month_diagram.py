# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import datetime
import json
from os.path import abspath, exists, split
from pathlib import Path
from pprint import pprint
from string import Template
from typing import Dict, List, Optional, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
from tqdm import tqdm

class NumEventsPerMonthAverageDiagram(CurrentEventDiagram):
    def __init__(self, basedir, graph_names:List[str]):
        super().__init__(basedir, "event_num_per_month_avg", graph_names)

    def createDiagram(self, force=True):
        q = """
            PREFIX coy: <https://schema.coypu.org/global#>
            SELECT DISTINCT ?month (COUNT(?e) as ?num) WHERE{
                ?t  a coy:Topic;
                    (coy:hasParentTopic)*/coy:hasArticle <https://en.wikipedia.org/wiki/2022_Russian_invasion_of_Ukraine>.
                ?e  coy:hasParentTopic ?t;
                    a coy:Event;
                    coy:hasDate ?date.
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
        super().__init__(basedir, "event_num_per_month", graph_names)

    def createDiagram(self, force=True):

        q = """
            PREFIX coy: <https://schema.coypu.org/global#>
            SELECT DISTINCT ?year ?month (COUNT(?e) as ?num) WHERE{
                ?t  a coy:Topic;
                    (coy:hasParentTopic)*/coy:hasArticle <https://en.wikipedia.org/wiki/2022_Russian_invasion_of_Ukraine>.
                ?e  coy:hasParentTopic ?t;
                    a coy:Event;
                    coy:hasDate ?date.
                BIND(MONTH(?date) as ?month).
                BIND(YEAR(?date) as ?year).
            } GROUP BY ?year ?month"""

        print(q)
        fpaths = [basedir / f"{gn}_base.jsonld" for gn in self.graph_names]
        fpaths = [
            Path("../current-events-to-kg/dataset/February_2022_base.jsonld"), 
            Path("../current-events-to-kg/dataset/March_2022_base.jsonld")
        ]
        n = CurrentEventsGraph(filepaths=fpaths)
        res = n.query(q)

        data = {}

        for row in res:
            num = int(row.num)
            month = int(row.month)
            year = int(row.year)

            if year not in data:
                data[year] = np.full(12, np.nan)
            data[year][month-1] = num
        
        fig = self.createPlot(data)
        fig.savefig(
            self.diagrams_dir / f"{self.filename}.png",
            dpi=400,
        )
        plt.show()
        
    
    def createPlot(self, data):
        fig, ax = plt.subplots()
        
        keys = sorted(list(data.keys()))
        y = []
        x = []
        labels = [None, 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        for year in keys:
            for month in range(12):
                if np.isnan(data[year][month]):
                    continue
                y.append(data[year][month])
                if month == 0 or len(x) == 0:
                    x.append(f"{labels[month+1]} {year-2000}")
                else:
                    x.append(f"{labels[month+1]}")

        ax.bar(x, y)
        ax.set_title("Number of Events about the 2022 Ukraine Invasion")
        ax.set_ylabel("Number of Events")
        ax.set_xlabel("Month")
        
        return fig





if __name__ == "__main__":
    basedir, _ = split(abspath(__file__))
    basedir = Path(basedir)
    m = ["February_2022", "March_2022", "April_2022", "May_2022", "June_2022", "July_2022", "August_2022"]
    #m = ["May_2022"]

    force = False

    # NumEventsPerMonthAverageDiagram(basedir, m).createDiagram()
    NumEventsPerMonthDiagram(basedir, m).createDiagram()
