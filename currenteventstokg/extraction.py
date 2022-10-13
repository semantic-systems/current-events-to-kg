# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import copy
import datetime
import json
import logging
import re
from os import makedirs
from string import Template
from typing import Dict, List, Optional, Tuple, Union

from bs4 import BeautifulSoup, NavigableString, Tag
from rdflib import Graph

from .analytics import Analytics
from .dateTimeParser import DateTimeParser
from .placeTemplatesExtractor import PlacesTemplatesExtractor
from .etc import month2int
from .falcon2Service import Falcon2Service
from .nominatimService import NominatimService
from .objects.article import Article
from .objects.infoboxRow import *
from .objects.link import Link
from .objects.newsEvent import NewsEvent
from .objects.osmElement import OSMElement
from .objects.sentence import Sentence
from .objects.topic import Topic
from .wikidataService import WikidataService


class Extraction:
    def __init__(self, basedir, inputData, outputData, analytics: Analytics, 
            nominatimService: NominatimService, wikidataService: WikidataService,
            falcon2Service: Falcon2Service, place_templates_extractor:PlacesTemplatesExtractor, args, bs_parser:str):
        self.basedir = basedir 
        self.inputData = inputData
        self.outputData = outputData
        self.analytics = analytics
        self.nominatimService = nominatimService
        self.wikidataService = wikidataService
        self.falcon2Service = falcon2Service
        self.place_templates = place_templates_extractor.get_templates(args.force_parse)
        self.args = args
        self.bs_parser = bs_parser
        
        # debug logger init
        logdir = self.basedir / "logs"
        makedirs(logdir, exist_ok=True)

        timeParseErrorLogger = logging.getLogger('timeParseError')
        timeParseErrorLogger.setLevel(logging.DEBUG)
        timeHandler = logging.FileHandler(logdir / "timeParseError.log", encoding='utf-8')
        timeHandler.setFormatter(logging.Formatter('%(message)s'))
        timeParseErrorLogger.addHandler(timeHandler)

        dateParseErrorLogger = logging.getLogger('dateParseError')
        dateParseErrorLogger.setLevel(logging.DEBUG)
        dateHandler = logging.FileHandler(logdir / "dateParseError.log", encoding='utf-8')
        dateHandler.setFormatter(logging.Formatter('%(message)s'))
        dateParseErrorLogger.addHandler(dateHandler)

        self.timeParseErrorLogger = timeParseErrorLogger
        self.dateParseErrorLogger = dateParseErrorLogger

    def __getTextAndLinksRecursive(self, x, startIndex=0) -> Tuple[str, list[Link]]:
        s = ""
        links = []
        curIndex = startIndex

        if(isinstance(x, NavigableString)):
            s += x.get_text()
            curIndex += len(x)
        elif(isinstance(x, Tag)):
            childrenText, childrenLinks, childrenTextLength = "",[], 0
            for c in x.children:
                childText, childLinks = self.__getTextAndLinksRecursive(c, curIndex)
                childrenText += childText
                childrenLinks += childLinks
                childrenTextLength += len(childrenText)

            # extract own link
            if(x.name == "a" and "href" in x.attrs):
                href = x["href"]

                # add url prefix to urls from wikipedia links
                if(href[0] == "/"):
                    href = "https://en.wikipedia.org" + href
                
                external = False
                if "class" in x.attrs and "external" in x["class"]:
                    external = True

                newLink = Link(href, childrenText, curIndex, curIndex + childrenTextLength, external)
                links.append(newLink)
            else:
                links += childrenLinks
            
            s += childrenText
            curIndex += childrenTextLength
        else:
            raise Exception(str(x) + " Type: " + str(type(x)))
        
        return s, links
    
    def __parseEventTagRecursive(self, x, links=None, sourceLinks=None, startIndex=0) -> Tuple[str, list[Link], str, list[Link]]:
        text = ""
        sourceText = ""
        curIndex = startIndex

        if not links and not sourceLinks:
            links, sourceLinks = [],[]

        for c in x.children:
            if(isinstance(c, NavigableString)):
                text += c
                curIndex += len(c)
            elif(isinstance(c, Tag)):
                textRec, linksRec, sourceTextRec, sourceLinksRec = self.__parseEventTagRecursive(
                    c, links, sourceLinks, curIndex)
                textLength = len(textRec)

                source = False
                # extract link
                if(c.name == "a"):
                    href = c["href"]

                    # add url prefix to urls from wikipedia links
                    if(href[0] == "/"):
                        href = "https://en.wikipedia.org" + href

                    external = False
                    if "class" in c.attrs and "external" in c["class"]:
                        external = True
                        if textRec[0] == "(" and textRec[-1] == ")":
                            source = True
                    
                    newLink = Link(href, textRec, curIndex, curIndex + textLength, external)

                    if source:
                        sourceLinks.append(newLink)
                    else:
                        links.append(newLink)

                if source:
                    sourceText += textRec
                else:
                    text += textRec
                
                curIndex += textLength
            else:
                raise Exception()
        return text, links, sourceText, sourceLinks

    def __getParentTopicElement(self, x):
        p = x.find_parent("li")

        if(p == None):
            # when parent is no link, but initial Topic without Link
            return x.parent.find_previous_sibling("p").b.string
        else:
            return p

    def __tryGetCoordinatesFromPage(self, p) -> Optional[list[float]]:
        c = p.find(attrs={"id": "coordinates"})
        if c:
            geodms = c.find("span", attrs={"class": "geo-dms"})
            if geodms:
                return self.__parseCoords(geodms)
        return

    def __testIfPageIsLocation(self, p, ib, coord, templates):
        # test for infobox template css classes
        if self.__testIfPageIsLocationCss(p, ib, coord):
            return True
        
        # test if templates match place templates
        if self.__testIfPageIsLocationTemplate(templates):
            return True

        return False

    def __testIfPageIsLocationCss(self, p, ib, coord):
        if ib:
            self.analytics.articleInfoboxClasses(ib.attrs["class"])

            for c in ["ib-settlement", "ib-country", "ib-islands", "ib-pol-div", "ib-school-district", 
                "ib-uk-place"]:
                if c in ib.attrs["class"]:
                    return True

        return False
    
    def __testIfPageIsLocationTemplate(self, templates):
        if templates & self.place_templates:
            return True

        return False
    
    def __dms2dd(self, dms:str) -> float: 
        res =  re.split('[°′″]', dms) # 36°13′50.3″N
        if len(res) == 2:
            degrees, direction = res
            minutes, seconds = 0, 0
        elif len(res) == 3:
            degrees, minutes, direction = res
            seconds = 0
        elif len(res) == 4:
            degrees, minutes, seconds, direction = res
        else:
            raise Exception()

        return (float(degrees) + float(minutes)/60 + float(seconds)/(3600)) * (-1 if direction in ['W', 'S'] else 1)
    
    
    def __parseCoords(self, coordsSpan) -> list[float]:
        lat = coordsSpan.find("span", attrs={"class": "latitude"}, recursive=False)
        lon = coordsSpan.find("span", attrs={"class": "longitude"}, recursive=False)
        if lat and lon:
            return [self.__dms2dd(lat.string), self.__dms2dd(lon.string)]
        return None
    

    def __getLocationFromInfobox(self, ib, templates, infoboxTemplates, topicFlag):

        def getTextAndLinksFromLocationValue(self, parentTag):
            text, links = "", []
            index = 0
            for c in parentTag.children:
                if isinstance(c, NavigableString) or (c.name and c.name in ["a", "b", "abbr"]):
                    t, l = self.__getTextAndLinksRecursive(c, startIndex=index)
                    index += len(t)
                    text += t
                    links += l
                elif c.name and c.name == "br":
                    text += "\n"
                    index += 1
                elif "class" in c.attrs and "flagicon" in c.attrs["class"]:
                    continue
                elif c.name and c.name in ["sup"]:
                    continue
                else:
                    break
            return text, links

        rows = {}

        ## Notes: 
        # Template:Infobox_election only flag img...

        # choose label based of Template
        if any(t in templates for t in ["Template:Infobox_storm"]):
            label = "Areas affected"
        else:
            label = "Location"
        
        # find location label tag
        th = ib.tbody.find("th", string=label, attrs={"class": "infobox-label"})
        if not th:
            return rows
        
        # find value tag
        td = th.find_next_sibling("td")
        div = td.find("div", attrs={"class": "location"}, recursive=False)
        if div:
            loc = div
        else:
            loc = td
        
        # parse value
        if(isinstance(loc, NavigableString)):
            locText, locLinks = loc.string, []
        else:
            locText, locLinks = getTextAndLinksFromLocationValue(self, loc)

        if locText:
            # get entities about the location value from falcon2 api
            falcon2_wikidata_entities, falcon2_dbpedia_entities = self.falcon2Service.querySentence(locText)

            # get wkts from infobox location value link labels
            ib_wkts = {}
            for l in locLinks:
                res = self.nominatimService.query(l.text)
                osmid, osmtype, ib_wkt = res.id(), res.type(), res.wkt()
                ib_wkts[l] = OSMElement(res.id(), res.type(), res.wkt())

            # create row
            rows[label] = InfoboxRowLocation(label, locText, locLinks, 
                                    falcon2_wikidata_entities, falcon2_dbpedia_entities, ib_wkts)
            self.analytics.numTopicsWithLocation += 1
        elif topicFlag:
            for t in infoboxTemplates:
                self.analytics.topicInfoboxTemplateWithoutLocationFound(t)
        
        # extract coordinates from "Location" label and save it as seperate row
        coords = None
        geodms = td.find("span", attrs={"class": "geo-dms"})
        if geodms:
            coords = self.__parseCoords(geodms)
            if coords:
                rows["Coordinates"] = InfoboxRow("Coordinates", coords, [])

        return rows
    
    
    def __getDateAndTimeFromTopicInfobox(self, ib, templates, labels) -> Tuple[
                Dict[(str,InfoboxRow)],
                Dict[str, str],
            ]:

        def getTextAndLinksFromDateValue(self, valueTag):
            text, links = "", []
            index = 0
            if(isinstance(valueTag, NavigableString)):
                text, links = valueTag.string, []
            else:
                for c in valueTag.children:
                    if c.name and c.name == "span" and (
                        "class" in c.attrs and "noprint" in c.attrs["class"] or 
                        "style" in c.attrs and "display:none" in c.attrs["style"]):
                        continue
                    elif isinstance(c, NavigableString) or (c.name and c.name in ["a", "b", "abbr", "span"]):
                        t, l = self.__getTextAndLinksRecursive(c, startIndex=index)
                        index += len(t)
                        text += t
                        links += l
                    elif c.name and c.name == "br":
                        text += "\n"
                        index += 1
                    elif c.name and c.name in ["sup"]:
                        continue
                    else:
                        break
            return text, links

        def extractRowForLabelIfExists(labels, label):
            if label in labels:
                th = ib.tbody.find("th", string=label)
                if th:
                    td = th.find_next_sibling("td")
                    text, links = getTextAndLinksFromDateValue(self, td)

                    return {label: InfoboxRow(label, text, links)}
            return {}

        microformats = {}
        if "vevent" in ib.attrs["class"]:
            dtstartTag = ib.find("span", attrs={"class": "dtstart"}, recursive=True)
            if dtstartTag:
                dtstart, l = self.__getTextAndLinksRecursive(dtstartTag)
                microformats["dtstart"] = dtstart
                self.analytics.numTopicsWithDtstart += 1
            
            dtendTag = ib.find("span", attrs={"class": "dtend"}, recursive=True)
            if dtendTag:
                dtend, l = self.__getTextAndLinksRecursive(dtendTag)
                microformats["dtend"] = dtend
                self.analytics.numTopicsWithDtend += 1
        
        dateRows = {}
        dateRows |= extractRowForLabelIfExists(labels, "Date")
        dateRows |= extractRowForLabelIfExists(labels, "Date(s)")
        dateRows |= extractRowForLabelIfExists(labels, "First outbreak")
        dateRows |= extractRowForLabelIfExists(labels, "Arrival Date")
        dateRows |= extractRowForLabelIfExists(labels, "Duration")
        dateRows |= extractRowForLabelIfExists(labels, "Start Date")
        dateRows |= extractRowForLabelIfExists(labels, "End Date")

        timeRows = {}
        timeRows |= extractRowForLabelIfExists(labels, "Time")

        hasTime, hasTimeSpan = False, False
        resRows = {}
        for label, ibRow in timeRows.items():
            value = re.sub(r"[–−]", r"-", ibRow.value)
            timeDict = DateTimeParser.parseTimes(value)
            if timeDict:
                time = timeDict["start"]
                hasTime = True
                endtime, timezone = None, None
                if "end" in timeDict:
                    endtime = timeDict["end"]
                    hasTimeSpan = True
                if "tz" in timeDict:
                    timezone = timeDict["tz"]
                timeRow = InfoboxRowTime(ibRow.label, ibRow.value, ibRow.valueLinks, time, endtime, timezone)
                resRows[label] = timeRow
            
            else:
                self.timeParseErrorLogger.info("\"" + value + "\"")
                self.analytics.numTopicsWithTimeParseError += 1
            
        for label, ibRow in dateRows.items():
            value = re.sub(r"[–−]", r"-", ibRow.value)

            # filter out some frequent unwanted values
            asOf = re.search(r"[aA]s of", value)
            if not asOf and value not in ["Wuhan, Hubei, China", "Wuhan, China"]:

                timeDict = DateTimeParser.parseTimes(value)

                if timeDict:
                    hasTime = True
                    spl = timeDict["start"].split(":")
                    startTime = [int(spl[0]), int(spl[1])]
                    if "end" in timeDict:
                        hasTimeSpan = True
                        spl = timeDict["end"].split(":")
                        endTime = [int(spl[0]), int(spl[1])]
                    else:
                        endTime = None

                dateDict = DateTimeParser.parseDates(value)
                
                if "date" in dateDict:
                    date = dateDict["date"]
                    self.analytics.numTopicsWithDate += 1
                    until, ongoing = None, False
                    if "until" in dateDict:
                        until = dateDict["until"]
                        self.analytics.numTopicsWithDateSpan += 1
                    elif "ongoing" in dateDict and dateDict["ongoing"] == True:
                        ongoing = True
                        self.analytics.numTopicsWithDateOngoing += 1

                    if timeDict and "tz" in timeDict:
                        timezone = timeDict["tz"]
                    else:
                        timezone = None
                    dateRow = InfoboxRowDate(
                        ibRow.label, ibRow.value, ibRow.valueLinks, date, until, ongoing, timezone)
                    resRows[label] = dateRow
                else:
                    self.dateParseErrorLogger.info("\"" + value + "\"")
                    self.analytics.numTopicsWithDateParseError += 1
        
        if hasTime:
            self.analytics.numTopicsWithTime += 1
            if hasTimeSpan:
                self.analytics.numTopicsWithTimeSpan += 1

        return resRows, microformats
        
        
    
    def __parseInfobox(self, ib, templates, topicFlag=False) -> Tuple[
            Dict[str, InfoboxRow],
            Dict[str, str] ]:
        tib = [t for t in templates if re.match("template:infobox", t.lower())]
        infoboxRows = {}

        # extract Locations
        locs = self.__getLocationFromInfobox(ib, templates, tib, topicFlag)
        infoboxRows |= locs

        # extract Dates and Times
        microformats = {}
        if topicFlag:
            for t in tib:
                self.analytics.topicInfoboxTemplate(t)

            labels = [str(th.string) for th in ib.tbody.find_all("th") if th.string]
            self.analytics.topicInfoboxLabels(labels)

            rows, microformats = self.__getDateAndTimeFromTopicInfobox(ib, templates, labels)
            if rows:
                infoboxRows |= rows
        
        return infoboxRows, microformats

    def __testIfUrlIsArticle(self, url:str) -> bool:
        # negative tests
        if re.match("https://en.wikipedia.org/wiki/\w*:", url):
            # 17.1.22 has link to category page in event text
            return False

        # positive test
        if re.match("https://en.wikipedia.org/wiki/", url):
            return True
        return False
    

    def __getArticleFromUrlIfArticle(self, url, topicFlag=False) -> Article:
        # return none if url is not an article
        if not self.__testIfUrlIsArticle(url):
            return None
        
        # get page
        page = self.inputData.fetchWikiPage(url)
        p = BeautifulSoup(page, self.bs_parser)

        # extract coordinates and infobox
        coord = self.__tryGetCoordinatesFromPage(p)
        ib = p.find("table", attrs={"class": "infobox"})

        # find tag with the jsonld graph with page informations
        # there are two of these, but i think they are always equal(?)
        articleGraphTag = p.find("script", attrs={"type": "application/ld+json"})
        if articleGraphTag == None:
            # if this is not present i take it as a indicator that this is not a article, 
            # but redirect page etc (not confirmed)
            return None
        
        # parse graph
        pageGraph = json.loads(articleGraphTag.string)
        # get 'real' url of page, due to redirects etc
        graphUrl = pageGraph["url"]
        # test again if it is eg redict page
        if not self.__testIfUrlIsArticle(graphUrl):
            return None
        
        # extract various info
        datePublished = None
        if "datePublished" in pageGraph:
            datePublished = str(pageGraph["datePublished"])
        dateModified = None
        if "dateModified" in pageGraph:
            dateModified = str(pageGraph["dateModified"])
        name = None
        if "name" in pageGraph:
            name = str(pageGraph["name"])
        headline = None
        if "headline" in pageGraph:
            headline = str(pageGraph["headline"])
        wikidataEntityURI = None
        if "mainEntity" in pageGraph:
            wikidataEntityURI = str(pageGraph["mainEntity"])
        
        # extract json with page loading stats etc
        # (RLQ=window.RLQ||[]).push(function(){mw.config.set(    <here>     );});
        statsString = articleGraphTag.find_previous_sibling("script").string[51:-5]
        statsJson = json.loads(statsString)
        templates = set(re.findall(r"Template:\w+", str(statsJson["wgPageParseReport"]["limitreport"]["timingprofile"])))

        # parse the infobox
        ibRows, microformats = {}, {}
        if ib:
            ibRows, microformats = self.__parseInfobox(ib, templates, topicFlag)
        
        # check if page is a location
        locFlag = self.__testIfPageIsLocation(p, ib, coord, templates)
        if locFlag:
            self.analytics.numArticlesWithLocFlag += 1
        
        ## location classifier testing code
        # locFlagOld = self.__testIfPageIsLocationCss(p, ib, coord)
        # locFlagNew = self.__testIfPageIsLocationTemplate(templates)
        # if  locFlag != locFlagOld or \
        #     locFlag != (locFlag or bool(coord)) or \
        #     locFlag != (locFlagOld or bool(coord)) :
        #     with open(self.basedir / "loclog.json", "a") as f:
        #         json.dump({"name":name, "old":locFlagOld, "new":locFlag, "coord":bool(coord)}, f)
        #         print("", file=f)
        
        # check for parent locations
        parent_locations_and_relation = self.wikidataService.getHigherlevelLocations(wikidataEntityURI)

        # check for OSM entitys from the wikidata uri of this page
        osmrelids, osmobjs = [], []
        if wikidataEntityURI:
            osmrelids, osmobjs = self.wikidataService.getOSMEntitys(wikidataEntityURI)

        # get one hop graph from wikidata around this pages wd URI
        wd_one_hop_g = Graph()
        entity_label_dict = {}
        if wikidataEntityURI:
            wd_one_hop_g = self.wikidataService.getOneHopSubgraph(wikidataEntityURI)

            # extract the "type" of this article through wikidata
            # extract article instance-classes with label
            is_instance_of_entity = []
            q = Template("""PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    SELECT DISTINCT ?i WHERE {
        <$e> wdt:P31 ?i .
    }""").substitute(e=wikidataEntityURI)

            qres = wd_one_hop_g.query(q)
            for row in qres:
                is_instance_of_entity.append(row.i)
            
            entity_label_dict = self.wikidataService.getEntitysLabels(is_instance_of_entity)

            if topicFlag and len(entity_label_dict) > 0:
                self.analytics.numTopicsWithType += 1
        
        # extract wikidata wkts
        articleWithWkt = False
        wiki_wkts = []
        if len(osmrelids) >= 1:
            articleWithWkt = True
            self.analytics.numArticlesWithOsmrelid +=1
            for x in osmrelids:
                res = self.nominatimService.lookup("relation/" + x)
                # id, type and wkt could be None!
                wiki_wkts.append(OSMElement(res.id(), res.type(), res.wkt()))
        elif len(osmobjs) >= 1:
            articleWithWkt = True
            self.analytics.numArticlesWithOsmobj +=1
            for x in osmobjs:
                res = self.nominatimService.lookup(x)
                # id, type and wkt could be None!
                wiki_wkts.append(OSMElement(res.id(), res.type(), res.wkt()))
        
        if articleWithWkt:
            self.analytics.numArticlesWithWkt += 1
        
        return Article(graphUrl, locFlag, coord, str(ib), ibRows, str(articleGraphTag.string), templates, 
                wiki_wkts, wikidataEntityURI, wd_one_hop_g, parent_locations_and_relation, 
                entity_label_dict, microformats, datePublished, dateModified, name, headline)

    def __getArticles(self, wikiArticleLinks):
        articles = []
        for l in wikiArticleLinks:
            url = l.href
            articles.append(self.__getArticleFromUrlIfArticle(url, topicFlag=False))
            self.analytics.numArticles += 1
        
        return articles

    def __parseTopic(self, t, parentTopics, date:datetime.date, num_topics:int, sourceUrl:str) -> list[Topic]:
        if(isinstance(t, NavigableString)):
            # when parent is no link, but initial Topic without Link
            return [Topic(t, t, None, None, None, date, num_topics, sourceUrl)]
        else:
            aList = t.find_all("a", recursive=False)
            # add italic topics
            iList = t.find_all("i", recursive=False)
            for i in iList:
                aList.append(i.find("a", recursive=False))

            if len(aList) == 0:
                # rare case when non inital topics have no link (14.1.2022 #4)
                text, _ = self.__getTextAndLinksRecursive(t.contents[0])
                text = text.strip("\n ")
                return [Topic(text, text, None, None, None, date, num_topics, sourceUrl)]
            else:
                topics = []
                for a in aList:
                    text, links = self.__getTextAndLinksRecursive(a)
                    href = a["href"]

                    # add url prefix to urls from wikipedia links
                    if(href[0] == "/"):
                        href = "https://en.wikipedia.org" + href
                    
                    # article == None if href is redlink like on 27.1.2022
                    article = self.__getArticleFromUrlIfArticle(href, topicFlag=True)
                    
                    # index of the topic
                    tnum = num_topics + len(topics)

                    t = Topic(a, text, href, article, parentTopics, date, tnum, sourceUrl)
                    topics.append(t)

            return topics
    
    def __splitEventTextIntoSentences(self, text, wikiLinks, articles) -> List[Sentence]:

        # split links occur, which are put into the sentence where they end in
        def getArticlesAndLinksInSpan(wikiLinks, articles, start, end, linkOffset):
            i = linkOffset
            sentenceLocNum = 0
            sentenceLinks = []
            sentenceArticles = []
            
            while(i < len(wikiLinks) and wikiLinks[i].endPos <= end):
                # switch context of link from event to sentence level
                l = copy.copy(wikiLinks[i])
                l.startPos -= start
                l.endPos -= start
                
                sentenceLinks.append(l)
                sentenceArticles.append(articles[i])
                
                if articles[i] and articles[i].locFlag:
                    sentenceLocNum += 1
                i += 1

            if sentenceLocNum > 1:
                self.analytics.numEventSentencesWithMoreThanOneLocation += 1

            return (i, sentenceLinks, sentenceArticles, sentenceLocNum)

        textlen = len(text)
        sentences = []
        locNum = 0
        i = 0
        start = 0

        for p in re.finditer(r'\. ', text):
            end = p.start()+2
            
            # skip this guess of a sentence ending -> its inside a link, links usually dont span sentences 
            if any([end > wl.startPos and end < wl.endPos for wl in wikiLinks]):
                continue

            res = getArticlesAndLinksInSpan(wikiLinks, articles, start, end, i)
            i, sentenceLinks, sentenceArticles, sentenceLocNum = res
            
            sentences.append(Sentence(text[start:end], start, end, sentenceLinks, sentenceArticles))
            locNum += sentenceLocNum

            start = end

        # if there are characters left and the last char in text is a ".", put them in a last sentence if
        if start != textlen and text[-1] == ".":
            res = getArticlesAndLinksInSpan(wikiLinks, articles, start, textlen, i)
            i, sentenceLinks, sentenceArticles, sentenceLocNum = res
            sentences.append(Sentence(text[start:textlen], start, textlen, sentenceLinks, sentenceArticles))
            locNum += sentenceLocNum

        # use everything as one sentence if no sentences have been found
        if len(sentences) == 0:
            res = getArticlesAndLinksInSpan(wikiLinks, articles, 0, textlen, 0)
            i, sentenceLinks, sentenceArticles, sentenceLocNum = res
            sentences.append(Sentence(text, 0, textlen, sentenceLinks, sentenceArticles))
            locNum += sentenceLocNum

        if locNum > 1:
            self.analytics.numEventsWithMoreThanOneLocation += 1

        return sentences # doest have Source at the end
    
    
    def __searchForEventTypesRecursive(self, topics) -> Dict[str, str]:
        eventTypes = {}
        
        for t in topics:
            if t.article:
                eventTypes |= t.article.classes_with_labels
        
        if len(eventTypes) == 0:
            for t in topics:
                if t.parentTopics:
                    res = self.__searchForEventTypesRecursive(t.parentTopics)
                    eventTypes |= res
        
        return eventTypes

    def parsePage(self, sourceUrl, page, year, monthStr):
        soup = BeautifulSoup(page, self.bs_parser)
        for day in range(self.args.monthly_start_day, self.args.monthly_end_day+1):
            self.analytics.dayStart()

            idStr = str(year) + "_" + monthStr + "_" + str(day)
            print(idStr + " ", end="", flush=True)

            # select doesnt work, because id starts with number
            daybox = soup.find(attrs={"id": idStr})
            if(daybox):
                month = month2int[monthStr]
                date = datetime.date(year, month, day)

                description = daybox.select_one(".description")

                # two versions of headings are used (afaik):
                # <p><b>Health and environment</b></p>
                # <div class="current-events-content-heading" role="heading">Armed conflicts and attacks</div>
                def isInitalTopic(tag:Tag):
                    return (tag.name == "p" and len(tag.attrs) == 0) \
                        or (tag.name == "div" and tag.has_attr('class') \
                        and "current-events-content-heading" in tag.attrs["class"])
                initalTopics = description.find_all(isInitalTopic, recursive=False)
                # print("InitialTopics:")
                # for i,x in enumerate(initalTopics):
                #     print(i, str(x)[:200])
                tnum = 0
                evnum = 0
                for i in initalTopics:
                    iText, _ = self.__getTextAndLinksRecursive(i)
                    iTopic = Topic(iText, iText, None, None, None, date, tnum, sourceUrl)
                    self.outputData.storeTopic(iTopic)
                    tnum += 1
                    #print("iTopic:", iText)

                    eventList = i.find_next_sibling("ul")

                    # extract events under their topics iteratively
                    s = []  # stack with [parentTopics, li]
                    lis = eventList.find_all("li", recursive=False)
                    s += [[[iTopic], li] for li in lis[::-1]]
                    while(len(s) > 0):
                        # print()
                        # for i,x in enumerate(s):
                        #     print(i, str(x[1])[:200])
                        # print()
                        xList = s.pop()
                        parentTopics = xList[0]
                        x = xList[1]

                        # x has ul's ? topic : event
                        ul = x.find("ul")
                        if(ul == None):  # x == event
                            print("E", end="", flush=True)
                            text, links, sourceText, sourceLinks = self.__parseEventTagRecursive(x)
                            #print("\n", text)
                            wikiArticleLinks = [l for l in links if self.__testIfUrlIsArticle(l.href)]

                            articles = self.__getArticles(wikiArticleLinks)
                            
                            sentences = self.__splitEventTextIntoSentences(text, wikiArticleLinks, articles)
                            
                            eventTypes = self.__searchForEventTypesRecursive(parentTopics)
                            if len(eventTypes) > 0:
                                self.analytics.numEventsWithType += 1

                            e = NewsEvent(x, parentTopics, text, sourceUrl, date, sentences, 
                                    sourceLinks, sourceText, eventTypes, evnum) 

                            self.analytics.numEvents += 1
                            self.outputData.storeEvent(e)

                            if(True in [a.locFlag for a in articles if a != None]):
                                self.analytics.numEventsWithLocation += 1
                            # else:
                            #     print("\n", e)

                            evnum += 1
                        else:  # x == topic(s)
                            print("T", end="", flush=True)
                            topics = self.__parseTopic(x, parentTopics, date, tnum, sourceUrl)

                            for t in topics:
                                #print("\n", t.text)
                                self.analytics.numTopics += 1
                                self.outputData.storeTopic(t)
                                tnum += 1
                                
                            # append subtopics to stack
                            subtopics = ul.find_all("li", recursive=False)
                            subtopicsAndParentTopic = [
                                [topics, st] for st in subtopics[::-1]]
                            s += subtopicsAndParentTopic

            print("")
            self.analytics.dayEnd()
        return
