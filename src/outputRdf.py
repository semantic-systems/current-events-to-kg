# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import hashlib
import os.path
import re

from rdflib import (FOAF, OWL, RDF, RDFS, XSD, BNode, Graph, Literal,
                    Namespace, URIRef)

from src.objects.newsEvent import NewsEvent
from src.objects.topic import Topic
from src.objects.infoboxRow import InfoboxRowLocation


# data under https://data.coypu.org/ENTITY-TYPE/DATA-SOURCE/ID
topics = Namespace("https://data.coypu.org/topic/wikipedia-current-events/")
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
        os.makedirs(self.outputFolder, exist_ok=True)


    def __getTopicURI(self, t):
        link = t.link
        
        if link != None and re.match("https://en.wikipedia.org/wiki/", link):
            uri = URIRef(link)
        else:
            uri =  topics[str(hashlib.md5(t.text.encode('utf-8')).hexdigest())]
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
    
    
    def __addCoordinates(self, graph, parentUri, coordinates: list[float]):
        puri = BNode()
        graph.add((parentUri, schema.hasCoordinates, puri))
        graph.add((puri, RDF.type, WGS.Point))
        graph.add((puri, WGS.lat, Literal(str(coordinates[0]), datatype=XSD.float)))
        graph.add((puri, WGS.long, Literal(str(coordinates[1]), datatype=XSD.float)))
    
    def __addOsmElement(self, graph, target, relation, osmElement):
        osmuri = BNode()
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
    
    def __addArticleTriples(self, graphs, target, article):
        base = graphs["base"]
        osm = graphs["osm"]
        raw = graphs["raw"]
        ohg = graphs["ohg"]
    
        base.add((target, RDF.type, schema.WikipediaArticle))
        if article.locFlag:
            base.add((target, RDF.type, schema.Location))
        if article.infobox:
            raw.add((target, schema.hasInfobox, Literal(str(article.infobox), datatype=XSD.string)))
        if article.coords:
            self.__addCoordinates(base, target, article.coords)
        if len(article.wikidataWkts) >= 1:
            for wkt in article.wikidataWkts:
                self.__addOsmElement(osm, target, schema.hasOsmElementFromWikidata, wkt)
        for row in article.ibcontent.values():
            ruri = BNode()
            base.add((target, schema.hasInfoboxRow, ruri))
            base.add((ruri, RDF.type, schema.InfoboxRow))
            base.add((ruri, RDFS.label, Literal(str(row.label), datatype=XSD.string)))
            base.add((ruri, schema.hasValue, Literal(str(row.value), datatype=XSD.string)))
            for i, l in enumerate(row.valueLinks):
                luri = self.__addLinkTriples(base, ruri, schema.hasLinkAsValue, l)
                if row.label == "Location":
                    self.__addOsmElement(osm, luri, schema.hasOsmElementFromText, article.infoboxWkts[i][1])
            # dates
            if row.label in article.dates:
                date = article.dates[row.label]
                base.add((ruri, schema.hasParsedDate, Literal(str(date["date"].isoformat()), datatype=XSD.dateTime)))
                if "until" in date:
                    base.add((ruri, schema.hasParsedEndDate, Literal(str(date["until"].isoformat()), datatype=XSD.dateTime)))
                elif "ongoing" in date:
                    base.add((ruri, schema.hasParsedDateOngoing, Literal("true", datatype=XSD.boolean)))
                if "tz" in date:
                    base.add((ruri, schema.hasParsedDateTimezone, Literal(str(date["tz"]), datatype=XSD.string)))
            # times
            if row.label in article.times:
                time = article.times[row.label]
                base.add((ruri, schema.hasParsedTime, Literal(str(time["start"]), datatype=XSD.time)))
                if "end" in time:
                    base.add((ruri, schema.hasParsedEndTime, Literal(str(time["end"]), datatype=XSD.time)))
                if "tz" in time:
                    base.add((ruri, schema.hasParsedTimezone, Literal(str(time["tz"]), datatype=XSD.string)))
            # falcon2 entities
            if isinstance(row, InfoboxRowLocation):
                for iri in row.falcon2_wikidata_entities:
                    base.add((ruri, schema.hasValueEntityFromFalcon2, URIRef(iri)))

        # microformats
        if "dtstart" in article.microformats:
            base.add((target, schema.hasMicroformatsDtstart, Literal(str(article.microformats["dtstart"]), datatype=XSD.string)))
        if "dtend" in article.microformats:
            base.add((target, schema.hasMicroformatsDtend, Literal(str(article.microformats["dtend"]), datatype=XSD.string)))

        base.add((target, OWL.sameAs, URIRef(article.wikidataEntity)))
        ohg += article.wikidata_one_hop_graph
        
        # add labels of classes which entity is instance of (classes are URIs of wd:entity in 1hop graph)
        for entityId, label in article.classes_with_labels.items():
            ohg.add((URIRef(WD[entityId]), RDFS.label, Literal(str(label), datatype=XSD.string)))
        
        # add doc infos
        if article.datePublished:
            base.add((target, schema.hasDatePublished, Literal(str(article.datePublished), datatype=XSD.dateTime)))
        if article.dateModified:
            base.add((target, schema.hasDateModified, Literal(str(article.dateModified), datatype=XSD.dateTime)))
        if article.name:
            base.add((target, schema.hasName, Literal(str(article.name), datatype=XSD.string)))
        if article.headline:
            base.add((target, schema.hasHeadline, Literal(str(article.headline), datatype=XSD.string)))


    
    def storeEvent(self, event: NewsEvent, graphs: dict[str,Graph]):
        base = graphs["base"]
        osm = graphs["osm"]
        raw = graphs["raw"]
        evuri = self.__getEventURIIndexBased(event)
        wdLocArticleURIs = [a.wikidataEntity for a in event.articles if a != None and a.locFlag == True]
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
            cluri = BNode()
            base.add((evuri, schema.hasEventType, cluri))
            base.add((cluri, schema.hasEventTypeLabel, Literal(str(label), datatype=XSD.string)))
            base.add((cluri, schema.hasEventTypeURI, URIRef(WD[entityId])))

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
                    self.__addArticleTriples(graphs, auri, article)

                    # link wikidata entities with parent locations (eg NY with USA)
                    for parent in article.parent_locations_and_relation:
                        # dont link reflexive (eg USA links USA as its country)
                        
                        if parent in wdLocArticleURIs and article.wikidataEntity != parent:
                            pLocBNode = BNode()
                            base.add((URIRef(article.wikidataEntity), schema.hasParentLocation, pLocBNode))
                            base.add((pLocBNode, schema.parentLocation, URIRef(parent)))
                            for prop in article.parent_locations_and_relation[parent]:
                                base.add((pLocBNode, schema.hasUsedPropertyOriginally, URIRef(prop)))

                            if parent in wdLocArticleURIs4countingLeafs:
                                wdLocArticleURIs4countingLeafs.remove(parent)
            lastSentenceUri = suri
        if len(wdLocArticleURIs4countingLeafs) > 1:
            self.analytics.numEventsWithMoreThanOneLeafLocation += 1
        
    
    def storeTopic(self, topic: Topic, graphs: dict[str,Graph]):
        base = graphs["base"]
        osm = graphs["osm"]
        raw = graphs["raw"]
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
            auri = URIRef(topic.article.link)
            base.add((turi, schema.hasArticle, auri))
            self.__addArticleTriples(graphs, auri, topic.article)
        
        # connect to parent topics
        if topic.parentTopics:
            for t in topic.parentTopics:
                parent = self.__getTopicURIIndexBased(t)
                base.add((turi, schema.hasParentTopic, parent))
        
    def loadGraph(self, fileName):
        path = self.outputFolder / fileName
        if(os.path.exists(path)):
            g = Graph()
            with open(path, "r", encoding="utf-8") as f:
                g.parse(file=f)
            return g
        return

    def saveGraph(self, graph, outputFileName="dataset.jsonld"):
        s = graph.serialize(format="json-ld")
        
        with open(self.outputFolder / outputFileName, mode='w', encoding="utf-8") as f:
            f.write(s)
    