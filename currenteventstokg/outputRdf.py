# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import hashlib
import re
from os import makedirs
from os.path import exists
from typing import overload
from urllib.parse import quote_plus

from rdflib import (FOAF, OWL, RDF, RDFS, XSD, BNode, Graph, Literal,
                    Namespace, URIRef)

from .objects.article import Article
from .objects.event import Event
from .objects.infoboxRow import *
from .objects.topic import Topic

# data under https://data.coypu.org/ENTITY-TYPE/DATA-SOURCE/ID
events_ns = Namespace("https://data.coypu.org/event/wikipedia-current-events/")
contexts_ns = Namespace("https://data.coypu.org/context/wikipedia-current-events/")
places_ns = Namespace("https://data.coypu.org/place/wikipedia-current-events/")
osm_element_ns = Namespace("https://data.coypu.org/osmelement/wikipedia-current-events/")
point_ns = Namespace("https://data.coypu.org/point/wikipedia-current-events/")
timespan_ns = Namespace("https://data.coypu.org/time-span/wikipedia-current-events/")

COY = Namespace("https://schema.coypu.org/global#")
CEV = Namespace("https://schema.coypu.org/events#")
NIF = Namespace("http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#")
SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")
WGS = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
WD = Namespace("http://www.wikidata.org/entity/")
CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
GN = Namespace("https://www.geonames.org/ontology#")
SCHEMA = Namespace("https://schema.org/")
DCTERMS = Namespace("http://purl.org/dc/terms/")


