# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
import datetime
from currenteventstokg.objects.topic import Topic
from currenteventstokg.objects.link import Link
from currenteventstokg.objects.sentence import Sentence
from currenteventstokg.objects.article import Article

from typing import Dict, List


class Event():
    def __init__(self, raw: str, parentTopics: List[Topic], text: str,
                 sourceUrl: str, date: datetime.date, sentences: List[Sentence],
                 sourceLinks: List[Link], sourceText: str, eventTypes: Dict[str, str], 
                 eventIndex: int, category:str):
        self.raw = raw
        self.parentTopics = parentTopics
        self.text = text
        self.sourceUrl = sourceUrl #eg https://en.wikipedia.org/wiki/Portal:Current_events/January_2022
        self.date = date
        self.sentences = sentences
        self.sourceLinks = sourceLinks #Links to eg a CNN article
        self.sourceText = sourceText
        self.eventTypes = eventTypes
        self.eventIndex = eventIndex # n-th event of the day
        self.category = category
    
    def getTextWithoutSource(self):
        t = self.text[:-len(self.sourceText)]
        return t
    
    def get_linked_articles(self) -> List[Article]:
        return [article for sentence in self.sentences for article in sentence.get_linked_articles()]

    def __str__(self):
        return "raw[:100]:" + str(self.raw)[:100] +"\n"\
            + "text:" + str(self.text) +"\n"\
            + "parentTopics:" + str(self.parentTopics)+"\n"    