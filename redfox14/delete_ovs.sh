# PARAMETER1: IP address of the pc
ovs-vsctl del-br br0
ifconfig eth0 $1 up