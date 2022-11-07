# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import re 
from datetime import datetime, time, timezone, timedelta, tzinfo
from pprint import pprint
from typing import Dict, Optional, Union, Tuple

class DateTimeParser:
    dateRegexes = None

    @classmethod
    def __convert_12_to_24_format(cls, h:int, pm:bool) -> int:
        if pm:
            if h != 12:
                return h + 12   
        else:
            if h == 12:
                return 0
        return h
    
    @classmethod
    def parseTimes(cls, value) -> Optional[Dict[str,time]]:
        match = re.search(r"UTC(?P<h>[\+-]\d\d?)(?::(?P<m>\d\d))?", value)
        if match:
            gd = match.groupdict()
            h = gd["h"]
            m = gd["m"]
            if h:
                h = int(h)
                if m:
                    m = int(m)
                else:
                    m = 0
            else:
                h,m = 0,0
            
            tz = timezone(timedelta(hours=h, minutes=m))
        else:
            tz = None

        match = re.search(
            r"(?P<hs>\d\d?):(?P<ms>\d\d)\s*((?P<ams>[aA].?[mM].?)|(?P<pms>[pP].?[mM].?))?" +
            r"(\s*(-|and|to)\s*" + 
            r"(?P<he>\d\d?):(?P<me>\d\d)\s*((?P<ame>[aA].?[mM].?)|(?P<pme>[pP].?[mM].?))?" +
            r")?", value)
        if match:
            time_dict = {}

            gd = match.groupdict()
            for bound in ["start", "end"]:
                x = bound[0]
                h,m = gd["h"+x], gd["m"+x]
                if h and m:
                    h,m = int(h), int(m)
                    am,pm = gd["am"+x], gd["pm"+x]
                    if pm or am:
                        h = cls.__convert_12_to_24_format(h, bool(pm))
                    time_dict[bound] = time(hour=h, minute=m, tzinfo=tz)
            
            assert "start" in time_dict

            return time_dict
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
        pprint(DateTimeParser.parseTimes(x))
    
    print("\nTesting timezone parsing...")

    assert DateTimeParser.parseTimes(u"""10:41 a.m. (UTC+3)""") == \
        {'start': time(10, 41, tzinfo=timezone(timedelta(hours=3, minutes=0)))}
    assert DateTimeParser.parseTimes(u"""10:41 a.m. (UTC-3)""") == \
        {'start': time(10, 41, tzinfo=timezone(timedelta(hours=-3, minutes=0)))}
    assert DateTimeParser.parseTimes(u"""10:41 a.m. (UTC+3:30)""") == \
        {'start': time(10, 41, tzinfo=timezone(timedelta(hours=3, minutes=30)))}
    assert DateTimeParser.parseTimes(u"""10:41 a.m. (UTC-3:30)""") == \
        {'start': time(10, 41, tzinfo=timezone(timedelta(hours=-3, minutes=30)))}

    assert DateTimeParser.parseTimes(u"""10:41 a.m. (UTC+13)""") == \
        {'start': time(10, 41, tzinfo=timezone(timedelta(hours=13, minutes=0)))}
    assert DateTimeParser.parseTimes(u"""10:41 a.m. (UTC-13)""") == \
        {'start': time(10, 41, tzinfo=timezone(timedelta(hours=-13, minutes=0)))}
    assert DateTimeParser.parseTimes(u"""10:41 a.m. (UTC+13:30)""") == \
        {'start': time(10, 41, tzinfo=timezone(timedelta(hours=13, minutes=30)))}
    assert DateTimeParser.parseTimes(u"""10:41 a.m. (UTC-13:30)""") == \
        {'start': time(10, 41, tzinfo=timezone(timedelta(hours=-13, minutes=30)))}
    
    print("All good!")