# this module will be imported in the into your flowgraph
#
# Configuration management for Simple RA
#
# Marcus Leech, Science Radio Laboratories, Inc.
#
import os
import signal
import numpy
import math
import sys
import time
import serial
import stat

cal_ontime = 30
CAL_INIT_REQUIRED = 0
CAL_WAITING = 1
CAL_ON = 2
CAL_BADDEVICE = 3
CAL_MANUAL = 4
cal_state = CAL_WAITING
serh = None

def calib_onoff_auto(depvar, devname, baudrate, initstring, onstring, offstring, lterm, every, seconds):
    global serh
    global cal_state
    global cal_ontime
    global CAL_INIT_REQUIRED
    global CAL_WAITING
    global CAL_ON
    global CAL_BADDEVICE
    global CAL_MANUAL
    
    f = open ("/tmp/ra_sender.pid", "w")
    f.write(str(os.getpid())+"\n")
    f.close()

    if (os.path.exists(devname)):
        s = os.stat(devname)
        if stat.S_ISREG(s.st_mode):
            if (s.st_size > 0):
                return "ON"
            else:
                return "OFF"
 
    #sys.stderr.write("Here I am"+"\n")

    if (cal_state == CAL_BADDEVICE):
        return "BAD-DEVICE"

    if (len(devname) == 0 or devname == "none"):
        return "OFF"

    if (cal_state == CAL_WAITING):
        t = int(time.time())
        f = t % int(every)
        if (f <= 4) and serh == None:
            #sys.stderr.write( "transitioning to ON at %d\n" % t)
            try:
               serh = serial.Serial (devname, baudrate, timeout=0)
            except:
                cal_state = CAL_BADDEVICE
                return "OFF"
            time.sleep(0.1)
            serh.setDTR(True)
            serh.write (initstring+lterm)
            serh.read (1000)
            cal_state = CAL_ON
            cal_ontime = seconds+1
            x=serh.read (1000)

    if (cal_state == CAL_ON):
        cal_ontime -= 1
        if ((cal_ontime % 3) == 0):
            # send onstring
            serh.write (onstring+lterm)
            #sys.stderr.write( "in CAL_ON, send onstring")
            x=serh.read(100)
        if (cal_ontime <= 0):
            t = int(time.time())
            #sys.stderr.write( "transitioning to OFF at %d\n" % t)
            # send offstring
            serh.setDTR(False)
            serh.write (offstring+lterm)
            x=serh.read(1000)
            cal_state = CAL_WAITING
            time.sleep(0.1)
            serh.write(offstring+lterm)
            time.sleep(0.1)
            x=serh.read(1000)
            time.sleep(0.1)
            serh.close()
            serh = None

    if (cal_state == CAL_ON):
        return "ON"

    return "OFF"

def calib_onoff_manual (control,devname,baudrate,onstring,offstring,lterm):
    global serh
    global cal_state
    global CAL_MANUAL
    global CAL_WAITING

    if (len(devname) == 0 or devname == "none"):
        return False

    if (cal_state == CAL_INIT_REQUIRED or cal_state == CAL_BADDEVICE):
        return False

    if (control == True):
        serh.write(onstring+lterm)
        x=serh.read (100)
        cal_state = CAL_MANUAL

    if (control == False):
        serh.write(offstring+lterm)
        x=serh.read(100)
        cal_state = CAL_WAITING

    return True


       
correction_counter = 0
corrections = [-1.0]*2
running_avgs = [0.0]*2
def update_corrections(l):
    global correction_counter
    global corrections
    global running_avgs
    
    a = 0.1
    
    if running_avgs[0] == 0.0 and running_avgs[1] == 0.0:
        running_avgs[0] = l[0]
        running_avgs[1] = l[1]
    
    running_avgs[0] = a*l[0] + ((1.0 - a)*running_avgs[0])
    running_avgs[1] = a*l[1] + ((1.0 - a)*running_avgs[1])
    
    correction_counter += 1
    
    if (correction_counter < 180):
        return [1.0,1.0]
    
    if (corrections[0] < 0.0):
        ratio = running_avgs[1]/(running_avgs[0]*0.97)
        corrections[0] = 1.0
        corrections[1] = 1.0/ratio

    return (corrections)

def map_udev(d):
    if '@' not in d:
        return (d)
    fn = d.strip("@")+".dprof"
    try:
        f = open (fn, "r")
    except:
        return (d)
    d = f.read()
    d = d.strip("\n")
    f.close()
    return (d)

    
