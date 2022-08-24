# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import copy
import json
import re
from datetime import datetime
from string import Template
from typing import List, Dict, Optional, Tuple, Union
import logging
from os import makedirs

from bs4 import BeautifulSoup, NavigableString, Tag
from rdflib import Graph

from src.analytics import Analytics
from src.nominatimService import NominatimService
from src.objects.article import Article
from src.objects.infoboxRow import InfoboxRow
from src.objects.link import Link
from src.objects.newsEvent import NewsEvent
from src.objects.osmElement import OSMElement
from src.objects.sentence import Sentence
from src.objects.topic import Topic
from src.wikidataService import WikidataService
from src.dateTimeParser import DateTimeParser

from src.etc import month2int


class Extraction:

    bsParser = "lxml" # "lxml" faster than "html.parser"

    def __init__(self, basedir, inputData, outputData, analytics: Analytics, 
            nominatimService: NominatimService, wikidataService: WikidataService, args):
        self.basedir = basedir 
        self.inputData = inputData
        self.outputData = outputData
        self.analytics = analytics
        self.nominatimService = nominatimService
        self.wikidataService = wikidataService
        self.args = args
        
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

    def getTextAndLinksRecursive(self, x, startIndex=0) -> Tuple[str, list[Link]]:
        s = ""
        links = []
        curIndex = startIndex

        if(isinstance(x, NavigableString)):
            s += x.get_text()
            curIndex += len(x)
        elif(isinstance(x, Tag)):
            childrenText, childrenLinks, childrenTextLength = "",[], 0
            for c in x.children:
                childText, childLinks = self.getTextAndLinksRecursive(c, curIndex)
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
    
    def parseEventTagRecursive(self, x, links=None, sourceLinks=None, startIndex=0) -> Tuple[str, list[Link], str, list[Link]]:
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
                textRec, linksRec, sourceTextRec, sourceLinksRec = self.parseEventTagRecursive(
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

    def getParentTopicElement(self, x):
        p = x.find_parent("li")

        if(p == None):
            # when parent is no link, but initial Topic without Link
            return x.parent.find_previous_sibling("p").b.string
        else:
            return p

    def tryGetCoordinatesFromPage(self, p) -> Optional[list[float]]:
        c = p.find(attrs={"id": "coordinates"})
        if c:
            geodms = c.find("span", attrs={"class": "geo-dms"})
            if geodms:
                return self.parseCoords(geodms)
        return

    def testIfPageIsLocation(self, p, ib, ibcontent, coord):
        # test for infobox template css classes
        if ib:
            self.analytics.articleInfoboxClasses(ib.attrs["class"])

            for c in ["ib-settlement", "ib-country", "ib-islands", "ib-pol-div", "ib-school-district", 
                "ib-uk-place"]:
                if c in ib.attrs["class"]:
                    return True        
                
        # test if article has coordinated on the top right
        if coord:
            return True

        # if "Location" in ibcontent:
        #     return True
        return False
    
    def getInfobox(self, p) -> Optional[Tag]:
        return p.find("table", attrs={"class": "infobox"})
    
    def dms2dd(self, dms:str) -> float: 
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
    
    
    def parseCoords(self, coordsSpan) -> list[float]:
        lat = coordsSpan.find("span", attrs={"class": "latitude"}, recursive=False)
        lon = coordsSpan.find("span", attrs={"class": "longitude"}, recursive=False)
        if lat and lon:
            return [self.dms2dd(lat.string), self.dms2dd(lon.string)]
        return None
    

    def getLocationFromInfobox(self, ib, templates, infoboxTemplates, topicFlag):

        def getTextAndLinksFromLocationValue(self, parentTag):
            text, links = "", []
            index = 0
            for c in parentTag.children:
                if isinstance(c, NavigableString) or (c.name and c.name in ["a", "b", "abbr"]):
                    t, l = self.getTextAndLinksRecursive(c, startIndex=index)
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
        
        # store row
        if locText:
            rows["Location"] = InfoboxRow(label, locText, locLinks)
            self.analytics.numTopicsWithLocation += 1
        elif topicFlag:
            for t in infoboxTemplates:
                self.analytics.topicInfoboxTemplateWithoutLocationFound(t)
        
        # extract coordinates from "Location" label and save it as seperate row
        coords = None
        geodms = td.find("span", attrs={"class": "geo-dms"})
        if geodms:
            coords = self.parseCoords(geodms)
            if coords:
                rows["Coordinates"] = InfoboxRow("Coordinates", coords, [])

        return rows
    
    
    def getDateAndTimeFromTopicInfobox(self, ib, templates, labels) -> \
            Tuple[Dict[(str,InfoboxRow)], Dict[str, Dict[str, Union[bool,str,datetime]]], \
            Dict[str, Tuple[List[str]]], Dict[str, str]]:

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
                        t, l = self.getTextAndLinksRecursive(c, startIndex=index)
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
                th = ib.tbody.find("th", string=label, attrs={"class": "infobox-label"})
                if th:
                    td = th.find_next_sibling("td")
                    text, links = getTextAndLinksFromDateValue(self, td)

                    return {label: InfoboxRow(label, text, links)}
            return {}

        microformats = {}
        if "vevent" in ib.attrs["class"]:
            dtstartTag = ib.find("span", attrs={"class": "dtstart"}, recursive=True)
            if dtstartTag:
                dtstart, l = self.getTextAndLinksRecursive(dtstartTag)
                microformats["dtstart"] = dtstart
                self.analytics.numTopicsWithDtstart += 1
            
            dtendTag = ib.find("span", attrs={"class": "dtend"}, recursive=True)
            if dtendTag:
                dtend, l = self.getTextAndLinksRecursive(dtendTag)
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
        times = {}
        for label, ibRow in timeRows.items():
            value = re.sub(r"[–−]", r"-", ibRow.value)
            timeDict = DateTimeParser.parseTimes(value)
            if timeDict:
                times[label] = timeDict
                hasTime = True
                if "end" in timeDict:
                    hasTimeSpan = True
            else:
                self.timeParseErrorLogger.info("\"" + value + "\"")
                self.analytics.numTopicsWithTimeParseError += 1
            
        dates = {}
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
                    dates[label] = {}
                    dates[label]["date"] = dateDict["date"]
                    self.analytics.numTopicsWithDate += 1
                    if "until" in dateDict:
                        dates[label]["until"] = dateDict["until"]
                        self.analytics.numTopicsWithDateSpan += 1
                    elif "ongoing" in dateDict and dateDict["ongoing"] == True:
                        dates[label]["ongoing"] = dateDict["ongoing"]
                        self.analytics.numTopicsWithDateOngoing += 1

                    if timeDict and "tz" in timeDict:
                        dates[label]["tz"] = timeDict["tz"]
                else:
                    self.dateParseErrorLogger.info("\"" + value + "\"")
                    self.analytics.numTopicsWithDateParseError += 1
        
        if hasTime:
            self.analytics.numTopicsWithTime += 1
            if hasTimeSpan:
                self.analytics.numTopicsWithTimeSpan += 1

        rows = dateRows | timeRows
        return rows, dates, times, microformats
        
        
    
    def parseInfobox(self, ib, templates, topicFlag=False) -> \
            Tuple[Dict[str, InfoboxRow], 
            Dict[str, Dict[str, Union[bool,str,datetime]]],
            Dict[str, Tuple[List[str]]],
            Dict[str, str] ]:
        tib = [t for t in templates if re.match("template:infobox", t.lower())]
        infoboxRows = {}

        locs = self.getLocationFromInfobox(ib, templates, tib, topicFlag)
        infoboxRows |= locs

        dates, times, microformats = {}, {}, {}
        if topicFlag:
            for t in tib:
                self.analytics.topicInfoboxTemplate(t)

            labels = [str(th.string) for th in ib.tbody.find_all("th", attrs={"class": "infobox-label"}) if th.string]
            self.analytics.topicInfoboxLabels(labels)

            rows, dates, times, microformats = self.getDateAndTimeFromTopicInfobox(ib, templates, labels)
            if rows:
                infoboxRows |= rows
        
        return infoboxRows, dates, times, microformats

    def testIfUrlIsArticle(self, url:str) -> bool:
        # negative tests
        if re.match("https://en.wikipedia.org/wiki/\w*:", url):
            # 17.1.22 has link to category page in event text
            return False

        # positive test
        if re.match("https://en.wikipedia.org/wiki/", url):
            return True
        return False
    

    def getArticleFromUrlIfArticle(self, url, topicFlag=False) -> Article:
        if not self.testIfUrlIsArticle(url):
            return None

        page = self.inputData.fetchWikiPage(url)
        p = BeautifulSoup(page, Extraction.bsParser)

        coord = self.tryGetCoordinatesFromPage(p)
        ib = self.getInfobox(p)

        # there are two of these, but i think they are always equal(?)
        articleGraphTag = p.find("script", attrs={"type": "application/ld+json"})
        if articleGraphTag == None:
            # if this is not present i take it as a indicator that this is not a article, 
            # but redirect page etc (not confirmed)
            return None
        
        pageGraph = json.loads(articleGraphTag.string)
        # get 'real' url of page, due to redirects etc
        graphUrl = pageGraph["url"]
        # test again if it is eg redict page
        if not self.testIfUrlIsArticle(graphUrl):
            return None

        # (RLQ=window.RLQ||[]).push(function(){mw.config.set(         );});
        statsString = articleGraphTag.find_previous_sibling("script").string[51:-5]
        statsJson = json.loads(statsString)
        templates = re.findall(r"Template:\w+", str(statsJson["wgPageParseReport"]["limitreport"]["timingprofile"]))

        ibcontent, dates, times, microformats = {}, {}, {}, {}
        if ib:
            ibcontent, dates, times, microformats = self.parseInfobox(ib, templates, topicFlag)
        
        locFlag = self.testIfPageIsLocation(p, ib, ibcontent, coord)
        if locFlag:
            self.analytics.numArticlesWithLocFlag += 1
        
        datePublished, dateModified = None, None
        if "datePublished" in pageGraph:
            datePublished = str(pageGraph["datePublished"])
        if "dateModified" in pageGraph:
            dateModified = str(pageGraph["dateModified"])
        
        wikidataEntityURI = str(pageGraph["mainEntity"])

        parent_locations_and_relation = self.wikidataService.getHigherlevelLocations(wikidataEntityURI)

        osmrelids, osmobjs = self.wikidataService.getOSMEntitys(wikidataEntityURI)

        wd_one_hop_g = self.wikidataService.getOneHopSubgraph(wikidataEntityURI)

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
        
        # get wkts from infobox loctaion value link labels
        ib_wkts = []
        if "Location" in ibcontent:
            loc = ibcontent["Location"]
            if loc.valueLinks and len(loc.valueLinks) >= 1:
                articleWithWkt = True
                for l in loc.valueLinks:
                    res = self.nominatimService.query(l.text)
                    osmid, osmtype, ib_wkt = res.id(), res.type(), res.wkt()
                    ib_wkts.append([l.text, OSMElement(res.id(), res.type(), res.wkt())])
        
        if articleWithWkt:
            self.analytics.numArticlesWithWkt += 1
        
        return Article(graphUrl, locFlag, coord, str(ib), ibcontent, str(articleGraphTag.string), templates, 
                ib_wkts, wiki_wkts, wikidataEntityURI, wd_one_hop_g, parent_locations_and_relation, 
                entity_label_dict, dates, times, microformats, datePublished, dateModified)

    def getArticles(self, wikiArticleLinks):
        articles = []
        for l in wikiArticleLinks:
            url = l.href
            articles.append(self.getArticleFromUrlIfArticle(url, topicFlag=False))
            self.analytics.article()
        
        return articles

    def parseTopic(self, t, parentTopics) -> list[Topic]:
        if(isinstance(t, NavigableString)):
            # when parent is no link, but initial Topic without Link
            return [Topic(t, t, None, None, None)]
        else:
            aList = t.find_all("a", recursive=False)
            # add italic topics
            iList = t.find_all("i", recursive=False)
            for i in iList:
                aList.append(i.find("a", recursive=False))

            if len(aList) == 0:
                # rare case when non inital topics have no link (14.1.2022 #4)
                text, _ = self.getTextAndLinksRecursive(t.contents[0])
                text = text.strip("\n ")
                return [Topic(text, text, None, None, None)]
            else:
                topics = []
                for a in aList:
                    text, links = self.getTextAndLinksRecursive(a)
                    href = a["href"]

                    # add url prefix to urls from wikipedia links
                    if(href[0] == "/"):
                        href = "https://en.wikipedia.org" + href
                    
                    # article == None if href is redlink like on 27.1.2022
                    article = self.getArticleFromUrlIfArticle(href, topicFlag=True)

                    t = Topic(a, text, href, article, parentTopics)
                    topics.append(t)

            return topics
    
    def splitEventTextIntoSentences(self, text, wikiLinks, articles):

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
    
    
    def searchForEventTypesRecursive(self, topics) -> dict:
        eventTypes = {}
        
        for t in topics:
            if t.article:
                eventTypes |= t.article.classes_with_labels
        
        if len(eventTypes) == 0:
            for t in topics:
                if t.parentTopics:
                    res = self.searchForEventTypesRecursive(t.parentTopics)
                    eventTypes |= res
        
        return eventTypes

    def parsePage(self, sourceUrl, page, year, monthStr, graphs: Dict[str,Graph]):
        soup = BeautifulSoup(page, Extraction.bsParser)
        for day in range(self.args.monthly_start_day, self.args.monthly_end_day+1):
            self.analytics.dayStart()

            idStr = str(year) + "_" + monthStr + "_" + str(day)
            print(idStr + " ", end="", flush=True)

            # select doesnt work, because id starts with number
            daybox = soup.find(attrs={"id": idStr})
            if(daybox):
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
                    iText, _ = self.getTextAndLinksRecursive(i)
                    iTopic = Topic(iText, iText, None, None, None)
                    self.outputData.storeTopic(iTopic, graphs)
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
                            text, links, sourceText, sourceLinks = self.parseEventTagRecursive(x)
                            #print("\n", text)
                            wikiArticleLinks = [l for l in links if self.testIfUrlIsArticle(l.href)]

                            articles = self.getArticles(wikiArticleLinks)
                            
                            sentences = self.splitEventTextIntoSentences(text, wikiArticleLinks, articles)
                            
                            eventTypes = self.searchForEventTypesRecursive(parentTopics)
                            if len(eventTypes) > 0:
                                self.analytics.numEventsWithType += 1

                            e = NewsEvent(x, parentTopics, text, links, wikiArticleLinks, articles, 
                                    sourceUrl, day, month2int[monthStr], year, sentences, sourceLinks, sourceText, eventTypes, evnum) 

                            self.analytics.event()
                            self.outputData.storeEvent(e, graphs)

                            if(True in [a.locFlag for a in articles if a != None]):
                                self.analytics.eventWithLocation()
                            # else:
                            #     print("\n", e)

                            evnum += 1
                        else:  # x == topic(s)
                            print("T", end="", flush=True)
                            topics = self.parseTopic(x, parentTopics)

                            for t in topics:
                                #print("\n", t.text)
                                self.analytics.topic()
                                self.outputData.storeTopic(t, graphs)
                                
                            # append subtopics to stack
                            subtopics = ul.find_all("li", recursive=False)
                            subtopicsAndParentTopic = [
                                [topics, st] for st in subtopics[::-1]]
                            s += subtopicsAndParentTopic

                            tnum += 1
            print("")
            self.analytics.dayEnd()
        return

