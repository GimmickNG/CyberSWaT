from typing import Dict, List, Tuple, Union, OrderedDict as ODict
from mininet.net import Mininet
from mininet.log import info, warning, error
from mininet.topo import Topo
from .ns_topo import NodeNamespace
from collections.abc import MutableMapping
from collections import OrderedDict
import random, string
# TODO instead of making namespaced topo, make namespaced mininet which takes multiple
# topos, as this is far easier - just modify the nameToNode dict to include the namespaces
# for each node/host/switch/etc and then everything else is already done by mininet...?

class NamespacedDict(MutableMapping):
    # namespace mapping dict is responsible for storing the resolved names in each topology
    # each name in the topology is scrambled (or otherwise made random) and then stored back
    # in this mapping, so that hostnames like "std::hmi" can be mapped to them, e.g. 
    # "std::hmi" === "hmi" ==> "3942386e"

    def __init__(self):
        # active_namespaces is an ordered set of keys, e.g. {"std", "otn", "itn"}
        self.active_namespaces: ODict[str, NodeNamespace] = OrderedDict()
        # all_namespaces = an ordered dict of ns-nodenamespaces, e.g. {"std": NodeNamespace()}
        self._all_namespaces: ODict[str, NodeNamespace] = OrderedDict()
        self.store = dict()
        # starts by being in build mode by default; call build_complete() to stop building
        self._build = True

    def __getitem__(self, key):
        tkey = self._keytransform(key)
        if tkey is None:
            return None
        return self.store[tkey]

    def __setitem__(self, key, value):
        self.store[self._keytransform(key)] = value

    def __delitem__(self, key):
        del self.store[self._keytransform(key)]

    def __iter__(self):
        return iter(self.store)
    
    def __len__(self):
        return len(self.store)

    def _keytransform(self, key):
        # converts a qualified or unqualified name to its real name
        # e.g. "std::hmi" or "hmi" (if "using std;") => "hmi34352350afh"

        # when resolving a key, check if it is fully qualified or not
        if "::" in key:
            # fully qualified; look up the node namespace dict in _all_namespaces;
            # retrieve the name mapping, e.g. "std::hmi"=> {"std": {"hmi": "hmi34352350afh"}}
            # and use this key ("hmi34352350afh") as the key to the store
            ns_name, node_name = key.split("::", 1)
            if ns_name in self._all_namespaces:
                namespace = self._all_namespaces[ns_name]
                mapping = namespace.get_nodes()
                return mapping.get(node_name, key)
        else:
            # not fully qualified; look up the active namespaces in reverse order and
            # check for a node name in the list of each nodes that matches this key;
            # finally, retrieve the name mapping in the same way as above
            node_name = key
            for ns_name, namespace in reversed(self.active_namespaces.items()):
                mapping = namespace.get_nodes()
                if node_name in mapping:
                    return mapping[node_name]
        # FIX ERROR - the hosts stored in mininet contain the "original" name
        # that is, h1, c0, s1, etc. - without the namespaces - so this means that
        # looping through the mininet object (self.hosts, self.switches, self.controllers)
        # will result in the unqualified names being sent here, AND it will also
        # cause strange behaviour with multiple topos, as names can collide at build
        # time, e.g. when instances of CLI call iter() and getitem() on the net object
        # Solution could be e.g. creating custom Host, Switch and Controller decorators
        # that return a qualified or unqualified name, depending on whether the namespace
        # is currently used or not. This would probably require some communication between
        # the Host objects and the Net object

        # key not present in namespaces; happens when adding node for first time
        # here, scramble name and add to default mapping
        if len(self.active_namespaces):
            most_recent_namespace = next(reversed(self.active_namespaces.values()))
        elif len(self._all_namespaces):
            most_recent_namespace = next(reversed(self._all_namespaces.values()))
        else:
            raise KeyError("No namespaces exist for this network. Were they removed?")
        if self._build:
            return most_recent_namespace.add_node(key)
        else:
            error(f"Key not found: {key} for namespace {most_recent_namespace.name}", '\n')

    def __enter__(self):
        # does nothing, as main logic handled in use_namespace() function
        # that is, if use_namespace is called as is, then it just adds to
        # the list of active namespaces.
        pass

    def __exit__(self, exc_type, exc_value, exc_tb):
        # if use_namespace is called in a context manager, then this is called;
        # here, remove the active namespace at the time of function call (i.e. 
        # self.active_namespace) from the list of active namespaces (and all other
        # namespaces that were made active after it?)
        # if not called in a context manager, then __exit__ never called so it
        # is equivalent to a permanent using declarative

        try:
            self.active_namespaces.popitem(last=True)
        except KeyError:
            raise RuntimeError("Active namespaces cleared out while it was being used")
        return True

    def get_all_namespaces(self) -> Dict[str, NodeNamespace]:
        return self._all_namespaces

    def get_active(self) -> Dict[str, NodeNamespace]:
        return self.active_namespaces

    def unuse_namespace(self, ns: Union[NodeNamespace, str]):
        ns_name = ns.name if isinstance(ns, NodeNamespace) else ns
        if ns_name in self.get_active():
            del self.active_namespaces[ns_name]
            return True
        return False
    
    def use_namespace(self, ns):
        if isinstance(ns, NodeNamespace):
            self.active_namespaces[ns.name] = self._all_namespaces[ns.name] = ns
            return True
        elif isinstance(ns, str):
            if ns not in self.get_active():
                self.active_namespaces[ns] = self.get_all_namespaces()[ns]
                return True
        return False

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
            if parsed_namespace in self.get_active():
                return name # already qualified; return it
            name = node_name

        # namespace not found or not qualified; search for the unqualified node
        # name in the list of active namespaces
        for ns in reversed(self.get_active()):
            if name in ns.nodes:
                return self.ensure_namespace(name, ns.name)
        return orig_name
    
    def build_complete(self):
        self._build = False
            


