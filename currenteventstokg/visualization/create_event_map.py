# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import json
import re
from glob import glob
from os import makedirs
from os.path import abspath, exists, split
from pathlib import Path
from pprint import pprint
from string import Template
from time import time
from typing import Dict, List, Tuple, Union
import argparse

import imageio
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import networkx as nx
import numpy as np
import pandas as pd
from currenteventstokg import currenteventstokg_dir
from geopandas import (GeoDataFrame, GeoSeries, datasets, read_file,
                       read_parquet)
from rdflib import RDF, RDFS, XSD, BNode, Graph, Literal, Namespace, URIRef
from shapely.geometry import (LineString, MultiLineString, MultiPoint,
                              MultiPolygon, Point, Polygon)
from shapely.wkt import load, loads
from SPARQLWrapper import JSON, SPARQLWrapper
from tqdm import tqdm
from currenteventstokg.etc import month2int, months, graph_name_list

def loadGraph(ds_dir, glob_name):
    # ds_name = ["dataset_base.jsonld", "dataset_raw.jsonld","dataset_ohg.jsonld", "dataset_osm.jsonld"]
    # for i, f in enumerate(ds_name):
    #     ds_name[i] = Path("./dataset/") / ds_name[i]

    g = Graph()
    print("glob_path:")
    print(ds_dir / glob_name)
    ds_paths = glob(str(ds_dir / glob_name))

    print("found files:")
    print(ds_paths)

    for f in ds_paths:
        print("Loading " + f + " ...")
        g.parse(f)

        for e in ["osm"]:
            match = re.match(r"\A(\S+)_base.jsonld", f.split("/")[-1])
            prefix = match.group(1)
            e_name = prefix + "_" + e + ".jsonld"
            e_path = str(ds_dir / e_name)
            print("Loading " + e_path + " ...")
            g.parse(e_path)

    n = Namespace("http://data.coypu.org/")
    g.namespace_manager.bind('n', n)
    NIF = Namespace("http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#")
    g.namespace_manager.bind('nif', NIF)
    # SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")
    # g.namespace_manager.bind('sem', SEM)
    # WGS = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
    # g.namespace_manager.bind('wgs', WGS)
    return g


def pngs2gif(png_paths:List[Path], out_path:Path, frame_duration:float):
    frames = []
    for filename in png_paths:
        print(f"Loading {filename}...")
        image = imageio.imread(filename)
        frames.append(image)
    
    imageio.mimsave(
        str(out_path),
        frames, 
        'GIF', 
        duration=frame_duration,
    )
    print(f"Gif save to {str(out_path)}")


