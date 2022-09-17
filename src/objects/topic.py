# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from datetime import date
from src.objects.article import Article
from typing import List


class Topic():
    def __init__(self, raw:str, text:str, link:str, article:Article, parentTopics:List["Topic"], 
                 date: date, index: int, sourceUrl: str):
        self.raw = raw
        self.text = text
        self.link = link
        self.parentTopics = parentTopics
        self.article = article
        self.date = date
        self.index = index # n-th topic of the day [0-n]
        self.sourceUrl = sourceUrl
        
    
    def __str__(self):
        return "raw[:100]:" + str(self.raw)[:100] +"\n"\
            + "text:" + str(self.text) +"\n"\
            + "link:" + str(self.link) +"\n"\
            + "parentTopics:" + str(self.parentTopics)+"\n"