# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from currenteventstokg.objects.infoboxRow import InfoboxRow
from currenteventstokg.objects.osmElement import OSMElement
from rdflib import Graph
from typing import Dict, List

class Article():
    def __init__(self, url: str, location_flag: bool, coordinates: List[float], 
            infobox: str, infobox_rows: List[InfoboxRow], articleGraph: str, 
            templates: List[str], wikidata_wkts: List[OSMElement], 
            wikidata_entity: str, wikidata_one_hop_graph: Graph, 
            parent_locations_and_relation: Dict[str, List[str]], 
            classes_with_labels: Dict[str, str], microformats: Dict[str, str], 
            date_published: str, date_modified: str, name: str, headline: str):
        self.url = url
        self.location_flag = location_flag
        self.coordinates = coordinates
        self.infobox = infobox
        self.infobox_rows = infobox_rows
        self.wikidata_wkts = wikidata_wkts
        self.wikidata_entity = wikidata_entity
        self.wikidata_one_hop_graph = wikidata_one_hop_graph
        self.parent_locations_and_relation = parent_locations_and_relation
        # classes_with_labels: wikidata classes, where the wd entity of this article is an instance of
        self.classes_with_labels = classes_with_labels 
        self.microformats = microformats
        self.date_published = date_published
        self.date_modified = date_modified
        self.name = name
        self.headline = headline


