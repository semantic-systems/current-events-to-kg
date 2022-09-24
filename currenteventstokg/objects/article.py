# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from currenteventstokg.objects.infoboxRow import InfoboxRow
from currenteventstokg.objects.osmElement import OSMElement
from rdflib import Graph
from typing import Dict, List

class Article():
    def __init__(self, link: str, locFlag: bool, coords: List[float], 
            infobox: str, ibcontent: List[InfoboxRow], articleGraph: str, 
            templates: List[str], wikidataWkts: List[OSMElement], 
            wikidataEntity: str, wikidata_one_hop_graph: Graph, 
            parent_locations_and_relation: Dict[str, List[str]], 
            classes_with_labels: Dict[str, str], microformats: Dict[str, str], 
            datePublished: str, dateModified: str, name: str, headline: str):
        self.link = link
        self.locFlag = locFlag
        self.coords = coords
        self.infobox = infobox
        self.ibcontent = ibcontent
        self.wikidataWkts = wikidataWkts
        self.wikidataEntity = wikidataEntity
        self.wikidata_one_hop_graph = wikidata_one_hop_graph
        self.parent_locations_and_relation = parent_locations_and_relation
        self.classes_with_labels = classes_with_labels
        self.microformats = microformats
        self.datePublished = datePublished
        self.dateModified = dateModified
        self.name = name
        self.headline = headline
