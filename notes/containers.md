Three concepts:

Namespace - What you can see 
Govern what "you" can see on the host machine
You don't actually have to set PID 1. Just the first process in a given namespace becomes PID 1. PID 1 is special. 
Signals it doesn't have a handler for `SIGTERM`, so a plain `SIGTERM` doesn't do anything to it. 
It has to reap orphaned zombie processes. 
If it dies, the kernel kills everything else in the namespace. This is why Docker stop sometimes hangs for 10 seconds, and this will become more relevant when building graceful shutdown. 

Even though they manually set the PID, the `ps` command is getting the process information from the `proc` directory. In order for `ps` inside the container to properly identify what PID 1 is, it's going to need its own `proc` directory. Mounting `proc` from inside the new PID namespace gives a view of that namespace's processes. `/rootfs/proc` is just the empty directory that it got mounted onto. 

Chroot - Where are you running from? 
You designate a directory that's supposed to be the root file system for the container. This generally contains the file system for what you're running. This is what's probably taking up the most space in a container image. 

After running `sleep` in a container, you can go on the host and search for a `sleep` process and see what the root directory it's running out of is. 

/proc is empty in the container at first
we need to mount the proc directory. But it's important we mount it from the namespace. 

Interesting that you have to unshare the container's mount with the host. 

Not a security boundary on its own. 

Chgrp - What you can use 
/sys/fs/cgroup Lists to see groups you can create, things like:
cpuset cpu io memory hugetlb pids rdma

my container build:

wget https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/alpine-minirootfs-3.24.2-x86_64.tar.gz
tar -xvf tarball -C rootfs
sudo unshare --pid --fork --mount --uts --net --mount-proc=/proc (I ran this by itself, and I think that it basically gave me my normal bash in a new namespace. Which is why bash was PID 1.)
sudo unshare --pid --fork --mount --uts --net --mount-proc=$HOME/code/minigrid/contain/rootfs/proc chroot $HOME/code/minigrid/contain/rootfs /bin/sh  (WORKED)


/ # ps
PID   USER     TIME  COMMAND
    1 root      0:00 /bin/sh
    2 root      0:00 ps
    I only see the two processes because those are the only two processes in the 'rootfs/proc` directory. 

/ # ip a
1: lo: <LOOPBACK> mtu 65536 qdisc noop state DOWN qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00  
    I think I only see a loopback because I didn't attach or give any network interfaces to this container. 

set a hostname, rooty. 

sudo ps -ef | grep /bin/sh ()


Why set memory.swap.max to 0?
    Presumably to prevent the container from using as much memory as it wanted, but swapping everything exceeding that to disk. I am waiting for some of the sleep processes to end. A worker that goes over its limit doesn't die. It gets slow, and a dead worker is easy to detect, but a slow one is hard. 
What gets killed when you hit the memory limit, the shell or tail? Who decides?
    The tail gets killed, not the shell. I think the OOM killer decides. The kill is limited to the C group, and the kernel picks a victim by checking the OOM score, which is mostly how much memory each process is using. You can protect a single process with `oom_score_adj`, or you can set `memory.oom.group` to kill the entire cgroup together. I'm thinking a grid worker wants the second one because that is its scalability unit, and it would be unfortunate if half of the grid worker died versus having the entire grid worker die. 
When the container's processes started sleep, how did those new processes end up in the cgroup without you adding them?
    I assumed these processes ended up in the C group because they were started by a process in the C group. In reality, a cgroup represents a virtual file system. Creating a directory there creates a kernel object, and all the information about that kernel object is stored as files in that virtual file system. 

    "Resource temporarily unavailable" is the right error here because currently there are 20 processes, and I do have permission to create more processes, but I am at the cap of processes that I can be running. I believe that there are 19 sleep processes because one of the processes the container is running is the shell. I think backing off And giving up after a set limit is probably the right answer. 



Final container script, run script with sudo :
#! /bin/sh
set -eu
rootfs_path="/home/wheels/code/minigrid/contain/rootfs"

mkdir -p /sys/fs/cgroup/minigrid

echo 50M > /sys/fs/cgroup/minigrid/memory.max
echo 0 > /sys/fs/cgroup/minigrid/memory.swap.max
echo 20 > /sys/fs/cgroup/minigrid/pids.max
echo $$ > /sys/fs/cgroup/minigrid/cgroup.procs 
exec unshare --pid --fork --mount --uts --net --mount-proc="$rootfs_path/proc" chroot "$rootfs_path" /bin/sh