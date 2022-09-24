import argparse
import subprocess
from os import makedirs
from os.path import abspath, exists, split
from pathlib import Path

from ..jsonld2ttl import jsonld2ttl


basedir, _ = split(abspath(__file__))
basedir = Path(basedir)

ttl_dataset_dir = basedir / 'dataset_ttl'

def loadMonth(month_year:str, virtuoso_dir:Path, extensions=["osm"]): #, "ohg", "raw"
    create_script_path = str(virtuoso_dir / "create_graph.sh")
    
    jsonld_base_graph_file_name = f"{month_year}_base.jsonld"

     # create ttl file for importing into virtuoso
    print("Create .ttl file...")
    ttl_file_name = jsonld2ttl(basedir, jsonld_base_graph_file_name, extensions)

    print(f"Move {ttl_file_name} to virtuoso...")
    cmd = f"cp {str(ttl_dataset_dir / ttl_file_name)} {str(ttl_dir)}"
    print(cmd)
    subprocess.call(cmd, shell=True, cwd=virtuoso_dir)

    print(f"Load {ttl_file_name} into virtuoso...")
    cmd = f"{create_script_path} {month_year}"
    print(cmd)
    subprocess.call(cmd, shell=True, cwd=virtuoso_dir)


def bulkLoadMonths(months:str, virtuoso_dir:Path, num_processes:int, extensions=["osm"]):
    rdf_loader_run_script_path = str(virtuoso_dir / "rdf_loader_run.sh")
    queue_graph_script_path = str(virtuoso_dir / "queue_graph_for_bulkload.sh")


    ttl_files = []
    for month_year in months.split((",")):
        jsonld_base_graph_file_name = f"{month_year}_base.jsonld"

        # create ttl file for importing into virtuoso
        print("Create .ttl file...")
        ttl_file_name = jsonld2ttl(basedir, jsonld_base_graph_file_name, extensions)
        ttl_files.append(ttl_file_name)

        print(f"Move {ttl_file_name} to virtuoso...")
        cmd = f"cp {str(ttl_dataset_dir / ttl_file_name)} {str(ttl_dir)}"
        print(cmd)
        subprocess.call(cmd, shell=True, cwd=virtuoso_dir)

        print(f"Queue {ttl_file_name} for loading into virtuoso...")
        cmd = f"{queue_graph_script_path} {month_year}"
        print(cmd)
        subprocess.call(cmd, shell=True, cwd=virtuoso_dir)

    print(f"Bulk load...")
    ret_array = []
    for i in range(num_processes):
        print(f"Process {i} started...")
        ret = subprocess.Popen([rdf_loader_run_script_path, str(num_processes), "&"])
        ret_array.append(ret)
    
    print(f"Wait for bulk load processes...")
    for i,ret in enumerate(ret_array):
        ret.wait()
        print(f"Process {i} finished...")

    for ttl_file_name in ttl_files:
        print(f"Move {ttl_file_name} back to {str(ttl_dir)}...")
        cmd = f"mv {str(virtuoso_dir / ttl_file_name)} {str(ttl_dir)}"
        print(cmd)
        subprocess.call(cmd, shell=True, cwd=virtuoso_dir)


def bulkDropMonths(months:str, virtuoso_dir:Path):
    remove_script_path = str(virtuoso_dir / "remove_graph.sh")

    for month_year in months.split((",")):
        print(f"Drop graph <{month_year}>...")
        subprocess.call(f"{remove_script_path} {month_year}", shell=True, cwd=virtuoso_dir)


def dropMonth(month_year:str, virtuoso_dir:Path):
    remove_script_path = str(virtuoso_dir / "remove_graph.sh")

    print(f"Drop graph <{month_year}>...")
    subprocess.call(f"{remove_script_path} {month_year}", shell=True, cwd=virtuoso_dir)


def list_loaded_graphs():
    list_loaded_script_path = str(virtuoso_dir / "list_loaded_graphs.sh")

    subprocess.call(list_loaded_script_path, shell=True, cwd=virtuoso_dir)

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument('-l', '--load', 
        action='store', 
        help="Loads a month into Vituoso. (e.g. -l March_2022)",
        type=str)
    
    parser.add_argument('-ls', '--list', 
        action='store_true', 
        help="Print loading list.")
    
    parser.add_argument('-bl', '--bulk_load', 
        action='store', 
        help="Loads several months into Vituoso, seperated by comma. (e.g. -bl February_2022,March_2022)",
        type=str)

    parser.add_argument('-bd', '--bulk_drop', 
        action='store', 
        help="Drops several months from Vituoso, seperated by comma. (e.g. -bd February_2022,March_2022)",
        type=str)
    
    parser.add_argument('-np', '--num_processes', 
        action='store', 
        help="Number of precesses to load into virtuoso with. (recommended: #cores / 2.5)",
        type=int,
        default=1)
    
    parser.add_argument('-d', '--drop', 
        action='store', 
        help="Drops a month from Vituoso. (e.g. -d March_2022)",
        type=str)
    
    parser.add_argument('-v', '--virtuoso_dir', 
        action='store', 
        help="Root directory of your virtuoso.",
        type=str,
        required=True)
    
    args = parser.parse_args()

    virtuoso_dir = Path(args.virtuoso_dir)

    # make sure dir exists
    ttl_dir = virtuoso_dir / "ttl_files"
    makedirs(ttl_dir, exist_ok=True)
    
    if args.load:
        loadMonth(args.load, virtuoso_dir)
    
    if args.bulk_load:
        bulkLoadMonths(args.bulk_load, virtuoso_dir, args.num_processes)
    
    if args.bulk_drop:
        bulkDropMonths(args.bulk_drop, virtuoso_dir)

    if args.drop:
        dropMonth(args.drop, virtuoso_dir)
    
    if args.list:
        list_loaded_graphs()

    
    
    