class EventMap:
    def __init__(self, basedir, jsonld_base_graph_file_name):
        self.jsonld_base_graph_file_name = jsonld_base_graph_file_name

        prefix = jsonld_base_graph_file_name.split(".")[0]
        self.prefix_dmy = "_".join(prefix.split("_")[0:-1])

        self.sub_dir = "event_map_diagram"

        self.cache_dir = basedir / "cache" / self.sub_dir
        makedirs(self.cache_dir, exist_ok=True)
        
        self.wkt2id_path = self.cache_dir / "wkt2id.json"

        self.resource_dir = basedir / "resources"

        self.maps_output_dir = basedir / "diagrams" / self.sub_dir
        makedirs(self.maps_output_dir, exist_ok=True)

        f_split = self.jsonld_base_graph_file_name.split("_")
        self.month_str = f_split[0]
        self.year = int(f_split[1])
        # if file is partial month, eg 1_2_January_2022.jsonld
        if self.month_str.isdigit():
            self.month_str = f_split[2]
            self.year = int(f_split[3])       
        self.month = month2int[self.month_str]

        self.month_gdf = None

    def loadMonthData(self, force, no_ua=True):
        cache_path =  self.cache_dir / f"{self.month_str}_{self.year}.parquet"
        if exists(cache_path) and not force:
            print("Loading data cache", cache_path)
            gdf = read_parquet(cache_path)
        else:
            start_t_month = time()
            data, geometry = self._queryMonth(self.year, self.month, force)
            print(f"{(time() - start_t_month)/60}min for querying {self.month_str}_{self.year}")
            gdf = GeoDataFrame(data=data, geometry=geometry)
            #print("Columns:", gdf.columns)

            gdf.to_parquet(cache_path)

        gdf = self._calculate_gdf_columns(gdf, no_ua)
        
        self.month_gdf = gdf
    
    def _calculate_gdf_columns(self, gdf, no_ua=True):
        # calculate representative points
        rps = gdf["geometry"].representative_point()

        # filter for events in ukraine
        with open(self.resource_dir / "ukraine.wkt", "r", encoding="utf-8") as f:
            ua_bounds = load(f)
            
        in_ua = rps.within(ua_bounds)
        gdf = gdf[in_ua]

        # remove row with whole ua
        if no_ua:
            gdf = gdf[gdf.geometry != ua_bounds]
        
        # sum days up
        sum_label = f"sum"
        gdf[sum_label] = gdf.sum(axis=1)

        #print(gdf[sum_label].head(10))

        rps = gdf["geometry"].representative_point()

        # calculate DAG for draw determine drawing order
        g = nx.DiGraph()
        for i in rps.index:
            rp = rps.loc[i]

            g.add_node(i)

            idxs = gdf.sindex.query(rp, predicate="within")
            label_ids = [gdf.iloc[x].name for x in idxs]

            for idx in label_ids:
                if i != idx: 
                    g.add_node(idx)
                    if not g.has_edge(i, idx): # inhibit addition of inverse edges
                        g.add_edge(idx, i)  # idx in i
                    else:
                        pass #TODO investigate this
        
        g = nx.transitive_reduction(g)
        # nx.draw(g, with_labels=True)
        # plt.show()

        # assign each area the sum of it and all areas beneath it
        added = []
        index = []
        for i in rps.index:
            rp = rps.loc[i]
            # is_in = gdf.geometry.contains(rp)
            # added.append(gdf[month_sum][is_in].sum())
  
            i_in_these = [i]
            i_in_these.extend(list(nx.ancestors(g, i)))
            added.append(gdf[sum_label][i_in_these].sum())
            index.append(i)
        
        gdf["layered_sum"] = pd.Series(added, index)

        # reorder dataframe, that map gets drawn in a way, 
        # so that the "mother areas" gets drawn before "child areas"
        # e.g. germany before hamburg
        tgs = list(nx.topological_generations(g))
        draw_order = list(nx.topological_sort(g))
        gdf = gdf.reindex(draw_order)
        print(gdf.head())

        gdf["layered_sum_log"] = np.log10(gdf["layered_sum"])
        gdf["sum_log"] = np.log10(gdf["sum"])

        print("Columns:", gdf.columns)

        return gdf


    def createMonthMap(self, force=False, vmax=None, label="layered_sum"):  
        print("Columns:", self.month_gdf.columns)

        fig = self._gdf2map(self.month_gdf, f"{self.month_str} {str(self.year)}", vmax, label)
        
        suffix = ""
        if vmax:
            suffix = f"_{vmax}"
        png_path = self.maps_output_dir / f"{str(self.year)}_{str(self.month)}{suffix}.png"
        
        fig.savefig(
            png_path,
            dpi=400,
            bbox_inches='tight',
        )
        # fig.savefig(self.maps_output_dir / f"{str(self.year)}_{str(self.month)}.svg")

        return png_path


    def createDayMap(self, day:int, force_query=False, vmax:int=None, label="sum_log", no_ua=True) -> Path:
        cache_path =  self.cache_dir / f"{day}_{self.month_str}_{self.year}.parquet"
        
        if exists(cache_path):
            gdf = read_parquet(cache_path)
        else:
            data, geometry = self._queryDay(day, self.month, self.year, force_query)

            gdf = GeoDataFrame(data=data, geometry=geometry)
            print("Columns:", gdf.columns)

            #print(gdf.head(12))

            gdf.to_parquet(cache_path)
        
        gdf = self._calculate_gdf_columns(gdf, no_ua)
        
        days_dir = self.maps_output_dir / f"{self.month_str}_{self.year}_{vmax}"
        makedirs(days_dir, exist_ok=True)

        filename = f"{str(self.year)}_{str(self.month)}_{str(day)}.png"
        
        fig = self._gdf2map(gdf, f"{str(day)} {self.month_str} {str(self.year)}", vmax=vmax, label=label)
        fig.savefig(
            days_dir / filename,
            dpi=400,
            bbox_inches='tight',
        )
        # plt.show()

        return days_dir / filename
    

    def createMonthGif(self, vmax:int=None, force:bool=False, label="sum_log", no_ua=True):
        files = []
        for day in range(1,32):
            f = self.createDayMap(day, force_query=force, vmax=vmax, label=label, no_ua=no_ua)
            files.append(f)
        
        pngs2gif(files, self.maps_output_dir / f"{str(self.year)}_{str(self.month)}.gif", 1)
    

    def _gdf2map(self, gdf, title, vmax:int=None, label="sum_log"):
        # import world_outline
        # gdf_world_outline = read_file(
        #     str(self.resource_dir / "ne_110m_admin_0_countries/ne_110m_admin_0_countries.shp")
        # )
        gdf_world_outline_10 = read_file(
            str(self.resource_dir / "ne_10m_admin_0_countries_lakes/ne_10m_admin_0_countries_lakes.shp")
        )
        # gdf_world_outline_50 = read_file(
        #     str(self.resource_dir / "ne_50m_admin_0_countries_lakes/ne_50m_admin_0_countries_lakes.shp")
        # )

        # # plot
        # for i in gdf.index:
        #     print(i)
        fig, ax = plt.subplots(1, 1)
        ax.set_title(title)
        ax.set_xlim(20,42)
        ax.set_ylim(44,53)
        ax.set_axis_off()

        # world boundary
        # gdf_world_outline.boundary.plot(ax=ax, color="black", linewidth=0.5)
        gdf_world_outline_10.boundary.plot(ax=ax, color="black", linewidth=0.5)
        #gdf_world_outline_50.boundary.plot(ax=ax, color="black", linewidth=0.5)
        
        # ukraine bounds
        #ua_geo = GeoSeries(ua_bounds)
        #ua_geo.boundary.plot(ax=ax)

        print(gdf.columns)


        if vmax == None:
            vmax = gdf[label].max()

        kwds_dict = {
            'label': "Number of Events",
            'orientation': "horizontal",
            "pad": 0.05,
            "shrink": 0.7,
            "fraction": 0.05,
        }

        gdf.plot( # .loc[[i,i]]
            column=label,
            #column=sum_label,
            ax=ax, 
            legend=True, 
            legend_kwds=kwds_dict,
            vmin=0,
            vmax=vmax,
        )
        # plt.show()

        print(ax.get_figure().get_axes())
        
        # generate labels if on log scale
        if label[-4:] == "_log":
            ticks = np.linspace(0, vmax, 7)
            tick_labels = 10 ** ticks
            tick_labels = np.around(tick_labels)
            ticks = np.log10(tick_labels)
            # round labels
            tick_labels = [str(x.round(2)) for x in tick_labels]
            print(vmax, ticks, tick_labels)
            # apply
            if len(ax.get_figure().get_axes()) > 1:
                # if exists, is on 2nd slot
                colorbar = ax.get_figure().get_axes()[1]
                colorbar.set_xticks(ticks, labels=tick_labels)

            else:
                # if not, create one
                colorbar = plt.colorbar(
                    mappable=plt.cm.ScalarMappable(mcolors.Normalize(0,vmax)),
                    ax=ax, 
                    **kwds_dict,
                )
                colorbar.set_ticks(ticks, labels=tick_labels)
        
        return fig


    def _queryMonth(self, year:int, month:int, force:bool) -> Tuple[Dict, List]:
        cache_file_path_month = self.cache_dir / f"{months[month-1]}_{year}.json"
        
        data = {}
        wkt2id = self._load_wkt2id()

        month_ids = []
        for day in range(1,32):
            data_day, wkt2id = self._querySparql(day, month, year, wkt2id, force)
            
            # append day to data
            date = f"{year}-{month}-{day}"
            data[date] = data_day
            month_ids.extend(data_day.keys())
        
        self._cache_wkt2id(wkt2id)

        # pick geometries which are present in the data
        picked_wkt2id = {wkt:idx for wkt,idx in wkt2id.items() if idx in month_ids}

        geometry = self._wkt2id2geometry(picked_wkt2id)

        return data, geometry
    
    def _wkt2id2geometry(self, wkt2id)-> List:
        print("generating geometry list...")
        start_t = time()
        geometry = [loads(x) for x in sorted(wkt2id, key=wkt2id.get)]
        print(f"{time() - start_t}sec for generating geometry list ")

        return geometry

    def _load_wkt2id(self):
        if exists(self.wkt2id_path):
            print(f"Loading wkt2id from cache...")
            with open(self.wkt2id_path, "r", encoding="utf-8") as f:
                wkt2id = json.load(f)
        else:
            wkt2id = {}
        
        return wkt2id
    
    def _cache_wkt2id(self, wkt2id):
        with open(self.wkt2id_path, "w", encoding="utf-8") as f:
            json.dump(wkt2id, f, separators=(",",":"))


    def _queryDay(self, day:int, month:int, year:int, force:bool=False) -> Tuple[Dict, List]:
        wkt2id = self._load_wkt2id()

        data_day, wkt2id = self._querySparql(day, month, year, wkt2id, False)
        
        date = f"{year}-{month}-{day}"
        data = {}
        data[date] = data_day 

        self._cache_wkt2id(wkt2id)

        # pick geometries which are present in the data
        picked_wkt2id = {x:y for x,y in wkt2id.items() if y in data_day}

        geometry = self._wkt2id2geometry(picked_wkt2id)

        return data, geometry


    def _querySparql(self, day:int, month:int, year:int, wkt2id:Dict[str,int], force:bool) -> Tuple[Dict, Dict]:
        cache_file_path_day = self.cache_dir / f"{year}-{month}-{day}.json"

        if exists(cache_file_path_day) and len(wkt2id) != 0 and not force:
            print(f"Loading {cache_file_path_day} from cache...")
            with open(cache_file_path_day, "r", encoding="utf-8") as f:
                data_day = json.load(f)
                
                # cast values to int
                data_day = {int(k):int(v) for k,v in data_day.items()}
        else:
            print("Query day", day)

            start_t_day = time()
            q = Template("""
PREFIX coy: <https://schema.coypu.org/global#>
PREFIX coy_ev: <https://schema.coypu.org/events#>
PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
PREFIX gn: <https://www.geonames.org/ontology#>
PREFIX nif: <http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#>
SELECT DISTINCT ?e ?wd_wkt FROM <${month}_${year}> WHERE{
    ?e  a crm:E5_Event;
        crm:P117_occurs_during+/gn:wikipediaArticle <https://en.wikipedia.org/wiki/2022_Russian_invasion_of_Ukraine>;
        coy_ev:hasMentionDate ?date;
        crm:P1_is_identified_by ?c.
    ?c  nif:subString/nif:subString/gn:wikipediaArticle ?a.

    {?a  owl:sameAs/coy_ev:hasOsmElement ?osm.}
    UNION
    {?a  coy_ev:hasOsmElement ?osm.}

    ?osm coy_ev:hasOsmWkt ?wd_wkt.
    ?p  a crm:E53_Place;
        gn:wikipediaArticle ?a.
    FILTER(DAY(?date) = $day)
}""").substitute(day=day, month=months[month-1], year=year)

            sparql = SPARQLWrapper("http://localhost:8890/sparql")

            sparql.setQuery(q)
            sparql.setReturnFormat(JSON)
            #sparql.setTimeout(60*60*24)


            print("Querying...", end="")
            start_t = time()
            res = sparql.query()
            print(f"{time() - start_t}sec for query")

            print("Converting to JSON...", end="")
            start_t = time()
            res = res.convert()
            print(f"{time() - start_t}sec")               


            # convert to data dict + geometry
            data_day = {}
            print("rowcount:", len(res["results"]["bindings"]))
            for row in res["results"]["bindings"]:
                wd_wkt = str(row["wd_wkt"]["value"])

                # update wkt2id & set current_wkt_id
                if wd_wkt not in wkt2id:
                    current_wkt_id = len(wkt2id)

                    wkt2id[wd_wkt] = current_wkt_id
                else:
                    current_wkt_id = wkt2id[wd_wkt]
                
                # update data_day
                if current_wkt_id not in data_day:
                    data_day[current_wkt_id] = 0
                data_day[current_wkt_id] += 1

            print(f"{(time() - start_t_day)/60}min for day")

            # cache day
            with open(cache_file_path_day, "w", encoding="utf-8") as f:
                json.dump(data_day, f, separators=(",",":"))
        
        return data_day, wkt2id

