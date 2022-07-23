import json
from pprint import pprint

from rdflib import Graph

from src.objects.newsEvent import NewsEvent
from src.objects.topic import Topic


# Replacement for OutputRdf for testing purposes
class OutputJson:

    def __init__(self, basedir, args, analytics, outputFolder):
        self.basedir = basedir
        self.args = args
        self.analytics = analytics

        self.outputFolder = self.basedir / outputFolder
        os.makedirs(self.outputFolder, exist_ok=True)
        
        self.outfile = "eventsWithLocation.json"

    def storeEvent(self, event: NewsEvent, graphs: dict[str,Graph]):
        for s in event.sentences:
            for i,l in enumerate(s.links):
                a = s.articles[i]
                if a:
                    if a.locFlag:                    
                        line = { 
                            "text":str(event.text),
                            "s_begin":str(s.start),
                            "location":str(l.text),
                            "begin":str(l.startPos),
                            "end":str(l.endPos),
                        }
                        with open(self.outputFolder / self.outfile, "a", encoding="utf-8") as f:
                            json.dump(line, f, separators=(',', ':'))  
                            f.write("\n")
                        
                        return
        if True in [a.locFlag for a in event.articles if a != None]:
            print(event.text)
            pprint(event.articles)
            for s in event.sentences:
                for x in [s.text, s.start, s.end, s.links, s.articles]:
                    pprint(x)

        
    
    def storeTopic(self, topic: Topic, graphs: dict[str,Graph]):
        pass
        
    def loadGraph(self, fileName):
        return None

    def saveGraph(self, graph, outputFileName="dataset.jsonld"):
        pass
    