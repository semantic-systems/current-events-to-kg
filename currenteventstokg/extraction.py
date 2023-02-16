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
from functools import lru_cache

from bs4 import BeautifulSoup, NavigableString, Tag
from rdflib import Graph, URIRef

from .analytics import Analytics
from .dateTimeParser import DateTimeParser
from .placeTemplatesExtractor import PlacesTemplatesExtractor
from .etc import month2int
from .falcon2Service import Falcon2Service
from .nominatimService import NominatimService
from .objects.article import Article
from .objects.infoboxRow import *
from .objects.link import Link
from .objects.event import Event
from .objects.osmElement import OSMElement
from .objects.sentence import Sentence
from .objects.topic import Topic
from .objects.reference import Reference
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

        self.article_recursions = 2
        
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

                # skip citations in <sup> tags
                if c.name == "sup":
                    continue

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

    def __testIfPageIsLocation(self, p, ib, templates):
        # test for infobox template css classes
        if self.__testIfPageIsLocationCss(p, ib):
            return True
        
        # test if templates match place templates
        if self.__testIfPageIsLocationTemplate(templates):
            return True

        return False

    def __testIfPageIsLocationCss(self, p, ib):
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
    
    
    def __parseCoords(self, coordsSpan) -> Optional[List[float]]:
        lat = coordsSpan.find("span", attrs={"class": "latitude"}, recursive=False)
        lon = coordsSpan.find("span", attrs={"class": "longitude"}, recursive=False)
        if lat and lon:
            return [self.__dms2dd(lat.string), self.__dms2dd(lon.string)]
        return None
    

    def __getLocationFromInfobox(
        self, ib, templates, infoboxTemplates, topicFlag, article_recursions_left:int=0) -> Tuple[
            List[InfoboxRow],
            Optional[List[float]]
        ]:

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
        coords = None

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
            return rows, coords
        
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

            if falcon2_wikidata_entities:
                self.analytics.numArticlesWithFalcon2WikidataEntity += 1
            
            wp_urls_of_wd_entities, falcon_articles = [],[]
            if article_recursions_left > 0:
                # get wikipedia articles from links
                self.__add_articles_to_links(locLinks, topic_flag=False, article_recursions_left=article_recursions_left)

                # get wikipedia articles from falcons wikidata entities
                wd_uris = [URIRef(e) for e in falcon2_wikidata_entities]
                wd_uris2wp_urls = self.wikidataService.get_wp_article_urls(wd_uris)
                wp_urls_of_wd_entities = wd_uris2wp_urls.values()
                for url in wp_urls_of_wd_entities:
                    a = self.__getArticleFromUrlIfArticle(url, topicFlag=False, article_recursions_left=article_recursions_left)

                    # only use article if it is about a location to filter out some false results
                    if a and a.location_flag:
                        falcon_articles.append(a)
            
            if falcon_articles:
                self.analytics.numArticlesWithFalcon2LocationArticle += 1

            # get wkts from infobox location value link labels
            ib_wkts = {}
            for l in locLinks:
                res = self.nominatimService.query(l.text)
                osmid, osmtype, ib_wkt = res.id(), res.type(), res.wkt()
                ib_wkts[l] = OSMElement(res.id(), res.type(), res.wkt())

            # create row
            rows[label] = InfoboxRowLocation(label, locText, locLinks,
                                    falcon2_wikidata_entities, falcon_articles, 
                                    falcon2_dbpedia_entities, ib_wkts)
            if topicFlag:
                self.analytics.numTopicsWithLocation += 1
        elif topicFlag:
            for t in infoboxTemplates:
                self.analytics.topicInfoboxTemplateWithoutLocationFound(t)
        
        # extract coordinates from "Location" label
        geodms = td.find("span", attrs={"class": "geo-dms"})
        if geodms:
            coords = self.__parseCoords(geodms)
        
        return rows, coords
    
    
    def __getDateAndTimeFromTopicInfobox(self, ib, templates, labels) -> Tuple[
                Dict[(str,InfoboxRow)],
                Dict[str, datetime.datetime],
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
        
        def parse_microformat(mf:str) -> Optional[datetime.datetime]:
            # format observed: 2021-01-25 (and 2021, but will be ignored)
            match = re.search(r"(?P<y>[0-9]{4})-(?P<m>[0-9]{2})-(?P<d>[0-9]{2})", mf)
            if match:
                y = int(match.group("y"))
                m = int(match.group("m"))
                d = int(match.group("d"))
                return datetime.datetime(y,m,d)
            return None

        microformats = {}
        if "vevent" in ib.attrs["class"]:
            dtstartTag = ib.find("span", attrs={"class": "dtstart"}, recursive=True)
            if dtstartTag:
                dtstart, l = self.__getTextAndLinksRecursive(dtstartTag)
                dtstart_datetime = parse_microformat(dtstart)
                if dtstart_datetime:
                    microformats["dtstart"] = dtstart_datetime
                    self.analytics.numTopicsWithDtstart += 1
            
            dtendTag = ib.find("span", attrs={"class": "dtend"}, recursive=True)
            if dtendTag:
                dtend, l = self.__getTextAndLinksRecursive(dtendTag)
                dtend_datetime = parse_microformat(dtend)
                if dtend_datetime:
                    microformats["dtend"] = dtend_datetime
                    self.analytics.numTopicsWithDtend += 1
        
        # Date tags seperated into 2 groups.
        # Both can have spans from start to end, but have different single date meaning.
        date_rows_beginnings = {}
        date_rows_beginnings |= extractRowForLabelIfExists(labels, "Date")
        date_rows_beginnings |= extractRowForLabelIfExists(labels, "Date(s)")
        date_rows_beginnings |= extractRowForLabelIfExists(labels, "First outbreak")
        date_rows_beginnings |= extractRowForLabelIfExists(labels, "Arrival Date")
        date_rows_beginnings |= extractRowForLabelIfExists(labels, "Start Date")

        date_rows_endings = {}
        date_rows_endings |= extractRowForLabelIfExists(labels, "End Date")
        date_rows_endings |= extractRowForLabelIfExists(labels, "Duration")

        timeRows = {}
        timeRows |= extractRowForLabelIfExists(labels, "Time")

        # Extract time
        hasTime, hasTimeSpan = False, False
        resRows = {}
        for label, ibRow in timeRows.items():
            value = re.sub(r"[–−]", r"-", ibRow.value)
            timeDict = DateTimeParser.parseTimes(value)
            if timeDict:
                time = timeDict["start"]
                hasTime = True
                endtime = None
                if "end" in timeDict:
                    endtime = timeDict["end"]
                    hasTimeSpan = True
                timeRow = InfoboxRowTime(ibRow.label, ibRow.value, ibRow.valueLinks, time, endtime)
                resRows[label] = timeRow
            
            else:
                self.timeParseErrorLogger.info("\"" + value + "\"")
                self.analytics.numTopicsWithTimeParseError += 1

        # Extract date(span) and combine with time
        for i, date_rows in enumerate([date_rows_beginnings, date_rows_endings]):
            is_ending = bool(i)

            for label, ibRow in date_rows.items():
                value = re.sub(r"[–−]", r"-", ibRow.value)

                # filter out some frequent values which are no dates
                asOf = re.search(r"[aA]s of", value)
                if not asOf and value not in ["Wuhan, Hubei, China", "Wuhan, China"]:

                    timeDict = DateTimeParser.parseTimes(value)

                    startTime, endTime = [], []
                    if timeDict:
                        hasTime = True
                        startTime = timeDict["start"]
                        if "end" in timeDict:
                            hasTimeSpan = True
                            endTime = timeDict["end"]

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
                        
                        # combine dates and times
                        if date and not until and not ongoing:
                            if startTime:
                                # eg 10.1.22 13:00
                                date = date.replace(hour=startTime.hour, minute=startTime.minute)
                                if endTime:
                                    # eg 22.3.22 13:00-14:00
                                    until = date.replace(hour=endTime.hour, minute=endTime.minute)
                        elif startTime or endTime:
                            # eg 22.3.22-23.3.22 13:00(-14:00)
                            # time span discarded, as it is not a single span but multiple
                            self.dateParseErrorLogger.info("\"" + value + "\"")
                        
                        if date and not until and not ongoing and is_ending:
                            until = date
                            date = None
                        
                        dateRow = InfoboxRowDate(
                            ibRow.label, ibRow.value, ibRow.valueLinks, 
                            date, until, ongoing)
                        resRows[label] = dateRow
                    else:
                        self.dateParseErrorLogger.info("\"" + value + "\"")
                        self.analytics.numTopicsWithDateParseError += 1
        
        if hasTime:
            self.analytics.numTopicsWithTime += 1
            if hasTimeSpan:
                self.analytics.numTopicsWithTimeSpan += 1

        return resRows, microformats
        
        
    
    def __parseInfobox(self, ib, templates, topicFlag=False, article_recursions_left:int=0) -> Tuple[
            Dict[str, InfoboxRow],
            Dict[str, datetime.datetime],
            Optional[List[float]]
        ]:
        tib = [t for t in templates if re.match("template:infobox", t.lower())]
        infoboxRows = {}

        # extract Locations
        locs, coordinates = self.__getLocationFromInfobox(ib, templates, tib, topicFlag, article_recursions_left)
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
        
        return infoboxRows, microformats, coordinates


    def __testIfUrlIsArticle(self, url:str) -> bool:
        # negative tests
        if re.match("https://en.wikipedia.org/wiki/\w*:", url):
            # 17.1.22 has link to category page in event text
            return False

        # positive test
        if re.match("https://en.wikipedia.org/wiki/", url):
            return True
        return False
    
    
    def __add_articles_to_links(self, links:List[Link], topic_flag=False, article_recursions_left:int=0):
        if article_recursions_left > 0:
            for l in links:
                a = self.__getArticleFromUrlIfArticle(l.href, topicFlag=topic_flag, article_recursions_left=article_recursions_left)
                l.article = a


    # !!! check article_recursions_left > 0 or set it to a known value BEFORE calling this function 
    @lru_cache(maxsize=3000)
    def __getArticleFromUrlIfArticle(self, url:str, topicFlag:bool=False, article_recursions_left:int=0) -> Optional[Article]:
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
        
        # decrement article recursion level tracker to stop infinite depth in article links
        article_recursions_left -= 1 
        if article_recursions_left < 0:
            article_recursions_left = 0
        
        # parse the infobox
        ibRows, microformats, ib_coordinates = {}, {}, None
        if ib:
            ibRows, microformats, ib_coordinates = self.__parseInfobox(
                ib, templates, topicFlag, article_recursions_left
            )
        
        # check if page is a location
        locFlag = self.__testIfPageIsLocation(p, ib, templates)
        if locFlag:
            self.analytics.numArticlesWithLocFlag += 1
        
        # # location classifier testing code
        # locFlagOld = self.__testIfPageIsLocationCss(p, ib)
        # locFlagNew = self.__testIfPageIsLocationTemplate(templates)
        # if  locFlagNew != locFlagOld or locFlagNew != bool(coord) :
        #     with open(self.basedir / "loclog.json", "a") as f:
        #         json.dump({"name":name, "old":locFlagOld, "new":locFlagNew, "coord":bool(coord)}, f)
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
        
        self.analytics.numArticles += 1

        return Article(graphUrl, locFlag, coord, str(ib), ibRows, ib_coordinates, str(articleGraphTag.string), templates, 
                wiki_wkts, wikidataEntityURI, wd_one_hop_g, parent_locations_and_relation, 
                entity_label_dict, microformats, datePublished, dateModified, name, headline)
    

    def __parseTopic(self, t, parentTopics, date:datetime.date, num_topics:int, sourceUrl:str) -> list[Topic]:
        if(isinstance(t, NavigableString)):
            # when parent is no link, but initial Topic without Link
            return [Topic(t, t, None, [], date, num_topics, sourceUrl)]
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
                return [Topic(text, text, None, [], date, num_topics, sourceUrl)]
            else:
                topics = []
                for a in aList:
                    text, links = self.__getTextAndLinksRecursive(a)
                    href = a["href"]

                    # add url prefix to urls from wikipedia links
                    if(href[0] == "/"):
                        href = "https://en.wikipedia.org" + href
                    
                    # article == None if href is redlink like on 27.1.2022
                    article = self.__getArticleFromUrlIfArticle(href, topicFlag=True, article_recursions_left=self.article_recursions)
                    
                    # index of the topic
                    tnum = num_topics + len(topics)

                    t = Topic(a, text, article, parentTopics, date, tnum, sourceUrl)
                    topics.append(t)

            return topics
    

    def __extract_reference_numbers_from_event(self, x:Tag) -> List[int]:
        refs = []

        sups = x.find_all("sup")

        for sup in sups:
            if "id" in sup.attrs:
                sup_id = str(sup.attrs["id"])

                if sup_id.startswith("cite_ref-"):
                    ref_nr = self.__get_nr_from_cite_id(sup_id)
                    refs.append(ref_nr)
        
        return refs
        
    
    def __parse_event(self, x:Tag, parentTopics:List[Topic], events_index:int, 
            category:Optional[str], date:datetime.date, sourceUrl:str,
            references:Dict[int,List[Reference]]
        ) -> Event:

        # parse
        text, links, sourceText, sourceLinks = self.__parseEventTagRecursive(x)

        # get articles behind links
        wikiArticleLinks = [l for l in links if self.__testIfUrlIsArticle(l.href)]
        self.__add_articles_to_links(wikiArticleLinks, topic_flag=False, article_recursions_left=self.article_recursions)
        
        # split everything into sentences
        sentences = self.__splitEventTextIntoSentences(text, wikiArticleLinks)
        
        # get types for this event from parent topics
        eventTypes = self.__searchForEventTypesRecursive(parentTopics)
        if len(eventTypes) > 0:
            self.analytics.numEventsWithType += 1
        
        # extract references/citations
        reference_numbers = self.__extract_reference_numbers_from_event(x)

        # get references extracted from below
        referenced_sources = [ref for nr,ref in references.items() if nr in reference_numbers]

        return Event(str(x), parentTopics, text, sourceUrl, date, sentences, 
                sourceLinks, sourceText, eventTypes, events_index, category, referenced_sources)
    

    def __splitEventTextIntoSentences(self, text:str, wikiLinks:List[Link]) -> List[Sentence]:

        # split links occur, which are put into the sentence where they end in
        def getLinksInSpan(wikiLinks, start, end, linkOffset):
            linkIndex = linkOffset
            sentenceLocNum = 0
            sentenceLinks = []
            
            while(linkIndex < len(wikiLinks) and wikiLinks[linkIndex].endPos <= end):
                # switch context of link from event to sentence level
                l = copy.copy(wikiLinks[linkIndex])
                l.startPos -= start
                l.endPos -= start
                
                sentenceLinks.append(l)
                
                article = l.article
                if article and article.location_flag:
                    sentenceLocNum += 1
                linkIndex += 1

            if sentenceLocNum > 1:
                self.analytics.numEventSentencesWithMoreThanOneLocation += 1

            return (linkIndex, sentenceLinks, sentenceLocNum)

        textlen = len(text)
        sentences = []
        locNum = 0
        linkIndex = 0
        start = 0

        for p in re.finditer(r'\. ', text):
            end = p.start()+2
            
            # skip this guess of a sentence ending -> its inside a link, links usually dont span sentences 
            if any([end > wl.startPos and end < wl.endPos for wl in wikiLinks]):
                continue

            linkIndex, sentenceLinks, sentenceLocNum = getLinksInSpan(wikiLinks, start, end, linkIndex)
            
            sentences.append(Sentence(text[start:end], start, end, sentenceLinks))
            locNum += sentenceLocNum

            start = end

        # if there are characters left and the last char in text is a ".", put them in a last sentence if
        if start != textlen and text[-1] == ".":
            linkIndex, sentenceLinks, sentenceLocNum = getLinksInSpan(wikiLinks, start, textlen, linkIndex)
            sentences.append(Sentence(text[start:textlen], start, textlen, sentenceLinks))
            locNum += sentenceLocNum

        # use everything as one sentence if no sentences have been found
        if len(sentences) == 0:
            linkIndex, sentenceLinks, sentenceLocNum = getLinksInSpan(wikiLinks, 0, textlen, 0)
            sentences.append(Sentence(text, 0, textlen, sentenceLinks))
            locNum += sentenceLocNum

        if locNum > 0:
            self.analytics.numEventsWithLocation += 1
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


    def __extract_events_from_ul(self, eventList:Tag, category:Optional[str], 
            tnum:int, evnum:int, date:datetime.date, sourceUrl:str, 
            references:Dict[int,List[Reference]]
        ) -> Tuple[int,int]:

        # extract events under their topics iteratively
        stack = []  # stack with [parentTopics, li]

        lis = eventList.find_all("li", recursive=False)
        stack += [[[], li] for li in lis[::-1]]
        while(len(stack) > 0):
            # get next li tag with its topics
            parentTopics, li = stack.pop()

            # li has ul's ? topic : event
            ul = li.find("ul")
            if(ul == None):  # li == event
                print("E", end="", flush=True)
                e = self.__parse_event(li, parentTopics, evnum, category, date, sourceUrl, references)

                self.analytics.numEvents += 1
                self.outputData.storeEvent(e)
                evnum += 1
                
            else:  # li == topic(s)
                print("T", end="", flush=True)
                topics = self.__parseTopic(li, parentTopics, date, tnum, sourceUrl)

                for t in topics:
                    self.analytics.numTopics += 1
                    self.outputData.storeTopic(t)
                    tnum += 1
                    
                # append subelements to stack
                subelements = ul.find_all("li", recursive=False)
                subelementsAndParentTopic = [
                    [topics, st] for st in subelements[::-1]]
                stack += subelementsAndParentTopic
        
        return tnum, evnum

    
    def __get_nr_from_cite_id(self, id_str:str) -> int:
        return  int(id_str.split("-")[-1])

    
    def __extract_reference(self, li:Tag) -> Optional[Reference]:
        self.analytics.numReferences += 1

        ref_nr = self.__get_nr_from_cite_id(str(li.attrs["id"]))
        
        cite_tag = li.find("cite")

        if cite_tag:
            # only news references
            if "class" in cite_tag.attrs and "news" in cite_tag.attrs["class"]:
                self.analytics.numReferencesNews += 1

                a_tags = cite_tag.find_all("a")
                ref_links = []
                for a_tag in a_tags:
                    if "href" in a_tag.attrs \
                        and "class" in a_tag.attrs and "external" in a_tag.attrs["class"]:

                        url = a_tag.attrs["href"]
                        anchor_text, _ = self.__getTextAndLinksRecursive(a_tag)
                        
                        return Reference(ref_nr, url, anchor_text)
            

    def __extract_references_from_page(self, page:Tag) -> Dict[int,List[Reference]]:
        references = {}

        reflist = page.select_one(".reflist")
        if reflist:
            ol = reflist.select_one(".references")
            assert ol.name == "ol"

            for li in ol.children:
                if li.name == "li" and "id" in li.attrs:
                    li_id = str(li.attrs["id"])

                    if li_id.startswith("cite_note-"):
                        ref = self.__extract_reference(li)
                        
                        if ref:
                            assert ref.nr not in references
                            references[ref.nr] = ref
                
        return references




    def parsePage(self, sourceUrl, page, year, monthStr):
        soup = BeautifulSoup(page, self.bs_parser)

        # get all links from all superscript [x] references from the bottom of the page
        references = self.__extract_references_from_page(soup)

        # parse all available days
        for day in range(self.args.monthly_start_day, self.args.monthly_end_day+1):
            self.analytics.dayStart()

            idStr = str(year) + "_" + monthStr + "_" + str(day)
            print(idStr + " ", end="", flush=True)

            # select doesnt work, because id starts with number
            daybox = soup.find(attrs={"id": idStr})
            if(daybox):
                month = month2int[monthStr]
                date = datetime.date(year, month, day)

                ## get box with events of class .description
                # "normal" usage of {{Current events|year=2005|month=01|day=7|content= 
                description = daybox.select_one(".description")

                # case of {{Current events header|2005|01|08}} usage where a table is generated...
                if not description:
                    table = daybox.find_next("table", attrs={"class": "vevent"})
                    description = table.select_one(".description")
                    if not description:
                        raise Exception(f".description class tag not found for {idStr}")

                ## try getting category tags
                # two versions of headings are used (afaik):
                # <p><b>Health and environment</b></p>
                # <div class="current-events-content-heading" role="heading">Armed conflicts and attacks</div>
                def is_category(tag:Tag):
                    return (tag.name == "p" and len(tag.attrs) == 0) \
                        or (tag.name == "div" and tag.has_attr('class') \
                        and "current-events-content-heading" in tag.attrs["class"])
                categories = description.find_all(is_category, recursive=False)
                
                # create list of event lists
                event_lists = {} # list of ul lists of events with category str as key
                if categories:
                    ## format with categories from 2004
                    for i in categories:
                        category, _ = self.__getTextAndLinksRecursive(i)
                        eventList = i.find_next_sibling("ul")
                        event_lists[category] = eventList
                else:
                    ## format where no categories are used prior to 2004

                    # eventList = description.find_next_sibling("ul")
                    # ^ does not work somehow?? but iterateing over children works...
                    for child in description.children:
                        if child.name == "ul":
                            event_lists[None] = child
                
                ## extract all events
                tnum = 0
                evnum = 0
                for category,eventList in event_lists.items():
                    tnum, evnum = self.__extract_events_from_ul(eventList, category, tnum, evnum, date, sourceUrl, references)
                    

            print("")
            self.analytics.dayEnd()
        
        hits, misses, maxsize, currsize = self.__getArticleFromUrlIfArticle.cache_info()
        print("Article cache info: hits=", hits, "misses=", misses, "maxsize=", maxsize, "currsize=", currsize)
        self.analytics.report_cache_stats(hits, misses, currsize)

        return

