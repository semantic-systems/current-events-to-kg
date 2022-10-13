from bs4 import BeautifulSoup, NavigableString, Tag
from os.path import exists
from pathlib import Path
import json
from .inputHtml import InputHtml
import re
from typing import Set

class PlacesTemplatesExtractor():
    def __init__(self, basedir:Path, args, inputHtml:InputHtml, parser:str):
        self.basedir = basedir
        self.inputHtml = inputHtml
        self.parser = parser

        self.templates_cache_path = self.basedir / args.cache_dir / "places_templates.json"
    
    def get_templates(self, force_parse:bool) -> Set[str]:
        if exists(self.templates_cache_path) and not force_parse:
            print(f"Loading places templates from {self.templates_cache_path}")
            with open(self.templates_cache_path, mode='r', encoding="utf-8") as f:
                template_list = json.load(f)
                return set(template_list)
        else:
            page = self.inputHtml.fetchLocationTemplatesPage()
            soup = BeautifulSoup(page, self.parser)
            
            content = soup.find("div", class_="mw-parser-output")
            
            def f(text):
                return bool(re.match("Template:Infobox", str(text)))
            place_template_links = content.find_all("a", string=f)

            href_list = [str(l.attrs["href"]).split("/")[-1] for l in place_template_links]
            
            template_list = [l for l in href_list]

            # cache
            with open(self.templates_cache_path, mode='w', encoding="utf-8") as f:
                json.dump(template_list, f)
            
            return set(template_list)



            
            
        
