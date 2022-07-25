# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from atexit import register
from json import dump, load
from os import makedirs
from os.path import exists
from string import Template
from time import sleep
from typing import Dict, List, Tuple
from urllib.error import HTTPError, URLError

from rdflib import BNode, Graph, Literal, URIRef
from SPARQLWrapper import JSON, JSONLD, TURTLE, XML, SPARQLWrapper, __version__

from src.sleeper import Sleeper


class WikidataService(Sleeper):

    # Limits: https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual#Query_limits

    def __init__(self, basedir, args, analytics, progName, progVersion, progGitRepo, server, minSecondsBetweenQueries=5):
        super().__init__()
        self.basedir = basedir
        self.args = args
        self.analytics = analytics
        self.minSecondsBetweenQueries = minSecondsBetweenQueries

        self.oneHopCacheDir = self.basedir / args.cache_dir / "wikidata_one_hop/"
        makedirs(self.oneHopCacheDir, exist_ok=True)

        self.osmCacheFilePath = self.basedir / args.cache_dir / "osm_entity_cache.json"
        self.__loadOSMCache()

        self.higherLevelLocationCacheFilePath = self.basedir / args.cache_dir / "higher_level_location_cache.json"
        self.__loadHigherLevelLocationCache()

        self.labelCacheFilePath = self.basedir / args.cache_dir / "label_cache.json"
        self.__loadLabelCache()

        # save caches after termination
        register(self.__saveCaches)

        # wikidata wants a "bot" included in agent string
        self.agent = progName + "(bot)/" + progVersion + " (" + progGitRepo + ") " + f"sparqlwrapper {__version__}"
        print(f"wikidata server: {server}")
        print(f"wikidata user-agent: {self.agent}")
        self.sparql = SPARQLWrapper(server, agent=self.agent)
    

    def getEntitysLabels(self, entityURIs:List[str]) -> Dict[str,str]:
        result = {}
        query = False
        first = True
        q = q = "PREFIX wd: <http://www.wikidata.org/entity/>\nSELECT DISTINCT ?e ?l WHERE{\n"
        for eURI in entityURIs:
            eid = eURI.split("/")[-1]
            if not self.args.ignore_wikidata_label_cache and eid in self.labelCache:
                result[eid] = self.labelCache[eid]
            else:
                query = True
                if first:
                    first = False
                    q += Template("""{
    BIND(wd:$e AS ?e).
    ?e rdfs:label ?l.
}""").substitute(e=eid)
                else:
                    q += Template("""UNION {
    BIND(wd:$e AS ?e).
    ?e rdfs:label ?l.
}""").substitute(e=eid)
        
        
        if query:
            q += "\nFILTER(LANG(?l) = \"en\") .\n}"

            self.sparql.setQuery(q)
            self.sparql.setReturnFormat(JSON)

            self.sleepUntilNewRequestLegal(self.minSecondsBetweenQueries)
            
            res = self.__queryAndConvertThreeTrysOn110()

            for row in res["results"]["bindings"]:
                eid = row["e"]["value"].split("/")[-1]
                label = row["l"]["value"]
                
                result[eid] = label
                self.labelCache[eid] = label

        return result        
            

    def getHigherlevelLocations(self, entityURI:str) -> Dict[str, List[str]]:
        eid = entityURI.split("/")[-1]
        if not self.args.ignore_wikidata_higher_level_location_cache and eid in self.higherLevelLocationCache:
            result = self.higherLevelLocationCache[eid]
        else:
            # exclude prop for pictures about places with filter
            q = Template("""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
SELECT DISTINCT ?wd_r ?loc WHERE{
  wd:$e ?wdt_r ?loc .
  
  ?wd_r wdt:P1647+ wd:P276. # transitive subprop of location
  ?wd_r wikibase:directClaim ?wdt_r .
  FILTER NOT EXISTS{ ?wd_r wdt:P1647 wd:P18. } 
}""").substitute(e=eid)

            self.sparql.setQuery(q)
            self.sparql.setReturnFormat(JSON)

            self.sleepUntilNewRequestLegal(self.minSecondsBetweenQueries)
            res = self.__queryAndConvertThreeTrysOn110()

            result = {}
            for row in res["results"]["bindings"]:
                value = row["loc"]["value"]
                if value in result:
                    result[value].append(row["wd_r"]["value"])
                else:
                    result[value] = [ row["wd_r"]["value"] ]

            self.higherLevelLocationCache[eid] = result 

        return result


    def getOneHopSubgraph(self, entityURI:str) -> Graph:
        filePath = self.__getOneHopSubgraphCacheFileName(entityURI)
        if exists(filePath) and not self.args.ignore_wikidata_one_hop_graph_cache:
            result = self.__loadOneHopSubgraph(entityURI)
        else:
            # use SELECT query to get all triples 
            # (because CONSTRUCT is not supported from our wikidata server)

            q = Template("""
SELECT ?p ?o WHERE {
    <$e> ?p ?o .
}""").substitute(e=entityURI)
            self.sparql.setQuery(q)
            self.sparql.setReturnFormat(JSON)

            self.sleepUntilNewRequestLegal(self.minSecondsBetweenQueries)
            json = self.__queryAndConvertThreeTrysOn110()

            result = Graph()
            for row in json["results"]["bindings"]:
                p, o = row["p"],  row["o"]

                # create predicate object
                if p["type"] == "uri":
                    pre = URIRef(p["value"])
                else:
                    raise ValueError(p["type"])
                
                # create object object
                if o["type"] == "uri":
                    obj = URIRef(o["value"])
                elif o["type"] == "literal":
                    lang = None
                    if "xml:lang" in o:
                        lang = o["xml:lang"]
                    dtype = None
                    if "datatype" in o:
                        dtype = o["datatype"]
                    
                    obj = Literal(o["value"], datatype=dtype, lang=lang)
                elif o["type"] == "bnode":
                    # cut "_:" from front of value
                    obj = BNode(value=o["value"][2:])
                else:
                    raise ValueError(o["type"] + str(o))
                
                # add triple
                result.add((URIRef(entityURI),pre,obj))

            self.__cacheOneHopSubgraph(entityURI, result)
            
        return result
    

    def getOSMEntitys(self, entityURI:str) -> Tuple[str, str]:
        # osmrelids: eg 62422  -> https://www.wikidata.org/wiki/Property:P402
        # osmobjs: [way|node]/{id} -> https://www.wikidata.org/wiki/Property:P10689

        if not self.args.ignore_wikidata_osm_entity_cache and entityURI in self.osmCache:
            res = self.osmCache[entityURI]
            osmrelids, osmobjs = res["osmrelids"], res["osmobjs"]
        else:
            q = Template("""PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?osmrelid ?osmobj WHERE {
    OPTIONAL {<$e> wdt:P402 ?osmrelid . }
    OPTIONAL {<$e> wdt:P10689 ?osmobj. }
}""").substitute(e=entityURI)
            self.sparql.setQuery(q)
            self.sparql.setReturnFormat(JSON)

            self.sleepUntilNewRequestLegal(self.minSecondsBetweenQueries)
            results = self.__queryAndConvertThreeTrysOn110()

            osmrelidsSet, osmobjsSet = set(), set()
            for row in results["results"]["bindings"]:
                if "osmrelid" in row:
                    osmrelidsSet.add(row["osmrelid"]["value"])
                if "osmobj" in row:
                    osmobjsSet.add(row["osmobj"]["value"])
            
            osmobjs = list(osmobjsSet)
            osmrelids = list(osmrelidsSet)
            self.osmCache[entityURI] = {"osmrelids":osmrelids, "osmobjs":osmobjs} 
            
        return osmrelids, osmobjs

    
    def __queryAndConvertThreeTrysOn110(self):
        for t in range(3):
            try:
                res = self.sparql.queryAndConvert()
                self.analytics.numWikidataQueries += 1
                return res
            except HTTPError as e:
                if e.code == 429:
                    # check when query can be reqeated (untested, never happend)
                    timeout = int(e.headers["Retry-After"])
                    print(f"Wikidata request limit exceeded! Waiting {timeout} sec...")
                    sleep(timeout)
                else:
                    raise e
            except URLError as e:
                if e.reason.errno != 110:
                    raise e
                else:
                    print("\nwikidataService.py URLError 110 #" + str(t+1))
                    if t == 2:
                        raise e
        

    
    
    def __loadOSMCache(self):
        if(exists(self.osmCacheFilePath) and not self.args.ignore_wikidata_osm_entity_cache): 
            with open(self.osmCacheFilePath, mode='r', encoding="utf-8") as f:
                self.osmCache = load(f)
        else:
            self.osmCache = {}
    
    def __loadHigherLevelLocationCache(self):
        if(exists(self.higherLevelLocationCacheFilePath) and not self.args.ignore_wikidata_higher_level_location_cache): 
            with open(self.higherLevelLocationCacheFilePath, mode='r', encoding="utf-8") as f:
                self.higherLevelLocationCache = load(f)
        else:
            self.higherLevelLocationCache = {}

    def __loadLabelCache(self):
        if(exists(self.labelCacheFilePath) and not self.args.ignore_wikidata_label_cache): 
            with open(self.labelCacheFilePath, mode='r', encoding="utf-8") as f:
                self.labelCache = load(f)
        else:
            self.labelCache = {}

    def __saveCaches(self):
        with open(self.osmCacheFilePath, mode='w', encoding="utf-8") as f:
            dump(self.osmCache, f)
        
        with open(self.higherLevelLocationCacheFilePath, mode='w', encoding="utf-8") as f:
            dump(self.higherLevelLocationCache, f)

        with open(self.labelCacheFilePath, mode='w', encoding="utf-8") as f:
            dump(self.labelCache, f)
    

    def __getOneHopSubgraphCacheFileName(self, entityURI):
        eid = entityURI.split("/")[-1]
        return self.oneHopCacheDir / (eid + ".jsonld")
    
    def __cacheOneHopSubgraph(self, entityURI, graph):
        filePath = self.__getOneHopSubgraphCacheFileName(entityURI)

        s = graph.serialize(format="json-ld")
        with open(filePath, mode='w', encoding="utf-8") as f:
            f.write(s)
    
    def __loadOneHopSubgraph(self, entityURI):
        filePath = self.__getOneHopSubgraphCacheFileName(entityURI)
        
        g = Graph()
        with open(filePath, mode='r', encoding="utf-8") as f:
            g.parse(file=f)
        
        return g

    

    