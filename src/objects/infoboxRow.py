# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

class InfoboxRow():
    def __init__(self, label, value, valueLinks):
        self.label = label
        self.value = value
        self.valueLinks = valueLinks

class InfoboxRowLocation(InfoboxRow):
    def __init__(self, label, value, valueLinks, falcon2_wikidata_entities, falcon2_dbpedia_entities):
        self.label = label
        self.value = value
        self.valueLinks = valueLinks
        self.falcon2_wikidata_entities = falcon2_wikidata_entities
        self.falcon2_dbpedia_entities = falcon2_dbpedia_entities
    