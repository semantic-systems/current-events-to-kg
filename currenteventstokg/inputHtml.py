# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import os.path
from pathlib import Path
import re
from typing import Optional
from urllib.error import URLError
import zstd
from time import time_ns

import requests

from .analytics import Analytics
from .sleeper import Sleeper


class InputHtml(Sleeper):

    def __init__(self, analytics:Optional[Analytics], cache_dir:Path, ignore_wiki_cache:bool, ignore_current_events_page_cache:bool, reqCooldown:float=0.1):
        super().__init__()
        self.ignore_wiki_cache = ignore_wiki_cache
        self.ignore_current_events_page_cache = ignore_current_events_page_cache
        self.cooldown = reqCooldown # in s
        self.analytics = analytics

        self.cacheWikiDir = cache_dir / "wiki/"
        os.makedirs(self.cacheWikiDir, exist_ok=True)

        self.cacheCurrentEventsDir = cache_dir / "currentEvents/"
        os.makedirs(self.cacheCurrentEventsDir, exist_ok=True)

        self.cache_infobox_templates_dir = cache_dir / "infobox_templates/"
        os.makedirs(self.cache_infobox_templates_dir, exist_ok=True)
    

    def __fetchPage(self, filePath, url, force=False):
        if(os.path.exists(filePath) and not force):  
            if self.analytics:
                self.analytics.numOpenings += 1
            with open(filePath, mode='r', encoding="utf-8") as f:
                res = f.read()
            return res
        else:
            page = self.__requestWithThreeTrys(url)
            
            with open(filePath, mode='w', encoding="utf-8") as f:
                f.write(page.text)
            
            return page.text
    
    def __fetch_page_zstd(self, file_path:Path, url:str, force:bool=False):
        file_path_zstd = Path(str(file_path) + ".zst")

        def compress_and_store(text:str, path:Path):
            t = time_ns()
            text_comp = zstd.compress(text.encode("utf-8"))
            t = time_ns()-t

            with open(path, mode='wb') as f:
                f.write(text_comp)
        
        # open file
        if os.path.exists(file_path_zstd) and not force:
            if self.analytics:
                t = time_ns()

            with open(file_path_zstd, mode='rb') as f:
                res_comp = f.read()
            res = zstd.decompress(res_comp)
            res = res.decode("utf-8")

            if self.analytics:
                t = time_ns() - t
                self.analytics.numOpenings += 1
                self.analytics.numOpeningsZstd += 1
                self.analytics.avgOpeningTimeZstd.add_value(float(t))

            return res
        
        elif os.path.exists(file_path) and not force:
            if self.analytics:
                t = time_ns()
            
            with open(file_path, mode='r', encoding="utf-8") as f:
                res = f.read()
            
            if self.analytics:
                t = time_ns() - t
                self.analytics.avgOpeningTimeUncompressend.add_value(float(t))
            
            # store compressed and delete uncompressed
            compress_and_store(res, file_path_zstd)
            os.remove(file_path)

            if self.analytics:
                self.analytics.numOpenings += 1

            return res

        else:
            # get and store compressed
            page = self.__requestWithThreeTrys(url)
            
            compress_and_store(page.text, file_path_zstd)
            return page.text        

    
    
    def __requestWithThreeTrys(self, url):
        for t in range(3):
            try:
                diff, waited = self.sleepUntilNewRequestLegal(self.cooldown)

                if self.analytics:
                    #exclude first diff with >8000000
                    if diff >= 0:
                        self.analytics.avgTimeBetweenRequest.add_value(diff)
                        self.analytics.avgWaitTimeUntilRequest.add_value(waited)
                    self.analytics.numDownloads += 1

                return requests.get(url)
            except Exception as e:
                    print("\ninputHtml.py HTTP request #" + str(t+1))
                    print(e)
                    if t == 2:
                        raise e


    def fetchCurrentEventsPage(self, suffix):
        urlBase = "https://en.wikipedia.org/wiki/Portal:Current_events/" # eg April_2022
        filePath = self.cacheCurrentEventsDir / (suffix + ".html")
        sourceUrl = urlBase + suffix
        return sourceUrl, self.__fetch_page_zstd(filePath, sourceUrl, self.ignore_current_events_page_cache)
    

    def fetchWikiPage(self, url):
        urlBase = "https://en.wikipedia.org/wiki/"
        urlSuffix = re.split("/", url)[4]
        filePath = self.cacheWikiDir / (urlSuffix + ".html")
        
        return self.__fetch_page_zstd(filePath, urlBase + urlSuffix, self.ignore_wiki_cache)

    def fetchLocationTemplatesPage(self):
        url = "https://en.wikipedia.org/wiki/Wikipedia:List_of_infoboxes/Place"
        filePath = self.cache_infobox_templates_dir / ("places.html")
        
        return self.__fetch_page_zstd(filePath, url, self.ignore_wiki_cache)
