#!/usr/bin/env python
import sys
import os
import time
import subprocess
from optparse import OptionParser


#
#
# Little daemon to handle "front panel" LEDs and the CAL signal
#
#
# The available GPIOs given the way I've wire it are as follows:
#
# EXPORT#           Breakout board pin    Assigned to function
# ===========================================================
# 98                1                     CAL control
# 97                2
# 104               4
# 99                5                     CPU UP
# 100               6                     TASK RUNNING
# 101               8                     HIGH TEMP
# 118              11
# 103              15
#
# 

def init_gpio(name):
    try:
        f = open ("/sys/class/gpio/unexport", "w")
        f.write (name+"\n")
        f.close()
    except:
        pass
    f = open ("/sys/class/gpio/export","w")
    f.write(name+"\n")
    f.close()
    f = open ("/sys/class/gpio/gpio"+name+"/direction", "w")
    f.write ("out"+"\n")
    f.close()

def set_gpio_val(val,name):
    f = open ("/sys/class/gpio/gpio"+name+"/value", "w")
    f.write (val+"\n")
    f.close()


def main():
    SYSTEM = "99"
    TASK = "100"
    CAL = "98"
    HITEMP = "101"
    STRUE="1"
    SFALSE="0"
    PAUSE=0.25
    WATCH_TIMER=2
    CAL_TIMER=1
    CAL_WINDOW=45
    CAL_PERIOD=300
    
    tstate = STRUE
    
    parser = OptionParser()
    parser.add_option ("-i", "--interval", dest="interval", type="int", default=1800, help="Set calibration interval (secs)")
    parser.add_option ("-d", "--duration", dest="duration", type="int", default=30, help="Set calibration on-time (secs)")
    parser.add_option ("-w", "--watched", dest="watched", type="string", default="/tmp/ra_sender.pid", help="Set file to watch for assigned RA task")
    parser.add_option ("-t", "--temperature", dest="temperature", type="string", default="/sys/class/thermal/thermal_zone0/temp",
        help="File to use to determine CPU temperature")
    parser.add_option ("-l", "--limit", dest="limit", type="int", default=65,
        help="Temperature limit for CPU Temp lamp")
    
    
    (o, args) = parser.parse_args()
    
    CAL_WINDOW=o.duration
    CAL_PERIOD=o.interval
    
    
    initlist = [SYSTEM, TASK, CAL, HITEMP]
    
    
    
    for i in initlist:
        init_gpio(i)
    
    
    set_gpio_val(STRUE,SYSTEM)
    set_gpio_val(STRUE,TASK)
    set_gpio_val(STRUE,HITEMP)
    time.sleep(5)
    set_gpio_val(SFALSE,TASK)
    set_gpio_val(SFALSE,HITEMP)
    
    task_check_count = WATCH_TIMER/PAUSE
    cal_check_count = CAL_TIMER/PAUSE
    cal_state = False
    cal_window_count = CAL_WINDOW
    seen_task = False
    tempavg = 50000.0
    a = 0.2
    f = open ("/tmp/cal_state_file", "w")
    f.close()
    while True:
        
        #
        # Do the once-per-second check
        #
        if cal_check_count <= 0:
            t = int(time.time())
            cal_check_count = CAL_TIMER/PAUSE
            
            #
            # If we're somewhere near the start of a CAL_PERIOD
            #
            if (t % CAL_PERIOD) < 3:
                #
                # Turn on only if we haven't already
                #
                if (cal_state == False):
                    set_gpio_val(STRUE, CAL)
                    cal_window_count = CAL_WINDOW
                    cal_state = True
                    f = open("/tmp/cal_state_file", "w")
                    f.write ("ON\n")
                    f.close()

            #
            # We're ON and it's time to be OFF
            #
            if (cal_window_count <= 0 and cal_state == True):
                set_gpio_val (SFALSE, CAL)
                cal_state = False
                cal_window_count = CAL_WINDOW
                f = open ("/tmp/cal_state_file", "w")
                f.close()

            #
            # Decrement cal_window counter
            #
            cal_window_count -= 1                
                    
        if task_check_count <= 0:
            task_check_count = WATCH_TIMER/PAUSE
            if os.path.exists(o.watched):
                f = open(o.watched)
                line = f.readline()
                if (line != ""):
                    pid = int(line)
                    if pid > 1:
                        try:
                            os.kill(pid, 0)
                        except OSError:
                            seen_task = False
                            pass
                        else:
                            seen_task = True
                else:
                    seen_task = False
            else:
                seen_task = False
                
            if os.path.exists(o.temperature):
                f = open (o.temperature, "r")
                l = f.readline()
                f.close()
                temp = int(l)
                temp = float(temp)
                tempavg = (temp*a) + ((1.0-a)*tempavg)
                
            
        task_check_count -= 1
        cal_check_count -= 1
        
        if (tempavg > o.limit*1000.0):
            set_gpio_val(tstate, HITEMP)
        else:
            set_gpio_val(SFALSE, HITEMP)
        
        if (seen_task == True):
            set_gpio_val(tstate, TASK)
        else:
            set_gpio_val(SFALSE, TASK)
            
        if tstate == STRUE:
            tstate = SFALSE
        else:
            tstate = STRUE
            
        time.sleep(PAUSE)

if __name__ == '__main__':
    main()  
    
