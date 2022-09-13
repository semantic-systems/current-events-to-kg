import requests
from atexit import register



class Falcon2Service():
    def __init__(self, basedir, args):
        self.basedir = basedir
        self.args = args

        self.wdCachePath = self.basedir / args.cache_dir / "falcon2_wikidata_entities.json"
        self.wdCache = self.__loadJsonDict(self.wdCachePath)

        self.url_long = 'https://labs.tib.eu/falcon/falcon2/api?mode=long&db=1'
        self.headers = {'content-type': 'application/json', 'Accept-Charset': 'UTF-8'}

        # save caches after termination
        register(self.__saveCaches)
    

    def __saveCaches(self):
        self.__saveJsonDict(self.wdCachePath, self.wdCache, self.args.ignore_falcon2_cache)
 

    def __loadJsonDict(self, file_path, force):
        if(exists(file_path) and not force):
            with open(file_path, mode='r', encoding="utf-8") as f:
                return load(f)
        else:
            return {}
    
    
    def __saveJsonDict(self, file_path, dic):
        with open(file_path, mode='w', encoding="utf-8") as f:
            dump(dic, f)
    

    def querySentence(text):
        text=text.replace('"','')
        text=text.replace("'","")

        payload = '{"text":"'+text+'"}'
        for i in range(3):
            r = requests.post(self.url_long, data=payload.encode('utf-8'), headers=self.headers)
            if r.status_code == 200:
                response = r.json()

                # remove brackets from wikidata iris
                entities_wikidata = [ x[1].replace('<','').replace('>','')
                            for x in response['entities_wikidata']]
                entities_dbpedia = [ x[0] for x in response['entities_dbpedia']]

                return entities_wikidata, entities_dbpedia

        raise Exception("Could not query Falcon2 API")