class NSNet(Mininet):
    """
    A topology that combines multiple topologies, using namespaces
    to ensure that nodes are unique in the overall topology. Can be
    used with `NamespacedCLI` to support `use` namespace declaratives.
    """

    def __init__(self, topo: Union[Topo, Tuple[str, Topo], List[Tuple[str, Topo]]], *args, **params):
        super().__init__(*args, topo=None, build=False, **params)
        
        # nameToNode delegates
        self.nameToNode = NamespacedDict()
        self.get_active = self.nameToNode.get_active
        self.get_all_namespaces = self.nameToNode.get_all_namespaces
        self.unuse_namespace = self.nameToNode.unuse_namespace
        
        # cleanup input parameters if necessary
        if isinstance(topo, Topo):
            topo = [('', topo)]
        elif isinstance(topo, (List, Tuple)):
            if len(topo) == 2 and isinstance(topo[0], str):
                topo = [topo] # not a list of pairs; just one pair - encapsulate
            elif not len(topo):
                raise ValueError("Expected at least one topology.")
        else:
            raise TypeError("Expected either a Topo, or a list of pairs of type (str, Topo)")

        self._ns_topos = topo
        if params.get('build', True):
            self.build()

    def build(self):
        # a namespace is a dict containing the name of the namespace and all the variables
        # under that namespace. When resolving a namespace, it looks through the list in 
        # reverse order (ordered in ascending order of priority) and checks for the first
        # variable in the namespace dict that matches the current namespace. This is only
        # done if the `using` directive is used; otherwise, if a fully qualified namespace
        # is used, then it is resolved directly.
        for namespace, topo in self._ns_topos:
            with self.use_namespace(NodeNamespace(namespace)):
                super().buildFromTopo(topo)
        self.nameToNode.build_complete()
        del self._ns_topos
        super().build()

    def use_namespace(self, ns: Union[NodeNamespace, str]):
        if self.nameToNode.use_namespace(ns):
            return self.nameToNode
        raise KeyError("Namespace {name} not found in list of namespaces.")