# -*- coding: utf-8 -*-
#
# Copyright 2012 James Thornton (http://jamesthornton.com)
# BSD License (see LICENSE for details)
#
from bulbs.config import Config
from bulbs.factory import Factory
from bulbs.client import Client
from bulbs.element import Vertex, Edge
from bulbs.model import Relationship
from bulbs.index import Index


# A framework is an understanding of how things could fit together.
## It's important to design with the understanding that your understanding is incomplete.
# When designing these things, it's important to remember that your understanding is incomplete.

class Graph(object):
    """
    Abstract base class for the Graph implementations. See the Bulbs 
    Neo4j Server and Rexster documentation for server-specific 
    implementations. 

    :param config: Optional. Defaults to the default config.
    :type config: Config
        
    Example:

    >>> from bulbs.neo4jserver import Graph
    >>> g = Graph()
    >>> james = g.vertices.create(name="James")
    >>> julie = g.vertices.create(name="Julie")
    >>> g.edges.create(james, "knows", julie)

    """    
    #: The Client class to use for this Graph.
    client_class = Client

    #: The default Index class.
    default_index = Index

    def __init__(self, config=None):

        #: Client object.
        self.client = self.client_class(config)

        self._factory = Factory(self.client)

        #: Generic VertexProxy object.
        self.vertices = self.build_proxy(Vertex)

        #: Generic EdgeProxy object.
        self.edges = self.build_proxy(Edge)

        #: Config object for convienence
        self.config = self.client.config


    def add_proxy(self, proxy_name, element_class, index_class=None):
        """
        Adds an element proxy to the Graph object for the element class.

        :param proxy_name: Attribute name to use for the proxy.
        :type proxy_name: str

        :param element_class: Element class managed by this proxy.
        :type element_class: Element

        :param index_class: Index class used for Element's primary index. Defaults to default_index.
        :type index_class: Index

        :rtype: None

        """
        proxy = self.build_proxy(element_class, index_class)
        setattr(self, proxy_name, proxy)
    
    def build_proxy(self, element_class, index_class=None):
        """
        Returns an element proxy built to specifications.

        :param element_class: Element class managed by this proxy.
        :type element_class: Element

        :param index_class: Optional Index class used for Element's primary index. 
            Defaults to default_index.
        :type index_class: Index

        :rtype: Element proxy

        """
        if not index_class:
            index_class = self.default_index
        return self._factory.build_element_proxy(element_class, index_class)

    def load_graphml(self, uri):
        """
        Loads a GraphML file into the database and returns the response.

        :param uri: URI of the GraphML file.
        :type uri: str

        :rtype: Response

        """
        raise NotImplementedError
        
    def save_graphml(self):
        """
        Returns a GraphML file representing the entire database.

        :rtype: Response

        """
        raise NotImplementedError

    def warm_cache(self):
        """
        Warms the server cache by loading elements into memory.

        :rtype: Response

        """
        raise NotImplementedError

    def clear(self):
        """Deletes all the elements in the graph.

        :rtype: Response

        .. admonition:: WARNING 

           This will delete all your data!

        """
        raise NotImplementedError
