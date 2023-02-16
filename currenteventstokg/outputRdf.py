# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import re
from os import makedirs
from os.path import exists
from typing import overload, Tuple, Optional, List
from urllib.parse import quote_plus
import datetime

from rdflib import (FOAF, OWL, RDF, RDFS, XSD, BNode, Graph, Literal,
                    Namespace, URIRef)

from .objects.article import Article
from .objects.event import Event
from .objects.infoboxRow import InfoboxRowDate, InfoboxRowTime, InfoboxRowLocation
from .objects.topic import Topic
from .objects.osmElement import OSMElement
from .graphConsistencyKeeper import GraphConsistencyKeeper

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

        self.gck = GraphConsistencyKeeper(
            self.args.dataset_endpoint, 
            self.args.dataset_endpoint_subgraph, 
            self.args.dataset_endpoint_username, 
            self.args.dataset_endpoint_pw
        )


    def __get_osm_uri(self, osmElement:OSMElement) -> URIRef:
        suffix = str(osmElement.osmType) + "_" + str(osmElement.osmId)
        uri = osm_element_ns[suffix]
        return uri
    
    def __get_point_uri(self, coordinates:List[float]) -> URIRef:
        url_encoded_coords = quote_plus(f"{coordinates[0]}_{coordinates[1]}")
        uri = point_ns[url_encoded_coords]
        return uri
    
    def __get_event_id(self, event:Event) -> str:
        date = event.date
        return f"{date.year:04}-{date.month:02}-{date.day:02}_{event.eventIndex}"

    def __get_wiki_article_url_identifier(self, article:Article) -> str:
        return article.url.rsplit('/', 1)[-1]
    
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
            uri = events_ns[suffix]
        elif isinstance(obj, Topic):
            if obj.article:
                # Topics with link to wiki article
                suffix = self.__get_wiki_article_url_identifier(obj.article)
                uri = article_topics_ns[suffix]
            else:
                # Topics without link
                suffix = quote_plus(obj.text)
                uri = text_topics_ns[suffix]
        return uri
    
    def __get_place_uri(self, article:Article) -> URIRef:
        suffix = self.__get_wiki_article_url_identifier(article)
        uri = locations_ns[suffix]
        return uri
    
    def __get_context_uri(self, event:Event) -> URIRef:
        suffix = self.__get_event_id(event)
        uri = contexts_ns[suffix]
        return uri
    
    def __get_sentence_uri(self, context_uri:URIRef, index:int) -> URIRef:
        uri = sentences_ns[context_uri.rsplit('/', 1)[-1] + f"_{index}"]
        return uri

    def __get_phrase_uri(self, sentence_uri:URIRef, index:int) -> URIRef:
        uri = phrases_ns[sentence_uri.rsplit('/', 1)[-1] + f"_{index}"]
        return uri
    
    def __get_article_uri(self, article:Article) -> URIRef:
        suffix = self.__get_wiki_article_url_identifier(article)
        uri = wikipedia_article_ns[suffix]
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
        uri = timespan_ns[suffix]
        return uri
    
    
    def __addCoordinates(self, graph:Graph, parentUri:URIRef, coordinates: list[float]):
        # add coords via wgs:Point
        puri = self.__get_point_uri(coordinates)
        graph.add((parentUri, COY.hasLocation, puri))
        graph.add((puri, RDF.type, WGS.Point))

        graph.add((puri, RDFS.label, Literal(f"{coordinates[0]},{coordinates[1]}", datatype=XSD.string)))
        
        graph.add((puri, WGS.lat, Literal(str(coordinates[0]), datatype=XSD.float)))
        graph.add((puri, WGS.long, Literal(str(coordinates[1]), datatype=XSD.float)))

        # add coords directly for compatibility
        graph.add((parentUri, COY.hasLatitude, Literal(str(coordinates[0]), datatype=XSD.decimal)))
        graph.add((parentUri, COY.hasLongitude, Literal(str(coordinates[1]), datatype=XSD.decimal)))
    

    def __addOsmElement(self, target:URIRef, osmElement:OSMElement):
        graph = self.graphs["osm"]
        osmuri = self.__get_osm_uri(osmElement)
        if osmElement.osmType or osmElement.osmId or osmElement.wkt:
            graph.add((target, COY.hasOsmElement, osmuri))
            graph.add((osmuri, RDF.type, COY.OsmElement))
            graph.add((osmuri, RDFS.label, Literal(f"{osmElement.osmType} {osmElement.osmId}", datatype=XSD.string)))

            if osmElement.osmType:
                graph.add((osmuri, COY.hasOsmType, Literal(str(osmElement.osmType), datatype=XSD.string)))
            if osmElement.osmId:
                graph.add((osmuri, COY.hasOsmId, Literal(str(osmElement.osmId), datatype=XSD.integer)))
            if osmElement.wkt:
                graph.add((osmuri, GEO.asWKT, Literal(str(osmElement.wkt), datatype=GEO.wktLiteral)))
        
        # delete old triples in dataset endpoint
        if self.args.delete_old_entities:
            self.gck.delete_osmelement_triples(osmuri)
    

    def __add_place(self, graph:Graph, article:Article) -> URIRef:
        place_uri = self.__get_place_uri(article)
        graph.add((place_uri, RDF.type, COY.Location))
        graph.add((place_uri, RDFS.label, Literal(f"{article.name}", datatype=XSD.string)))

        # only use one row as the location (should only be one)
        location_rows = [ibr for ibr in article.infobox_rows.values() if isinstance(ibr, InfoboxRowLocation)]
        location_row = location_rows[0] if len(location_rows) > 0 else None
        if location_row:
            graph.add((place_uri, COY.isIdentifiedBy, Literal(str(location_row.value), datatype=XSD.string)))
            link_articles = [ l.article for l in location_row.valueLinks if l.article ]
            for loc_article in set(location_row.falcon2_articles + link_articles):
                article_uri, _ = self.__add_article_triples(loc_article)
                loc_place_uri = self.__add_place(graph, loc_article)
                graph.add((place_uri, COY.isLocatedIn, loc_place_uri))
        
        return place_uri
    
    def __add_timespan(self, graph:Graph, article:Article) -> Optional[URIRef]:
        # slots
        start_date_slot = None
        end_date_slot = None
        start_time_slot = None
        end_time_slot = None
        ongoing_flag_slot = False
        timezone_slot = None

        timespan_label = ""

        # use microformats as date first
        if "dtstart" in article.microformats:
            start_date_slot = article.microformats["dtstart"]
            timespan_label += f"dtstart: {start_date_slot}\n"
        if "dtend" in article.microformats:
            end_date_slot = article.microformats["dtend"]
            timespan_label += f"dtend: {end_date_slot}\n"
        
        def has_time(dt:datetime.datetime) -> bool:
            t = dt.time()
            if t.hour != 0 and t.minute != 0:
                return True
            else:
                return False
        
        date_rows = []
        time_rows = []
        for row in article.infobox_rows.values():
            if isinstance(row, InfoboxRowTime):
                time_rows.append(row)
            elif isinstance(row, InfoboxRowDate):
                date_rows.append(row)

        # fill slots if empty or more info
        for row in date_rows:
            slot_filled = False

            # fill start
            if row.start_date:
                if not start_date_slot:
                    start_date_slot = row.start_date
                    slot_filled = True
                elif start_date_slot and not has_time(start_date_slot) and has_time(row.start_date):
                    start_date_slot = start_date_slot.replace(
                        hour=row.start_date.hour, minute=row.start_date.minute)
                    slot_filled = True
            
            # fill end
            if row.ongoing and not end_date_slot:
                ongoing_flag_slot = True
            elif row.end_date and not ongoing_flag_slot:
                if not end_date_slot:
                    end_date_slot = row.end_date
                    slot_filled = True
                elif end_date_slot and not has_time(end_date_slot) and has_time(row.end_date):
                    end_date_slot = end_date_slot.replace(
                        hour=row.end_date.hour, minute=row.end_date.minute)
                    slot_filled = True
                    
            # fill timezone
            if not timezone_slot:
                if row.start_date and row.start_date.tzinfo:
                    timezone_slot = row.start_date.tzinfo
                    slot_filled = True
                elif row.end_date and row.end_date.tzinfo:
                    timezone_slot = row.end_date.tzinfo
                    slot_filled = True
            
            if slot_filled:
                timespan_label += f"{row.label}: {row.value}\n"

        for row in time_rows:
            slot_filled = False

            if start_date_slot and not end_date_slot:
                # combine dates and times to one time span
                # discard time(span) if time(span) produces multiple spans
                if row.start_time and not has_time(start_date_slot):
                    start_date_slot = start_date_slot.replace(
                        hour=row.start_time.hour, minute=row.start_time.minute)
                    slot_filled = True

                if row.end_time:
                    end_date_slot = start_date_slot.replace(
                        hour=row.end_time.hour, minute=row.end_time.minute)
                    slot_filled = True
            elif not start_date_slot and not end_date_slot:
                # add time triples extra
                if not start_time_slot:
                    start_time_slot = row.start_time
                    slot_filled = True
                if not end_time_slot:
                    end_time_slot = row.end_time
                    slot_filled = True
            
            if not timezone_slot:
                if row.start_time.tzinfo:
                    timezone_slot = row.start_time.tzinfo
                    slot_filled = True
                elif row.end_time and row.end_time.tzinfo:
                    timezone_slot = row.end_time.tzinfo
                    slot_filled = True
            
            if slot_filled:                
                timespan_label += f"{row.label}: {row.value}\n"
        
        # if only the start datetime was found (nothing set the end), assume that the event is a point in time
        if start_date_slot and not end_date_slot and not ongoing_flag_slot:
            end_date_slot = start_date_slot
        
        # set found timezone for all found values
        if timezone_slot:
            if start_date_slot: start_date_slot = start_date_slot.replace(tzinfo=timezone_slot)
            if end_date_slot: end_date_slot = end_date_slot.replace(tzinfo=timezone_slot)
            if start_time_slot: start_time_slot = start_time_slot.replace(tzinfo=timezone_slot)
            if end_time_slot: end_time_slot = end_time_slot.replace(tzinfo=timezone_slot)
        
        # store date/time triples from slots
        timespan_uri = None
        if start_date_slot or end_date_slot or ongoing_flag_slot or start_time_slot or end_time_slot:
            timespan_uri = self.__get_timespan_uri(start_date_slot, end_date_slot, ongoing_flag_slot, start_time_slot, end_time_slot, timezone_slot)
            graph.add((timespan_uri, RDF.type, COY.Timespan))
            graph.add((timespan_uri, RDFS.label, Literal(timespan_label, datatype=XSD.string)))

            if start_date_slot:
                graph.add((timespan_uri, COY.hasStartDate, Literal(start_date_slot.isoformat(), datatype=XSD.dateTime)))
            if end_date_slot:
                graph.add((timespan_uri, COY.hasEndDate, Literal(end_date_slot.isoformat(), datatype=XSD.dateTime)))
            elif ongoing_flag_slot:
                graph.add((timespan_uri, COY.hasOngoingSpan, Literal("true", datatype=XSD.boolean)))
            if start_time_slot:
                graph.add((timespan_uri, COY.hasStartTimestamp, Literal(start_time_slot, datatype=XSD.time)))
            if end_time_slot:
                graph.add((timespan_uri, COY.hasEndTimestamp, Literal(end_time_slot, datatype=XSD.time)))
        
        return timespan_uri
    

    def __add_article_triples(self, article:Article, is_topic_article:bool=False) -> Tuple[URIRef, Optional[URIRef]]:
        base = self.graphs["base"]
        osm = self.graphs["osm"]
        raw = self.graphs["raw"]
        ohg = self.graphs["ohg"]

        article_uri = self.__get_article_uri(article)
    
        base.add((article_uri, RDF.type, GN.WikipediaArticle))
        base.add((article_uri, RDFS.label, Literal(str(article.name), datatype=XSD.string)))

        # source document (Wiki article url)
        source_uri = URIRef(str(article.url))
        base.add((source_uri, RDF.type, FOAF.Document))
        base.add((article_uri, DCTERMS.source, source_uri)) 

        if article.infobox:
            raw.add((article_uri, COY.hasRawHtml, Literal(str(article.infobox), datatype=XSD.string)))
        
        place_uri = None
        if article.location_flag or is_topic_article:
            place_uri = self.__add_place(base, article)
            base.add((place_uri, GN.wikipediaArticle, article_uri))

            if article.coordinates:
                self.__addCoordinates(base, place_uri, article.coordinates)
            if article.infobox_coordinates:
                self.__addCoordinates(base, place_uri, article.infobox_coordinates)

        # add wikidata entity stuff
        if article.wikidata_entity:
            wd_entity_uri = URIRef(article.wikidata_entity)
            if len(article.wikidata_wkts) >= 1:
                for osm_element in article.wikidata_wkts:
                    self.__addOsmElement(wd_entity_uri, osm_element)
            
            # link new entities to the wikidata entity
            base.add((article_uri, OWL.sameAs, wd_entity_uri))
            if place_uri:
                base.add((place_uri, OWL.sameAs, wd_entity_uri))

            # add one-hop graph around wikidata entity to ohg graph
            ohg += article.wikidata_one_hop_graph
        
        # add labels of classes which entity is instance of (classes are URIs of wd:entity in 1hop graph)
        for entityId, label in article.classes_with_labels.items():
            wd_class_entity_uri = URIRef(WD[entityId])
            ohg.add((wd_class_entity_uri, RDFS.label, Literal(str(label), datatype=XSD.string)))

            # delete old triple in dataset endpoint
            if self.args.delete_old_entities:
                self.gck.delete_label_triples(wd_class_entity_uri)
        
        # add doc infos
        if article.date_published:
            base.add((article_uri, SCHEMA.datePublished, Literal(str(article.date_published), datatype=XSD.dateTime)))
        if article.date_modified:
            base.add((article_uri, SCHEMA.dateModified, Literal(str(article.date_modified), datatype=XSD.dateTime)))
        if article.name:
            base.add((article_uri, SCHEMA.name, Literal(str(article.name), datatype=XSD.string)))
        if article.headline:
            base.add((article_uri, SCHEMA.headline, Literal(str(article.headline), datatype=XSD.string)))
        
            
        # add OSM elements of links texts from infoboxes "Location" values to the article
        loc_rows = [row for row in article.infobox_rows.values() if isinstance(row, InfoboxRowLocation)]
        for row in loc_rows:
            for l in row.valueLinks:
                self.__addOsmElement(article_uri, row.valueLinks_wkts[l])
            
        # delete old triples in dataset endpoint
        if self.args.delete_old_entities:
            self.gck.delete_article_and_location_triples(article_uri)

        return article_uri, place_uri


    def __add_isodatetime_from_date(self, graph:Graph, target_uri:URIRef, date:datetime.date):
        isodatetime = datetime.datetime(date.year, date.month, date.day)
        graph.add((target_uri, COY.hasMentionDate, Literal(isodatetime, datatype=XSD.dateTime)))

    
    def storeEvent(self, event: Event):
        base = self.graphs["base"]
        osm = self.graphs["osm"]
        raw = self.graphs["raw"]

        # add all existing articles
        all_articles = event.get_linked_articles()
        
        wd_location_article_URIs = [
            a.wikidata_entity for a in all_articles 
            if a.wikidata_entity and a.location_flag == True
        ]
        wd_loc_article_URIs4counting_leafs = set(wd_location_article_URIs)
        
        # filters for a specific event for generating an example sample ("2021–2022 Boulder County fires")
        if self.args.sample_mode and event.date != datetime.datetime(2022,1,1) and event.eventIndex != 1:
            return
        
        # URIs
        event_uri = self.__get_event_uri(event)
        context_uri = self.__get_context_uri(event)

        ## Event triples
        base.add((event_uri, RDF.type, COY.NewsSummary))
        base.add((event_uri, RDF.type, COY.WikiNews))
        base.add((event_uri, RDF.type, COY.Event))

        text_literal = Literal(str(event.text), datatype=XSD.string)
        base.add((event_uri, RDFS.label, text_literal))
        
        base.add((event_uri, COY.isIdentifiedBy, context_uri))

        if event.category:
            base.add((event_uri, COY.hasTag, Literal(str(event.category), datatype=XSD.string)))
        
        self.__add_isodatetime_from_date(base, event_uri, event.date)

        raw.add((event_uri, COY.hasRawHtml, Literal(str(event.raw), datatype=XSD.string)))

        # connect with topic
        for t in event.parentTopics:
            parent_event = self.__get_event_uri(t)
            base.add((event_uri, COY.isOccuringDuring, parent_event))

        # wikidata type
        for entityId, label in event.eventTypes.items():
            class_uri = URIRef(WD[entityId])
            base.add((event_uri, COY.hasWikidataEventType, class_uri))
            base.add((class_uri, RDFS.label, Literal(str(label), datatype=XSD.string)))


        ## Context node triples
        base.add((context_uri, RDF.type, NIF.Context))
        base.add((context_uri, RDFS.label, text_literal))

        # string
        base.add((context_uri, NIF.isString, Literal(str(event.text), datatype=XSD.string)))
        base.add((context_uri, NIF.beginIndex, Literal(0, datatype=XSD.nonNegativeInteger)))
        base.add((context_uri, NIF.endIndex, Literal(len(event.text), datatype=XSD.nonNegativeInteger)))

        # source (https://en.wikipedia.org/wiki/Portal:Current_events/...)
        source_uri = URIRef(event.sourceUrl)
        base.add((context_uri, NIF.sourceUrl, source_uri)) 
        base.add((source_uri, RDF.type, FOAF.Document))

        # the news sources from behind the event summary
        for l in event.sourceLinks:
            source_link_uri = URIRef(l.href)

            base.add((context_uri, DCTERMS.source, source_link_uri))
            base.add((source_link_uri, RDF.type, COY.News))
            base.add((source_link_uri, RDFS.label, Literal(str(l.text), datatype=XSD.string)))

            # delete old triples in dataset endpoint
            if self.args.delete_old_entities:
                self.gck.delete_news_source_triples(source_link_uri)

        # the news sources refrenced through [xx] down below.
        for ref in event.sourceReferences:
            source_link_uri = URIRef(ref.url)

            base.add((context_uri, DCTERMS.source, source_link_uri))
            base.add((source_link_uri, RDF.type, COY.News))
            base.add((source_link_uri, RDFS.label, Literal(str(ref.anchor_text), datatype=XSD.string)))

            # delete old triples in dataset endpoint
            if self.args.delete_old_entities:
                self.gck.delete_news_source_triples(source_link_uri)

        # sentences
        lastSentenceUri = None
        for i, sentence in enumerate(event.sentences):
            sentence_uri = self.__get_sentence_uri(context_uri, i)

            base.add((sentence_uri, RDF.type, NIF.Sentence))
            base.add((sentence_uri, RDFS.label, Literal(str(sentence.text), datatype=XSD.string)))

            base.add((sentence_uri, NIF.referenceContext, context_uri))
            base.add((context_uri, NIF.subString, sentence_uri))
            base.add((sentence_uri, NIF.anchorOf, Literal(str(sentence.text), datatype=XSD.string)))
            base.add((sentence_uri, NIF.beginIndex, Literal(sentence.start, datatype=XSD.nonNegativeInteger)))
            base.add((sentence_uri, NIF.endIndex, Literal(sentence.end, datatype=XSD.nonNegativeInteger)))
            if(lastSentenceUri != None):
                base.add((sentence_uri, NIF.previousSentence, lastSentenceUri))
                base.add((lastSentenceUri, NIF.nextSentence, sentence_uri))

            # links per sentence as nif:Phrase
            for j, link in enumerate(sentence.links):
                article = link.article

                # link
                link_uri = self.__get_phrase_uri(sentence_uri, j)
                base.add((link_uri, RDF.type, NIF.Phrase))
                base.add((link_uri, RDFS.label, Literal(str(link.text), datatype=XSD.string)))

                base.add((link_uri, NIF.referenceContext, sentence_uri))
                base.add((sentence_uri, NIF.subString, link_uri))
                base.add((link_uri, NIF.anchorOf, Literal(str(link.text), datatype=XSD.string)))
                base.add((link_uri, NIF.beginIndex, Literal(link.startPos, datatype=XSD.nonNegativeInteger)))
                base.add((link_uri, NIF.endIndex, Literal(link.endPos, datatype=XSD.nonNegativeInteger)))
                
                # article
                if article:
                    article_uri, _ = self.__add_article_triples(article)
                    base.add((link_uri, GN.wikipediaArticle, article_uri))

                    # optimize searching for articles by wikidata entity
                    wd_entity2Article = {a.wikidata_entity:a for a in all_articles if a and a.wikidata_entity}

                    # link wikidata entities with parent locations in this sentence (eg NY with USA)
                    for parent_wd_entity in article.parent_locations_and_relation:
                        # dont link reflexive (eg USA links USA as its country)
                        if parent_wd_entity in wd_location_article_URIs and \
                                article.wikidata_entity != parent_wd_entity:
                            parent_loc_article = wd_entity2Article[parent_wd_entity]
                            parent_loc_place_uri = self.__get_place_uri(parent_loc_article)
                            place_uri = self.__get_place_uri(article)
                            base.add((place_uri, COY.isLocatedIn, parent_loc_place_uri))

                            if parent_wd_entity in wd_loc_article_URIs4counting_leafs:
                                wd_loc_article_URIs4counting_leafs.remove(parent_wd_entity)
            lastSentenceUri = sentence_uri
        if len(wd_loc_article_URIs4counting_leafs) > 1:
            self.analytics.numEventsWithMoreThanOneLeafLocation += 1
        
        # delete old triples in dataset endpoint
        if self.args.delete_old_entities:
            self.gck.delete_newssummary_triples(event_uri)
        
    
    def storeTopic(self, topic: Topic):
        base = self.graphs["base"]
        osm = self.graphs["osm"]
        raw = self.graphs["raw"]

        # filters for a specific topics for generating an example sample
        if self.args.sample_mode and topic.date != datetime.datetime(2022,1,1) and topic.index != 0:
            return
        
        ## Event triples
        event_uri = self.__get_event_uri(topic)

        base.add((event_uri, RDF.type, COY.TextTopic))
        base.add((event_uri, RDF.type, COY.WikiNews))
        base.add((event_uri, RDF.type, COY.Event))

        base.add((event_uri, RDFS.label, Literal(str(topic.text), datatype=XSD.string)))
        
        # store date of usage of this topic
        self.__add_isodatetime_from_date(base, event_uri, topic.date)

        # store raw html element of this topic
        raw.add((event_uri, COY.hasRawHtml, Literal(str(topic.raw), datatype=XSD.string)))

        # connect to parent topics
        if topic.parentTopics:
            for pt in topic.parentTopics:
                parent_e5 = self.__get_event_uri(pt)
                base.add((event_uri, COY.isOccuringDuring, parent_e5))
        
        if topic.article:
            base.add((event_uri, RDF.type, COY.ArticleTopic))

            # add article
            article_uri, place_uri = self.__add_article_triples(topic.article, is_topic_article=True)
            base.add((event_uri, GN.wikipediaArticle, article_uri))

            # connect place with event
            if place_uri:
                base.add((event_uri, COY.hasLocation, place_uri))
            
            # add timespan
            timespan_uri = self.__add_timespan(base, topic.article)
            if timespan_uri:
                base.add((event_uri, COY.hasTimespan, timespan_uri))
        
        # delete old triples in dataset endpoint
        if self.args.delete_old_entities:
            self.gck.delete_topic_triples(event_uri)


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
            filename = file_prefix + "_" + graph_name + ".jsonld"
            if not exists(self.outputFolder / filename):
                return False
        return True
        
    