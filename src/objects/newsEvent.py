# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

class NewsEvent():
    def __init__(self, raw, parentTopics, text, links, wikiLinks, articles, 
            sourceUrl, day:int, month:int, year:int, sentences, sourceLinks, sourceText, eventTypes, eventIndex):
        self.sourceUrl = sourceUrl #eg https://en.wikipedia.org/wiki/Portal:Current_events/January_2022
        self.raw = raw
        self.parentTopics = parentTopics
        self.text = text
        self.links = links
        self.wikiLinks = wikiLinks
        self.articles = articles
        self.day = day
        self.month = month
        self.year = year
        self.sentences = sentences
        self.sourceLinks = sourceLinks #Links to eg a CNN article
        self.sourceText = sourceText
        self.eventTypes = eventTypes
        self.eventIndex = eventIndex # n-th event of the day
    
    def getTextWithoutSource(self):
        t = self.text[:-len(self.sourceText)]
        return t

    def __str__(self):
        return "raw[:100]:" + str(self.raw)[:100] +"\n"\
            + "text:" + str(self.text) +"\n"\
            + "parentTopics:" + str(self.parentTopics)+"\n"\
            + "links:" + str(self.links) +"\n"\
            + "articles:" + str(self.articles) +"\n"
    