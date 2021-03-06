# -*- coding: utf-8 -*-
#
# Copyright 2012 James Thornton (http://jamesthornton.com)
# BSD License (see LICENSE for details)
#
"""
Bulbs supports pluggable clients. This is the Rexster client.

"""
import os

from bulbs.utils import json, build_path, get_file_path, get_logger, urlsplit
from bulbs.registry import Registry
from bulbs.config import Config, DEBUG

# specific to this client
from bulbs.client import Client, Response, Result 
from bulbs.rest import Request, RESPONSE_HANDLERS
from bulbs.typesystem import JSONTypeSystem
from bulbs.groovy import GroovyScripts
from bulbs.utils import coerce_id

# The default URIs
REXSTER_URI = "http://localhost:8182/graphs/tinkergraph"
SAIL_URI = "http://localhost:8182/graphs/sailgraph"

# The logger defined in Config
log = get_logger(__name__)


class RexsterResult(Result):
    """
    Container class for a single result, not a list of results.

    :param result: The raw result.
    :type result: dict

    :param config: The client Config object.
    :type config: Config 

    """

    def __init__(self,result, config):
        self.config = config

        #: The raw result.
        self.raw = result

        #: The data in the result.
        self.data = result

    def get_id(self):
        """Returns the element ID."""
        _id = self.data['_id']

        # OrientDB uses string IDs
        return coerce_id(_id)
               
    def get_type(self):
        """Returns the element's base type, either vertex or edge."""
        return self.data['_type']
        
    def get_map(self):
        """Returns the element's property map."""
        property_map = dict()
        private_keys = ['_id','_type','_outV','_inV','_label']
        for key in self.data: # Python 3
            value = self.data[key]
            if key not in private_keys:
                property_map.update({key:value})
        return property_map

    def get_uri(self):
        """Returns the element URI."""
        path_map = dict(vertex="vertices",edge="edges")
        _id = self.get_id()
        _type = self._get_type()
        element_path = path_map[_type]
        root_uri = self.config.root_uri
        uri = "%s/%s/%s" % (root_uri,element_path,_id)
        return uri
                 
    def get_outV(self):
        """Returns the ID of the edge's outgoing vertex (start node)."""
        _outV = self.data.get('_outV')
        return int(_outV)
        
    def get_inV(self):
        """Returns the ID of the edge's incoming vertex (end node)."""
        _inV = self.data.get('_inV')
        return int(_inV)

    def get_label(self):
        """Returns the edge label (relationship type)."""
        return self.data.get('_label')

    def get(self,attribute):
        """Returns the value of a client-specific attribute."""
        return self.data[attribute]


class RexsterResponse(Response):
    
    result_class = RexsterResult

    def __init__(self, response, config):
        self.config = config
        self.handle_response(response)
        self.headers = self.get_headers(response)
        self.content = self.get_content(response)
        self.results, self.total_size = self.get_results()
        self.raw = self._maybe_get_raw(response, config)

    def _maybe_get_raw(self,response, config):
        # don't store raw response in production else you'll bloat the obj
        if config.log_level == DEBUG:
            return response

    def handle_response(self,http_resp):
        """Handle HTTP server response."""
        headers, content = http_resp
        response_handler = RESPONSE_HANDLERS.get(headers.status)
        response_handler(http_resp)

    def get_headers(self,response):
        """Return the headers from the HTTP response."""
        headers, content = response
        return headers

    def get_content(self,response):
        """Return the content from the HTTP response."""
        
        # response is a tuple containing (headers, content)
        # headers is an httplib2 Response object, content is a string
        # see http://httplib2.googlecode.com/hg/doc/html/libhttplib2.html
        headers, content = response

        if content:
            content = json.loads(content.decode('utf-8'))
            return content

    def get_results(self):
        """Return results from response, formatted as Result objects, and its total size."""
        if type(self.content.get('results')) == list:
            results = (self.result_class(result, self.config) for result in self.content['results'])
            total_size = len(self.content['results'])
        elif self.content.get('results'):
            results = self.result_class(self.content['results'], self.config)
            total_size = 1
        else:
            results = None
            total_size = 0
        return results, total_size


