An overlay file system combines an upper file system and a lower file system into the combined overlay file system. 

If file A exists in both file systems, the object in the upper file system is visible while the object in the lower file system is hidden, or if it's a directory merged with the upper object. 

mount -t overlay overlay -olowerdir=/lower upperdir=/upper, workdir=/work /merged

The previous command creates an overlay file system called `merged`, which consists of `lower` as its lower directory and `upper` as its upper directory. 

I ran the command, but it appears that there are two work directories. 

Editing a.txt in merged puts a file in upper
I cannot delete b.txt in merged, no such file or directory from cli. Deleted from ui and got the following file:
c--------- 2 root   root   0, 0 Oct 12 11:37 b.txt
adding c.txt to merged adds it to upper through the "copy-up" operation.
    copy-up copies the entire file, so appending one line to a 2 GB log in an image layer costs a 2 GB copy.

Copy-Up - 
    Modifying a file in lower creates a copy of the file in upper and edits the copy
Opaque Directory - 
    Where the upper filesystem contains an opaque directory, any directory in the lower filesystem with the same name is ignored.
Whiteout - 
    A whiteout is created as a character device with 0/0 device number or as a zero-size regular file with the xattr “trusted.overlay.whiteout”.

    When a whiteout is found in the upper level of a merged directory, any matching name in the lower level is ignored, and the whiteout itself is also hidden.

    Basically, whiteout is for a single file, and an opaque directory is for hiding an entire directory. 
Work Directory - 
    Copyups and whiteouts get built in, work first, and then they are renamed into upper in a single step. Crashes leave junk in the work directory. Never a half-copied file in upper. A rename is only atomic within one filesystem, which is why work and upper must be on the same one.