from typing import Optional
from mininet.cli import CLI
from mininet.log import error, warning, output
from utils.nns import NodeNamespace
from utils.ns_net import NSNet
import argparse
import shlex
import sys

class NamespacedCLI( CLI ):
    def __init__(self, mininet:NSNet, stdin=sys.stdin, script=None, **kwargs):
        if isinstance(mininet, NSNet):
            self.parseline = self._parseline
            self.initialize_argparse()
        else:
            warning("Mininet instance is not an NSNet; namespace features will not be enabled.", '\n')
        super().__init__(mininet, stdin, script, **kwargs)

    def initialize_argparse( self ):
        self.parent_parser = argparse.ArgumentParser("ns", description="The namespace utility.")
        self.root_nsparser = self.parent_parser.add_subparsers(required=True)

        self.set_parser = self.root_nsparser.add_parser("use")
        self.set_parser.add_argument("namespace", type=str.lower, help="The namespace to switch to.")
        self.set_parser.set_defaults(parse_fn=self.do_set)

        self.unset_parser = self.root_nsparser.add_parser("unuse")
        self.unset_parser.add_argument("namespace", type=str.lower, help="The namespace to stop using.")
        self.unset_parser.set_defaults(parse_fn=self.do_unset)

        self.show_parser = self.root_nsparser.add_parser("show", description="Shows namespaces or mappings")
        self.show_parser.add_argument("--active", "-a", action="store_true", help="Show only the active namespaces or mappings.")
        self.show_parser.add_argument("--mapping", "-m", action="store_true", help="Shows mappings.")
        self.show_parser.set_defaults(parse_fn=self.do_show)

    def _parseline(self, line: str):
        return super().parseline(self._try_substitute(line))

    def help_ns( self ):
        self.parent_parser.print_help(sys.stdout)
    
    def do_ns( self, line ):
        args = self._parse_args(self.parent_parser, line)
        if args is None:
            return
        
        # hand off parsing to delegate function
        args.parse_fn(line)

    def help_set( self ):
        self.set_parser.print_help(sys.stdout)

    def do_set( self, line ):
        args = self._parse_args(self.set_parser, line)
        if args is None:
            return

        self.mn.use_namespace(args.namespace)

    def help_unset( self ):
        self.unset_parser.print_help(sys.stdout)

    def do_unset( self, line ):
        args = self._parse_args(self.unset_parser, line)
        if args is None:
            return

        try:
            if args.namespace == "all":
                for ns in self.mn.get_active():
                    self.mn.unuse_namespace(ns)
            else:
                self.mn.unuse_namespace(args.namespace)
        except KeyError as err:
            error(err, '\n')

    def help_show( self ):
        self.show_parser.print_help(sys.stdout)

    def do_show( self, line ):
        args = self._parse_args(self.show_parser, line)
        if args is None:
            return

        if args.mapping:
            if args.active:
                pass    #TODO show mapping
            else:
                pass    #TODO show all mappings
        else:
            if args.active:
                for ns in self.mn.get_active():
                    output(ns.name)
            else:
                for ns in self.mn.get_all_namespaces():
                    output(ns.name)

    def _try_substitute(self, line) -> str:
        if '`' not in line or not isinstance(self.mn, NSNet):
            return line

        ##
        # check if names match any with namespace
        # e.g. if node called std::plc101 and if namespace list has "std" in it, then add it to the name
        # repeat for all names in string for all namespaces
        # retrieve list of registered namespaces from net object when creating CLI so that it doesn't become inefficient
        # i.e. NamespaceCLI(net) -> net.topo1.namespace, nodes = "std", [plc101, plc201]
        # then std only matches if encounter "plc101" or "plc201" in the string
        # since list used, order of resolve matters for user
        ##

        active_namespaces = self.mn.get_active()
        for ns in reversed(active_namespaces.values()):
            # use `` to demarcate namespaces, e.g. `hmi`; replace with "std::hmi"
            # replace name of any node in active namespace if 
            # it is encountered in a whole-word boundary search in the line
            # e.g. if line = "hmi curl historian", and "hmi" is in ns, and ns.name="std"
            # then replace "hmi" with "std::hmi" but not if it is "httphmi.com"
            for ns_name, node_name in ns.get_nodes().items():
                if '`' not in line:
                    break
                line = NodeNamespace.format(ns_name, node_name).join(
                    line.split(f"`{node_name}`")
                )
        
        output(line, '\n')
        return line

    def _parse_args( self, parser, line ) -> Optional[argparse.Namespace]:
        try:
            return parser.parse_args(shlex.split(line))
        except (SystemExit, Exception):
            return None

    #def _default(self, line):
    #    # if _parse_command succeeds, then it is a "namespace" command
    #    # show error (default action) only if it fails
    #    if not self._parse_command(line):
    #        return super().default(line)