class OutputRdf:

    def __init__(self, basedir, args, analytics, outputFolder="./dataset/"):
        self.basedir = basedir
        self.args = args
        self.analytics = analytics

        self.outputFolder = self.basedir / outputFolder
        makedirs(self.outputFolder, exist_ok=True)

        self.graphs = {
            "base": Graph(),
            "raw": Graph(),
            "ohg": Graph(),
            "osm": Graph(),
        }


    def __getTopicURI(self, t) -> URIRef:
        link = t.link
        
        if link != None and re.match("https://en.wikipedia.org/wiki/", link):
            uri = URIRef(link)
        else:
            uri =  topics_ns[str(hashlib.md5(t.text.encode('utf-8')).hexdigest())]
        return uri

    def __getTopicURIIndexBased(self, t) -> URIRef:
        prefix = t.sourceUrl + "#"
        suffix = str(t.date.day) + "_t" + str(t.index)
        uri = Namespace(prefix)[suffix]
        return uri

    
    def __getEventURIIndexBased(self, e:Event) -> URIRef:
        prefix = e.sourceUrl + "#"
        suffix = str(e.date.day) + "_e" + str(e.eventIndex)
        uri = Namespace(prefix)[suffix]
        return uri

    def __get_osm_uri(self, osmElement:OSMElement) -> URIRef:
        suffix = str(osmElement.osmType) + "_" + str(osmElement.osmId)
        uri = osm_element_ns[suffix]
        return uri
    
    def __get_infobox_row_uri(self, infobox_row:InfoboxRow, article:Article) -> URIRef:
        prefix = article.url + "#"
        url_encoded_label = quote_plus(infobox_row.label)
        suffix = f"infoboxrow_{url_encoded_label}"
        uri = Namespace(prefix)[suffix]
        return uri
    
    def __get_point_uri(self, coordinates:List[float]) -> URIRef:
        url_encoded_coords = quote_plus(f"{coordinates[0]}_{coordinates[1]}")
        uri = point_ns[url_encoded_coords]
        return uri
    

    
    def __get_event_id(self, event:Event) -> str:
        date = event.date
        return f"{date.year}_{date.month}_{date.day}_e_{event.eventIndex}"
    
    @overload
    def __get_event_uri(self, topic:Topic) -> URIRef:
        pass
    @overload
    def __get_event_uri(self, event:Event) -> URIRef:
        pass
    def __get_event_uri(self, obj) -> URIRef:
        if isinstance(obj, Event):
            date = obj.date
            suffix = self.__get_event_id(obj)
        elif isinstance(obj, Topic):
            if obj.article:
                suffix = "a_" + obj.article.url.rsplit('/', 1)[-1]
            else:
                suffix = "l_" + quote_plus(obj.text)
        uri = events_ns[suffix]
        return uri
    
    def __get_place_uri(self, article:Article) -> URIRef:
        suffix = article.url.rsplit('/', 1)[-1]
        uri = places_ns[suffix]
        return uri
    
    def __get_context_uri(self, event:Event) -> URIRef:
        suffix = self.__get_event_id(event)
        uri = contexts_ns[suffix]
        return uri
    
    def __get_sentence_uri(self, context_uri:URIRef, index:int) -> URIRef:
        uri = context_uri + f"#s{index}"
        return uri

    def __get_phrase_uri(self, sentence_uri:URIRef, index:int) -> URIRef:
        uri = sentence_uri + f"_l{index}"
        return uri
        
    
    def __get_article_uri(self, article:Article) -> URIRef:
        uri = URIRef(article.url)
        return uri

    def __get_timespan_uri(self, 
            date_or_beginning:Optional[datetime.datetime], 
            ending:Optional[datetime.datetime], 
            ongoing:bool, 
            time:Optional[List[str]], 
            endtime:Optional[List[str]], 
            timezone:Optional[str]):
        parts = []
        if date_or_beginning:
            parts.append(f"sd_{date_or_beginning}")
        if ending:
            parts.append(f"ed_{ending}")
        elif ongoing:
            parts.append(f"o")
        if time:
            parts.append(f"st_{time}")
        if endtime:
            parts.append(f"et_{endtime}")
        if timezone:
            parts.append(f"t_{timezone}")
        suffix = quote_plus("_".join(parts))
        uri = contexts_ns[suffix]
        return uri
    
    
    def __addCoordinates(self, graph:Graph, parentUri:URIRef, coordinates: list[float]):
        puri = self.__get_point_uri(coordinates)
        graph.add((parentUri, CEV.hasCoordinates, puri))
        graph.add((puri, RDF.type, WGS.Point))
        graph.add((puri, WGS.lat, Literal(str(coordinates[0]), datatype=XSD.float)))
        graph.add((puri, WGS.long, Literal(str(coordinates[1]), datatype=XSD.float)))
    

    def __addOsmElement(self, target:URIRef, osmElement:OSMElement):
        graph = self.graphs["osm"]
        osmuri = self.__get_osm_uri(osmElement)
        if osmElement.osmType or osmElement.osmId or osmElement.wkt:
            graph.add((target, CEV.hasOsmElement, osmuri))
            graph.add((osmuri, RDF.type, CEV.OsmElement))
            if osmElement.osmType:
                graph.add((osmuri, CEV.hasOsmType, Literal(str(osmElement.osmType), datatype=XSD.string)))
            if osmElement.osmId:
                graph.add((osmuri, CEV.hasOsmId, Literal(str(osmElement.osmId), datatype=XSD.integer)))
            if osmElement.wkt:
                graph.add((osmuri, CEV.hasOsmWkt, Literal(str(osmElement.wkt), datatype=GEO.wktLiteral)))
    

    def __add_place(self, graph:Graph, article:Article) -> URIRef:
        place_uri = self.__get_place_uri(article)
        graph.add((place_uri, RDF.type, CRM.E53_Place))

        # only use one row as the location (should only be one)
        location_rows = [ibr for ibr in article.infobox_rows if isinstance(ibr, InfoboxRowLocation)]
        location_row = location_rows[0] if len(location_rows) > 0 else None
        if location_row:
            graph.add((place_uri, CRM.P1_is_identified_by, location_row.value))
        
            for loc_article in set(location_row.falcon2_articles + location_row.link_articles):
                article_uri = self.__addArticleTriples(loc_article)
                loc_place_uri = self.__add_place(graph, loc_article)
                graph.add((loc_place_uri, CRM.P189_approximates, place_uri))
        
        return place_uri
    

    def __add_article_triples(self, article:Article) -> URIRef:
        base = self.graphs["base"]
        osm = self.graphs["osm"]
        raw = self.graphs["raw"]
        ohg = self.graphs["ohg"]

        article_uri = self.__get_article_uri(article)
    
        base.add((article_uri, RDF.type, GN.WikipediaArticle))

        if article.infobox:
            raw.add((article_uri, CEV.hasInfobox, Literal(str(article.infobox), datatype=XSD.string)))
        
        if article.location_flag:
            place_uri = self.__add_place(base, article)
            base.add((place_uri, GN.wikipediaArticle, article_uri))

            if article.coordinates:
                self.__addCoordinates(base, place_uri, article.coordinates)
            if article.infobox_coordinates:
                self.__addCoordinates(base, place_uri, article.infobox_coordinates)

        if len(article.wikidata_wkts) >= 1:
            for osm_element in article.wikidata_wkts:
                self.__addOsmElement(article_uri, osm_element)
        
        base.add((article_uri, OWL.sameAs, URIRef(article.wikidata_entity)))
        ohg += article.wikidata_one_hop_graph
        
        # add labels of classes which entity is instance of (classes are URIs of wd:entity in 1hop graph)
        for entityId, label in article.classes_with_labels.items():
            ohg.add((URIRef(WD[entityId]), RDFS.label, Literal(str(label), datatype=XSD.string)))
        
        # add doc infos
        if article.date_published:
            base.add((article_uri, SCHEMA.datePublished, Literal(str(article.date_published), datatype=XSD.dateTime)))
        if article.date_modified:
            base.add((article_uri, SCHEMA.dateModified, Literal(str(article.date_modified), datatype=XSD.dateTime)))
        if article.name:
            base.add((article_uri, SCHEMA.name, Literal(str(article.name), datatype=XSD.string)))
        if article.headline:
            base.add((article_uri, SCHEMA.headline, Literal(str(article.headline), datatype=XSD.string)))
        
        date_rows = []
        time_rows = []
        loc_rows = []
        for row in article.infobox_rows.values():
            if isinstance(row, InfoboxRowTime):
                time_rows.append(row)
            elif isinstance(row, InfoboxRowLocation):
                loc_rows.append(row)
            elif isinstance(row, InfoboxRowDate):
                date_rows.append(row)
            
        # add OSM elements of links texts from infoboxes "Location" values to the article
        for row in loc_rows:
            for l in row.valueLinks:
                self.__addOsmElement(article_uri, row.valueLinks_wkts[l])

        ## add timespan

        # slots
        date_or_beginning = None
        ending = None
        ongoing = False
        timezone = None
        time = None
        endtime = None

        timespan_label = ""

        # use microformats as date first
        if "dtstart" in article.microformats:
            date_or_beginning = article.microformats["dtstart"]
        if "dtend" in article.microformats:
            ending = article.microformats["dtend"]
        
        def has_time(dt:datetime.datetime) -> bool:
            t = dt.time()
            if t.hour != 0 and t.minute != 0:
                return True
            else:
                return False

        # fill slots if empty
        for row in date_rows:
            slot_filled = False

            if row.date and row.enddate:
                # fill slots with span dates
                if not date_or_beginning and row.date:
                    date_or_beginning = row.date
                    slot_filled = True
                if not ending and row.enddate:
                    ending = row.enddate
                    slot_filled = True
            elif row.date:
                # add date as either beginning or ending
                if row.start_or_end_date == "start":
                    if date_or_beginning:
                        if not has_time(date_or_beginning) and has_time(row.date):
                            date_or_beginning = row.date
                            slot_filled = True
                    else:
                        date_or_beginning = row.date
                        slot_filled = True
                else:
                    if ending:
                        if not has_time(ending) and has_time(row.enddate):
                            date_or_beginning = row.date
                            slot_filled = True
                    else:
                        ending = row.date
                        slot_filled = True
            
            # only add tz if dates were used
            if slot_filled and not timezone and row.timezone:
                timezone = row.timezone
                slot_filled = True
            
            if slot_filled:
                timespan_label += f"{row.label}: {row.value}\n"
        
        for row in time_rows:
            slot_filled = False
            row_time_split = row.time.split(":", 1)
            row_time_split = [int(i) for i in row_time_split]
            
            if row.endtime:
                row_endtime = row.endtime.split(":", 1)
                row_endtime = [int(i) for i in row_endtime]

            if date_or_beginning and ending and row.time and row.endtime:
                # add time span to date span
                if not has_time(date_or_beginning):
                    date_or_beginning.hour = row_time_split[0]
                    date_or_beginning.min = row_time_split[1]
                    slot_filled = True

                if not has_time(ending):
                    ending.hour = row_endtime[0]
                    ending.min = row_endtime[1]
                    slot_filled = True
            else:
                # add time triples extra
                if not time:
                    time = row.time
                    slot_filled = True
                if not endtime:
                    endtime = row.endtime
                    slot_filled = True
                if not timezone:
                    timezone = row.timezone
                    slot_filled = True
            
            if slot_filled:
                timespan_label += f"{row.label}: {row.value}\n"
        
        # store date/time triples from slots
        if date_or_beginning or ending or ongoing or time or endtime:
            timespan_uri = self.__get_timespan_uri(date_or_beginning, ending, ongoing, time, endtime, timezone)
            base.add((article_uri, CRM["P4_has_time-span"], timespan_uri))
            base.add((timespan_uri, RDF.type, CRM["E52_Time-Span"]))
            base.add((timespan_uri, RDFS.label, Literal(timespan_label, datatype=XSD.string)))

            if date_or_beginning:
                base.add((timespan_uri, CEV.hasDate, Literal(date_or_beginning.isoformat(), datatype=XSD.dateTime)))
            if ending:
                base.add((timespan_uri, CEV.hasEndDate, Literal(ending.isoformat(), datatype=XSD.dateTime)))
            elif ongoing:
                base.add((timespan_uri, CEV.hasOngoingSpan, Literal("true", datatype=XSD.boolean)))
            if timezone:
                base.add((timespan_uri, CEV.hasTimezone, Literal(timezone, datatype=XSD.string))) 
            if time:
                base.add((timespan_uri, CEV.hasTime, Literal(time, datatype=XSD.time)))
            if endtime:
                base.add((timespan_uri, CEV.hasEndTime, Literal(endtime, datatype=XSD.time)))
        
        return article_uri

    
    def storeEvent(self, event: Event):
        base = self.graphs["base"]
        osm = self.graphs["osm"]
        raw = self.graphs["raw"]


        all_articles = []
        for s in event.sentences:
            # add all existing articles
            all_articles.extend([a for a in s.articles if a])
        
        wd_loc_article_URIs = [
            a.wikidata_entity for a in all_articles 
            if a != None and a.wikidata_entity != None and a.location_flag == True
        ]
        wd_loc_article_URIs4counting_leafs = set(wd_loc_article_URIs)
        
        # filters for a specific event for generating an example sample ("2021–2022 Boulder County fires")
        if self.args.sample_mode and event.date != datetime.datetime(2022,1,1) and event.eventIndex != 1:
            return
        
        # URIs
        e5_event_uri = self.__get_event_uri(event)
        context_uri = self.__get_context_uri(event)

        ## E5_Event triples
        base.add((e5_event_uri, RDF.type, CRM.E5_Event))
        base.add((e5_event_uri, CRM.P1_is_identified_by, context_uri))
        base.add((e5_event_uri, CEV.hasMentionDate, Literal(event.date.isoformat(), datatype=XSD.date)))
        base.add((e5_event_uri, COY.hasTag, Literal(str(event.category), datatype=XSD.string)))

        raw.add((e5_event_uri, CEV.hasRaw, Literal(str(event.raw), datatype=XSD.string)))

        # connect with topic
        for t in event.parentTopics:
            parent_e5 = self.__get_event_uri(t)
            base.add((e5_event_uri, CRM.P117_occurs_during, parent_e5))

        # wikidata type
        for entityId, label in event.eventTypes.items():
            class_uri = URIRef(WD[entityId])
            base.add((e5_event_uri, CEV.hasWikidataEventType, class_uri))
            base.add((class_uri, RDFS.label, Literal(str(label), datatype=XSD.string)))


        ## Context node triples
        base.add((context_uri, RDF.type, NIF.Context))

        # string
        base.add((context_uri, NIF.isString, Literal(str(event.text), datatype=XSD.string)))
        base.add((context_uri, NIF.beginIndex, Literal(0, datatype=XSD.nonNegativeInteger)))
        base.add((context_uri, NIF.endIndex, Literal(len(event.text), datatype=XSD.nonNegativeInteger)))

        # source (https://en.wikipedia.org/wiki/Portal:Current_events/...)
        source_uri = URIRef(event.sourceUrl)
        base.add((context_uri, NIF.sourceUrl, source_uri)) 
        base.add((source_uri, RDF.type, FOAF.Document))

        # the news sources
        for l in event.sourceLinks:
            source_link_uri = URIRef(l.href)

            base.add((context_uri, DCTERMS.source, source_link_uri))
            base.add((source_link_uri, RDF.type, COY.News))
            base.add((source_link_uri, RDFS.label, Literal(str(l.text), datatype=XSD.string)))

        # sentences
        lastSentenceUri = None
        sentences = event.sentences
        for i in range(len(sentences)):
            sentence = sentences[i]
            sentence_uri = self.__get_sentence_uri(context_uri, i)

            base.add((sentence_uri, RDF.type, NIF.Sentence))
            base.add((sentence_uri, NIF.referenceContext, context_uri))
            base.add((context_uri, NIF.subString, sentence_uri))
            base.add((sentence_uri, NIF.anchorOf, Literal(str(sentence.text), datatype=XSD.string)))
            base.add((sentence_uri, NIF.beginIndex, Literal(sentence.start, datatype=XSD.nonNegativeInteger)))
            base.add((sentence_uri, NIF.endIndex, Literal(sentence.end, datatype=XSD.nonNegativeInteger)))
            if(lastSentenceUri != None):
                base.add((sentence_uri, NIF.previousSentence, lastSentenceUri))
                base.add((lastSentenceUri, NIF.nextSentence, sentence_uri))

            # links per sentence as nif:Phase
            links = sentence.links
            articles = sentence.articles
            for j in range(len(links)):
                article = articles[j]
                link = links[j]

                # link
                link_uri = self.__get_phrase_uri(sentence_uri, j)
                base.add((link_uri, RDF.type, NIF.Phase))
                base.add((link_uri, NIF.referenceContext, sentence_uri))
                base.add((sentence_uri, NIF.subString, link_uri))
                base.add((link_uri, NIF.anchorOf, Literal(str(link.text), datatype=XSD.string)))
                base.add((link_uri, NIF.beginIndex, Literal(link.startPos, datatype=XSD.nonNegativeInteger)))
                base.add((link_uri, NIF.endIndex, Literal(link.endPos, datatype=XSD.nonNegativeInteger)))
                
                # article
                if article:
                    article_uri = self.__add_article_triples(article)
                    base.add((link_uri, GN.wikipediaArticle, article_uri))

                    # optimize searching for articles by wikidata entity
                    wd_entity2Article = {a.wikidata_entity:a for a in all_articles if a and a.wikidata_entity}

                    # link wikidata entities with parent locations in this sentence (eg NY with USA)
                    for parent_wd_entity in article.parent_locations_and_relation:
                        # dont link reflexive (eg USA links USA as its country)
                        if parent_wd_entity in wd_loc_article_URIs and \
                                article.wikidata_entity != parent_wd_entity:
                            parent_loc_article = wd_entity2Article[parent_wd_entity]
                            parent_loc_place_uri = self.__get_place_uri(parent_loc_article)
                            place_uri = self.__get_place_uri(article)
                            base.add((place_uri, CRM.P89_falls_within, parent_loc_place_uri))

                            if parent_wd_entity in wd_loc_article_URIs4counting_leafs:
                                wd_loc_article_URIs4counting_leafs.remove(parent_wd_entity)
            lastSentenceUri = sentence_uri
        if len(wd_loc_article_URIs4counting_leafs) > 1:
            self.analytics.numEventsWithMoreThanOneLeafLocation += 1
        
    
    def storeTopic(self, topic: Topic):
        base = self.graphs["base"]
        osm = self.graphs["osm"]
        raw = self.graphs["raw"]

        # filters for a specific topics for generating an example sample
        if self.args.sample_mode and topic.date != datetime.datetime(2022,1,1) and topic.index != 0:
            return
        
        ## E5_Event triples
        e5_event_uri = self.__get_event_uri(topic)

        base.add((e5_event_uri, RDF.type, CRM.E5_Event))
        base.add((e5_event_uri, CRM.P1_is_identified_by, Literal(str(topic.text), datatype=XSD.string)))
        
        # store date of usage of this topic
        base.add((e5_event_uri, CEV.hasMentionDate, Literal(topic.date.isoformat(), datatype=XSD.date)))

        raw.add((e5_event_uri, CEV.hasRaw, Literal(str(topic.raw), datatype=XSD.string)))

        # connect to parent topics
        if topic.parentTopics:
            for pt in topic.parentTopics:
                parent_e5 = self.__get_event_uri(pt)
                base.add((e5_event_uri, CRM.P117_occurs_during, parent_e5))
        
        if topic.article:
            article_uri = self.__add_article_triples(topic.article)
            base.add((e5_event_uri, GN.wikipediaArticle, article_uri))
        

    def __load_graph(self, filename:str, dest_graph:Graph):
        path = self.outputFolder / filename
        with open(path, "r", encoding="utf-8") as f:
            dest_graph.parse(file=f)
        

    def load(self, file_prefix:str):
        for name, g in self.graphs.items():
            self.__load_graph(file_prefix + "_" + name + ".jsonld", g)
    

    def reset(self):
        for name in self.graphs:
            self.graphs[name] = Graph()


    def __save_graph(self, graph:Graph, filename:str):
        s = graph.serialize(format="json-ld")
        path = self.outputFolder / filename
        with open(path, mode='w', encoding="utf-8") as f:
            f.write(s)
        print("Graph saved to", path)
        
    
    def save(self, file_prefix:str):
        for name in self.graphs.keys():
            filename = file_prefix + "_" + name + ".jsonld"            
            self.__save_graph(self.graphs[name], filename)
            
    
    def exists(self, file_prefix:str):
        for graph_name in self.graphs.keys():
            if not exists(file_prefix + "_" + graph_name + ".jsonld"):
                return False
        return True
        
    