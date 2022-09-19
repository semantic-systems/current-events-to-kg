# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

class Article():
    def __init__(self, link, locFlag, coords, infobox, ibcontent, articleGraph, templates, 
            wikidataWkts, wikidataEntity, wikidata_one_hop_graph, parent_locations_and_relation,
            classes_with_labels, microformats, datePublished, dateModified, name, headline):
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
        
    
    