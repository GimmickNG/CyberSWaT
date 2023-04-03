#!/usr/bin/env python3
"""
simple-cps run.py
"""

# import logging
from typing import Optional, cast
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.node import Host
from mininet.log import setLogLevel
#from mininet.topo import SingleSwitchTopo

from tqdm.auto import tqdm, trange
from time import sleep, time
from common import logger
from datetime import datetime

import uuid
import json
import argparse
import os, sys

from topo import SimplifiedICSTopo

def get_dir(dir_name) -> str:
    from os.path import abspath, join

    return abspath(join(__file__, dir_name))

def start(net: Mininet, progress:Optional[tqdm]=None, **kwargs):
    # declare possibly unbound variables
    try:
        if progress is None:
            progress = tqdm(total=100)
        remaining_progress = 100 - progress.n
        frequency = kwargs.get("frequency", 1)

        net.start()

        progress.set_description("Setting up NAT for local router...")
        net.get('gate_r').cmd('make', 'router-gate')
        sleep(0.1)
        progress.update(10)
        
        # setup remote service
        rem_srv = net.get('rem_srv')
        progress.set_description("Setting up NAT for remote router...")
        net.get('rem_r').cmd('make', 'router-remote')
        sleep(0.2)
        progress.update(10)

        # suppress ping output
        progress.set_description("Ensuring connectivity between ICS and remote server...")
        setLogLevel('error')
        ping_data = net.pingFull(net.get('gate_r', 'rem_r'), count=20)
        setLogLevel('output')

        with open(os.devnull, 'w') as null:
            out_str = f"Run parameters: {kwargs} \nPing results: \n"
            for node, dest, ping_outputs in ping_data:
                #ping_outputs => sent, received, rttmin, rttavg, rttmax, rttdev
                out_str += " - %s -> %s: %i sent, %i received; min/avg/max/dev %.3f/%.3f/%.3f/%.3f \n" % ((node, dest) + ping_outputs)

            progress.set_description("Starting remote AD servers...")

            # add delay of 120 seconds to ensure both are started up and waiting before running
            start_time = int(time() + kwargs.get("start_delay", 15))
            with open('./server_settings.json', 'w') as settings:
                json.dump({
                    'key': uuid.uuid4().hex,
                    'start_time': start_time,
                    'frequency': frequency
                }, settings)

            server = rem_srv.popen(['make', 'remote-server'], cwd="rest-service/", stdout=null, stderr=null)
            while not len(rem_srv.cmd('pgrep', 'flask')):
                sleep(0.2)
            progress.update(remaining_progress * .5)

            progress.update(progress.total - progress.n)
            progress.set_description("Setup complete.")
            progress.close()
            logger.output(out_str)

            hmi = net.get('hmi')
            client = hmi.popen(['make', 'ad-client'], stdout=sys.stdout, stderr=sys.stderr, cwd='sim-client/')
            dashboard = hmi.popen(['make', 'dashboard'], stdout=null, stderr=null, cwd='sim-client/')
            logger.output("Starting client in %i seconds at %s.\n" % (int(start_time - time()), datetime.fromtimestamp(start_time)))

            CLI(net)
            #try:
            #    client.wait()
            #except KeyboardInterrupt:
            if True:
                dashboard.terminate()
                client.terminate()
                server.terminate()
                rem_srv.popen("pkill", "flask")
                logger.output('\n')
    except KeyboardInterrupt:
        logger.output("Exiting...")
    except Exception as err:
        logger.error(err)
    finally:
        net.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remote Delay Tester")
    parser.add_argument("--frequency", "-f", type=int, default=1, help="Data collection & sending frequency (Hz)")
    parser.add_argument("--link-bandwidth", "-b", type=float, default=1000, help="Link bandwidth (Mbps)")
    parser.add_argument("--link-jitter", "-j", type=float, default=0, help="Link jitter (ms)")
    parser.add_argument("--link-loss", "-l", type=float, default=0, help="Link loss (% between 0 and 100)")
    parser.add_argument("--link-delay", "-d", type=float, default=0, help="Link delay (ms)")
    parser.add_argument("--num-links", "-n", type=int, default=30, help="Number of links between ICS and AD server")
    parser.add_argument("--start-delay", "-s", type=float, default=15, help="Number of seconds to wait before starting inference."
                        "Used to ensure client and server are both running first.")
    args = parser.parse_args()

    try:
        with tqdm(total=100) as setup_progress:
            setup_progress.set_description("Starting topology...")
            topo = SimplifiedICSTopo(
                bandwidth=args.link_bandwidth, jitter=args.link_jitter,
                delay=args.link_delay, loss=args.link_loss, num_links=args.num_links
            )
            setup_progress.update(30)

            setup_progress.set_description("Starting Mininet...")
            net = Mininet(topo=topo, link=TCLink, controller=None)#, autoSetMacs=True)
            setup_progress.update(30)

            setup_progress.set_description("Initializing network...")
            start(net, setup_progress, **vars(args))
    except Exception as err:
        logger.error("Error: [ %s ]\n" % str(err).strip())
        logger.error("Shutting down...\n")
