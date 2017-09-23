#!/usr/bin/env python
import os
import sys
import signal
import time

user = sys.argv[1]
cmd = sys.argv[2]
cmd = cmd[0:7]

c = "ps -fu %s | grep python.*%s|grep -v grep" % (user, cmd)
f = os.popen(c)

lines = f.readlines()

for l in lines:
    if not "grep" in l:
        toks = l.split()
        pid = int(toks[1])
        try:
            os.kill(pid, signal.SIGINT)
        except:
            pass
        time.sleep(10)
        try:
            os.kill(pid, signal.SIGHUP)
            os.kill(pid, signal.SIGKILL)
        except:
            pass
