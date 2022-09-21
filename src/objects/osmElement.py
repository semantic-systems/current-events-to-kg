# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

class OSMElement:
    def __init__(self, osmId:str, osmType:str, wkt:str):
        self.osmId = osmId
        self.osmType = osmType
        self.wkt = wkt
