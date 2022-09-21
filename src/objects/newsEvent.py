# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
import datetime
from src.objects.topic import Topic
from src.objects.link import Link
from src.objects.sentence import Sentence

from typing import Dict, List


class NewsEvent():
    def __init__(self, raw: str, parentTopics: List[Topic], text: str,
                 sourceUrl: str, date: datetime.date, sentences: List[Sentence],
                 sourceLinks: List[Link], sourceText: str, eventTypes: Dict[str, str], eventIndex: int):
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
    
    def getTextWithoutSource(self):
        t = self.text[:-len(self.sourceText)]
        return t

    def __str__(self):
        return "raw[:100]:" + str(self.raw)[:100] +"\n"\
            + "text:" + str(self.text) +"\n"\
            + "parentTopics:" + str(self.parentTopics)+"\n"    