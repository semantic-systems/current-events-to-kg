# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

months = ["January","February","March","April","May","June","July","August","September","October","November","December"]

month2int = {"January":1,"February":2,"March":3,"April":4,"May":5,"June":6,"July":7,
    "August":8,"September":9,"October":10,"November":11,"December":12}

def graph_name_list(start:int, end:int):
    res = []
    current = start
    while current <= end:
        month = int(current%100)
        year = int((current-month)/100)
        res.append(f"{months[month-1]}_{year}")
        month += 1
        if month > 12:
            year += 1
            month = 1
        current = int(year*100+month)
    return res