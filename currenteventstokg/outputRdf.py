# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import hashlib
from os.path import exists
from os import makedirs
import re

from rdflib import (FOAF, OWL, RDF, RDFS, XSD, BNode, Graph, Literal,
                    Namespace, URIRef)
from urllib.parse import quote_plus
from .objects.event import Event
from .objects.topic import Topic
from .objects.infoboxRow import *
from .objects.article import Article


# data under https://data.coypu.org/ENTITY-TYPE/DATA-SOURCE/ID
topics_ns = Namespace("https://data.coypu.org/topic/wikipedia-current-events/")
osm_element_ns = Namespace("https://data.coypu.org/osmelement/wikipedia-current-events/")

schema = Namespace("https://schema.coypu.org/global#")
NIF = Namespace("http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#")
SEM = Namespace("http://semanticweb.cs.vu.nl/2009/11/sem/")
WGS = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
WD = Namespace("http://www.wikidata.org/entity/")

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


    def __getTopicURI(self, t):
        link = t.link
        
        if link != None and re.match("https://en.wikipedia.org/wiki/", link):
            uri = URIRef(link)
        else:
            uri =  topics_ns[str(hashlib.md5(t.text.encode('utf-8')).hexdigest())]
        return uri

    def __getTopicURIIndexBased(self, t):
        prefix = t.sourceUrl + "#"
        suffix = str(t.date.day) + "_t" + str(t.index)
        uri = Namespace(prefix)[suffix]
        return uri

    
    def __getEventURIIndexBased(self, e):
        prefix = e.sourceUrl + "#"
        suffix = str(e.date.day) + "_e" + str(e.eventIndex)
        uri = Namespace(prefix)[suffix]
        return uri

    def __get_osm_uri(self, osmElement):
        suffix = str(osmElement.osmType) + "_" + str(osmElement.osmId)
        uri = osm_element_ns[suffix]
        return uri
    
    def __get_infobox_row_uri(self, infobox_row:InfoboxRow, article:Article):
        prefix = article.url + "#"
        url_encoded_label = quote_plus(infobox_row.label)
        suffix = f"ibrow_{url_encoded_label}"
        uri = Namespace(prefix)[suffix]
        return uri
    
    
    def __addCoordinates(self, graph, parentUri, coordinates: list[float]):
        puri = BNode()
        graph.add((parentUri, schema.hasCoordinates, puri))
        graph.add((puri, RDF.type, WGS.Point))
        graph.add((puri, WGS.lat, Literal(str(coordinates[0]), datatype=XSD.float)))
        graph.add((puri, WGS.long, Literal(str(coordinates[1]), datatype=XSD.float)))
    
    def __addOsmElement(self, graph, target, relation, osmElement):
        osmuri = self.__get_osm_uri(osmElement)
        if osmElement.osmType or osmElement.osmId or osmElement.wkt:
            graph.add((target, relation, osmuri))
            graph.add((osmuri, RDF.type, schema.OsmElement))
            if osmElement.osmType:
                graph.add((osmuri, schema.hasOsmType, Literal(str(osmElement.osmType), datatype=XSD.string)))
            if osmElement.osmId:
                graph.add((osmuri, schema.hasOsmId, Literal(str(osmElement.osmId), datatype=XSD.integer)))
            if osmElement.wkt:
                graph.add((osmuri, schema.hasOsmWkt, Literal(str(osmElement.wkt), datatype=GEO.wktLiteral)))
    
    def __addLinkTriples(self, graph, target, predicate, link) -> BNode:
        luri = BNode()
        graph.add((target, predicate, luri))
        graph.add((luri, RDF.type, schema.Link))
        graph.add((luri, NIF.referenceContext, target))
        hrefuri = URIRef(str(link.href))
        graph.add((hrefuri, RDF.type, FOAF.Document))
        graph.add((luri, schema.hasReference, hrefuri))
        graph.add((luri, schema.hasText, Literal(str(link.text), datatype=XSD.string)))
        graph.add((luri, NIF.beginIndex, Literal(link.startPos, datatype=XSD.nonNegativeInteger)))
        graph.add((luri, NIF.endIndex, Literal(link.endPos, datatype=XSD.nonNegativeInteger)))
        return luri
    
    def __addArticleTriples(self, target, article):
        base = self.graphs["base"]
        osm = self.graphs["osm"]
        raw = self.graphs["raw"]
        ohg = self.graphs["ohg"]
    
        base.add((target, RDF.type, schema.WikipediaArticle))
        if article.location_flag:
            base.add((target, RDF.type, schema.Location))
        if article.infobox:
            raw.add((target, schema.hasInfobox, Literal(str(article.infobox), datatype=XSD.string)))
        if article.coordinates:
            self.__addCoordinates(base, target, article.coordinates)
        if len(article.wikidata_wkts) >= 1:
            for wkt in article.wikidata_wkts:
                self.__addOsmElement(osm, target, schema.hasOsmElementFromWikidata, wkt)
        for row in article.infobox_rows.values():
            ruri = self.__get_infobox_row_uri(row, article)
            print(ruri)
            base.add((target, schema.hasInfoboxRow, ruri))

            # add base values of InfoboxRow
            base.add((ruri, RDFS.label, Literal(str(row.label), datatype=XSD.string)))
            base.add((ruri, schema.hasValue, Literal(str(row.value), datatype=XSD.string)))
            for i, l in enumerate(row.valueLinks):
                luri = self.__addLinkTriples(base, ruri, schema.hasLinkAsValue, l)
                # add OSM elements to location links
                if isinstance(row, InfoboxRowLocation):
                    self.__addOsmElement(osm, luri, schema.hasOsmElementFromText, row.valueLinks_wkts[l])
            
            # add specific values
            if isinstance(row, InfoboxRowLocation):
                base.add((ruri, RDF.type, schema.InfoboxRowLocation))
                for iri in row.falcon2_wikidata_entities:
                    base.add((ruri, schema.hasValueEntityFromFalcon2, URIRef(iri)))
            
            elif isinstance(row, InfoboxRowTime):
                base.add((ruri, RDF.type, schema.InfoboxRowTime))
                base.add((ruri, schema.hasTime, Literal(row.time, datatype=XSD.time)))
                if row.endtime:
                    base.add((ruri, schema.hasEndTime, Literal(row.endtime, datatype=XSD.time)))
                if row.timezone:
                    base.add((ruri, schema.hasTimezone, Literal(row.timezone, datatype=XSD.string)))
            
            elif isinstance(row, InfoboxRowDate):
                base.add((ruri, RDF.type, schema.InfoboxRowDate))
                base.add((ruri, schema.hasDate, Literal(row.date.isoformat(), datatype=XSD.dateTime)))
                if row.enddate:
                    base.add((ruri, schema.hasEndDate, Literal(row.enddate.isoformat(), datatype=XSD.dateTime)))
                elif row.ongoing:
                    base.add((ruri, schema.hasDateOngoing, Literal("true", datatype=XSD.boolean)))
                if row.timezone:
                    base.add((ruri, schema.hasTimezone, Literal(row.timezone, datatype=XSD.string)))
            
            else:
                base.add((ruri, RDF.type, schema.InfoboxRow))                

        # microformats
        if "dtstart" in article.microformats:
            base.add((target, schema.hasMicroformatsDtstart, Literal(str(article.microformats["dtstart"]), datatype=XSD.string)))
        if "dtend" in article.microformats:
            base.add((target, schema.hasMicroformatsDtend, Literal(str(article.microformats["dtend"]), datatype=XSD.string)))

        base.add((target, OWL.sameAs, URIRef(article.wikidata_entity)))
        ohg += article.wikidata_one_hop_graph
        
        # add labels of classes which entity is instance of (classes are URIs of wd:entity in 1hop graph)
        for entityId, label in article.classes_with_labels.items():
            ohg.add((URIRef(WD[entityId]), RDFS.label, Literal(str(label), datatype=XSD.string)))
        
        # add doc infos
        if article.date_published:
            base.add((target, schema.hasDatePublished, Literal(str(article.date_published), datatype=XSD.dateTime)))
        if article.date_modified:
            base.add((target, schema.hasDateModified, Literal(str(article.date_modified), datatype=XSD.dateTime)))
        if article.name:
            base.add((target, schema.hasName, Literal(str(article.name), datatype=XSD.string)))
        if article.headline:
            base.add((target, schema.hasHeadline, Literal(str(article.headline), datatype=XSD.string)))


    
    def storeEvent(self, event: Event):
        base = self.graphs["base"]
        osm = self.graphs["osm"]
        raw = self.graphs["raw"]
        evuri = self.__getEventURIIndexBased(event)

        all_articles = []
        for s in event.sentences:
            all_articles.extend(s.articles)
        
        wdLocArticleURIs = [a.wikidata_entity for a in all_articles if a != None and a.location_flag == True]
        wdLocArticleURIs4countingLeafs = set(wdLocArticleURIs)
        
        # filters for a specific event for generating an example sample
        if self.args.sample_mode and event.parentTopics[0].text != "2021–2022 Boulder County fires":
            return

        # type
        base.add((evuri, RDF.type, schema.Event))
        base.add((evuri, RDF.type, NIF.Context))
        
        # save date
        base.add((evuri, schema.hasDate, Literal(event.date.isoformat(), datatype=XSD.date)))

        raw.add((evuri, schema.hasRaw, Literal(str(event.raw), datatype=XSD.string)))

        # string
        base.add((evuri, NIF.isString, Literal(str(event.text), datatype=XSD.string)))
        base.add((evuri, NIF.beginIndex, Literal(0, datatype=XSD.nonNegativeInteger)))
        base.add((evuri, NIF.endIndex, Literal(len(event.text), datatype=XSD.nonNegativeInteger)))

        # source (wikipedia/Portal...)
        sourceUri = URIRef(event.sourceUrl)
        base.add((evuri, NIF.sourceUrl, sourceUri)) 
        base.add((sourceUri, RDF.type, FOAF.Document))
        
        # connect with topic
        for t in event.parentTopics:
            parent = self.__getTopicURIIndexBased(t)
            base.add((evuri, schema.hasParentTopic, parent))

        # wikidata type
        for entityId, label in event.eventTypes.items():
            cluri = URIRef(WD[entityId])
            base.add((evuri, schema.hasEventType, cluri))
            base.add((cluri, RDFS.label, Literal(str(label), datatype=XSD.string)))

        # the news sources
        for l in event.sourceLinks:
            self.__addLinkTriples(base, evuri, schema.hasSource, l)

        # sentences
        lastSentenceUri = None
        sentences = event.sentences
        for i in range(len(sentences)):
            sentence = sentences[i]
            suri = URIRef(str(evuri) + "_" + str(i))
            base.add((suri, RDF.type, NIF.Sentence))
            base.add((suri, NIF.referenceContext, evuri))
            base.add((evuri, schema.hasSentence, suri))
            base.add((suri, schema.hasSentencePosition, Literal(i, datatype=XSD.nonNegativeInteger)))
            base.add((suri, NIF.anchorOf, Literal(str(sentence.text), datatype=XSD.string)))
            base.add((suri, NIF.beginIndex, Literal(sentence.start, datatype=XSD.nonNegativeInteger)))
            base.add((suri, NIF.endIndex, Literal(sentence.end, datatype=XSD.nonNegativeInteger)))
            if(lastSentenceUri != None):
                base.add((suri, NIF.previousSentence, lastSentenceUri))
                base.add((lastSentenceUri, NIF.nextSentence, suri))

            # links per sentence
            links = sentence.links
            articles = sentence.articles
            for j in range(len(links)):
                article = articles[j]
                link = links[j]

                # link
                self.__addLinkTriples(base, suri, schema.hasLink, link)
                
                # article
                if article:
                    auri = URIRef(link.href)
                    self.__addArticleTriples(auri, article)

                    # link wikidata entities with parent locations (eg NY with USA)
                    for parent in article.parent_locations_and_relation:
                        # dont link reflexive (eg USA links USA as its country)
                        
                        if parent in wdLocArticleURIs and article.wikidata_entity != parent:
                            pLocBNode = BNode()
                            base.add((URIRef(article.wikidata_entity), schema.hasParentLocation, pLocBNode))
                            base.add((pLocBNode, schema.parentLocation, URIRef(parent)))
                            for prop in article.parent_locations_and_relation[parent]:
                                base.add((pLocBNode, schema.hasUsedPropertyOriginally, URIRef(prop)))

                            if parent in wdLocArticleURIs4countingLeafs:
                                wdLocArticleURIs4countingLeafs.remove(parent)
            lastSentenceUri = suri
        if len(wdLocArticleURIs4countingLeafs) > 1:
            self.analytics.numEventsWithMoreThanOneLeafLocation += 1
        
    
    def storeTopic(self, topic: Topic):
        base = self.graphs["base"]
        osm = self.graphs["osm"]
        raw = self.graphs["raw"]
        turi = self.__getTopicURIIndexBased(topic)
        
        # filters for a specific topics for generating an example sample
        if self.args.sample_mode and str(turi) not in ["https://en.wikipedia.org/wiki/2021%E2%80%932022_Boulder_County_fires", 
                "http://data.coypu.org/Disastersandaccidents"]:
            return
        
        base.add((turi, RDF.type, schema.Topic))
        base.add((turi, RDFS.label, Literal(str(topic.text), datatype=XSD.string)))
        
        # store raw html topic link
        raw.add((turi, schema.hasRaw, Literal(str(topic.raw), datatype=XSD.string)))

        # store date of usage of this topic
        base.add((turi, schema.hasUsageDate, Literal(topic.date.isoformat(), datatype=XSD.date)))
        
        # store article behind link
        if topic.article:
            auri = URIRef(topic.article.url)
            base.add((turi, schema.hasArticle, auri))
            self.__addArticleTriples(auri, topic.article)
        
        # connect to parent topics
        if topic.parentTopics:
            for t in topic.parentTopics:
                parent = self.__getTopicURIIndexBased(t)
                base.add((turi, schema.hasParentTopic, parent))
        

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
        
    