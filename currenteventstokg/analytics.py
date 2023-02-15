# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from time import time
from pprint import pprint, pformat
from sys import stdout
from json import dump, load
from os import makedirs
from abc import ABC, abstractmethod
from typing import List, Tuple

class AnalyticsDatatype(ABC):
    @abstractmethod
    def reset(self): pass
    def to_json_obj(self): pass
    def from_json_obj(self): pass
    def combine(self, other): pass

class Amount(AnalyticsDatatype):
    def __init__(self, amount=0):
        self.amount = amount
    
    def __iadd__(self, other:int):
        self.amount += other
        return self
    
    def __repr__(self) -> str:
        return f"{self.amount}"
    
    def to_json_obj(self):
        return self.amount
    
    def from_json_obj(self, obj):
        self.amount = obj
    
    def reset(self):
        self.amount = 0
    
    def combine(self, other:"Amount"):
        self.amount += other.amount

class Average(AnalyticsDatatype):
    def __init__(self, unit:str, summ=0, num=0):
        self.unit = unit
        self.sum = summ
        self.num = num
    
    def add_value(self, v:float):
        self.sum += v
        self.num += 1
    
    def get_average(self) -> float:
        if self.num == 0:
            return -1
        else:
            return self.sum/self.num
    
    def __repr__(self) -> str:
        return f"{str(self.get_average())} {self.unit}"
    
    def to_json_obj(self) -> object:
        return [self.sum, self.num, self.unit]
    
    def from_json_obj(self, obj):
        self.sum, self.num, self.unit = obj
    
    def reset(self):
        self.sum, self.num = 0,0

    def combine(self, other:"Average"):
        assert self.unit == other.unit
        self.sum += other.sum
        self.num += other.num

class ValueDict(AnalyticsDatatype):
    def __init__(self, d=None):
        if d:
            self.d = d
        else:
            self.d = {}
    
    def increment(self, key):
        if key in self.d:
            self.d[key] += 1
        else:
            self.d[key] = 1
    
    def get_sorted_by_value(self) -> List[Tuple]:
        return [(x, self.d[x]) for x in sorted(self.d, key=self.d.get, reverse=True)]
    
    def __repr__(self) -> str:
        return pformat(self.get_sorted_by_value(), width=200)
    
    def to_json_obj(self) -> object:
        return self.d
    
    def from_json_obj(self, obj):
        self.d = obj

    def reset(self):
        self.d = {}
    
    def combine(self, other:"ValueDict"):
        for k,v in other.d.items():
            if k in self.d:
                self.d[k] += v
            else:
                self.d[k] = v

