from collections import OrderedDict
from typing import OrderedDict as ODict

# TODO use URN - formalize namespace as URN using urnparse

class NodeNamespace:
    def __init__(self, name, nodes:ODict[str, str] = None):
        self.name = name
        self.set_nodes(nodes or OrderedDict())

    def set_nodes(self, nodes:ODict[str, str]):
        self.nodes = nodes

    def get_nodes(self) -> ODict[str, str]:
        return self.nodes

    def add_node(self, key) -> str:
        node_name = NodeNamespace.format(self.name, key)
        self.nodes[key] = node_name
        return node_name

    @staticmethod
    def format(namespace, name):
        return f"{namespace}::{name}"