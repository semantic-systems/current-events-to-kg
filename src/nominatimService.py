from logging import ERROR
from os import makedirs

from OSMPythonTools import logger
from OSMPythonTools.cachingStrategy import JSON, CachingStrategy
from OSMPythonTools.nominatim import Nominatim


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

    
    def query(self, q):
        self.analytics.numNominatimQueries += 1
        return self.n.query(q, params={"limit":1}, wkt=True)

    def lookup(self, q):
        self.analytics.numNominatimQueries += 1
        return self.n.query(q, params={"limit":1}, wkt=True, lookup=True)
        