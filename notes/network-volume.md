docker run -d --name alpine1 alpine /bin/sh -c "echo 'Hello'; sleep infinty"

docker exec -it alpine1 /bin/sh

pinging container vis hostname doesn't work on default bridge, but IP does

created a bridge network called my_network and launched 2 containers onto it
    ping by name and IP work
    resolv.conf has:
    nameserver 127.0.0.11
    options ndots:0

Alpine 1 on bridge, alpine2 on my_network
    no ping by IP or hostname
    Add alpine 1 to my_network
        ping both ways

Add nginx container: 
    docker run --name nginx -p 8080:80 -d nginx

iptables output:
    Chain PREROUTING (policy ACCEPT)
    target     prot opt source               destination         
    DOCKER     0    --  0.0.0.0/0            0.0.0.0/0            ADDRTYPE match dst-type LOCAL

    Chain INPUT (policy ACCEPT)
    target     prot opt source               destination         

    Chain OUTPUT (policy ACCEPT)
    target     prot opt source               destination         
    DOCKER     0    --  0.0.0.0/0           !127.0.0.0/8          ADDRTYPE match dst-type LOCAL

    Chain POSTROUTING (policy ACCEPT)
    target     prot opt source               destination         
    MASQUERADE  0    --  172.18.0.0/16        0.0.0.0/0           
    MASQUERADE  0    --  172.17.0.0/16        0.0.0.0/0           

    Chain DOCKER (2 references)
    target     prot opt source               destination         
    DNAT       6    --  0.0.0.0/0            0.0.0.0/0            tcp dpt:8080 to:172.17.0.3:80

I count 6 interfaces that arent the host:
    docker0 - default bridge
    br-f3a3ba5f81ee - my_network
    vethd85 - alpine1 my_network
    vetha27 - alpine2 default
    veth4c2 - alpine2 my_network
    veth6d8 - nginx default

Volumes
Why does name resolution only work on user-defined networks?
    Containers that attach to the default bridge network receive a copy of the hosts/etsy/resolve.com file. Containers that attach to a custom network use Docker's embedded DNS server at 127.0.0.11.
    The default bridge is the legacy network and is kept the way that it is for backwards compatibility. 
Named volume vs bind mount: which would you use for the results DB, and which for mounting config into a worker?
    Named: Managed by Docker, typically in /var/lib/docker/volumes. 
    Bind: Uses an absolute path anywhere on the host. Host-dependent. 
    Named mount for the database Permissions should just work, and it's not tied to a path on one host. bind mount for config. Edited on the host. It lives in Git and gets mounted read-only, so the worker can't change it. 
Say a coordinator and workers will run on different VMs. Does a bridge network help with that at all? What will they actually use to reach each other?
    I don't think a bridge network will help with that. I think they will need an overlay network istead of a bridge network. Apparently, overlay networks need Docker Swarm. Containers will reach each other across virtual machines through the virtual machine's own network. The coordinator will publish a port, and workers will connect to that VM's IP or hostname. 

--network host vs -p
    Hard to say exactly what each costs. But putting a container on the network gives it access to everything on that network. Doing a port mapping exposes the container to an external network. For example, a database that only ever gets hit by containers can just live happily on a network, but a web application that will be accessed from the outside world will need a port mapping. I think the port mappings will need a firewall entry. 

    actual answer: Network host just skips the entire Docker networking stack: no bridge, no NAT. If it listens on port 5000, the VM is listening on port 5000. There's no network isolation, but you gain no NAT overhead, and the containers use real interfaces and client IPs. 

    Using `-p` is a NAT hop via IP tables, and you gain isolation and port remapping. 

    For a bind mount, there's no translation between the host and the container. A container will write the files using the UID and GID of the user in the container. That might not necessarily match something on the host. On worker VMs, that's how we get results that end up undeletable by the service account. We can fix it with a user line in the Docker file or "--user $(id -u):$(id -g)"