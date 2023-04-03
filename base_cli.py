from mininet.cli import CLI
from select import poll
from cmd2.utils import categorize
from cmd2 import Cmd
import cmd2
import sys

class NewCLI ( Cmd ):
    prompt = CLI.prompt
    def __init__( self, mininet, stdin=sys.stdin, script=None,
                  **kwargs ):
        """Start and run interactive or batch mode CLI
           mininet: Mininet network object
           stdin: standard input for CLI
           script: script to run in batch mode"""
        self.mn = mininet
        self._exit_hooks = getattr(self, "_exit_hooks", [])
        # Local variable bindings for py command
        self.locals = { 'net': mininet }
        # Attempt to handle input
        self.inPoller = poll()
        self.inPoller.register( stdin )
        self.inputFile = script
        Cmd.__init__( self, stdin=stdin, include_py=True, **kwargs )
        for hook in self._exit_hooks:
            self.register_cmdfinalization_hook(hook)

        self.default_error = '*** Unknown command: {}\n'
        if self.inputFile:
            self.do_run_script( self.inputFile )
            return

        self.py_locals = self.getLocals()
        self.initReadline()
        self.run()

    def sigint_handler(self, signum: int, frame) -> None:
        # Make sure no nodes are still waiting
        for node in self.mn.values():
            while node.waiting:
                self.pfeedback( f'...stopping {node}' )
                node.sendInt()
                node.waitOutput()
        super().sigint_handler(signum, frame)

    def do_help( self, line ):  # pylint: disable=arguments-differ
        "Describe available CLI commands."
        Cmd.do_help( self, line )
        if line == '':
            self.poutput( self.helpStr )

    readlineInited = False
    initReadline = CLI.initReadline
    run = CLI.run
    getLocals = CLI.getLocals
    helpStr = CLI.helpStr
    isatty = CLI.isatty
    precmd = CLI.precmd
    default = CLI.default
    waitForNode = CLI.waitForNode

    do_nodes = CLI.do_nodes
    do_ports = CLI.do_ports
    do_net = CLI.do_net
    do_sh = CLI.do_sh
    do_px = CLI.do_px
    do_pingall = CLI.do_pingall
    do_pingpair = CLI.do_pingpair
    do_pingpairfull = CLI.do_pingpairfull
    do_iperf = CLI.do_iperf
    do_iperfudp = CLI.do_iperfudp
    do_intfs = CLI.do_intfs
    do_dump = CLI.do_dump
    do_link = CLI.do_link
    do_xterm = CLI.do_xterm
    do_gterm = CLI.do_gterm
    do_x = CLI.do_x
    do_noecho = CLI.do_noecho
    do_dpctl = CLI.do_dpctl
    do_time = CLI.do_time
    do_links = CLI.do_links
    do_switch = CLI.do_switch
    do_wait = CLI.do_wait

    categorize((
        do_nodes, do_ports, do_net, 
        do_sh, do_px, do_pingall, 
        do_pingpair, do_pingpairfull, do_iperf,
        do_iperfudp, do_intfs, do_dump, 
        do_link, do_xterm, do_gterm,
        do_x, do_noecho, do_dpctl,
        do_time, do_links, do_switch,
        do_wait
    ), "Mininet")