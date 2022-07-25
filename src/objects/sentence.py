# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

class Sentence():
    def __init__(self, text, start, end, links, articles):
        self.text = text
        self.start = start
        self.end = end
        self.links = links
        self.articles = articles
    
    