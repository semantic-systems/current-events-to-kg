from time import time, sleep

class Sleeper:

    def __init__(self):
        self.lastReq = 0

    def sleepUntilNewRequestLegal(self, minSecondsBetweenQueries:float) -> float:
        now = time()
        diff = now - self.lastReq
        t = minSecondsBetweenQueries - diff

        # if you already waited longer
        if(t < 0):
            t = 0
        
        sleep(t)
        
        self.lastReq = time()

        if self.lastReq == 0: #exclude first diff with >8000000
            return -1.0
        else:
            return diff