class Analytics:

    def __init__(self, basedir, args, analyticsDir):
        self.basedir = basedir
        self.args = args

        self.analyticsDir = self.basedir / analyticsDir
        makedirs(self.analyticsDir, exist_ok=True)

        # num*
        self.numOpenings = Amount()
        self.numDownloads = Amount()
        self.numWikidataQueries = Amount()
        self.numNominatimQueries = Amount()
        self.numArticles = Amount()
        self.numArticlesWithWkt = Amount()
        self.numArticlesWithLocFlag = Amount()
        self.numArticlesWithOsmrelid = Amount()
        self.numArticlesWithOsmobj = Amount()
        self.numArticlesWithFalcon2WikidataEntity = Amount()
        self.numArticlesWithFalcon2LocationArticle = Amount()
        self.numArticleCacheHits = Amount()
        self.numArticleCacheMisses = Amount()
        self.numArticleCacheCachedArticles = Amount()
        self.numTopics = Amount()
        self.numTopicsWithLocation = Amount()
        self.numTopicsWithType = Amount()
        self.numTopicsWithDate = Amount()
        self.numTopicsWithDateSpan = Amount()
        self.numTopicsWithDateOngoing = Amount()
        self.numTopicsWithDateParseError = Amount()
        self.numTopicsWithTime = Amount()
        self.numTopicsWithTimeSpan = Amount()
        self.numTopicsWithTimeParseError = Amount()
        self.numTopicsWithDtstart = Amount()
        self.numTopicsWithDtend = Amount()
        self.numEvents = Amount()
        self.numEventsWithLocation = Amount()
        self.numEventSentencesWithMoreThanOneLocation = Amount()
        self.numEventsWithMoreThanOneLocation = Amount()
        self.numEventsWithMoreThanOneLeafLocation = Amount()
        self.numEventsWithType = Amount()
        self.numFalconQuerys = Amount()
        self.numFalconSuccessfulQuerys = Amount()
        self.numReferences = Amount()
        self.numReferencesNews = Amount()
        

        # avg* = [sum, num, "unit"]
        self.avgWaitTimeUntilRequest = Average("sec")
        self.avgTimeBetweenRequest = Average("sec")
        self.avgDayTime = Average("sec")
        self.avgMonthTime = Average("min")

        # dict*
        self.dictTopicInfoboxLabels = ValueDict()
        self.dictTopicInfoboxTemplates = ValueDict()
        self.dictTopicInfoboxTemplatesWithoutLocationFound = ValueDict()
        self.dictArticleInfoboxClasses = ValueDict()
        
        # not to print
        self.dayStartTime = 0
        self.monthStartTime = 0
        self.last_article_cache_hits = 0
        self.last_article_cache_misses = 0
        self.last_article_cache_currsize = 0


        self.development_analytics_vars = ["dictTopicInfoboxLabels", "dictTopicInfoboxTemplates", 
                "dictTopicInfoboxTemplatesWithoutLocationFound", "dictArticleInfoboxClasses"]

    def topicInfoboxLabels(self, labels):
        if self.args.development_analytics:
            for l in labels:
                self.dictTopicInfoboxLabels.increment(l)
    
    def topicInfoboxTemplate(self, x):
        if self.args.development_analytics:
            self.dictTopicInfoboxTemplates.increment(x)
    
    def topicInfoboxTemplateWithoutLocationFound(self, x):
        if self.args.development_analytics:
            self.dictTopicInfoboxTemplatesWithoutLocationFound.increment(x)
    
    def articleInfoboxClasses(self, l):
        if self.args.development_analytics:
            for x in l:
                self.dictArticleInfoboxClasses.increment(x)
    
    def dayStart(self):
        self.dayStartTime = time()
    
    def dayEnd(self):
        self.avgDayTime.add_value(time() - self.dayStartTime)

    def monthStart(self):
        self.monthStartTime = time()
    
    def monthEnd(self):
        self.avgMonthTime.add_value((time() - self.monthStartTime)/60)
    
    def report_cache_stats(self, hits:int, misses:int, currsize:int):
        self.numArticleCacheHits += (hits - self.last_article_cache_hits)
        self.numArticleCacheMisses += (misses - self.last_article_cache_misses)
        self.numArticleCacheCachedArticles += (currsize - self.last_article_cache_currsize)
        self.last_article_cache_hits = hits
        self.last_article_cache_misses = misses
        self.last_article_cache_currsize = currsize


    def __printTemplateVars(self, width, stream=stdout):
        for k, v in self.__dict__.items():
            if self.args.development_analytics or k not in self.development_analytics_vars:
                if isinstance(v, AnalyticsDatatype):
                    print(f"{k}: {str(v)}", file=stream)


    def printAnalytics(self, title="Analytics", w=200, stream=stdout):
        print("\n" + title + ":", file=stream)
        self.__printTemplateVars(w, stream)
    
    def save(self, suffix):
        res = {}
        for k, v in self.__dict__.items():
            if self.args.development_analytics or k not in self.development_analytics_vars:
                if isinstance(v, AnalyticsDatatype):
                    res[k] = v.to_json_obj()
        
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
            if k in res:
                json_value = res[k]
                if isinstance(v, Amount):
                    self.__dict__[k] = Amount(json_value)
                elif isinstance(v, ValueDict):
                    self.__dict__[k] = ValueDict(json_value)
                elif isinstance(v, Average):
                    self.__dict__[k] = Average(json_value[2], json_value[0], json_value[1])
            else:
                if isinstance(v, AnalyticsDatatype):
                    self.__dict__[k].reset()
        print("Done")
        

    def reset(self):
        for k, v in self.__dict__.items():
            if isinstance(v, AnalyticsDatatype):
                v.reset()
    
    def __iadd__(self, other:"Analytics"):
        for k,v in self.__dict__.items():
            other_v = other.__dict__[k]
            if isinstance(v, AnalyticsDatatype):
                v.combine(other_v)
        return self

