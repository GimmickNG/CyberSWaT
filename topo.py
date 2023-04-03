import ipaddress as ipy
from mininet.topo import Topo
from mininet.util import irange
from mininet.examples.linuxrouter import LinuxRouter
from typing import AnyStr, List, Set, Tuple, Union
from common import getIP, getRoute, getWanIP

class ICSTopo( Topo ):
    def build_admin_network(self, starting_network: ipy.IPv4Network, external_ip: ipy.IPv4Address) -> Tuple[str, ipy.IPv4Network]:
        # create router with default route to external ip
        gate_r: str = self.addHost('gate_r', cls=LinuxRouter, ip=self.get_ip(external_ip, 31), defaultRoute=self.get_route(external_ip))
        
        # get all subnets for the starting network
        netmask = 28
        admin_subnets = starting_network.subnets(new_prefix=netmask)
        
        # router-switch subnet, for connecting computers in admin network to this router
        net_hosts = next(admin_subnets).hosts()
        admin_rip = next(net_hosts)
        default_route = self.get_route(admin_rip)

        self.comps: List[str] = [
            self.addHost(name=f'cadcomp{i + 1}', ip=self.get_ip(host_ip, netmask), defaultRoute=default_route)
        for i, host_ip in enumerate(net_hosts)]

        adnet: str = self.addSwitch('adnet', dpid=self.get_next_dpid(), failMode='standalone')
        for cad_comp in self.comps:
            self.addLink(adnet, cad_comp)
        self.addLink(adnet, gate_r, intfName1='adbus-gate_r', intfName2='gate_r-adbus', params2={'ip': self.get_ip(admin_rip, netmask)})

        # router PTP subnet, for connecting two routers
        router_ptp = next(next(admin_subnets).subnets(new_prefix=31))

        return gate_r, router_ptp

    def build_control_network(self, starting_network: ipy.IPv4Network, external_ip: ipy.IPv4Address) -> Tuple[str, ipy.IPv4Network]:
        # create router with default route to external ip
        org_r: str = self.addHost('org_r', cls=LinuxRouter, ip=self.get_ip(external_ip, 31), defaultRoute=self.get_route(external_ip))
        
        # get all subnets for the starting network
        netmask = 29
        control_subnets = starting_network.subnets(new_prefix=netmask)
        
        # router-switch subnet, for connecting hmi and historian in control network to this router
        net_hosts = next(control_subnets).hosts()
        control_rip = next(net_hosts)
        default_route = self.get_route(control_rip)

        orm_s: str = self.addSwitch('orm_s', dpid=self.get_next_dpid(), failMode='standalone')
        self.addLink(orm_s, org_r, intfName1='orm_s-org_r', intfName2='org_r-orm_s', params2={'ip': self.get_ip(control_rip, netmask)})

        for device, ip in zip(("hmi", "historian"), net_hosts):
            self.addLink(
                orm_s, self.addHost(device, ip=self.get_ip(ip, netmask), defaultRoute=default_route),
                intfName1=f'orm_s-{device}', intfName2=f'{device}-orm_s'
            )

        # router PTP subnet, for connecting two routers
        router_ptp = next(next(control_subnets).subnets(new_prefix=31))
        
        return org_r, router_ptp

    def build_ot_network(self, starting_network: ipy.IPv4Network, external_ip: ipy.IPv4Address) -> Tuple[str, ipy.IPv4Network]:
        from simulator.config import walk_devices, create_device_config, ExecutableNode, NETMASK as netmask

        def create_router(route_getter):
            class OTRouter(LinuxRouter):
                def config(self, **params):
                    super().config(**params)
                    
                    # add routes to router
                    self.routes = route_getter()
                    for route in self.routes:
                        self.cmd(f"ip route add {route}")

                def terminate(self):
                    for route in self.routes:
                        self.cmd(f"ip route del {route}")
                    super().terminate()
            
            return OTRouter


        # create router with default route to external ip
        device_ips: Set[str] = set()
        device_list, remaining_networks = create_device_config(
            starting_networks=starting_network.subnets(new_prefix=netmask - 1),
            external_ip=external_ip
        )
        ot_subnets = iter(remaining_networks)

        # The PLANT router is the first (and only) device in the device_list, as it contains the others below it;
        # create a router for it, and then expand the device list to include the others in the loop below
        ot_routes = []
        plant: ExecutableNode = device_list[0]
        plant_rip = plant.get_ip(with_port=False)
        plant_router: str = self.addHost(
            plant.get_short_name(), cls=create_router(lambda: ot_routes), 
            ip=self.get_ip(external_ip, 31), defaultRoute=self.get_route(external_ip)
        )

        plant_router_net = next(ot_subnets).subnets(new_prefix=31)
        for i, router in enumerate(plant.devices):
            # first element of walk_devices() is the router itself, but 
            # we don't want it to appear in the loop below, so consume 
            # it now
            router_devices = walk_devices([router])
            router = next(router_devices)

            # get route and ip address info of stage (router <-> router)
            stage_rip, plant_rip = next(plant_router_net).hosts()

            # create switch for this stage that connects to the router
            switch_name, router_name = f"fs{i+2}", router.get_short_name()

            stage_router = self.addHost(router_name, cls=LinuxRouter, ip=self.get_ip(stage_rip, 31), defaultRoute=self.get_route(plant_rip))
            self.addLink(
                stage_router, plant_router, intfName1=f"{router_name}-{plant_router}", intfName2=f"{plant_router}-{router_name}",
                params1={'ip': self.get_ip(stage_rip, 31)}, params2={'ip': self.get_ip(plant_rip, 31)}
            )
            
            # add switch that is connected to devices
            # router.get_ip() is the internal address of the router,
            # whereas (stage_rip, mtu_rip) are the external addresses
            # of the router and its mtu_r complement (ptp ip address)
            internal_rip = ipy.IPv4Address(router.get_ip(with_port=False))
            internal_subnet = ipy.IPv4Network((internal_rip, netmask), strict=False)
            ot_routes.append(f"{internal_subnet} via {stage_rip}")

            stage_route = self.get_route(internal_rip)
            stage_switch = self.addSwitch(switch_name, dpid=self.get_next_dpid(), failMode='standalone')
            self.addLink(
                stage_switch, stage_router, intfName1=f"{switch_name}-{router_name}", intfName2=f"{router_name}-{switch_name}",
                params2={'ip': self.get_ip(internal_rip, netmask)}
            )

            # connection: plant <-> router <-> plc_net <-> device
            for device in router_devices:
                device_ip = device.get_ip(with_port=False)
                if device_ip not in device_ips:
                    device_ips.add(device_ip)
                    self.addLink(stage_switch, self.addHost(
                        device.get_short_name(), defaultRoute=stage_route, ip=self.get_ip(device_ip, netmask)
                    ))

        self.device_list = device_list
        # router PTP subnet, for connecting two routers
        router_ptp = next(next(ot_subnets).subnets(new_prefix=31))

        return plant_router, router_ptp

    def build_remote_service(self, starting_network: ipy.IPv4Network, external_ip: ipy.IPv4Address) -> Tuple[str, ipy.IPv4Network]:
        rem_r: str = self.addHost("rem_r", cls=LinuxRouter, ip=self.get_ip(external_ip, 31), defaultRoute=self.get_route(external_ip))
        
        # don't bother implementing vlsm as this is not a realistic use case
        # use the 172.16.x.x/24 subnet and give each device 1 subnet
        # TODO try and use automatic IP for everything - allocate IPs using ipaddress, and then use those in makefile etc.
        netmask = 28
        internal_subnets = starting_network.subnets(new_prefix=netmask)
        net_hosts = next(internal_subnets).hosts()
        
        # create switch
        rem_is: str = self.addSwitch("rem_is", dpid=self.get_next_dpid(), failMode='standalone')
        switch_ip = next(net_hosts)
        self.addLink(rem_r, rem_is, intfName1="rem_r-rem_is", intfName2="rem_is-rem_r", params1={'ip': self.get_ip(switch_ip, netmask)})
        
        for device, ip in zip(("rem_srv", "rem_cpu", "rem_dsc"), net_hosts):
            self.addHost(device, ip=self.get_ip(ip, netmask), defaultRoute=self.get_route(switch_ip))
            self.addLink(device, rem_is, intfName1=f"{device}-rem_is", intfName2=f"rem_is-{device}")
        

        # router PTP subnet, for connecting two routers
        router_ptp = next(next(internal_subnets).subnets(new_prefix=31))

        return rem_r, router_ptp

    def build_internet(self, chain_size: int, start: str, end: str, starting_network: ipy.IPv4Network, ending_network: ipy.IPv4Network) -> None:
        start_addr, end_addr = int(starting_network.network_address), int(ending_network.network_address)
        networks: List[ipy.IPv4Network] = [ipy.IPv4Network((addr, 31), strict=False) for addr in range(start_addr, end_addr, (end_addr - start_addr) // chain_size)][:chain_size] + [ending_network]
        ext_nets: List[str] = [self.addHost(
            f"enet_{dest+1}", ip=self.get_ip(router_ip := next(rip.hosts()), 31), defaultRoute=self.get_route(router_ip)
        ) for dest, rip in enumerate(networks[1:-1])] + [end]
        src_nets: List[str] = [start] + ext_nets[:-1]

        for prev_network, prev_net, ext_net in zip(networks, src_nets, ext_nets):
            prev_address, curr_address = prev_network.hosts()
            self.addLink(
                ext_net, prev_net, intfName1=f'{ext_net}-{prev_net}', intfName2=f'{prev_net}-{ext_net}',
                params1={'ip': self.get_ip(curr_address, 31)}, params2={'ip': self.get_ip(prev_address, 31)}
            )

    def build(self, *args, **params):
        super().build(*args, **params)

        self.next_dpid: int = 0

        ics_router, ics_enet = None, ipy.IPv4Network((self.generate_public_ip(), 31), False)
        external_ip, prev_router, prev_router_ip = next(ics_enet.hosts()), None, None
        for build_net, subnet in zip(
            (self.build_admin_network, self.build_control_network, self.build_ot_network), 
            ipy.IPv4Network("172.16.0.0/12").subnets(new_prefix=22)
        ):
            # create hierarchical network with outer layer (admin net) getting external IP
            # and lower layers (control, OT) getting IP addresses of routers in layers before it
            # e.g. public (random) -> 172.16.0.0 -> 172.16.4.0 -> 172.16.8.0
            router, external_connections = build_net(subnet, external_ip)
            if prev_router is not None and prev_router_ip is not None:
                self.addLink(
                    prev_router, router, intfName1=f"{prev_router}-{router}",
                    intfName2=f"{router}-{prev_router}", params2={'ip': self.get_ip(external_ip, 31)},
                    params1={'ip': self.get_ip(prev_router_ip, 31)},
                )
            elif ics_router is None:
                ics_router = router
            prev_router, (prev_router_ip, external_ip) = router, tuple(external_connections.hosts())
        
        rem_enet = ipy.IPv4Network((self.generate_public_ip(), 31), False)
        remote_router, remote_internal = self.build_remote_service(
            next(ipy.IPv4Network("172.16.0.0/12").subnets(new_prefix=24)), next(rem_enet.hosts())
        )

        if ics_router is not None:
            self.build_internet(30, ics_router, remote_router, ics_enet, rem_enet)

    def generate_public_ip(self) -> ipy.IPv4Address:
        from random import getrandbits

        while True:
            address = ipy.IPv4Address(getrandbits(32))
            if address.is_global:
                return address

    def get_route(self, address: ipy.IPv4Address) -> str:
        return f"via {address.compressed}"

    def get_ip(self, address: Union[ipy.IPv4Address, AnyStr], netmask: Union[int, AnyStr]) -> str:
        if isinstance(address, ipy.IPv4Address):
            return f"{address.compressed}/{netmask}"
        return f"{address}/{netmask}"

    def get_next_dpid(self) -> str:
        next_dpid = self.next_dpid
        self.next_dpid += 1
        return str(next_dpid)

class SimplifiedICSTopo( Topo ):
    """
    A simplified version of the above ICS topology.  Nodes within the ICS are folded into 
    one 'ics' node since this topology mainly focuses on the interactions between the ICS
    and the remote server;  traffic within the ICS is considered to have practically zero
    delay.
    """ 

    def build(self, *args, **params):
        super().build(*args, **params)

        gate_r = self.addHost('gate_r', cls=LinuxRouter, ip=getIP('gate_r'), defaultRoute=getRoute('rem_r'))
        adbus = self.addSwitch('adbus', dpid='99', failMode='standalone')
        hmi = self.addHost('hmi', ip=getIP('org_r-adbus'), defaultRoute=getRoute('gate_r'))
        
        self.addLink(adbus, gate_r, intfName1='adbus-gate_r', intfName2='gate_r-adbus', params2={'ip': getIP('gate_r')})
        self.addLink(hmi, adbus, intfName1='hmi-adbus', intfName2='adbus-hmi')

        rem_is = self.addSwitch("rem_is", dpid='90', failMode='standalone')
        rem_r = self.addHost("rem_r", cls=LinuxRouter, ip=getWanIP("rem_r"), defaultRoute=getRoute('gate_r-rem_r'))
        rem_ad = self.addHost("rem_srv", ip=getIP("rem_srv"), defaultRoute=getRoute('rem_r-rem_is'))
        
        #connect remote service to wan
        net_start, net_prev, ext_net = None, None, None
        net_name, nlinks = "enet_%i", params.get("num_links", 30)
        if nlinks > 1:
            for src in range(0, nlinks):
                dest = src + 1
                net_prev, ext_net = ext_net, self.addSwitch(net_name % dest, dpid=str(src), failMode='standalone')
                if net_start is None:
                    net_start = ext_net
                elif net_prev:
                    self.addLink(
                        ext_net, net_prev,
                        bw=params.get('bandwidth', 1000),
                        delay=f"{params.get('delay', 1)}ms",
                        loss=params.get('loss', 0),
                        jitter=f"{params.get('jitter', 0)}ms",
                        intfName1='%s-%s' % (net_name % dest, net_name % src),
                        intfName2='%s-%s' % (net_name % src, net_name % dest)
                    )
            self.addLink(gate_r, net_start, intfName1="gate_r-rem_r", params1={'ip': getWanIP('gate_r-rem_r')})
            self.addLink(net_prev, rem_r, intfName2="rem_r-gate_r", params2={'ip': getWanIP('rem_r')})
        else:
            self.addLink(
                gate_r, rem_r, 
                intfName1="gate_r-rem_r", 
                intfName2="rem_r-gate_r",
                loss=params.get('loss', 0),
                bw=params.get('bandwidth', 1000),
                delay=f"{params.get('delay', 1)}ms",
                jitter=f"{params.get('jitter', 0)}ms",
                params1={'ip': getWanIP('gate_r-rem_r')}
            )

        self.addLink(rem_r, rem_is, intfName1="rem_r-rem_is", intfName2="rem_is-rem_r", params1={'ip': getIP('rem_r-rem_is')})
        self.addLink(rem_is, rem_ad, intfName1="rem_is-rem_ad", intfName2="rem_ad-rem_is")