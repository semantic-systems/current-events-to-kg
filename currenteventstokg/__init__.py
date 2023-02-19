# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from pathlib import Path
from os.path import abspath, split
from rdflib import Namespace

currenteventstokg_dir = Path(split(abspath(__file__))[0])

# data under https://data.coypu.org/ENTITY-TYPE/DATA-SOURCE/ID
events_ns = Namespace("https://data.coypu.org/newssummary/wikipedia-current-events/")
article_topics_ns = Namespace("https://data.coypu.org/articletopic/wikipedia-current-events/")
text_topics_ns = Namespace("https://data.coypu.org/texttopic/wikipedia-current-events/")
contexts_ns = Namespace("https://data.coypu.org/context/wikipedia-current-events/")
sentences_ns = Namespace("https://data.coypu.org/sentence/wikipedia-current-events/")
phrases_ns = Namespace("https://data.coypu.org/phrase/wikipedia-current-events/")
locations_ns = Namespace("https://data.coypu.org/location/wikipedia-current-events/")
osm_element_ns = Namespace("https://data.coypu.org/osmelement/wikipedia-current-events/")
point_ns = Namespace("https://data.coypu.org/point/wikipedia-current-events/")
timespan_ns = Namespace("https://data.coypu.org/timespan/wikipedia-current-events/")
wikipedia_article_ns = Namespace("https://data.coypu.org/wikipediaarticle/wikipedia-current-events/")

COY = Namespace("https://schema.coypu.org/global#")
NIF = Namespace("http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#")
SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")
WGS = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
WD = Namespace("http://www.wikidata.org/entity/")
GN = Namespace("https://www.geonames.org/ontology#")
SCHEMA = Namespace("https://schema.org/")
DCTERMS = Namespace("http://purl.org/dc/terms/")