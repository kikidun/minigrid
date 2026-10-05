#! /bin/sh
set -eu
rootfs_path="/home/wheels/code/minigrid/contain/rootfs"

mkdir -p /sys/fs/cgroup/minigrid

echo 50M > /sys/fs/cgroup/minigrid/memory.max
echo 0 > /sys/fs/cgroup/minigrid/memory.swap.max
echo 20 > /sys/fs/cgroup/minigrid/pids.max
echo $$ > /sys/fs/cgroup/minigrid/cgroup.procs 
exec unshare --pid --fork --mount --uts --net --mount-proc="$rootfs_path/proc" chroot "$rootfs_path" /bin/sh