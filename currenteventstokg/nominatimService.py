# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from logging import ERROR
from os import makedirs

from OSMPythonTools import logger
from OSMPythonTools.cachingStrategy import JSON, CachingStrategy
from OSMPythonTools.nominatim import Nominatim

from typing import Dict


class NominatimService:

    # Limits : https://operations.osmfoundation.org/policies/nominatim/

    def __init__(self, basedir, args, analytics, progName, progVersion, progGitRepo, server, waitBetweenQueries=5):
        self.basedir = basedir
        self.analytics = analytics

        self.cacheNominatim = self.basedir / args.cache_dir / "nominatim/"
        makedirs(self.cacheNominatim, exist_ok=True)
        
        self.agent = progName + "(bot)/" + progVersion + " (" + progGitRepo + ")"
        print(f"nominatim server: {server}")
        print(f"nominatim user-agent: {self.agent}")

        self.n = Nominatim(endpoint=server, waitBetweenQueries=waitBetweenQueries, userAgent=self.agent)
        CachingStrategy.use(JSON, cacheDir=self.cacheNominatim)
        logger.setLevel(ERROR)

    
    def __query(self, q, kwargs:Dict):
        last_exception = None
        for i in range(1,4):
            try:
                res = self.n.query(q, **kwargs)
                self.analytics.numNominatimQueries += 1
                return res
            except Exception as e:
                last_exception = e
                print(f"nominatimService.py query try #{i} failed:", e)
        raise last_exception

    
    def query(self, q):
        return self.__query(q, {"params": {"limit":1}, "wkt":True})

    def lookup(self, q):
        return self.__query(q, {"params": {"limit":1}, "wkt":True, "lookup":True})
        