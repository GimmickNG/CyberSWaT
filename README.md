# CyberSWaT
Extension of the SWaT simulator by Chen et al. to use Modbus to communicate between field devices. 

## Commands
Below are a list of the supported commands for interfacing with devices in CyberSWaT's OT network.

- `otdump`: Prints out tag values of a field device, including debug tags (such as `Run_FBD`, as well as intrinsic debug tags beginning with `debug`, such as debug cycles).
  - Syntax: `otdump <target> [--from <source>]`
- `otset`: Used to modify a field device’s tags.
  - Syntax: `otset <target> <tag>=<value>... [--from <source>]`
- `otlinks`: Displays all the high-level links between field devices, as defined in their code; links that are last known to be "up" are highlighted green, and those that were last "down" are highlighted red.
- `otping`: Queries a field device from another node in the network (by default, from the central `PLANT` router) to determine if its server is reachable or not. Fails if a device is not started on its node, even if the node is reachable via Mininet's ping command.
  - Syntax: `otping <target> [--from <source>]`
- `otpingall`: Queries each field device's targets, and uses this information to display devices that are reachable and unreachable from a given field device (e.g. `PLC101->LIT101`). Useful for diagnosing faulty devices, and/or connection issues.
- `otstat`: Shows the status of each field device acting as a server (or the equivalent, if a protocol apart from Modbus is used).
  - Syntax: `otstat [<device>...]`
- `query`: Opens a REPL to allow the user to query a field device. At present, uses the Pymodbus REPL for this task.
  - Syntax: `query <device>`
- `scenario`: Allows the user to select a different network configuration for field devices. Useful for diagnosing connection issues, or for working with field devices at different levels of granularity.
  - For more information, type `scenario -h` at the command line.
- `treevis`: Displays links between devices in the network as a tree. Useful for visualizing the path taken by packets in the network.
  - Syntax: `treevis [<root>]`
- `logdump`: Outputs the operational logs of a particular field device's script.
  - Syntax: `logdump <device>`
- `errdump`: Outputs a field device script's error logs, which can help in understanding why a device may have crashed during operation.
  - Syntax: `errdump <device>`
- `dump`: The extended version of Mininet's dump command, which includes options to display a device's parents (i.e. the devices which it receives commands from) and/or its targets (the devices it sends commands to).
  - Syntax: `dump <device> [-p] [-c]`
