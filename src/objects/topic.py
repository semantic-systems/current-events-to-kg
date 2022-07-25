# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

class Topic():
    def __init__(self, raw, text, link, article, parentTopics):
        self.raw = raw
        self.text = text
        self.link = link
        self.parentTopics = parentTopics
        self.article = article
    
    def __str__(self):
        return "raw[:100]:" + str(self.raw)[:100] +"\n"\
            + "text:" + str(self.text) +"\n"\
            + "link:" + str(self.link) +"\n"\
            + "parentTopics:" + str(self.parentTopics)+"\n" \
            + "location:" + str(self.location) +"\n" \
            + "infobox[:100]:" + str(self.infobox)[:100]+"\n" \
            + "coordinates:" + str(self.coordinates)+"\n"