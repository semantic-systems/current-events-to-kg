import json
import re
from atexit import register
from os.path import exists
from pprint import pprint
from typing import Dict, List, Optional, Tuple, Union
import argparse


import requests
import matplotlib.pyplot as plt
from getkey import getkey
from .current_events_graph import CurrentEventsGraph
from .current_events_diagram import CurrentEventDiagram
from currenteventstokg import currenteventstokg_module_dir


class LocationClassificationDiagram(CurrentEventDiagram):
    def __init__(self, graph_names:List[str]):
        super().__init__("location_classification", graph_names, ["base"], CurrentEventsGraph)
        
    def create_diagram(self, force_vote=False):
        # load jan_2022 data
        d = {}
        with open(self.cache_dir / "loclog.json", "r") as f:
            for line in f:
                j = json.loads(line)
                d[j["name"]] = j
        
        num_locs, num_non_locs = self.__count_articles(d)
        #print(num_locs, num_non_locs)
        
        old = {"tp":[],"fp":[],"tn":[],"fn":[]}
        new = {"tp":[],"fp":[],"tn":[],"fn":[]}
        old_coord = {"tp":[],"fp":[],"tn":[],"fn":[]}
        new_coord = {"tp":[],"fp":[],"tn":[],"fn":[]}
        new_old = {"tp":[],"fp":[],"tn":[],"fn":[]}
        new_old_coord = {"tp":[],"fp":[],"tn":[],"fn":[]}

        if not exists(self.cache_dir / "answers.json") or force_vote:
            # manually vote
            answers = {}
            print("1 or 0 (True or False)")
            for j in d.values():
                while True:
                    #print(j, old, new, old_coord, new_coord)
                    print(f"{j['name']}")
                    i = getkey()
                    if i != "0" and i != "1":
                        continue
                    else:
                        i = bool(int(i))
                        answers[j["name"]] = i
                        break
            
            with open(self.cache_dir / "answers.json", "a") as f:
                json.dump(answers, f)
                print("", file=f)


        ## load votes
        with open(self.cache_dir / "answers.json", "r") as f:
            for i, line in enumerate(f):
                answers = json.loads(line)

                old = {"tp":[],"fp":[],"tn":[],"fn":[]}
                new = {"tp":[],"fp":[],"tn":[],"fn":[]}
                old_coord = {"tp":[],"fp":[],"tn":[],"fn":[]}
                new_coord = {"tp":[],"fp":[],"tn":[],"fn":[]}
                new_old = {"tp":[],"fp":[],"tn":[],"fn":[]}
                new_old_coord = {"tp":[],"fp":[],"tn":[],"fn":[]}

                tests = {
                    "old":old, "new":new, 
                    "old_coord":old_coord, "new_coord":new_coord, 
                    "new_old":new_old, "new_old_coord":new_old_coord
                }
                
                for name, vote in answers.items():
                    self.__count_vote(vote, d[name], tests)

                accs = []
                recs = []
                pres = []
                sups = []
                f1s = []

                for key in tests:
                    var = tests[key]
                    precision, recall, accuracy, support, f1 = self.__calculate_metrics(
                            len(var["tp"])+num_locs, 
                            len(var["fp"]), 
                            len(var["tn"])+num_non_locs, 
                            len(var["fn"]))
                    accs.append(accuracy)
                    recs.append(recall)
                    pres.append(precision) 
                    sups.append(support)
                    f1s.append(f1)
                    
                # plot
                plt.style.use(currenteventstokg_module_dir / "resources" / "bar.mplstyle")
                
                fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2,2, squeeze=False, layout="constrained")
                
                labels = {
                    "old":"a", "new":"b", 
                    "old_coord":"a+c", "new_coord":"b+c", 
                    "new_old":"a+b", "new_old_coord":"a+b+c"
                }
                
                x = [labels[x] for x in tests.keys()]
                ax1.bar(x, f1s)
                ax1.set_title("F1")
                ax1.set_ylabel("F1")
                ax1.set_ylim(0.8, 1)

                ax2.bar(x, accs)
                ax2.set_title("Accuracy")
                ax2.set_ylabel("Accuracy")
                ax2.set_ylim(0.9, 1)

                ax3.bar(x, pres)
                ax3.set_title("Precision")
                ax3.set_ylabel("Precision")
                ax3.set_ylim(0.8, 1)

                ax4.bar(x, recs)
                ax4.set_title("Recall")
                ax4.set_ylabel("Recall")
                ax4.set_ylim(0.8, 1)

                for ax in [ax1, ax2, ax3, ax4]:
                    ax.set_xlabel("Classification Method")
            
                fig.savefig(
                    self.diagrams_dir / f"{self.filename}_{i}.svg",
                    #dpi=400,
                )

    def __count_vote(self, vote, j, tests):
        name = j['name']
        for stmt, var in [
                (j["old"], tests["old"]),
                (j["new"], tests["new"]),
                ((j["new"] or j["coord"]), tests["new_coord"]),
                ((j["old"] or j["coord"]), tests["old_coord"]),
                ((j["old"] or j["new"]), tests["new_old"]),
                ((j["old"] or j["new"] or j["coord"]), tests["new_old_coord"])]:
            if stmt:
                if vote:
                    var["tp"].append(name)
                else:
                    var["fp"].append(name)
            else:
                if vote:
                    var["fn"].append(name)
                else:
                    var["tn"].append(name)
        
    
    def __count_articles(self, d):
        g = CurrentEventsGraph(["January_2022"])
        q = """
            PREFIX gn: <https://www.geonames.org/ontology#>
            PREFIX schema: <https://schema.org/>
            PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
            SELECT DISTINCT ?name ?loc WHERE{
            ?a  a gn:WikipediaArticle;
                schema:name ?name.
            BIND(EXISTS{
                ?p  a crm:E53_Place;
                    gn:wikipediaArticle ?a.
            } AS ?loc).
        }"""
        res = g.query(q)

        d_name_set = set(d.keys())

        locs = 0
        non_locs = 0
        for row in res:
            name = str(row["name"])
            loc = bool(row["loc"])
            if name not in d_name_set:
                if loc:
                    locs += 1
                else:
                    non_locs += 1
            #print(name, loc)
        return locs, non_locs

    def __calculate_precision(self, true_pos:int, false_pos:int):
        try:
            precision = true_pos / (false_pos + true_pos)
        except ZeroDivisionError:
            precision = 0
        return precision

    def __calculate_accuracy(self, true_pos:int, true_neg:int, support:int):
        try:
            accuracy = (true_pos + true_neg) / support
        except ZeroDivisionError:
            accuracy = 0
        return accuracy

    def __calculate_metrics(self, true_pos:int, false_pos:int, true_neg:int, false_neg:int):
        support = true_pos + false_pos + true_neg + false_neg

        precision = self.__calculate_precision(true_pos, false_pos)
        accuracy = self.__calculate_accuracy(true_pos, true_neg, support)
        
        try:
            recall = true_pos / (true_pos + false_neg)
        except ZeroDivisionError:
            recall = 0
        
        try:
            f1 = 2 * (precision * recall) / (precision + recall)
        except ZeroDivisionError:
            f1 = 0
        
        return precision, recall, accuracy, support, f1



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    
    parser.add_argument("-fv", '--force_vote',
        action='store_true', 
        help="force vote")
    
    args = parser.parse_args()

    
    LocationClassificationDiagram(["January_2022"]).create_diagram(args.force_vote)