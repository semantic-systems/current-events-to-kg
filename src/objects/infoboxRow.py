# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
import datetime
from typing import Optional

class InfoboxRow():
    def __init__(self, label, value, valueLinks):
        self.label = label
        self.value = value
        self.valueLinks = valueLinks

class InfoboxRowLocation(InfoboxRow):
    def __init__(self, label, value, valueLinks, 
            falcon2_wikidata_entities, falcon2_dbpedia_entities, valueLinks_wkts):
        super().__init__(label, value, valueLinks)
        self.falcon2_wikidata_entities = falcon2_wikidata_entities
        self.falcon2_dbpedia_entities = falcon2_dbpedia_entities
        self.valueLinks_wkts = valueLinks_wkts

class InfoboxRowTime(InfoboxRow):
    def __init__(self, label, value, valueLinks, 
            time:str, endtime:Optional[str], timezone:Optional[str]):
        super().__init__(label, value, valueLinks) 
        self.time = time # XSD.time conform string
        self.endtime = endtime # XSD.time conform string
        self.timezone = timezone

class InfoboxRowDate(InfoboxRow):
    def __init__(self, label, value, valueLinks, 
            date: datetime.datetime, enddate: Optional[datetime.datetime], ongoing: bool, timezone: Optional[str]):
        super().__init__(label, value, valueLinks) 
        self.date = date
        self.enddate = enddate
        self.ongoing = ongoing
        self.timezone = timezone
    