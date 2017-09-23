#!/usr/bin/env python
import os
import sys
import time
import serial
import random
from optparse import OptionParser
TIMEPERIOD=1.0
INIT="C,0,0,0,0\r"
ONE="PO,B,0,1\r"
ZERO="PO,B,0,0\r"
GAP=3
pattern=[1,2,3,5,7]


parser = OptionParser(usage="%prog: [options]")
parser.add_option("", "--dev", dest="dev", type="string", default="/dev/ttyACM0",
    help="Set BitWhacker device name")
parser.add_option("", "--pause", dest="pause", type="int", default=15,
    help="Initial pause time")
parser.add_option("", "--runtime", dest="runtime", type="int", default=60,
    help="Runtime before exit")

     
        
(options, args) = parser.parse_args()

try:
	srh = serial.Serial(options.dev, 115200, timeout=0)
except:
	print "No device %s" % options.dev
	print "Leaving"
	sys.exit()

time.sleep(options.pause)
	
srh.write(INIT)
then = time.time()
while time.time()-then < options.runtime:
    v = random.randint(0,len(pattern)-1)
    srh.write(ONE)
    time.sleep(pattern[v]*TIMEPERIOD)
    q=srh.read(100)
    srh.write(ZERO)
    time.sleep(GAP*TIMEPERIOD)

srh.write(ZERO)
srh.read(1000)
time.sleep(2)
srh.close()
    
    
