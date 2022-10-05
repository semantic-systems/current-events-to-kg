# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from .create_topic_graph import querySparql
from rdflib import Graph
import rdflib
from glob import glob
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional
from SPARQLWrapper import JSON, SPARQLWrapper
from time import time
from abc import ABC, abstractmethod
from currenteventstokg import currenteventstokg_module_dir
from multiprocessing import Pool

class CurrentEventsGraphABC(ABC):
    @abstractmethod
    def __init__(self, graph_names:List[str], graph_modules=["base"]):
        pass
    @abstractmethod
    def query(self, q):
        pass

class CurrentEventsGraph(CurrentEventsGraphABC):
    def __init__(self, graph_names:List[str], graph_modules=["base"]):
        dataset_dir = currenteventstokg_module_dir / "dataset/"

        filepaths = []
        for gn in graph_names:
            filepaths.append([str(dataset_dir / f"{gn}_{gm}.jsonld") for gm in graph_modules])
        
        # load
        g = Graph()
        for graph_modules in filepaths:
            for graph_module in graph_modules:
                print(f"Parsing {f}")
                g.parse(graph_module)
        
        self.g = g
    
    def query(self, q) -> rdflib.query.Result:
        res = self.g.query(q)
        # if len(res.bindings) > 0:
        #     keys = [str(k) for k in list(res.bindings[0].keys())]
        res = [row.asdict() for row in res]
        return res



def f(graph_modules, q):
    g = Graph()
    for graph_module in graph_modules:
        print(f"Parse {graph_module}")
        g.parse(graph_module)

    print(f"Querying...")
    res = g.query(q)
    res = [row.asdict() for row in res]
    return res

class CurrentEventsGraphSplit(CurrentEventsGraphABC):
    def __init__(self, graph_names:List[str], graph_modules=["base"]):
        dataset_dir = currenteventstokg_module_dir / "dataset/"

        filepaths = []
        for gn in graph_names:
            filepaths.append([str(dataset_dir / f"{gn}_{gm}.jsonld") for gm in graph_modules])

        self.filepaths = filepaths
    
    def query(self, q, num_processes=1):
        with Pool(num_processes) as p:
            args = zip(self.filepaths, [q for i in range(len(self.filepaths))])
            args = list(args)
            res_list = p.starmap(f, args)
        
        return res_list


class SPARQLEndpoint():
    def __init__(self, url:str):
        endpoint = SPARQLWrapper(url)
        endpoint.setReturnFormat(JSON)
        self.endpoint = endpoint
        
    def query(self, q):
        for t in range(3):
            try:
                start_t = time()
                self.endpoint.setQuery(q)
                res = self.endpoint.query()
                print(f"{time() - start_t}sec for query")

                print("Converting to JSON...", end="")
                start_t = time()
                res = res.convert()
                print(f"{time() - start_t}sec")
                return res
            except:
                print("try", t+1, "failed")
                continue
        raise

    
class CurrentEventsVirtuoso(SPARQLEndpoint):
    def __init__(self):
        super().__init__("http://localhost:8890/sparql")