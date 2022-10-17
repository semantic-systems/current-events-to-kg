# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import json
from pprint import pprint

from rdflib import Graph

from .objects.event import Event
from .objects.topic import Topic


# Replacement for OutputRdf for testing purposes
class OutputJson:

    def __init__(self, basedir, args, analytics, outputFolder):
        self.basedir = basedir
        self.args = args
        self.analytics = analytics

        self.outputFolder = self.basedir / outputFolder
        os.makedirs(self.outputFolder, exist_ok=True)
        
        self.outfile = "eventsWithLocation.json"

    def storeEvent(self, event: Event, graphs: dict[str,Graph]):
        for s in event.sentences:
            for i,l in enumerate(s.links):
                a = s.articles[i]
                if a:
                    if a.location_flag:                    
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
        if True in [a.location_flag for a in event.articles if a != None]:
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
    