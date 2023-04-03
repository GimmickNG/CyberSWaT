from .nns import NodeNamespace
from mininet.topo import Topo
from typing import List
import string, random

class NamespacedTopo(Topo):
    """
    A topology that combines multiple topologies, using namespaces
    to ensure that nodes are unique in the overall topology. Can be
    used with `NamespacedCLI` to support `use` namespace declaratives.
    """

    def __init__(self, topologies: List[Topo], namespaces: List[str] = None, *args, **params):
        super().__init__(topologies, namespaces, *args, **params)

    def build(self, topologies, namespaces):
        # declarations
        self.namespaces = []
        self.active_namespaces = []
        
        # bound functions 
        self.add_namespace = self.namespaces.append
        self.remove_namespace = self.namespaces.remove
        
        if len(topologies) > 1:
            namespaces = namespaces or []
            while len(namespaces) < len(topologies):
                ns = ''.join([random.choice(string.ascii_characters) for _ in range(3)])
                if ns not in namespaces:
                    namespaces.append(ns)
        elif len(topologies) == 1:
            namespaces = namespaces or ['']
        else:
            raise ValueError("Expected at least one topology.")

        # a namespace is a dict containing the name of the namespace and all the variables
        # under that namespace. When resolving a namespace, it looks through the list in 
        # reverse order (ordered in ascending order of priority) and checks for the first
        # variable in the namespace dict that matches the current namespace. This is only
        # done if the `using` directive is used; otherwise, if a fully qualified namespace
        # is used, then it is resolved directly.
        self_graph = self.g
        for topo, namespace in zip(topologies, namespaces):
            graph = topo.g
            # todo use context manager for ensure_namespace - set active namespace

            self.add_namespace(NodeNamespace(namespace, graph.nodes()))
            for node, attrs in graph.nodes(data=True):
                self_graph.add_node(self.ensure_namespace(node, namespace), attrs)

            for src, dst, k, attrs in graph.edges_iter(data=True, keys=True):
                self_graph.add_edge(
                    self.ensure_namespace(src, namespace),
                    self.ensure_namespace(dst, namespace),
                    k, attrs
                )

            for src, all_ports in topo.ports.items():
                for sport, (dst, dport) in all_ports.items():
                    super().addPort(
                        self.ensure_namespace(src, namespace),
                        self.ensure_namespace(dst, namespace),
                        sport, dport
                    )
    
    def get_active(self) -> List[ NodeNamespace ]:
        return self.active_namespaces

    def use_namespace(self, name):
        for namespace in self.namespaces:
            if namespace.name == name:
                self.active_namespaces.append(namespace)
                break
    
    def unuse_namespace(self, name):
        for namespace in reversed(self.namespaces):
            if namespace.name == name:
                self.active_namespaces.remove(namespace)
                break
    
    def ensure_namespace(self, name, namespace):
        if namespace and name.startswith(namespace + "::"):
            return name
        return NodeNamespace.format(namespace, name)

    def strip_namespace(self, name):
        # converts a qualified namespace into an ambiguous one if it is present
        # in the list of `using` (i.e. active) namespaces. That way, it is easier
        # for the user to type as it is an active namespace.
        # if there are no active namespaces that match, then return the fully qualified name.
        # e.g. namespace "std" exists, but not active; name is "std::vec"
        # return "std:vec" as "std" is not being used
        # if it is being used, return "vec"
        
        if "::" in name:
            parsed_namespace, node_name = name.split("::")
            for ns in reversed(self.get_active()):
                if parsed_namespace == ns.name and node_name in ns.nodes:
                    return node_name
        return name

    def qualify_namespace(self, name):
        # searches in the list of active namespaces in reverse order for a node
        # whose name matches the given name, and prepends the namespace name to 
        # it to qualify it
        orig_name = name
        if "::" in name:
            # inverse of strip_namespace: defaults to unqualified name instead
            # of qualified name
            parsed_namespace, node_name = name.split("::")
            for ns in reversed(self.get_active()):
                if parsed_namespace == ns.name:
                    return name # already qualified; return it
            name = node_name

        # namespace not found or not qualified; search for the unqualified node
        # name in the list of active namespaces
        for ns in reversed(self.get_active()):
            if name in ns.nodes:
                return self.ensure_namespace(name, ns.name)
        return orig_name

    def isSwitch(self, n):
        return super().isSwitch(self.qualify_namespace(n))

    def switches(self, sort=True):
        return [self.strip_namespace(n) for n in super().switches(sort)]

    def hosts(self, sort=True):
        return [self.strip_namespace(n) for n in super().hosts(sort)]
    
    def iterLinks(self, withKeys=False, withInfo=False):
        return (
            (self.strip_namespace(src), self.strip_namespace(dst), *rest)
        for src, dst, *rest in super().iterLinks(withKeys, withInfo))
        
    def port(self, src, dst):
        return super().port(self.strip_namespace(src), self.strip_namespace(dst))

    def _linkEntry(self, src, dst, key=None):
        return super()._linkEntry(self.strip_namespace(src), self.strip_namespace(dst), key)

    def nodeInfo(self, name):
        return super().nodeInfo(self.strip_namespace(name))

    def _frozen_error(self, *args, **kwargs):
        raise NotImplementedError("Cannot call function on frozen topology.")

    addNode = _frozen_error
    addHost = _frozen_error
    addSwitch = _frozen_error
    addLink = _frozen_error
    addPort = _frozen_error
    setNodeInfo = _frozen_error

    """
    def addNode(self, name, **opts):
        self._frozen_error() # return super().addNode(self.ensure_namespace(name), **opts)

    def addHost(self, name, **opts):
        self._frozen_error() # return super().addHost(self.ensure_namespace(name), **opts)

    def addSwitch(self, name, **opts):
        return super().addSwitch(self.ensure_namespace(name), **opts)

    def addLink(self, node1, node2, port1=None, port2=None, key=None, **opts):
        return super().addLink(
            self.ensure_namespace(node1), self.ensure_namespace(node2), port1, port2, key, **opts
        )

    def addPort(self, src, dst, sport=None, dport=None):
        if self.mask:
            return super().addPort(src, dst, sport, dport)
        return super().addPort(
            self.remove_namespace(src), self.remove_namespace(dst), sport, dport
        )

    def setNodeInfo(self, name, info):
        return super().setNodeInfo(self.ensure_namespace(name), info)
    
    """
    