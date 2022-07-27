# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from time import time, sleep
from typing import Tuple

class Sleeper:

    def __init__(self):
        self.lastReq = 0

    def sleepUntilNewRequestLegal(self, minSecondsBetweenQueries:float) -> Tuple[float,float]:
        now = time()
        diff = now - self.lastReq
        t = minSecondsBetweenQueries - diff

        # if you already waited longer
        if(t < 0):
            t = 0
        
        sleep(t)

        exclude = self.lastReq == 0

        self.lastReq = time()

        if exclude: #exclude first diff with >8000000
            return -1.0, t
        else:
            return diff, t