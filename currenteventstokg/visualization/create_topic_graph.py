# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import datetime
import json
import random
from os import makedirs
from os.path import abspath, exists, split
from pathlib import Path
from string import Template
from time import time
from typing import Dict, List, Tuple, Union
import argparse
import math

import igraph
import imageio
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from currenteventstokg import currenteventstokg_dir
from currenteventstokg.etc import month2int, months, graph_name_list
from pyvis.network import Network
from SPARQLWrapper import JSON, SPARQLWrapper
from tqdm import tqdm


def querySparql(query:str, query_name:str, cache_dir:Path, force:bool=False):
    cache_file_path = cache_dir / f"{query_name}.json"

    if exists(cache_file_path) and not force:
        print(f"Loading {cache_file_path} from cache...")
        with open(cache_file_path, "r", encoding="utf-8") as f:
            res = json.load(f)
    else:
        print("Querying...", end="")
        sparql = SPARQLWrapper("http://localhost:8890/sparql")
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)

        start_t = time()
        res = sparql.query()
        print(f"{time() - start_t}sec for query")

        print("Converting to JSON...", end="")
        start_t = time()
        res = res.convert()
        print(f"{time() - start_t}sec")

        # cache
        print("Caching...", end="")
        start_t = time()
        with open(cache_file_path, "w", encoding="utf-8") as f:
            json.dump(res, f, separators=(",",":"))
        print(f"{time() - start_t}sec")
    
    return res



