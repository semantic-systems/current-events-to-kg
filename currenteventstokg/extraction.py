# Copyright: (c) 2022-2023, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import copy
import datetime
import re
from typing import Dict, Generator, List, Optional, Tuple, Union

from bs4 import BeautifulSoup, NavigableString, Tag

from .analytics import Analytics
from .etc import month2int
from .falcon2Service import Falcon2Service
from .nominatimService import NominatimService
from .objects.event import Event
from .objects.link import Link
from .objects.reference import Reference
from .objects.sentence import Sentence
from .objects.topic import Topic
from .wikidataService import WikidataService
from .articleExtractor import ArticleExtractor


class Extraction:
    def __init__(self, basedir, inputData, outputData, analytics: Analytics, 
            article_extractor:ArticleExtractor, args, bs_parser:str):
        self.basedir = basedir 
        self.inputData = inputData
        self.outputData = outputData
        self.analytics = analytics
        self.article_extractor = article_extractor
        self.args = args
        self.bs_parser = bs_parser

        self.article_recursions = 2


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

        
    def __parseTopic(self, t, parentTopics, date:datetime.date, num_topics:int, sourceUrl:str):
        # create tag with content until ul
        soup = BeautifulSoup("<li></li>", self.bs_parser)
        topic_row = soup.find("li")
        for c in t.children:
            if c.name == "ul":
                break
            topic_row.append(copy.copy(c))
        
        text, links = self.article_extractor.getTextAndLinksRecursive(topic_row)
        text = text.strip()
        text = text.strip(":")

        if len(links) == 0:
            # topic row without link (e.g. 14.1.2022 #4)
            yield Topic(topic_row, text, None, [], date, num_topics, sourceUrl)

        else:
            # get topic labels
            link2topic_label = {}

            if len(links) == 1:
                # use whole text as topic label
                link2topic_label[links[0]] = text

            elif len(links) > 1:
                # split text by comma seperator between links and use pieces for links
                # between each comma as topic labels
                topic_label_seperators = set()

                # add commas outside of links to seperator list
                for match in re.finditer(r',', text):
                    in_link = False
                    for link in links:
                        if match.start() >= link.startPos and match.end() <= link.endPos:
                            in_link = True
                    if not in_link:
                        topic_label_seperators.add((match.start(), match.end()))

                # assign topic labels
                if not topic_label_seperators:
                    # no text seperators found => each topic link gets full text
                    for link in links:
                        link2topic_label[link] = text
                else:
                    # split text based on seperators between links
                    sorted_seperators = sorted(list(topic_label_seperators), key=lambda x: x[0])
                    sorted_links = sorted(links, key=lambda x: x.startPos)
                    current_seperator_index = 0 # current label end
                    label_start = 0
                    label_end = sorted_seperators[current_seperator_index][0]

                    for link in sorted_links:
                        if link.endPos > label_end:
                            # move to next label if link is after current end of label
                            if current_seperator_index+1 < len(sorted_seperators):
                                # move to next seperator if available
                                label_start = sorted_seperators[current_seperator_index][0]
                                label_end = sorted_seperators[current_seperator_index+1][0]
                                current_seperator_index += 1
                            else:
                                # use text end as last sepreator
                                label_start = sorted_seperators[current_seperator_index][0]
                                label_end = len(text)
                            
                            label_start += 1 # skip "," seperator char
                        
                        label = text[label_start:label_end]
                        link2topic_label[link] = label.strip()
                
            # create topics
            for i, link in enumerate(links):
                # NOTE: article == None if href is redlink like on 27.1.2022
                article = self.article_extractor.get_article(
                    link.href, topicFlag=True, 
                    article_recursions_left=self.article_recursions)
                
                label = link2topic_label[link]

                # index of the topic
                tnum = num_topics + i

                yield Topic(topic_row, label, article, parentTopics, date, tnum, sourceUrl)
    

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
        wikiArticleLinks = self.article_extractor.add_articles_to_wiki_links(links, 
            topic_flag=False, article_recursions_left=self.article_recursions
        )
        
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
                topics = list(self.__parseTopic(li, parentTopics, date, tnum, sourceUrl))

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
                        anchor_text, _ = self.article_extractor.getTextAndLinksRecursive(a_tag)
                        
                        return Reference(ref_nr, url, anchor_text)
            

    def __extract_references_from_page(self, page:Tag) -> Dict[int,List[Reference]]:
        references = {}

        reflist = page.select_one(".reflist")
        if reflist:
            ol = reflist.select_one(".references")
            if ol: # handle reference section without references...
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
                        category, _ = self.article_extractor.getTextAndLinksRecursive(i)
                        category = category.strip()
                        eventList = i.find_next_sibling("ul")
                        if eventList: # in case of empty category blocks...
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
        
        hits, misses, maxsize, currsize = self.article_extractor.get_article.cache_info()
        print("Article cache info: hits=", hits, "misses=", misses, "maxsize=", maxsize, "currsize=", currsize)
        self.analytics.report_cache_stats(hits, misses, currsize)
        
        return

