from mininet.log import lg as logger
from os.path import abspath, join
import socket, json

with open(abspath(join(__file__, "../ip_list.json")), "r") as data:
    all_data = json.loads(data.read())
    IP, NETMASK = all_data["IP"], all_data["NETMASK"]

def getIP(ip, m=True, s=None):
    if m:
        return IP[ip] + (NETMASK if s is None else "/%i" % s)
    return IP[ip]

def getRoute(ip, **args):
    return 'via ' + getIP(ip, m=False)

def getPrivateIP(ip, m=True):
    return getIP(ip, m=m, s=NETMASK)

def getWanIP(ip, m=True):
    return getIP(ip, m=m, s=8)

def getSubnet(ip_name, s=None):
    ip = getIP(ip_name, s=s)
    ip_idx = ip.find('/')
    mask = ip[ip_idx:] if ip_idx >= 0 else "/32"
    mask = int(mask[1:])
    return '%s%s/%i' % ('.'.join(ip.split(".")[:mask//8]), (".0"*((32-mask)//8)), mask)

def create_socket(ip, port, bind=False):
    if bind:
        operation = "bind socket"
    else:
        operation = "connect"
    address = ip + ":" + str(port)
    logger.output("Attempting to " + operation + " to: " + address, "\n")
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if bind:
                sock.bind((ip, port))
            else:
                sock.connect((ip, port))
            break
        except socket.error as err:
            logger.output("Error occurred when binding/connecting socket: ", err)
            pass
    logger.output("Success [" + operation + "] for address " + address, "\n")
    return sock
