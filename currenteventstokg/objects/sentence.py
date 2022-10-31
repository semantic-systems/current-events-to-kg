# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from currenteventstokg.objects.article import Article
from currenteventstokg.objects.link import Link

from typing import List, Optional


class Sentence():
    def __init__(self, text:str, start:int, end:int, links:List[Link]):
        self.text = text
        self.start = start
        self.end = end
        self.links = links
    
    def get_linked_articles(self) -> List[Article]:
        return [l.article for l in self.links if l.article]

    
    