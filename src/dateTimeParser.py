import re 
from datetime import datetime
from pprint import pprint
from typing import Dict, Optional, Union

class DateTimeParser:
    dateRegexes = None
    
    @classmethod
    def parseTimes(cls, value) -> Optional[Dict[str, str]]:
        m = re.search(r"UTC(?P<offset>[\+-]\d\d?(?::\d\d)?)?", value)
        if m:
            timezone = m[0].strip("\n ")
        else:
            timezone = None

        m = re.search(
            r"(?P<hs>\d\d?):(?P<ms>\d\d)\s*((?P<ams>[aA].?[mM].?)|(?P<pms>[pP].?[mM].?))?" +
            r"(\s*(-|and|to)\s*" + 
            r"(?P<he>\d\d?):(?P<me>\d\d)\s*((?P<ame>[aA].?[mM].?)|(?P<pme>[pP].?[mM].?))?" +
            r")?", value)
        if m:
            time = {}

            matchStr = m[0].strip("\n ")
            gd = m.groupdict()
            hs,ms = int(gd["hs"]), int(gd["ms"])
            ams, pms = gd["ams"], gd["pms"]
            if pms:
                hs = hs+12
            time["start"] = str(hs).zfill(2) + ":" + str(ms).zfill(2)
            
            he,me = gd["he"], gd["me"]
            ame, pme = gd["ame"], gd["pme"]
            end=None
            if he and me:
                he,me = int(he), int(me)
                if pme:
                    he = he + 12
                time["end"] = str(he).zfill(2) + ":" + str(me).zfill(2)

            if timezone:
                time["tz"] = timezone
            return time
        return
    
    @classmethod
    def parseDates(cls, value, timeDict=None) -> Dict[str, Union[datetime,bool]]:
        months = ["january","february","march","april","may","june","july","august",
                "september","october","november","december"]
        
        if cls.dateRegexes == None:
            cls.dateRegexes = cls.__compileRegexes()
        
        dateDict = {}
        for re_x in cls.dateRegexes:
            m = re_x.search(value)
            if m:

                #print(re_x)
                matchStr = m[0].strip("\n ")
                gd = m.groupdict()
                try:
                    mon = months.index(gd["mon"].lower())+1

                    if timeDict:
                        dateDict["date"] = datetime(int(gd["year"]), mon, int(gd["day"]), startTime[0], startTime[1])
                    else:
                        dateDict["date"] = datetime(int(gd["year"]), mon, int(gd["day"]))

                    if "day2" in gd:
                        if "mon2" in gd:
                            try:
                                mon2 = months.index(gd["mon2"].lower())+1
                            except ValueError as e:
                                continue
                        else:
                            mon2 = mon
                        
                        if "year2" in gd:
                            year2 = int(gd["year2"])
                        else:
                            year2 = int(gd["year"])

                        day2 = int(gd["day2"])

                        if timeDict and endTime:
                            dateDict["until"] = datetime(year2, mon2, day2, endTime[0], endTime[1])
                        else:
                            dateDict["until"] = datetime(year2, mon2, day2)
                    elif "on" in gd and gd["on"]:
                        dateDict["ongoing"] = True
                    elif timeDict and endTime:
                            dateDict["until"] = datetime(int(gd["year"]), mon, int(gd["day"]), endTime[0], endTime[1])
                except ValueError as e:
                    continue
                    
                break
        return dateDict
    
    def __compileRegexes() -> list[re.Pattern]:
        to = r"\s*(?:-|until|to)\s*"
        ongoing = r"(?P<on>([Pp]resent|[Oo]ngoing))"

        day = r"(?P<day>\d\d?)"
        day2 = r"(?P<day2>\d\d?)"
        month = r"(?P<mon>\w{3,9})"
        month2 = r"(?P<mon2>\w{3,9})"
        year = r"(?P<year>\d{2,4})"
        year2 = r"(?P<year2>\d{2,4})"

        dm = day + r"\s+" + month
        dmy = dm + r"\s+" + year
        dmyOn = dm + r"\s+" + year + to + ongoing
        ddmy = day + to + day2 + r"\s+" + month + r"\s+" + year
        dmdmy = dm + to + day2 + r"\s+" + month2 + r"\s+" + year
        dmydmy = dmy + to + day2 + r"\s+" + month2 + r"\s+" + year2
        re_dmy = re.compile(dmy)
        re_dmyOn = re.compile(dmyOn)
        re_ddmy = re.compile(ddmy)
        re_dmdmy = re.compile(dmdmy)
        re_dmydmy = re.compile(dmydmy)

        md = month + r"\s*(?:/|\s)\s*" + day
        mdy = md + r"\s*[/,]\s*" + year
        mdyOn = md + r"\s*[/,]\s*" + year + to + ongoing
        mddy = md + to + day2 + r"\s*[/,]\s*" + year
        mdmdy = md + to + month2 + r"\s*" + day2 + r"\s*[/,]\s*" + year
        mdymdy = mdy + to + month2 + r"\s*(?:/|\s)\s*" + day2 + r"\s*[/,]\s*" + year2
        re_mdy = re.compile(mdy)
        re_mdyOn = re.compile(mdyOn)
        re_mddy = re.compile(mddy)
        re_mdmdy = re.compile(mdmdy)
        re_mdymdy = re.compile(mdymdy)

        return [re_mdymdy, re_dmydmy, re_mdmdy, re_dmdmy, re_mddy, 
                re_ddmy, re_mdyOn, re_dmyOn, re_mdy, re_dmy]

if __name__ == '__main__':
    # for testing
    s=[]
    s.append(u"January 1, 2021")
    s.append(u"January 1, 2021 - present")
    s.append(u"January 1 - 12, 2021")
    s.append(u"January 1 - February 12, 2021")
    s.append(u"January 1, 2021 - February 12, 2022")

    s.append(u"1 January 2021")
    s.append(u"1 January 2021 - ongoing")
    s.append(u"1 - 2 January 2021")
    s.append(u"1 January - 12 February 2022")
    s.append(u"1 January 2021 - 12 February 2022")

    s.append(u"""January 15, 2022 
    10:41 a.m. – 9:22 p.m. (CST)""")
    s.append(u"""17 January 2022 (4 months ago)
    14:29 – 14:50 (UTC+4:00)""")
    s.append(u"""3 January 2020
    About 1:00 a.m. (local time, UTC+3)""")
    s.append(u"""Tanami Desert 
    27 June 2021 """)
    s.append(u"""February 23, 2020 
    c. 1:15 p.m. """)
    s.append(u"""December 30, 2021-January 1, 2022 """)
    s.append(u"""17 November 2019 - present
    (2 years and 6 months)""")

    for x in s:
        x = re.sub(r"[–−]", r"-", x)
        print("\n" + x.strip("\n "))
        pprint(DateTimeParser.parseDates(x))