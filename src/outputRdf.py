# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import hashlib
import os.path
import re

from rdflib import (FOAF, OWL, RDF, RDFS, XSD, BNode, Graph, Literal,
                    Namespace, URIRef)

from src.objects.newsEvent import NewsEvent
from src.objects.topic import Topic

n = Namespace("http://data.coypu.org/")
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
            uri =  n[str(hashlib.md5(t.text.encode('utf-8')).hexdigest())]
        return uri
    
    def __getEventURIIndexBased(self, e):
        prefix = e.sourceUrl + "#"
        suffix = str(e.day) + "_" + str(e.eventIndex)
        uri = Namespace(prefix)[suffix]
        return uri

    def __addParentTopics(self, sub, topics, graph):
        for t in topics:
            link = self.__getTopicURI(t)
            graph.add((sub, n.hasParentTopic, link))
    
    def __addCoordinates(self, graph, parentUri, coordinates: list[float]):

        puri = BNode()
        graph.add((parentUri, n.coordinates, puri))
        graph.add((puri, RDF.type, WGS.Point))
        graph.add((puri, WGS.lat, Literal(str(coordinates[0]), datatype=XSD.float)))
        graph.add((puri, WGS.long, Literal(str(coordinates[1]), datatype=XSD.float)))
    
    def __addOSMElement(self, graph, target, relation, osmElement):
        osmuri = BNode()
        graph.add((target, relation, osmuri))
        graph.add((osmuri, RDF.type, n.OSMElement))
        if osmElement.osmType:
            graph.add((osmuri, n.osmType, Literal(str(osmElement.osmType), datatype=XSD.string)))
        if osmElement.osmId:
            graph.add((osmuri, n.osmId, Literal(str(osmElement.osmId), datatype=XSD.integer)))
        if osmElement.wkt:
            graph.add((osmuri, n.osmWkt, Literal(str(osmElement.wkt), datatype=GEO.wktLiteral)))
    
    def __addLinkTriples(self, graph, target, predicate, link) -> BNode:
        luri = BNode()
        graph.add((target, predicate, luri))
        graph.add((luri, RDF.type, n.Link))
        graph.add((luri, NIF.referenceContext, target))
        graph.add((luri, n.references, URIRef(str(link.href))))
        graph.add((luri, n.text, Literal(str(link.text), datatype=XSD.string)))
        graph.add((luri, NIF.beginIndex, Literal(link.startPos, datatype=XSD.nonNegativeInteger)))
        graph.add((luri, NIF.endIndex, Literal(link.endPos, datatype=XSD.nonNegativeInteger)))
        return luri
    
    def __addArticleTriples(self, graphs, target, article):
        base = graphs["base"]
        osm = graphs["osm"]
        raw = graphs["raw"]
        ohg = graphs["ohg"]
    
        base.add((target, RDF.type, n.Article))
        if article.locFlag:
            base.add((target, RDF.type, n.Location))
        if article.infobox:
            raw.add((target, n.infobox, Literal(str(article.infobox), datatype=XSD.string)))
        if article.coords:
            self.__addCoordinates(base, target, article.coords)
        if len(article.wikidataWkts) >= 1:
            for wkt in article.wikidataWkts:
                self.__addOSMElement(osm, target, n.osmElementFromWikidata, wkt)
        for row in article.ibcontent.values():
            ruri = BNode()
            base.add((target, n.infoboxRow, ruri))
            base.add((ruri, RDF.type, n.InfoboxRow))
            base.add((ruri, RDFS.label, Literal(str(row.label), datatype=XSD.string)))
            base.add((ruri, n.value, Literal(str(row.value), datatype=XSD.string)))
            for i, l in enumerate(row.valueLinks):
                luri = self.__addLinkTriples(base, ruri, n.valueHasLink, l)
                if row.label == "Location":
                    self.__addOSMElement(osm, luri, n.osmElementFromLinkText, article.infoboxWkts[i][1])
            # dates
            if row.label in article.dates:
                date = article.dates[row.label]
                base.add((ruri, n.parsedDate, Literal(str(date["date"].isoformat()), datatype=XSD.dateTime)))
                if "until" in date:
                    base.add((ruri, n.parsedEndDate, Literal(str(date["until"].isoformat()), datatype=XSD.dateTime)))
                elif "ongoing" in date:
                    base.add((ruri, n.parsedDateOngoing, Literal("true", datatype=XSD.boolean)))
                if "tz" in date:
                    base.add((ruri, n.parsedDateTimezone, Literal(str(date["tz"]), datatype=XSD.string)))
            # times
            if row.label in article.times:
                time = article.times[row.label]
                base.add((ruri, n.parsedTime, Literal(str(time["start"]), datatype=XSD.time)))
                if "end" in time:
                    base.add((ruri, n.parsedEndTime, Literal(str(time["end"]), datatype=XSD.time)))
                if "tz" in time:
                    base.add((ruri, n.parsedTimezone, Literal(str(time["tz"]), datatype=XSD.string)))
        # microformats
        if "dtstart" in article.microformats:
            base.add((target, n.microformatsDtstart, Literal(str(article.microformats["dtstart"]), datatype=XSD.string)))
        if "dtend" in article.microformats:
            base.add((target, n.microformatsDtend, Literal(str(article.microformats["dtend"]), datatype=XSD.string)))

        base.add((target, OWL.sameAs, URIRef(article.wikidataEntity)))
        ohg += article.wikidata_one_hop_graph
        
        # add labels of classes which entity is instance of (classes are URIs of wd:entity in 1hop graph)
        for entityId, label in article.classes_with_labels.items():
            ohg.add((URIRef(WD[entityId]), RDFS.label, Literal(str(label), datatype=XSD.string)))
        
        # add doc infos
        if article.datePublished:
            base.add((target, n.datePublished, Literal(str(article.datePublished), datatype=XSD.dateTime)))
        if article.dateModified:
            base.add((target, n.dateModified, Literal(str(article.dateModified), datatype=XSD.dateTime)))


    
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
        base.add((evuri, RDF.type, n.Event))
        base.add((evuri, RDF.type, NIF.Context))
        
        # save date
        base.add((evuri, n.day, Literal(event.day, datatype=XSD.nonNegativeInteger)))
        base.add((evuri, n.month, Literal(event.month, datatype=XSD.nonNegativeInteger)))
        base.add((evuri, n.year, Literal(event.year, datatype=XSD.nonNegativeInteger)))

        raw.add((evuri, n.raw, Literal(str(event.raw), datatype=XSD.string)))

        # string
        base.add((evuri, NIF.isString, Literal(str(event.text), datatype=XSD.string)))
        base.add((evuri, NIF.beginIndex, Literal(0, datatype=XSD.nonNegativeInteger)))
        base.add((evuri, NIF.endIndex, Literal(len(event.text), datatype=XSD.nonNegativeInteger)))

        # source (wikipedia/Portal...)
        sourceUri = URIRef(event.sourceUrl)
        base.add((evuri, NIF.sourceUrl, sourceUri)) 
        base.add((sourceUri, RDF.type, FOAF.Document))
        
        self.__addParentTopics(evuri, event.parentTopics, base)

        # wikidata type
        for entityId, label in event.eventTypes.items():
            cluri = BNode()
            base.add((evuri, n.eventType, cluri))
            base.add((cluri, n.eventTypeLabel, Literal(str(label), datatype=XSD.string)))
            base.add((cluri, n.eventTypeURI, URIRef(WD[entityId])))

        # the news sources
        for l in event.sourceLinks:
            sluri = BNode()
            base.add((evuri, n.hasSource, sluri))
            base.add((sluri, RDF.type, n.Source))
            hrefuri = URIRef(l.href)
            base.add((sluri, n.sourceLink, hrefuri))
            base.add((hrefuri, RDF.type, FOAF.Document))
            base.add((sluri, n.sourceLinkText, Literal(str(l.text), datatype=XSD.string)))

        # sentences
        lastSentenceUri = None
        sentences = event.sentences
        for i in range(len(sentences)):
            sentence = sentences[i]
            suri = URIRef(str(evuri) + "_" + str(i))
            base.add((suri, RDF.type, NIF.Sentence))
            base.add((suri, NIF.referenceContext, evuri))
            base.add((evuri, n.hasSentence, suri))
            base.add((suri, n.sentencePosition, Literal(i, datatype=XSD.nonNegativeInteger)))
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
                self.__addLinkTriples(base, suri, n.hasLink, link)
                
                # article
                if article:
                    auri = URIRef(link.href)
                    self.__addArticleTriples(graphs, auri, article)

                    # link wikidata entities with parent locations (eg NY with USA)
                    for parent in article.parent_locations_and_relation:
                        # dont link reflexive (eg USA links USA as its country)
                        
                        if parent in wdLocArticleURIs and article.wikidataEntity != parent:
                            pLocBNode = BNode()
                            base.add((URIRef(article.wikidataEntity), n.hasParentLocation, pLocBNode))
                            base.add((pLocBNode, n.parentLocation, URIRef(parent)))
                            for prop in article.parent_locations_and_relation[parent]:
                                base.add((pLocBNode, n.originalProperty, URIRef(prop)))

                            if parent in wdLocArticleURIs4countingLeafs:
                                wdLocArticleURIs4countingLeafs.remove(parent)
            lastSentenceUri = suri
        if len(wdLocArticleURIs4countingLeafs) > 1:
            self.analytics.numEventsWithMoreThanOneLeafLocation += 1
        
    
    def storeTopic(self, topic: Topic, graphs: dict[str,Graph]):
        base = graphs["base"]
        osm = graphs["osm"]
        raw = graphs["raw"]
        turi = self.__getTopicURI(topic)
        
        # filters for a specific topics for generating an example sample
        if self.args.sample_mode and str(turi) not in ["https://en.wikipedia.org/wiki/2021%E2%80%932022_Boulder_County_fires", 
                "http://data.coypu.org/Disastersandaccidents"]:
            return
        
        base.add((turi, RDF.type, n.Topic))
        base.add((turi, RDFS.label, Literal(str(topic.text), datatype=XSD.string)))
        
        raw.add((turi, n.raw, Literal(str(topic.raw), datatype=XSD.string)))

        if topic.article:
           self.__addArticleTriples(graphs, turi, topic.article)
        if topic.parentTopics:
            for t in topic.parentTopics:
                self.__addParentTopics(turi, topic.parentTopics, base)
        
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
    