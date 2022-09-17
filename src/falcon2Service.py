import requests
from atexit import register
from os.path import exists
from json import dump, load



class Falcon2Service():
    def __init__(self, basedir, args):
        self.basedir = basedir
        self.args = args

        self.cachePath = self.basedir / args.cache_dir / "falcon2_entities_cache.json"
        self.text2entities = self.__loadJsonDict(self.cachePath)

        self.url_long = 'https://labs.tib.eu/falcon/falcon2/api?mode=long&db=1'
        self.headers = {'content-type': 'application/json', 'Accept-Charset': 'UTF-8'}

        # save caches after termination
        register(self.__saveCaches)
    

    def __saveCaches(self):
        self.__saveJsonDict(self.cachePath, self.text2entities)
 

    def __loadJsonDict(self, file_path):
        if(exists(file_path)):
            with open(file_path, mode='r', encoding="utf-8") as f:
                return load(f)
        else:
            return {}
    
    
    def __saveJsonDict(self, file_path, dic):
        with open(file_path, mode='w', encoding="utf-8") as f:
            dump(dic, f)
    

    def querySentence(self, text):
        entities_wikidata, entities_dbpedia = None, None
        if text in self.text2entities and not self.args.ignore_falcon2_cache:
            entities_wikidata, entities_dbpedia = self.text2entities[text]
        else:
            text_cleaned=text.replace('"','')
            text_cleaned=text_cleaned.replace("'","")

            payload = '{"text":"' + text_cleaned + '"}'
            for i in range(3):
                r = requests.post(self.url_long, data=payload.encode('utf-8'), headers=self.headers)
                if r.status_code == 200:
                    response = r.json()

                    # remove brackets from wikidata iris
                    entities_wikidata = [ x["URI"] for x in response['entities_wikidata']]
                    entities_dbpedia = [ x["URI"] for x in response['entities_dbpedia']]

                    self.text2entities[text] = [entities_wikidata, entities_dbpedia]
                    break
            
            # raise if query failed every time
            if not entities_wikidata or not entities_dbpedia:
                raise Exception("Could not query Falcon2 API")

        return entities_wikidata, entities_dbpedia
