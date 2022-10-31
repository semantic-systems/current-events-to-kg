# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from typing import Optional

class Link():
    def __init__(self, href:str, text:str, startPos:int, endPos:int, external:bool=False, article:Optional["Article"]=None):
        self.href = href
        self.text = text
        self.startPos = startPos
        self.endPos = endPos
        self.external = external
        self.article = article
    
    