def bulk_month_giffer(basedir:Path, base_files:List[str], force=False, sync_vmax=True, label="sum_log", no_ua=True):
    vmax = 0
    event_maps = []
    for f in base_files:
        print(f"Loading {f}")
        em = EventMap(basedir, f)
        em.loadMonthData(force, no_ua)
        event_maps.append(em)
        
        em_vmax = em.month_gdf[label].max()
        if em_vmax > vmax:
            vmax = em_vmax
    
    if not sync_vmax:
        vmax = None
    
    pngs = []
    maps_output_dir = None
    for em in event_maps:
        png_path = em.createMonthMap(force, vmax, label)
        pngs.append(png_path)
        maps_output_dir = em.maps_output_dir
    
    out_path = maps_output_dir / f"bulk_month_{label}_{no_ua}.gif"
    pngs2gif(pngs, out_path, 1)

    




if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("-f", '--force',
        action='store_true', 
        help="force")
    
    parser.add_argument("-omm", '--one_month_map',
        action='store',
        type=str,
        default=None,
        help="eg February_2022")
    
    parser.add_argument("-omg", '--one_month_gif',
        action='store',
        type=str,
        default=None,
        help="eg February_2022")
    
    parser.add_argument("-vmax", '--vmax',
        action='store',
        type=int,
        default=np.log10(30))
    
    parser.add_argument("-od", '--one_day',
        action='store',
        type=str,
        default=None,
        help="eg 2_February_2022")
    
    args = parser.parse_args()

    no_whole_ua = True
    label = "sum_log"

    if args.one_month_map:
        m = EventMap(currenteventstokg_dir, f"{args.one_month_map}_base.jsonld")
        m.loadMonthData(args.force, no_whole_ua)

        m.createMonthMap(args.force, label=label)

    elif args.one_month_gif:
        m = EventMap(currenteventstokg_dir, f"{args.one_month_gif}_base.jsonld")
        m.loadMonthData(args.force, no_whole_ua)

        m.createMonthGif(force=args.force, vmax=args.vmax, label=label, no_ua=no_whole_ua)

    elif args.one_day:
        day, month_year = args.one_day.split("_", 1)

        m = EventMap(currenteventstokg_dir, f"{month_year}_base.jsonld")
        m.loadMonthData(args.force, no_whole_ua)

        m.createDayMap(int(day), args.force, vmax=args.vmax, label=label, no_ua=no_whole_ua)

    else:
        m = graph_name_list(202202, 202208)
        base_files = [f"{gn}_base.jsonld" for gn in m]
        print(base_files)

        bulk_month_giffer(currenteventstokg_dir, base_files, args.force, sync_vmax=True, label=label, no_ua=no_whole_ua)



    

    
    
