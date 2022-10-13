# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from time import time
from pprint import pprint
from sys import stdout
from json import dump, load
from os import makedirs

class Analytics:

    def __init__(self, basedir, args, analyticsDir):
        self.basedir = basedir
        self.args = args

        self.analyticsDir = self.basedir / analyticsDir
        makedirs(self.analyticsDir, exist_ok=True)

        # num*
        self.numOpenings = 0
        self.numDownloads = 0
        self.numWikidataQueries = 0
        self.numNominatimQueries = 0
        self.numArticles = 0
        self.numArticlesWithWkt = 0
        self.numArticlesWithLocFlag = 0
        self.numArticlesWithOsmrelid = 0
        self.numArticlesWithOsmobj = 0
        self.numTopics = 0
        self.numTopicsWithLocation = 0
        self.numTopicsWithType = 0
        self.numTopicsWithDate = 0
        self.numTopicsWithDateSpan = 0
        self.numTopicsWithDateOngoing = 0
        self.numTopicsWithDateParseError = 0
        self.numTopicsWithTime = 0
        self.numTopicsWithTimeSpan = 0
        self.numTopicsWithTimeParseError = 0
        self.numTopicsWithDtstart = 0
        self.numTopicsWithDtend = 0
        self.numEvents = 0
        self.numEventsWithLocation = 0
        self.numEventSentencesWithMoreThanOneLocation = 0
        self.numEventsWithMoreThanOneLocation = 0
        self.numEventsWithMoreThanOneLeafLocation = 0
        self.numEventsWithType = 0
        self.numFalconQuerys = 0
        self.numFalconSuccessfulQuerys = 0

        # avg* = [sum, num, "unit"]
        self.avgWaitTimeUntilRequest = [0,0, "sec"]
        self.avgTimeBetweenRequest = [0,0, "sec"]
        self.avgDayTime = [0,0, "sec"]
        self.avgMonthTime = [0,0, "min"]

        # dict*
        self.dictTopicInfoboxLabels = {}
        self.dictTopicInfoboxTemplates = {}
        self.dictTopicInfoboxTemplatesWithoutLocationFound = {}
        self.dictArticleInfoboxClasses = {}
        
        # not to print
        self.dayStartTime = 0
        self.monthStartTime = 0

        self.development_analytics_vars = ["dictTopicInfoboxLabels", "dictTopicInfoboxTemplates", 
                "dictTopicInfoboxTemplatesWithoutLocationFound", "dictArticleInfoboxClasses"]

    def topicInfoboxLabels(self, labels):
        if self.args.development_analytics:
            for l in labels:
                self.__incrementDictValue(self.dictTopicInfoboxLabels, l)
    
    def topicInfoboxTemplate(self, x):
        if self.args.development_analytics:
            self.__incrementDictValue(self.dictTopicInfoboxTemplates, x)
    
    def topicInfoboxTemplateWithoutLocationFound(self, x):
        if self.args.development_analytics:
            self.__incrementDictValue(self.dictTopicInfoboxTemplatesWithoutLocationFound, x)
    
    def articleInfoboxClasses(self, l):
        if self.args.development_analytics:
            for x in l:
                self.__incrementDictValue(self.dictArticleInfoboxClasses, x)

    def __incrementDictValue(self, d, x):
        if x in d:
            d[x] += 1
        else:
            d[x] = 1

    def __getSortedListFromDictByValue(self, d):
        return [(x, d[x]) for x in sorted(d, key=d.get, reverse=True)]
    
    def waitTimeUntilRequest(self,t):
        self.avgWaitTimeUntilRequest[0] += t
        self.avgWaitTimeUntilRequest[1] += 1
    
    def timeBetweenRequest(self, t):
        self.avgTimeBetweenRequest[0] += t
        self.avgTimeBetweenRequest[1] += 1
    
    def __getAvg(self, sum, num):
        if num == 0:
            return -1
        else:
            return sum/num
    
    def dayStart(self):
        self.dayStartTime = time()
    
    def dayEnd(self):
        self.avgDayTime[0] += time() - self.dayStartTime
        self.avgDayTime[1] += 1

    def monthStart(self):
        self.monthStartTime = time()
    
    def monthEnd(self):
        self.avgMonthTime[0] += (time() - self.monthStartTime)/60
        self.avgMonthTime[1] += 1

    def __printTemplateVars(self, width, stream=stdout):
        w = 200
        for k, v in self.__dict__.items():
            if self.args.development_analytics or k not in self.development_analytics_vars:
                if k[0:3] == "num":
                    print(k+": "+str(v), file=stream)
                elif k[0:4] == "dict":
                    print(k + ": ", file=stream)
                    pprint(self.__getSortedListFromDictByValue(v), width=w, stream=stream)
                elif k[0:3] == "avg":
                    print(k + ": " + str(self.__getAvg(v[0], v[1])) + " " + v[2],
                        file=stream)


    def printAnalytics(self, title="Analytics", w=200, stream=stdout):
        print("\n" + title + ":", file=stream)
        self.__printTemplateVars(w, stream=stream)
    
    def save(self, suffix):
        res = {}
        for k, v in self.__dict__.items():
            if self.args.development_analytics or k not in self.development_analytics_vars:
                if k[0:3] == "num" or k[0:4] == "dict" or k[0:3] == "avg":
                    res[k] = v
        
        path = self.analyticsDir / (suffix+"_analytics.json")
        with open(path, "w", encoding="utf-8") as fp:
            dump(res, fp)

        print("Analytics saved to", path)

    
    def load(self, suffix):
        print("Fetching analytics of", suffix, end="...", flush=True)
        try:
            with open(self.analyticsDir / (suffix+"_analytics.json"), "r", encoding="utf-8") as fp:
                res = load(fp)
        except OSError as e:
            raise e

        for k, v in self.__dict__.items():
            if k[0:3] == "num" or k[0:4] == "dict" or k[0:3] == "avg":
                if k in res:
                    self.__dict__[k] = res[k]
                else:
                    self.__dict__[k] = self.__getDefault(k, v)
        print("Done")
        

    def reset(self):
        for k, v in self.__dict__.items():
            if k[0:3] == "num" or k[0:4] == "dict" or k[0:3] == "avg":
                self.__dict__[k] = self.__getDefault(k, v)

    def __getDefault(self, k, old_v):
        if k[0:3] == "num":
            return 0
        elif k[0:4] == "dict":
            return {}
        elif k[0:3] == "avg":
            return [0,0,old_v[2]]
    
    def __iadd__(self, other):
        for k in self.__dict__.keys():
            other_v = other.__dict__[k]
            if k[0:3] == "num":
                self.__dict__[k] += other_v
            elif k[0:4] == "dict":
                self.__dict__[k] |= other_v
            elif k[0:3] == "avg":
                self.__dict__[k][0] += other_v[0]
                self.__dict__[k][1] += other_v[1]
        return self

