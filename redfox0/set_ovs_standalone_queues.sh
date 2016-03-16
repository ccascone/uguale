# PARAMETER1: queuelen
# set a pfifo on interfaces and set the queuelen
for i in 1 2 3 4
do
    ifconfig eth$i txqueuelen $1
    tc qdisc del dev eth$i root
    tc qdisc add dev eth$i root handle 1: pfifo
done