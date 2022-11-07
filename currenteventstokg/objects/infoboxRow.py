# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import datetime
from typing import Optional, List, Dict
from currenteventstokg.objects.link import Link
from currenteventstokg.objects.osmElement import OSMElement

class InfoboxRow():
    def __init__(self, label:str, value:str, valueLinks:List[Link]):
        self.label = label
        self.value = value
        self.valueLinks = valueLinks

class InfoboxRowLocation(InfoboxRow):
    def __init__(self, label:str, value:str, valueLinks:List[Link],
            falcon2_wikidata_entities:List[str], falcon2_articles:List["Article"], 
            falcon2_dbpedia_entities:List[str], valueLinks_wkts:Dict[Link, OSMElement]):
        super().__init__(label, value, valueLinks)
        self.falcon2_wikidata_entities = falcon2_wikidata_entities
        self.falcon2_articles = falcon2_articles
        self.falcon2_dbpedia_entities = falcon2_dbpedia_entities
        self.valueLinks_wkts = valueLinks_wkts

class InfoboxRowTime(InfoboxRow):
    def __init__(self, label:str, value:str, valueLinks:List[Link], 
            start_time:datetime.time, end_time:Optional[datetime.time]):
        super().__init__(label, value, valueLinks) 
        self.start_time = start_time # XSD.time conform string
        self.end_time = end_time # XSD.time conform string

class InfoboxRowDate(InfoboxRow):
    def __init__(self, label:str, value:str, valueLinks:List[Link], 
            start_date: Optional[datetime.datetime], end_date: Optional[datetime.datetime], 
            ongoing: bool):
        super().__init__(label, value, valueLinks) 
        self.start_date = start_date
        self.end_date = end_date
        self.ongoing = ongoing
    