class TopicGraphDiagram:
    def __init__(self, basedir, graph_names:List[str]):
        self.basedir = basedir
        self.graph_names = graph_names # need to be sorted with first one first!
    
        self.start_month = month2int[self.graph_names[0].split("_")[0]]
        self.end_month = month2int[self.graph_names[-1].split("_")[0]]
        self.start_year = int(self.graph_names[0].split("_")[1])
        self.end_year = int(self.graph_names[-1].split("_")[1])

        self.filename = f"{self.start_month}_{self.start_year}_{self.end_month}_{self.end_year}"

        sub_dir = "topic_graph_diagram"

        self.cache_dir = basedir / "cache" / sub_dir
        makedirs(self.cache_dir, exist_ok=True)

        self.resource_dir = basedir / "resources"

        self.diagrams_dir = basedir / "diagrams" / sub_dir
        makedirs(self.diagrams_dir, exist_ok=True)

        self.draw_options = {
            "with_labels":True, 
            "font_size":5,
            "node_size":50,
            "arrowsize":5,
            "verticalalignment":"center_baseline",
            "edge_color":"#f7ce00",
            "node_color":"#0058b5",
        }

        self.root = "2022 Russian invasion of Ukraine"

    
    def createiGraph(self):
        g = self._minDateDiGraph(False)

        # spring layout doesnt work with directed graphs(?)
        gu = g.to_undirected()

        ig = igraph.Graph.from_networkx(g)

        ig.vs["label"] = ig.vs["_nx_name"]

        layout = ig.layout_fruchterman_reingold(niter=1)
        igraph.plot(ig, str(self.diagrams_dir / f"{self.filename}_igraph1.png"), layout=layout)

        layout = ig.layout_fruchterman_reingold(seed=layout, niter=1)
        igraph.plot(ig, str(self.diagrams_dir / f"{self.filename}_igraph2.png"), layout=layout)


    def createiGraphGif(self):
        frame_dir = self.cache_dir / "gif_frames_igraph"
        makedirs(frame_dir, exist_ok=True)

        g = self._minDateDiGraph(False)
        ig = igraph.Graph.from_networkx(g)

        seedlayout = ig.layout_fruchterman_reingold(niter=0)
        filenames = []
        for i in tqdm(range(30)):
            fname = str(frame_dir / f"{i}.png")

            layout = ig.layout_fruchterman_reingold(seed=seedlayout, niter=i)
            igraph.plot(ig, fname, layout=layout)
            
            filenames.append(fname)

        frames = []
        for filename in filenames:
            image = imageio.imread(filename)
            frames.append(image)

        imageio.mimsave(
            str(self.diagrams_dir / f"{self.filename}_igraph.gif"),
            frames, 'GIF')


    def createPyvisGraph(self, force=True, tree:bool=False):
        # g = self._minDateDiGraph(False)

        # create daily topic graph
        res = self._getDailyNewTopics(force, False)

        # create graph
        if tree:
            g = self._dailys2Tree(res)
        else:
            g = self._dailys2DiGraph(res)

        nt = Network("1000px", "1000px")
        nt.from_nx(g)
        nt.show_buttons(filter_=["physics", "edges", "nodes"])
        nt.show('nx.html')
    

    def getPosFromLayout(self, g:nx.DiGraph, layout_id:str):
        # spring layout doesnt work with directed graphs(?)
        gu = g.to_undirected()

        if layout_id == "kk":
            pos = nx.kamada_kawai_layout(gu)
        elif layout_id == "sl":
            pos = nx.spring_layout(gu, iterations=50, scale=None, seed=42)
        elif layout_id == "fdp":
            pos = nx.nx_agraph.graphviz_layout(g, prog="fdp") #nice: (twopi <) neato < fdp
        elif layout_id == "neato":
            pos = nx.nx_agraph.graphviz_layout(g, prog="neato") 
        elif layout_id == "twopi":
            pos = nx.nx_agraph.graphviz_layout(g, prog="twopi")

        return pos


    def createDiagram(self, force=False, layout:str="kk", tree:bool=False):
        # create daily topic graph
        res = self._getDailyNewTopics(force=force, use_a_date=False)

        # create graph
        if tree:
            g = self._dailys2Tree(res)
        else:
            g = self._dailys2DiGraph(res)

        pos = self.getPosFromLayout(g, layout)

        plt.figure(figsize=(12,8))
        nx.draw(
            g, 
            pos=pos, 
            with_labels=True, 
            node_size=70,
            arrowsize=15,
            verticalalignment="center_baseline",
            edge_color="#f7ce00",
            node_color="#0058b5",
            font_size=6,
            clip_on=False
        )

        # adjust the plot limits to remove plot margins
        plt.autoscale(enable=True, axis='both', tight=True)

        suffix = "tree_" if tree else "all_"
        suffix += layout
        fname = self.diagrams_dir / f"{self.filename}_{suffix}.svg"

        
        plt.savefig(
            fname,
            dpi=400,
            bbox_inches='tight',
        )
        print(f"Saved to {fname}...")
        plt.show()

    
    def createGif(self, force=False, layout:str="kk", tree:bool=False):
        frame_dir = self.cache_dir / "gif_frames"
        makedirs(frame_dir, exist_ok=True)

        ## create whole graph to get layout positions and limits
        res = self._getDailyNewTopics(force=force, use_a_date=False)

        if tree:
            g = self._dailys2Tree(res)

            # compute transitive reduction
            temp_g = self._dailys2DiGraph_DAG(res)
            tr_g = nx.transitive_reduction(temp_g)
        else:
            g = self._dailys2DiGraph(res)

        # compute layout
        pos = self.getPosFromLayout(g, layout)

        # plot whole graph to get limits
        fig, ax = plt.subplots(1, 1)
        nx.draw(
            g, 
            ax=ax,
            pos=pos,
            **self.draw_options,
            clip_on=False
        )

        # adjust the plot limits to remove plot margins
        ax.autoscale(enable=True, axis='both', tight=True)

        xlim, ylim = ax.get_xlim(), ax.get_ylim()
        plt.show()

        # calculate total days
        days = 0
        for year in sorted(res):
            for month in sorted(res[year]):
                days += len(res[year][month])
        print(days, "days")

        ## create daily new graph elements gif
        g = nx.DiGraph()

        filenames = []
        nodes = []
        partial_pos = {}
        i = 0
       
        with tqdm(total=days) as pbar:
            for year in sorted(res):
                for month in sorted(res[year]):
                    for day in sorted(res[year][month]):
                        # add new topic from this day to graph
                        topics = res[year][month][day]

                        if tree:
                            new_nodes = self._add_edges_forming_tree(g, tr_g, topics, self.root)
                        else:
                            new_nodes = self._addTopicsToGraph(g, topics)

                        if len(new_nodes) > 0:
                            # draw new nodes
                            partial_pos |= {n:xy for n,xy in pos.items() if n in new_nodes}

                            fig, ax = plt.subplots(1, 1)
                            if year == 0:
                                title = "Previously"
                            else:
                                title = f"{year}-{month}-{day}"
                            ax.set_title(title)
                            ax.set_xlim(xlim)
                            ax.set_ylim(ylim)
                            nx.draw(
                                g, 
                                ax=ax,
                                pos=partial_pos, 
                                with_labels=False, 
                                node_size=50,
                                arrowsize=10,
                                verticalalignment="center_baseline",
                                edge_color="#f7ce00",
                                node_color="#0058b5",
                            )
                            nx.draw_networkx_nodes(
                                g,
                                ax=ax,
                                pos=partial_pos,
                                node_size=50,
                                nodelist=new_nodes,
                                node_color="red",
                            )
                            nx.draw_networkx_labels(
                                g,
                                ax=ax,
                                pos=partial_pos,
                                labels={n:n for n in new_nodes},
                                font_size=5,
                            )
                            fname = frame_dir / f"{i}.png"

                            fig.savefig(
                                fname,
                                #dpi=400,
                                bbox_inches='tight',
                            )
                            plt.close(fig)
                            filenames.append(fname)

                            nodes.extend(new_nodes)
                            i += 1
                        pbar.update(1)
            
        print("nodes", len(nodes))
        print("Collecting gif frames...")
        frames = []
        for filename in filenames:
            image = imageio.imread(filename)
            frames.append(image)

        suffix = "tree_" if tree else "all_"
        suffix += layout
        fname = self.diagrams_dir / f"{self.filename}_{suffix}.gif"

        out_path = str(self.diagrams_dir / fname)
        print(f"Saving gif to {out_path}...")
        imageio.mimsave(
            out_path,
            frames, 
            'GIF', 
            duration=1)
        print("Done")

 
    def _queryTopicsArticleDate(self, force:bool=False):
        q_template = Template("""
            PREFIX coy_ev: <https://schema.coypu.org/events#>
            PREFIX schema: <https://schema.org/>
            PREFIX gn: <https://www.geonames.org/ontology#>
            PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            
            SELECT DISTINCT ?pt ?t ?pl ?l ?a_date (MIN(?date) as ?date) $from_string WHERE{
                ?pt a crm:E5_Event;
                    (crm:P117_occurs_during*)/gn:wikipediaArticle <https://en.wikipedia.org/wiki/2022_Russian_invasion_of_Ukraine> ;
                    coy_ev:hasMentionDate ?date.
                ?t crm:P117_occurs_during ?pt;
                   coy_ev:hasMentionDate ?date.

                { ?t gn:wikipediaArticle [ schema:name ?l ]. } 
                UNION {
                    ?t crm:P1_is_identified_by ?l.
                    FILTER(DATATYPE(?l) = xsd:string).
                    FILTER NOT EXISTS{?t gn:wikipediaArticle ?a.}
                }

                { ?pt gn:wikipediaArticle [ schema:name ?pl ]. } 
                UNION 
                {
                    ?pt crm:P1_is_identified_by ?pl.
                    FILTER(DATATYPE(?pl) = xsd:string).
                    FILTER NOT EXISTS{?pt gn:wikipediaArticle ?pa.}
                }
                    
                OPTIONAL{
                    ?t crm:P4_has_time-span ?ts.
                    ?ts coy_ev:hasStartDate ?a_date.
                }
                
            } GROUP BY ?pt ?t ?pl ?l ?a_date""")


        res = None
        min_date_row = {}
        for graph in self.graph_names:
            q = q_template.substitute(from_string=f"FROM <{graph}>")
            print(q)
            qres = querySparql(q, f"{graph}_ad", self.cache_dir, force)

            if res == None:
                res = qres
            
            for row in qres["results"]["bindings"]:
                t = str(row["t"]["value"])
                pt = str(row["pt"]["value"])
                date = datetime.date.fromisoformat(str(row["date"]["value"]))

                key = (pt,t)
                if key not in min_date_row or min_date_row[key][0] > date :
                    min_date_row[key] = (date, row)
            
        res["results"]["bindings"] = []
        for date,row in min_date_row.values():
            res["results"]["bindings"].append(row)
        
        return res

    
    def _minDateDiGraph(self, force:bool=False) -> nx.DiGraph:
        res = self._queryTopicsArticleDate(force)

        # create diagram
        g = nx.DiGraph()

        # convert to data dict + geometry
        print("rowcount:", len(res["results"]["bindings"]))
        for row in res["results"]["bindings"]:
            t = str(row["t"]["value"])
            l = str(row["l"]["value"])
            pt = str(row["pt"]["value"])
            pl = str(row["pl"]["value"])

            g.add_node(pl)
            g.add_node(l)
            g.add_edge(pl, l)
        
        return g
    

    def _dailys2DiGraph(self, dailys) -> nx.DiGraph:
        g = nx.DiGraph()
        g.add_node(self.root)

        for year in sorted(dailys):
            for month in sorted(dailys[year]):
                for day in sorted(dailys[year][month]):
                    for topic in dailys[year][month][day]:
                        pl = topic["pl"]
                        l = topic["l"]

                        if not g.has_node(l):
                            g.add_node(l)
                        if not g.has_node(pl):
                            g.add_node(pl)
                        if not g.has_edge(pl, l):
                            g.add_edge(pl, l)
        return g


    def _dailys2DiGraph_DAG(self, dailys) -> nx.DiGraph:
        g = nx.DiGraph()
        g.add_node(self.root)

        for year in sorted(dailys):
            for month in sorted(dailys[year]):
                for day in sorted(dailys[year][month]):
                    topics = dailys[year][month][day]
                    self._add_edges_acyclic(g, topics)
        return g
    

    def _add_edges_acyclic(self, g:nx.DiGraph, topics):
        new_nodes = []
        for topic in topics:
            pt = topic["pl"]
            t = topic["l"]

            if t != pt and (
                    g.has_node(t) and g.has_node(pt) and not (nx.has_path(g, t, pt) or nx.has_path(g, pt, t)) or
                    not g.has_node(t) or 
                    not g.has_node(pt)
                ):
                g.add_edge(pt,t)
                new_nodes.append(t)
        
        return new_nodes 
    
    
    def _dailys2Tree(self, dailys) -> nx.DiGraph:
        # compute transitive reduction
        temp_g = self._dailys2DiGraph_DAG(dailys)
        tr_g = nx.transitive_reduction(temp_g)

        g = nx.DiGraph()
        g.add_node(self.root)

        for year in sorted(dailys):
            for month in sorted(dailys[year]):
                for day in sorted(dailys[year][month]):
                    topics = dailys[year][month][day]
                    self._add_edges_forming_tree(g, tr_g, topics, self.root)
        return g


    def _add_edges_forming_tree(self, g:nx.DiGraph, transitive_reduction:nx.DiGraph, topics, root):
        new_nodes = []
        for topic in topics:
            pt = topic["pl"]
            t = topic["l"]
            
            if transitive_reduction.has_edge(pt, t) and not (g.has_node(root) and g.has_node(t) and nx.has_path(g, root, t)):
                if not g.has_node(t):
                    new_nodes.append(t)
                if not g.has_node(pt):
                    new_nodes.append(pt)

                g.add_edge(pt,t)
        
        return new_nodes  

    
    def _addTopicsToGraph(self, g, topics):
        new_nodes = []
        for topic in topics:
            pl = topic["pl"]
            l = topic["l"]

            if not g.has_node(l):
                new_nodes.append(l)
                g.add_node(l)
            if not g.has_node(pl):
                new_nodes.append(pl)
                g.add_node(pl)
            g.add_edge(pl, l)
        
        return new_nodes
        
    
    def _getDailyNewTopics(self, force:bool=False, use_a_date=False) -> Dict:
        # with all rows there are missing links between topics, because they have no a_date (article date)
        qres = self._queryTopicsArticleDate(force)

        start = datetime.datetime(self.start_year, self.start_month, 1)
        after_year = self.end_year if self.end_month==12 else self.end_year+1
        after_month = ((self.end_month+1)%12)
        after = datetime.datetime(after_year, after_month, 1)

        res = {}
        print("rowcount:", len(qres["results"]["bindings"]))
        for row in qres["results"]["bindings"]:
            t = str(row["t"]["value"])
            l = str(row["l"]["value"])
            pt = str(row["pt"]["value"])
            pl = str(row["pl"]["value"])
            a_date = None
            if "a_date" in row:
                a_date = datetime.datetime.fromisoformat(str(row["a_date"]["value"]))
            date = datetime.date.fromisoformat(str(row["date"]["value"]))

            print(date, pl, "->", l)


            if use_a_date and a_date:
                d = a_date
            else:
                d = datetime.datetime(date.year, date.month, date.day)
            
            if d and d < after:
                if d:
                    if d >= start:
                        year = d.year
                        month = d.month
                        day = d.day
                    else:
                        year = 0
                        month = 0
                        day = 0
                
                if year not in res:
                    res[year] = {}

                if month not in res[year]:
                    res[year][month] = {}

                if day not in res[year][month]:
                    res[year][month][day] = []

                res[year][month][day].append({
                    "t":t,
                    "l":l,
                    "pt":pt,
                    "pl":pl,
                })
            else:
                print("after or none", date, pl, "->", l)
        return res

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("type",
        choices=["gif", "fig", "pyvis"],
        nargs='?',
        default="gif")
     
    parser.add_argument("-f", '--force',
        action='store_true', 
        help="force")
    
    parser.add_argument("-t", '--tree',
        action='store_true', 
        help="force")
    
    parser.add_argument("-l", '--layout_algorithm',
        action='store', 
        choices=["kk", "sl", "fdp", "neato", "twopi"],
        default="kk")
    
    args = parser.parse_args()

    m = graph_name_list(202202, 202208)
    print(m)

    if args.type == "gif":
        TopicGraphDiagram(currenteventstokg_dir, m).createGif(args.force, args.layout_algorithm, args.tree)
    elif args.type == "fig":
        TopicGraphDiagram(currenteventstokg_dir, m).createDiagram(args.force, args.layout_algorithm, args.tree)
    elif args.type == "pyvis":
        TopicGraphDiagram(currenteventstokg_dir, m).createPyvisGraph(args.force, args.tree)

    # old test, works but not used and finished:
    # TopicGraphDiagram(currenteventstokg_dir, m[0:1]).createiGraphGif()
