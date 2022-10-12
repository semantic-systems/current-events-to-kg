# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import os.path
from pathlib import Path
import re
from typing import Optional

import requests

from .analytics import Analytics
from .sleeper import Sleeper


class InputHtml(Sleeper):

    def __init__(self, analytics:Optional[Analytics], cache_dir:Path, ignore_http_cache:bool, reqCooldown:float=0.1):
        super().__init__()
        self.ignore_http_cache = ignore_http_cache
        self.cooldown = reqCooldown # in s
        self.analytics = analytics

        self.cacheWikiDir = cache_dir / "wiki/"
        os.makedirs(self.cacheWikiDir, exist_ok=True)

        self.cacheCurrentEventsDir = cache_dir / "currentEvents/"
        os.makedirs(self.cacheCurrentEventsDir, exist_ok=True)

        self.cache_infobox_templates_dir = cache_dir / "infobox_templates/"
        os.makedirs(self.cache_infobox_templates_dir, exist_ok=True)
    

    def __fetchPage(self, filePath, url):
        if(os.path.exists(filePath) and not self.ignore_http_cache):  
            if self.analytics:
                self.analytics.numOpenings += 1
            with open(filePath, mode='r', encoding="utf-8") as f:
                res = f.read()
            return res
        else:
            page = self.__requestWithThreeTrysOn110(url)
            
            with open(filePath, mode='w', encoding="utf-8") as f:
                f.write(page.text)
            
            return page.text
    
    
    def __requestWithThreeTrysOn110(self, url):
        for t in range(3):
            try:
                diff, waited = self.sleepUntilNewRequestLegal(self.cooldown)

                if self.analytics:
                    #exclude first diff with >8000000
                    if diff >= 0:
                        self.analytics.timeBetweenRequest(diff)
                        self.analytics.waitTimeUntilRequest(waited)
                    self.analytics.numDownloads += 1

                return requests.get(url)
            except URLError as e:
                if e.reason.errno != 110:
                    raise e
                else:
                    print("\ninputHtml.py URLError 110 #" + str(t+1))
                    if t == 2:
                        raise e


    def fetchCurrentEventsPage(self, suffix):
        urlBase = "https://en.wikipedia.org/wiki/Portal:Current_events/" # eg April_2022
        filePath = self.cacheCurrentEventsDir / (suffix + ".html")
        sourceUrl = urlBase + suffix
        return sourceUrl, self.__fetchPage(filePath, sourceUrl)
    

    def fetchWikiPage(self, url):
        urlBase = "https://en.wikipedia.org/wiki/"
        urlSuffix = re.split("/", url)[4]
        filePath = self.cacheWikiDir / (urlSuffix + ".html")
        
        return self.__fetchPage(filePath, urlBase + urlSuffix)

    def fetchLocationTemplatesPage(self):
        url = "https://en.wikipedia.org/wiki/Wikipedia:List_of_infoboxes/Place"
        filePath = self.cache_infobox_templates_dir / ("places.html")
        
        return self.__fetchPage(filePath, url)
