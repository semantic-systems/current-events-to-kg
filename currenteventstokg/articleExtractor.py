# Copyright: (c) 2023, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from .analytics import Analytics
from .inputHtml import InputHtml
import datetime
import json
import re
from string import Template
from time import time_ns
from typing import Dict, Generator, List, Optional, Tuple, Union
from urllib.parse import urldefrag
from os import makedirs
import logging


from bs4 import BeautifulSoup, NavigableString, Tag
from rdflib import Graph, URIRef

from .analytics import Analytics
from .dateTimeParser import DateTimeParser
from .falcon2Service import Falcon2Service
from .lruCacheCompressed import lru_cache as lru_cache_compressed
from .nominatimService import NominatimService
from .objects.article import Article
from .objects.infoboxRow import InfoboxRow, InfoboxRowDate, InfoboxRowLocation, InfoboxRowTime
from .objects.link import Link
from .objects.osmElement import OSMElement
from .placeTemplatesExtractor import PlacesTemplatesExtractor
from .wikidataService import WikidataService


class ArticleExtractor:
    def __init__(self, basedir, inputData, analytics: Analytics, 
            nominatimService: NominatimService, wikidataService: WikidataService,
            falcon2Service: Falcon2Service, place_templates_extractor:PlacesTemplatesExtractor, 
            args, bs_parser:str):
        self.inputData = inputData
        self.analytics = analytics
        self.nominatimService = nominatimService
        self.wikidataService = wikidataService
        self.falcon2Service = falcon2Service
        self.place_templates = place_templates_extractor.get_templates(args.force_parse)
        self.bs_parser = bs_parser

        # debug logger init
        logdir = basedir / "logs"
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


    # !!! check article_recursions_left > 0 or set it to a known value BEFORE calling this function 
    @lru_cache_compressed(maxsize=10000, compressed=True)
    def get_article(self, url:str, topicFlag:bool=False, article_recursions_left:int=0) -> Optional[Article]:
        t = time_ns()
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
        
        # remove url fragments
        articleUrl = urldefrag(graphUrl).url

        # test again if it is eg redict page
        if not self.__testIfUrlIsArticle(articleUrl):
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

        td = (time_ns() - t) / 10**6
        self.analytics.avgArticleExtractionTime.add_value(float(td))

        return Article(articleUrl, locFlag, coord, str(ib), ibRows, ib_coordinates, str(articleGraphTag.string), templates, 
                wiki_wkts, wikidataEntityURI, wd_one_hop_g, parent_locations_and_relation, 
                entity_label_dict, microformats, datePublished, dateModified, name, headline)

    
    def add_articles_to_wiki_links(self, links:List[Link], topic_flag=False, article_recursions_left:int=0):
        wikiArticleLinks = [l for l in links if self.__testIfUrlIsArticle(l.href)]
        if article_recursions_left > 0:
            for l in wikiArticleLinks:
                a = self.get_article(l.href, topicFlag=topic_flag, article_recursions_left=article_recursions_left)
                l.article = a
        return wikiArticleLinks
    

    def getTextAndLinksRecursive(self, x, startIndex=0) -> Tuple[str, list[Link]]:
        if(isinstance(x, NavigableString)):
            text = x.get_text()
            return text, []
        elif(isinstance(x, Tag)):
            links = []
            childrenText = ""
            nextChildStartIndex = startIndex
            for c in x.children:
                childText, childLinks = self.getTextAndLinksRecursive(c, nextChildStartIndex)
                childrenText += childText
                links += childLinks
                nextChildStartIndex += len(childText)

            # extract own link
            if(x.name == "a" and "href" in x.attrs):
                href = x["href"]

                # add url prefix to urls from wikipedia links
                if(href[0] == "/"):
                    href = "https://en.wikipedia.org" + href
                
                external = False
                if "class" in x.attrs and "external" in x["class"]:
                    external = True

                newLink = Link(href, childrenText, startIndex, startIndex + len(childrenText), external)
                links.append(newLink)
            
            return childrenText, links
        else:
            raise Exception(str(x) + " Type: " + str(type(x)))
        
    
    def __testIfUrlIsArticle(self, url:str) -> bool:
        # negative tests
        if re.match("https://en.wikipedia.org/wiki/\w*:", url):
            # 17.1.22 has link to category page in event text
            return False

        # positive test
        if re.match("https://en.wikipedia.org/wiki/", url):
            return True
        return False


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
                dtstart, l = self.getTextAndLinksRecursive(dtstartTag)
                dtstart_datetime = parse_microformat(dtstart)
                if dtstart_datetime:
                    microformats["dtstart"] = dtstart_datetime
                    self.analytics.numTopicsWithDtstart += 1
            
            dtendTag = ib.find("span", attrs={"class": "dtend"}, recursive=True)
            if dtendTag:
                dtend, l = self.getTextAndLinksRecursive(dtendTag)
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
        coords = None

        ## Notes: 
        # Template:Infobox_election only flag img...

        # choose label based of Template
        if any(t in templates for t in ["Template:Infobox_storm"]):
            label = "Areas affected"
        else:
            label = "Location"
        
        # find location label tag
        th = None

        tbody = ib.tbody
        # check if infobox table isnt empty (like e.g. https://en.wikipedia.org/wiki/Portovelo)
        if tbody:
            th = tbody.find("th", string=label, attrs={"class": "infobox-label"})
        
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
                self.add_articles_to_wiki_links(locLinks, topic_flag=False, article_recursions_left=article_recursions_left)

                # get wikipedia articles from falcons wikidata entities
                wd_uris = [URIRef(e) for e in falcon2_wikidata_entities]
                wd_uris2wp_urls = self.wikidataService.get_wp_article_urls(wd_uris)
                wp_urls_of_wd_entities = wd_uris2wp_urls.values()
                for url in wp_urls_of_wd_entities:
                    a = self.get_article(url, topicFlag=False, article_recursions_left=article_recursions_left)

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
    
    
    def __parseCoords(self, coordsSpan) -> Optional[List[float]]:
        lat = coordsSpan.find("span", attrs={"class": "latitude"}, recursive=False)
        lon = coordsSpan.find("span", attrs={"class": "longitude"}, recursive=False)
        if lat and lon:
            return [self.__dms2dd(lat.string), self.__dms2dd(lon.string)]
        return None
    

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
        
        # convert to point decimal
        if isinstance(degrees, str):
            degrees = degrees.replace(",",".")
        if isinstance(minutes, str):
            minutes = minutes.replace(",",".")
        if isinstance(seconds, str):
            seconds = seconds.replace(",",".")
        
        return (float(degrees) + float(minutes)/60 + float(seconds)/(3600)) * (-1 if direction in ['W', 'S'] else 1)
    

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

    
    def __tryGetCoordinatesFromPage(self, p) -> Optional[list[float]]:
        c = p.find(attrs={"id": "coordinates"})
        if c:
            geodms = c.find("span", attrs={"class": "geo-dms"})
            if geodms:
                return self.__parseCoords(geodms)
        return
    

    def __testIfPageIsLocationTemplate(self, templates):
        if templates & self.place_templates:
            return True

        return False


    
