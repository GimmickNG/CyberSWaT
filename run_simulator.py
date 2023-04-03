#!/usr/bin/env python3
"""
simple-cps run.py
"""

# import logging
from subprocess import Popen
from typing import IO, Dict, Optional, TextIO, Tuple, cast
from mininet.net import Mininet
from nodecli import NodeCLI as CLI
from mininet.link import TCLink
from datetime import datetime

from tqdm import tqdm
from time import sleep, time
from topo import ICSTopo
from common import logger
from typing import List, IO

import argparse
import tempfile
import os, sys
import utils

def wait_progress(popen_partial, max_lines, total_progress, out: IO, wait=True):
    popen_partial(stdout=out, stderr=out)
    def return_gen(outfile, max, total, wait):
        last_tell = 0
        while out.tell() < max:
            if wait:
                sleep(0.1)
            diff = (out.tell() - last_tell) * (total / max)
            yield diff
            last_tell = out.tell()
    return out, return_gen(out, max_lines, total_progress, wait=wait)
    
def start(args):
    historian = None
    net: Optional[Mininet] = None
    started_devices: Dict[str, Tuple[Popen, TextIO, TextIO]] = {}

    try:
        with tqdm(total=100) as progress, open(os.devnull, 'w') as null, tempfile.NamedTemporaryFile('w+', 64) as man_out:
            progress.set_description("Starting topology v2...")
            topo = ICSTopo() # nodes=sdn_args.nodes, arg_hosts=sdn_args.hosts, bw=sdn_args.bw, loss=sdn_args.loss, delay=sdn_args.delay, random=sdn_args.random)
            progress.update(20)
            
            progress.set_description("Starting Mininet...")
            net = Mininet(topo=topo, link=TCLink, autoSetMacs=True, controller=None)
            progress.update(20)

            progress.set_description("Initializing network...")
            net.start()

            # setup remote service
            hmi, historian = net.get('hmi'), net.get('historian')
            
            progress.set_description("Setting up NAT for remote router...")
            net.get('rem_r').cmd('make', 'router-remote')
            sleep(0.1)
            progress.update(10)
            
            progress.set_description("Setting up NAT for local router...")
            net.get('gate_r').cmd('make', 'router-gate')
            sleep(0.1)
            progress.update(10)
            
            progress.set_description("Starting remote AD servers...")
            net.get('rem_dsc').popen('make', 'remote-discovery', cwd="rest-service/compute", stdout=null, stderr=null)
            sleep(0.1)
            progress.update(10)
            net.get('rem_srv').popen('make', 'remote-server', cwd="rest-service/", stdout=null, stderr=null)
            sleep(0.1)
            progress.update(10)
            
            progress.set_description("Starting remote AD compute service...")
            net.get('rem_cpu').popen('make', 'remote-compute', cwd="rest-service/compute", stdout=null, stderr=null)
            sleep(0.1)
            progress.update(10)
            
            progress.set_description("Starting historian DB...")
            """man_out, wait_gen = wait_progress(
                functools.partial(historian.popen, 'make', 'start-historian'),
                max_lines=10000, total_progress=progress.total - progress.n, wait=True
            )
            for diff in wait_gen:
                if progress.n + diff > progress.total:
                    diff = progress.total - progress.n
                progress.update(diff)
            """
            #client = hmi.popen('make', 'hmi-client', stdout=sys.stdout, stderr=sys.stdout)

            progress.update(progress.total - progress.n)
            progress.set_description("Setup complete.")
            progress.close()
            
            runnable_devices = utils.get_field_devices(net, topo.device_list)
            if 'n' not in input("Test OT network status? (Yn): ").lower():
                utils.ping_devices(net, runnable_devices, verbose=True, timeout=0.05)

            #logger.output("Opening HMI WebView", '\n')
            #hmi.popen('make', 'historian-viewer', stdout=null, stderr=null)
            # clear argv so that Cmd2 does not use it
            sys.argv = sys.argv[:1] 
            # pass by reference
            CLI(net, started_devices=started_devices)
    except KeyboardInterrupt:
        logger.output("Stopping simulation...", '\n')
    except Exception as err:
        logger.error(f"Error: [ {str(err).strip()} ]", '\n')
        #logger.exception(err, exc_info=True)
    finally:
        logger.output(f"Shutting down at {datetime.now()}...", '\n')
        for popen, out, err in started_devices.values():
            popen.terminate()
            out.close()
            err.close()
        if historian is not None:
            historian.popen("make", "stop-historian")
        if net is not None:
            net.stop()
        

if __name__ == "__main__":
    # TODO finish support for these arguments
    parser = argparse.ArgumentParser(description="CyberSWaT Runner")
    parser.add_argument("--ics-topos", "-t", default=(), nargs='+', help="A list of external ICS OT networks to attach to this simulator, for which a full ICS network (e.g. control/DMZ & admin network) will be attached. "
                                                                         "Must be Python files with a `get_topo()` function defined in them, which returns the name of a LinuxRouter host.")
    parser.add_argument("--other-topos", "-o", default=(), nargs="+", help="A list of other networks to attach to this simulator. Must be Python files with a `get_topo()` function defined in them, which returns a LinuxRouter host. "
                                                                           "Note: NAT will be enabled on this host, and external routes set up automatically.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Sets the log level to DEBUG instead of INFO.")

    args = parser.parse_args()
    start(args)
