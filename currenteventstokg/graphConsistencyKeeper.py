# Copyright: (c) 2023, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from string import Template
from typing import List, Optional

from rdflib import URIRef
from SPARQLWrapper import DIGEST, JSON, POST, QueryResult, SPARQLWrapper

class GraphConsistencyKeeper:
    def __init__(self, sparql_endpoint:str, subgraph:str, sparql_endpoint_user:Optional[str], sparql_endpoint_pw:Optional[str]):
        self.subgraph = subgraph

        self.sparql = SPARQLWrapper(sparql_endpoint)
        self.sparql.setMethod(POST)
        self.sparql.setReturnFormat(JSON)

        if sparql_endpoint_user and sparql_endpoint_pw:
            self.sparql.setHTTPAuth(DIGEST)
            self.sparql.setCredentials(sparql_endpoint_user, sparql_endpoint_pw)

        elif sparql_endpoint_user or sparql_endpoint_pw:
            # only one is defined
            raise Exception("Dataset SPAQRL endpoint credentials incomplete.")
    

    def __query(self, q:str):
        self.sparql.setQuery(q)
        self.sparql.query()


    def __query_and_convert(self, q:str) -> QueryResult:
        self.sparql.setQuery(q)
        return self.sparql.queryAndConvert()


    def __query_associated_articles(self, uri:URIRef) -> List[URIRef]:
        q = Template("""
PREFIX gn: <https://www.geonames.org/ontology#>

${subgraph}
SELECT DISTINCT ?a WHERE {
    ${uri} gn:wikipediaArticle ?a.

}""").substitute(
            subgraph=f"WITH <{self.subgraph}>" if self.subgraph else "", 
            uri=uri.n3())
        
        res = self.__query_and_convert(q)

        binds = res["results"]["bindings"]
        article_uris = []
        for bind in binds:
            article_uri = URIRef(bind["a"]["value"])
            article_uris.append(article_uri)
        
        return article_uris

    
    def __query_mentioned_articles(self, newssummary_uri:URIRef) -> List[URIRef]:
        q = Template("""
PREFIX coy:<https://schema.coypu.org/global#>
PREFIX gn: <https://www.geonames.org/ontology#>
PREFIX nif: <http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#>


${subgraph}
SELECT DISTINCT ?a WHERE {
    ${uri} a coy:NewsSummary;
        coy:isIdentifiedBy ?c.
    
    ?c  a nif:Context;
        nif:subString/nif:subString/gn:wikipediaArticle ?a.

}""").substitute(
            subgraph=f"WITH <{self.subgraph}>" if self.subgraph else "", 
            uri=newssummary_uri.n3())
        
        res = self.__query_and_convert(q)

        binds = res["results"]["bindings"]
        article_uris = []
        for bind in binds:
            uri_str = bind["a"]["value"]
            article_uris.append(URIRef(uri_str))
        
        return article_uris


    def delete_article_and_location_triples(self, article_uri:URIRef):
        q = Template("""
PREFIX coy:<https://schema.coypu.org/global#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX gn: <https://www.geonames.org/ontology#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wgs: <http://www.w3.org/2003/01/geo/wgs84_pos#>
PREFIX schema: <https://schema.org/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX dcterms: <http://purl.org/dc/terms/>

$subgraph
DELETE {

    ${uri} a gn:WikipediaArticle;
        dcterms:source ?doc;
        rdfs:label ?l;
        coy:hasRawHtml ?html;
        schema:name ?name;
        schema:headline ?hl;
        schema:datePublished ?dp;
        schema:dateModified ?dm;
        owl:sameAs ?wd;
        coy:hasOsmElement ?osm.
    
    ?doc a foaf:Document.

    ?wd ?wd_prop ?wd_obj.

    ?loc a coy:Location;
        gn:wikipediaArticle ${uri};
        rdfs:label ?loc_label;
        owl:sameAs ?wd;
        coy:isIdentifiedBy ?loc_id;
        coy:isLocatedIn ?parent_loc;
        coy:hasLatitude ?lat;
        coy:hasLongitude ?long;
        coy:hasLocation ?point.

} WHERE {

    # Article entity
    ${uri} a gn:WikipediaArticle;
        dcterms:source ?doc;
        rdfs:label ?l.
        
    OPTIONAL{$uri coy:hasRawHtml ?html.}
    OPTIONAL{$uri coy:hasOsmElement ?osm. }
    OPTIONAL{$uri schema:name ?name.}
    OPTIONAL{$uri schema:headline ?hl.}
    OPTIONAL{$uri schema:datePublished ?dp.}
    OPTIONAL{$uri schema:dateModified ?dm.}
    OPTIONAL{
        $uri owl:sameAs ?wd. 
        
        # one-hop graph
        ?wd ?wd_prop ?wd_obj.
    }

    ?doc a foaf:Document.

    # Location entity
    OPTIONAL{
        ?loc a coy:Location;
            gn:wikipediaArticle ${uri};
            rdfs:label ?loc_label.
        
        OPTIONAL{?loc owl:sameAs ?wd.}
        OPTIONAL{?loc coy:isIdentifiedBy ?loc_id.}
        OPTIONAL{?loc coy:isLocatedIn ?parent_loc.}

        # Coordinates
        OPTIONAL{
            ?loc coy:hasLatitude ?lat;
                coy:hasLongitude ?long;
                coy:hasLocation ?point. 
        }
    }
}""").substitute(
            subgraph=f"WITH <{self.subgraph}>" if self.subgraph else "", 
            uri=article_uri.n3())

        self.__query(q)
    

    def delete_topic_triples(self, topic_uri:URIRef):
        ## if its an ArticleTopic:
        # query article of topic before deleting
        article_uris = self.__query_associated_articles(topic_uri)

        # delete articles (should only be one)
        for article_uri in article_uris:
            self.delete_article_and_location_triples(article_uri)
        
        ## delete topic triples
        q = Template("""
PREFIX coy:<https://schema.coypu.org/global#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX gn: <https://www.geonames.org/ontology#>

${subgraph}
DELETE {

    $uri a coy:TextTopic;
        a coy:WikiNews;
        a coy:Event;
        rdfs:label ?l;
        coy:hasMentionDate ?md;
        coy:isOccuringDuring ?pt;
        coy:hasRawHtml ?html;
        
        a coy:ArticleTopic;
        gn:wikipediaArticle ?a;
        coy:hasLocation ?loc;
        coy:hasTimespan ?ts.


} WHERE {

    $uri a coy:TextTopic;
        a coy:WikiNews;
        a coy:Event;
        rdfs:label ?l;
        coy:hasMentionDate ?md.
    OPTIONAL{$uri coy:isOccuringDuring ?pt.}
    OPTIONAL{$uri coy:hasRawHtml ?html.}

    # if its an ArticleTopic
    OPTIONAL{
        $uri a coy:ArticleTopic;
            gn:wikipediaArticle ?a;
            coy:hasLocation ?loc.
        OPTIONAL{ $uri coy:hasTimespan ?ts }
    }

}""").substitute(
            subgraph=f"WITH <{self.subgraph}>" if self.subgraph else "", 
            uri=topic_uri.n3())
        
        self.__query(q)

    
    def delete_newssummary_triples(self, newssummary_uri:URIRef):
        q = Template("""
PREFIX coy:<https://schema.coypu.org/global#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX gn: <https://www.geonames.org/ontology#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX nif: <http://persistence.uni-leipzig.org/nlp2rdf/ontologies/nif-core#>

${subgraph}
DELETE {

    $uri a coy:NewsSummary;
        a coy:WikiNews;
        a coy:Event;
        rdfs:label ?l;
        coy:hasTag ?tag;
        coy:hasMentionDate ?date;
        coy:hasRawHtml ?html;
        coy:isIdentifiedBy ?c;
        coy:hasWikidataEventType ?ev_type;
        coy:isOccuringDuring ?pt.
        
    ?c a nif:Context;
        rdfs:label ?c_l;
        nif:sourceUrl ?wiki_source;
        dcterms:source ?news_source;
        nif:isString ?c_str;
        nif:beginIndex ?c_bi;
        nif:endIndex ?c_ei;
        nif:subString ?s.
    
    ?s a nif:Sentence;
        nif:referenceContext ?c;
        nif:beginIndex ?s_bi;
        nif:endIndex ?s_ei;
        nif:anchorOf ?s_anchor;
        rdfs:label ?s_l;
        nif:nextSentence ?s_next;
        nif:previousSentence ?s_prev;
        nif:subString ?link. 

    ?link a nif:Phrase;
        nif:referenceContext ?s;
        nif:beginIndex ?link_bi;
        nif:endIndex ?link_ei;
        nif:anchorOf ?link_anchor;
        rdfs:label ?link_l;
        gn:wikipediaArticle ?a.

} WHERE {

    $uri a coy:NewsSummary;
        a coy:WikiNews;
        a coy:Event;
        rdfs:label ?l;
        coy:hasTag ?tag;
        coy:hasMentionDate ?date;
        coy:hasRawHtml ?html;
        coy:isIdentifiedBy ?c.
    OPTIONAL{$uri coy:hasWikidataEventType ?ev_type.}
    OPTIONAL{$uri coy:isOccuringDuring ?pt.}

    ?c a nif:Context;
        rdfs:label ?c_l;
        nif:sourceUrl ?wiki_source;
        dcterms:source ?news_source;
        # dont delete *_source props since they dont have to be added again, but could be used elsewhere.
        nif:isString ?c_str;
        nif:beginIndex ?c_bi;
        nif:endIndex ?c_ei;
        nif:subString ?s.
    
    ?s a nif:Sentence;
        nif:referenceContext ?c;
        nif:beginIndex ?s_bi;
        nif:endIndex ?s_ei;
        nif:anchorOf ?s_anchor;
        rdfs:label ?s_l.
    OPTIONAL{ ?s nif:nextSentence ?s_next. }
    OPTIONAL{ ?s nif:previousSentence ?s_prev. }
    
    OPTIONAL{ 
        ?s nif:subString ?link. 

        ?link a nif:Phrase;
            nif:referenceContext ?s;
            nif:beginIndex ?link_bi;
            nif:endIndex ?link_ei;
            nif:anchorOf ?link_anchor;
            rdfs:label ?link_l;
            gn:wikipediaArticle ?a.
    }
    
}""").substitute(
            subgraph=f"WITH <{self.subgraph}>" if self.subgraph else "", 
            uri=newssummary_uri.n3())

        self.__query(q)
    

    def delete_osmelement_triples(self, uri:URIRef):
        q = Template("""
PREFIX coy:<https://schema.coypu.org/global#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>

${subgraph}
DELETE {

    ${uri} a coy:OsmElement;
        rdfs:label ?l;
        coy:hasOsmId ?id;
        coy:hasOsmType ?type;
        geo:asWKT ?wkt.

} WHERE {

    ${uri} a coy:OsmElement;
        rdfs:label ?l.
    OPTIONAL{ $uri coy:hasOsmId ?id }
    OPTIONAL{ $uri coy:hasOsmType ?type }
    OPTIONAL{ $uri geo:asWKT ?wkt }

}""").substitute(
            subgraph=f"WITH <{self.subgraph}>" if self.subgraph else "", 
            uri=uri.n3())

        res = self.__query(q)

    
    def delete_label_triples(self, uri:URIRef):
        q = Template("""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

${subgraph}
DELETE WHERE {

    ${uri} rdfs:label ?l.

}""").substitute(
            subgraph=f"WITH <{self.subgraph}>" if self.subgraph else "", 
            uri=uri.n3())

        res = self.__query(q)