class RexsterRequest(Request):
    """Makes requests to Rexster and returns a RexsterResponse.""" 
    
    response_class = RexsterResponse


class RexsterClient(Client):
    """Low-level client that connects to Neo4j Server and returns a response.""" 
    
    #: Default URI for the database.
    default_uri = REXSTER_URI

    vertex_path = "vertices"
    edge_path = "edges"
    index_path = "indices"
    gremlin_path = "tp/gremlin"
    transaction_path = "tp/batch/tx"
    multi_get_path = "tp/batch"

    def __init__(self, config=None, db_name=None):

        # This makes is easy to test different DBs 
        uri = self._get_uri(db_name) or self.default_uri

        self.config = config or Config(uri)
        self.registry = Registry(self.config)

        # Rexster supports Gremlin so include the Gremlin-Groovy script library
        self.scripts = GroovyScripts() 

        # Also include the Rexster-specific Gremlin-Groovy scripts
        scripts_file = get_file_path(__file__, "gremlin.groovy")
        self.scripts.update(scripts_file)

        # Add it to the registry. This allows you to have more than one scripts namespace.
        self.registry.add_scripts("gremlin", self.scripts)

        self.type_system = JSONTypeSystem()
        self.request = RexsterRequest(self.config, self.type_system.content_type)

    def _get_uri(self, db_name):
        if db_name is not None:
            uri = "http://localhost:8182/graphs/%s" % db_name
            return uri

    # Gremlin

    def gremlin(self,script,params=None): 
        """Executes a Gremlin script and returns the Response."""
        params = dict(script=script,params=params)
        return self.request.post(self.gremlin_path,params)

    # Vertex Proxy

    def create_vertex(self,data):
        """Creates a vertex and returns the Response."""
        data = self._remove_null_values(data)
        return self.request.post(self.vertex_path,data)

    def get_vertex(self,_id):
        """Gets the vertex with the _id and returns the Response."""
        path = build_path(self.vertex_path,_id)
        return self.request.get(path,params=None)

    def update_vertex(self,_id,data):
        """Updates the vertex with the _id and returns the Response."""
        data = self._remove_null_values(data)
        path = build_path(self.vertex_path,_id)
        return self.request.put(path,data)
        
    def delete_vertex(self,_id):
        """Deletes a vertex with the _id and returns the Response."""
        path = build_path(self.vertex_path,_id)
        return self.request.delete(path,params=None)

    # Edge Proxy

    def create_edge(self,outV,label,inV,data={}): 
        """Creates a edge and returns the Response."""
        data = self._remove_null_values(data)
        edge_data = dict(_outV=outV,_label=label,_inV=inV)
        data.update(edge_data)
        return self.request.post(self.edge_path,data)

    def get_edge(self,_id):
        """Gets the edge with the _id and returns the Response."""
        path = build_path(self.edge_path,_id)
        return self.request.get(path,params=None)

    def update_edge(self,_id,data):
        """Updates the edge with the _id and returns the Response."""
        data = self._remove_null_values(data)
        path = build_path(self.edge_path,_id)
        return self.request.put(path,data)

    def delete_edge(self,_id):
        """Deletes a edge with the _id and returns the Response."""
        path = build_path(self.edge_path,_id)
        return self.request.delete(path,params=None)

    # Vertex Container

    def outE(self,_id,label=None):
        """Return the outgoing edges of the vertex."""
        script = self.scripts.get('outE')
        params = dict(_id=_id,label=label)
        return self.gremlin(script,params)

    def inE(self,_id,label=None):
        """Return the incoming edges of the vertex."""
        script = self.scripts.get('inE')
        params = dict(_id=_id,label=label)
        return self.gremlin(script,params)

    def bothE(self,_id,label=None):
        """Return all incoming and outgoing edges of the vertex."""
        script = self.scripts.get('bothE')
        params = dict(_id=_id,label=label)
        return self.gremlin(script,params)

    def outV(self,_id,label=None):
        """Return the out-adjacent vertices to the vertex."""
        script = self.scripts.get('outV')
        params = dict(_id=_id,label=label)
        return self.gremlin(script,params)
        
    def inV(self,_id,label=None):
        """Return the in-adjacent vertices of the vertex."""
        script = self.scripts.get('inV')
        params = dict(_id=_id,label=label)
        return self.gremlin(script,params)
        
    def bothV(self,_id,label=None):
        """Return all incoming- and outgoing-adjacent vertices of vertex."""
        script = self.scripts.get('bothV')
        params = dict(_id=_id,label=label)
        return self.gremlin(script,params)

    # Index Proxy - General

    def get_all_indices(self):
        """Returns a list of all the element indices."""
        return self.request.get(self.index_path,params=None)

    def get_index(self,name):
        path = build_path(self.index_path,name)
        return self.request.get(path,params=None)

    def delete_index(self,name): 
        """Deletes the index with the index_name."""
        path = build_path(self.index_path,name)
        return self.request.delete(path,params=None)
            
    # Index Proxy - Vertex

    def create_vertex_index(self,index_name,*args,**kwds):
        """Creates a vertex index with the specified params."""
        path = build_path(self.index_path,index_name)
        index_type = kwds.get('index_type','manual')
        index_keys = kwds.get('index_keys',None)                              
        params = {'class':'vertex','type':index_type}
        if index_keys: 
            params.update({'keys':index_keys})
        return self.request.post(path,params)

    def get_vertex_index(self,name):
        """Returns the vertex index with the index_name."""
        return self.get_index(name)

    def delete_vertex_index(self,name): 
        """Deletes the vertex index with the index_name."""
        return self.delete_index(name)

    # Index Proxy - Edge

    def create_edge_index(self,name,*args,**kwds):
        """Creates a edge index with the specified params."""
        path = build_path(self.index_path,name)
        index_type = kwds.get('index_type','manual')
        index_keys = kwds.get('index_keys',None)                              
        params = {'class':'edge','type':index_type}
        if index_keys: 
            params.update({'keys':index_keys})
        return self.request.post(path,params)
        
    def get_edge_index(self,name):
        """Returns the edge index with the index_name."""
        return self.get_index(name)
        
    def delete_edge_index(self,name):
        """Deletes the edge index with the index_name."""
        self.delete_index(name)

    #def create_automatic_vertex_index(self,index_name,element_class,keys=None):
    #    keys = json.dumps(keys) if keys else "null"
    #    params = dict(index_name=index_name,element_class=element_class,keys=keys)
    #    script = self.scripts.get('create_automatic_vertex_index',params)
    #    return self.gremlin(script)
        
    #def create_indexed_vertex_automatic(self,data,index_name):
    #    data = json.dumps(data)
    #    params = dict(data=data,index_name=index_name)
    #    script = self.scripts.get('create_automatic_indexed_vertex',params)
    #    return self.gremlin(script)

    # Index Container - General

    def index_count(self,index_name,key,value):
        path = build_path(self.index_path,index_name,"count")
        params = dict(key=key,value=value)
        return self.request.get(path,params)

    def index_keys(self,index_name):
        path = build_path(self.index_path,index_name,"keys")
        return self.request.get(path,params=None)

    # Index Container - Vertex

    def put_vertex(self,index_name,key,value,_id):
        """Adds a vertex to the index with the index_name."""
        # Rexster's API only supports string lookups so convert value to a string 
        path = build_path(self.index_path,index_name)
        params = {'key':key,'value':str(value),'class':'vertex','id':_id}
        return self.request.put(path,params)

    def lookup_vertex(self,index_index_name,key,value):
        """Returns the vertices indexed with the key and value."""
        path = build_path(self.index_path,index_index_name)
        params = dict(key=key,value=value)
        return self.request.get(path,params)

    def query_vertex(self,index_name,params):
        """Queries for an edge in the index and returns the Response."""
        path = build_path(self.index_path,index_name)
        return self.request.get(path,params)

    def remove_vertex(self,index_name,_id,key=None,value=None):
        """Removes a vertex from the index and returns the Response."""
        # Can Rexster have None for key and value?
        path = build_path(self.index_path,index_name)
        params = {'key':key,'value':value,'class':'vertex','id':_id}
        return self.request.delete(path,params)

    # Index Container - Edge

    def put_edge(self,index_name,key,value,_id):
        """Adds an edge to the index and returns the Response."""
        # Rexster's API only supports string lookups so convert value to a string 
        path = build_path(self.index_path,index_name)
        params = {'key':key,'value':str(value),'class':'edge','id':_id}
        return self.request.put(path,params)

    def lookup_edge(self,index_index_name,key,value):
        """Looks up an edge in the index and returns the Response."""
        path = build_path(self.index_path,index_index_name)
        params = dict(key=key,value=value)
        return self.request.get(path,params)

    def query_edge(self,index_name,params):
        """Queries for an edge in the index and returns the Response."""
        path = build_path(self.index_path,index_name)
        return self.request.get(path,params)

    def remove_edge(self,index_name,_id,key=None,value=None):
        """Removes an edge from the index and returns the Response."""
        # Can Rexster have None for key and value?
        path = build_path(self.index_path,index_name)
        params = {'key':key,'value':value,'class':'edge','id':_id}
        return self.request.delete(path,params)
    
    # Model Proxy - Vertex

    def create_indexed_vertex(self,data,index_name,keys=None):
        """Creates a vertex, indexes it, and returns the Response."""
        data = self._remove_null_values(data)
        params = dict(data=data,index_name=index_name,keys=keys)
        script = self.scripts.get("create_indexed_vertex")
        return self.gremlin(script,params)
    
    def update_indexed_vertex(self,_id,data,index_name,keys=None):
        """Updates an indexed vertex and returns the Response."""
        data = self._remove_null_values(data)
        params = dict(_id=_id,data=data,index_name=index_name,keys=keys)
        script = self.scripts.get("update_indexed_vertex")
        return self.gremlin(script,params)

    # Model Proxy - Edge

    def create_indexed_edge(self,data,index_name,keys=None):
        """Creates a edge, indexes it, and returns the Response."""
        data = self._remove_null_values(data)
        params = dict(data=data,index_name=index_name,keys=keys)
        script = self.scripts.get("create_indexed_edge")
        return self.gremlin(script,params)
    
    def update_indexed_edge(self,_id,data,index_name,keys=None):
        """Updates an indexed edge and returns the Response."""
        data = self._remove_null_values(data)
        params = dict(_id=_id,data=data,index_name=index_name,keys=keys)
        script = self.scripts.get("update_indexed_edge")
        return self.gremlin(script,params)

    # Utils

    def warm_cache(self):
        """Warms the server cache by loading elements into memory."""
        script = self.scripts.get('warm_cache')
        return self.gremlin(script,params=None)

    # Rexster Specific Stuff

    def rebuild_vertex_index(self,index_name):
        params = dict(index_name=index_name)
        script = self.scripts.get('rebuild_vertex_index',params)
        return self.gremlin(script)

    def rebuild_edge_index(self,index_name):
        params = dict(index_name=index_name)
        script = self.scripts.get('rebuild_edge_index',params)
        return self.gremlin(script)


    # TODO: manual/custom index API

    def multi_get_vertices(self,id_list):
        path = build_path(self.multi_get_path,"vertices")
        idList = self._build_url_list(id_list)
        params = dict(idList=idList)
        return self.request.get(path,params)

    def multi_get_edges(self,id_list):
        path = build_path(self.multi_get_path,"edges")
        idList = self._build_url_list(id_list)
        params = dict(idList=idList)
        return self.request.get(path,params)

    def _build_url_list(items):
        items = [str(item) for item in items]
        url_list = "[%s]" % ",".join(items)
        return url_list

    def execute_transaction(self,transaction):
        params = dict(tx=transaction.actions)
        return self.request.post(self.transction_path,params)

    def _remove_null_values(self,data):
        """Removes null property values because they aren't valid in Neo4j."""
        # Neo4j Server uses PUTs to overwrite all properties so no need
        # to worry about deleting props that are being set to null.
        clean_data = [(k, data[k]) for k in data if data[k] is not None]  # Python 3
        return dict(clean_data)

