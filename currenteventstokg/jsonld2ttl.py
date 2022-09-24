from os import makedirs
from os.path import exists
from pathlib import Path
from typing import Dict, List, Tuple, Union

from rdflib import Graph


def jsonld2ttl(basedir:Path, base_file_name:str, graph_extensions:List[str], force:bool=True) -> str:
    ds_dir = basedir / "./dataset/"
    out_dir = basedir / "./dataset_ttl/"
    makedirs(out_dir, exist_ok=True)

    prefix = base_file_name.split(".")[0]
    prefix_dmy = "_".join(prefix.split("_")[0:-1])

    out_name = prefix_dmy + ".ttl"
    out_path = out_dir / out_name


    if not exists(out_path) or force:
        # load graph
        g = Graph()
        f_path = ds_dir / base_file_name
        print(f"Parsing {f_path}...")
        g.parse(f_path)

        for ge in graph_extensions:
            f_path = ds_dir / (f"{prefix_dmy}_{ge}.jsonld")
            print(f"Parsing {f_path}...")
            g.parse(f_path)

        # convert and save
        print(f"Saving to {out_path}...")
        g.serialize(str(out_path), format="turtle", encoding="utf-8")

    return out_name
