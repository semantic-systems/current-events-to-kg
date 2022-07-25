# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import os.path
import re

import requests

from src.analytics import Analytics
from src.sleeper import Sleeper


class InputHtml(Sleeper):

    def __init__(self, basedir, args, analytics:Analytics, reqCooldown=0.1):
        super().__init__()
        self.args = args
        self.basedir = basedir
        self.cooldown = reqCooldown # in s
        self.analytics = analytics

        self.cacheWikiDir = self.basedir / args.cache_dir / "wiki/"
        os.makedirs(self.cacheWikiDir, exist_ok=True)

        self.cacheCurrentEventsDir = self.basedir / args.cache_dir / "currentEvents/"
        os.makedirs(self.cacheCurrentEventsDir, exist_ok=True)
    

    def __fetchPage(self, filePath, url):
        if(os.path.exists(filePath) and not self.args.ignore_http_cache):  
            self.analytics.open()
            with open(filePath, mode='r', encoding="utf-8") as f:
                res = f.read()
            return res
        else:

            page = self.__requestWithThreeTrysOn110(url)
            
            # Issue: url and so filepath is from before possible redirect
            with open(filePath, mode='w', encoding="utf-8") as f:
                f.write(page.text)
            
            return page.text
    
    def __requestWithThreeTrysOn110(self, url):
        for t in range(3):
            try:
                diff = self.sleepUntilNewRequestLegal(self.cooldown)
                
                #exclude first diff with >8000000
                if diff >= 0:
                    self.analytics.timeBetweenRequest(diff)
                    self.analytics.waitTimeUntilRequest(self.cooldown - diff)

                
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
