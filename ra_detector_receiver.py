#!/usr/bin/env python
import socket
import numpy
import os
import struct
import binascii
from optparse import OptionParser
import operator
import serial
import math

doephem=True
try:
    import ephem
except:
    doephem=False
import time
import math
import sys

def doit(a,loglograte,port,dcgain,frq1,frq2,longit,decln,logf,prefix,legend):

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    host = "0.0.0.0"
    sock.bind ((host,port))
    sock.listen(1)
    c, addr = sock.accept()

    df1 = bytearray(4)
    df2 = bytearray(4)
    df3 = bytearray(4)
    df4 = bytearray(4)
    df5 = bytearray(4)

    tpb1 = [0.0]*1800
    tpb2 = [0.0]*1800
    tpb3 = [0.0]*1800
    tpb4 = [0.8]*1800

    s1 = 0.0
    s2 = 0.0
    s3 = 0.0
    s4 = 0.0
    x = 0
    then = int(time.time())
    now = then
    chans = [1,2,3,4,5]
    while True:
        for w in chans:
            if w == 1:
                v = memoryview(df1)
            if w == 2:
                v = memoryview(df2)
            if w == 3:
                v = memoryview(df3)
            if w == 4:
                v = memoryview(df4)
            if w == 5:
                v = memoryview(df5)

            # Read a float, put it where it belongs (v is a memoryview of df1..df5)
            toread = 4
            while toread:
                nbytes = c.recv_into (v, toread)
                if nbytes <= 0:
                    sys.exit()
                v = v[nbytes:]
                toread -= nbytes

        #
        # Once we've read all 5 values (4 channels, plus calib state)
        # Unpack first four into their respective floating-point values, and integrate
        #   based on 'a' and a standard single-pole IIR function
        #
        d1 = struct.unpack_from('f', buffer(df1))
        d1 = d1[0]
        s1 = a * d1 + ((1.0 - a) * s1)

        d2 = struct.unpack_from('f', buffer(df2))
        d2 = d2[0]
        s2 = a * d2 + ((1.0 - a) * s2)

        d3 = struct.unpack_from('f', buffer(df3))
        d3 = d3[0]
        s3 = a * d3 + ((1.0 - a ) * s3)

        d4 = struct.unpack_from('f', buffer(df4))
        d4 = d4[0]
        s4 = a * d4 + ((1.0 - a ) * s4)


        #
        # The calib state value
        #
        cs = struct.unpack_from('f', buffer(df5))
        cs = cs[0]
        s5 = a * cs + ((1.0 -a ) * cs)

        now = int(time.time())
        #
        # If it's time to log that data, do it
        #
        if (now-then) >= lograte:
            if (logf):
                logpwrdata (legend,[s1*dcgain,s2*dcgain,s3*dcgain,s4*dcgain,s5*dcgain],[frq1,frq2],longit,int(cs),prefix)

            then = now

def doit_fft(fftsize,a,lograte,port,frq1,frq2,srate,longit,decln,logf,prefix,nchan,nhost,hlist,caldict,combine):

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    host = "0.0.0.0"
    sock.bind ((host,port))
    sock.listen(1)
    cal_state = "OFF"
    cal_serial = None
    SKIP_COUNT = 40
    CAL_INTERVAL = 60
    CAL_TIME = 6
    skip_samples = SKIP_COUNT
    
    cfds = []
    addrs = []
    
    hdict = {}
    for i in range(0,len(hlist)):
        hdict[hlist[i]] = i
    
    
    #
    # Accept as many connections as our caller specified
    #
    for i in range(0,nhost):
        c, addr = sock.accept()
        cfds.append(c)
        addrs.append(addr[0])
    
    #
    # Our list of FFT averages
    #
    # There'll be nhost * nchan of them
    #
    avg_ffts = []
    avg_cals = []
    ffts = []
    
    #
    # Single-precision FP on the wire
    #
    WIREFLOATSZ = 4
    
    for i in range(0,nhost*nchan):
        avg_ffts.append([-999.0] * fftsize)
        avg_cals.append([-999.0] * fftsize)
        ffts.append(bytearray(fftsize*WIREFLOATSZ))

    x = 0
    then = int(time.time())
    now = then
    
    #
    # Vectorize alpha value
    #
    alpha_vect = [a]*fftsize
    
    #
    # Vectorize beta value
    #
    beta_vect = [1.0-a]*fftsize

    #
    # Forever, read data from remote host(s).
    # Each data chunk will be "nchans" of interleaved FFT data
    #
    while True:
        for h in range(0,nhost):
            for c in range(0,nchan):

                #
                # Figure out which FFT to read into
                #  get a memoryview of it
                #
                hind = hdict[addrs[h]]
                ndx = (hind * nchan) + c
                v = memoryview(ffts[ndx])

                toread = fftsize*WIREFLOATSZ
                while toread:
                    nbytes = cfds[h].recv_into (v, toread)
                    if nbytes <= 0:
                         sys.exit()
                    v = v[nbytes:]
                    toread -= nbytes
        #
        # Skip samples will be > 0 after transition into/out-of CAL state
        # We want to ignore the resulting transient
        #
        if skip_samples > 0:
            skip_samples -= 1
            continue
        
        #
        # We have a buncha FFT buffers now, process them
        #
        for nx in range(0,len(ffts)):
            
            #
            # Turn buffer into actual floats
            #
            f1 = struct.unpack_from('%df' % fftsize, buffer(ffts[nx]))
             
            #
            # We perform a vector-based single-pole IIR calculation to
            #   effect an integrator
            #
            #  Yn = alpha*val + beta*Yn-1
            #
            #  Where beta = 1.0-alpha
            #
            
            #
            # Maintain two different integrator pathways for two CAL states
            #
            if (cal_state != "ON"):
                #
                # Deal with initial loading of integrator
                #
                if (avg_ffts[nx][0] < -500):
                    avg_ffts[nx] = f1

                t1 = map(operator.mul, f1, alpha_vect)
                tt1 = map(operator.mul, avg_ffts[nx], beta_vect)
                avg_ffts[nx] = map(operator.add, t1, tt1)
            else:
                #
                # Deal with initial loading of integrator
                #
                if (avg_cals[nx][0] < -500):
                    avg_cals[nx] = f1

                t1 = map(operator.mul, f1, alpha_vect)
                tt1 = map(operator.mul, avg_cals[nx], beta_vect)
                avg_cals[nx] = map(operator.add, t1, tt1)
        

        #
        # Might be time to do some logging
        #
        now = int(time.time())
        if (now-then) >= 10:
            if (logf):
                
                #
                # Change the DECLN tag(s) in the output log
                # Make the logging interval smaller during CAL ON state
                #
                if cal_state == "ON":
                    decs = ["-999"]*len(avg_ffts)
                    lrate = lograte/3
                    vect=avg_cals
                else:
                    decs = decln
                    lrate = lograte
                    vect=avg_ffts
                
                logfftdata ([frq1]*len(avg_ffts),vect,longit,decs,lrate,srate,prefix,combine)
            then = now
        
        #
        # Handle the "simple" calibration-control case
        #  Just a cheap USB-to-TTL-serial with the DTR pin tied to
        #  an inverted-logic relay driver
        #
        if (caldict["type"] == "simple" and caldict["device"] != ""):
            #
            # Every CAL_INTERVAL minutes...
            #
            if ((int(now) % (CAL_INTERVAL*60)) == 0 and cal_state == "OFF" and caldict["device"] != ""):
                try:
                    cal_serial = serial.Serial (caldict["device"], caldict["speed"])
                    cal_time = now
                    cal_state = "ON"
                    
                    #
                    # Force sample skip
                    #
                    skip_samples = SKIP_COUNT
                except:
                    cal_serial = None
                    cal_state = "OFF"
                    pass
            #
            # Already in "ON" state, check for time to turn "OFF"
            #
            elif (cal_state == "ON" and cal_serial != None):
                if ((now - cal_time) >= (CAL_TIME*60)):
                    cal_state = "OFF"
                    cal_serial.close()
                    cal_serial = None
 
                    #
                    # Force sample skip
                    #
                    skip_samples = SKIP_COUNT
                
#
# Remember last time we logged FFT data
#
lastfftlogged = time.time()

#
# Initial value for darkslides--we'll create it on the fly on first logging
#
darkslides=None

#
# Maximum sky coverage--from -90 to +90
#
COVERAGE=180
darkcounts=[1]*COVERAGE
dsinit=[False]*COVERAGE

#
# What we use to determine if current observation is "outside" of main galactic plane
#
OUTSIDE_GP=45.0

def linearize(v):
    v = numpy.divide(v, 10.0)
    v = numpy.power(10.0, v)
    return v

import copy
def logfftdata (flist,plist,longit,decln,rate,srate,pfx,combine):
    global lastfftlogged
    global doephem
    global darkslides
    global darkcounts
    global dsinit
    
    #
    # Initialize darkslides to length of plist entries
    #
    if (darkslides == None):
        darkslides = [[-200.0]*len(plist[0])]*COVERAGE

    decisid = None
    t = time.gmtime()
    if (doephem):
        sid = cur_sidereal (longit, 0)[0]
        sids = sid.split(",")
        decisid = float(sids[0])+float(sids[1])/60.0+float(sids[2])/3600.0
    else:
        sid = "??,??,??"
        
    
    if os.path.exists(pfx+"-current_decln.txt"):
        f = open (pfx+"-current_decln.txt", "r")
        v = f.readline()
        v = v.strip("\n")
        v = float(v)
        f.close()
        for i in range(len(decln)):
            decln[i] = v
        
    #
    # Not time for it yet, buddy
    #
    t2 = time.time()
    if ((t2 - lastfftlogged) < rate):
        return

    lastfftlogged = t2
    di = 0
    #
    # MUST be 1:1 correspondence between flist and plist
    #
    if combine == True and len(plist) == 2:
        lp1 = linearize(plist[0])
        lp2 = linearize(plist[1])
        ratio = numpy.sum(lp1)/numpy.sum(lp2)
        
        #
        # If one side is significantly stronger than another, there's a problem
        #  So, we append a message to an "ALERT" file
        #
        if (ratio > 2.50 or ratio < (1.0/2.5)):
            f = open(pfx+"-ALERT.txt", "a")
            f.write("%02d:%02d:%02d: ratio %f\n" % (t.tm_hour, t.tm_min, t.tm_sec, ratio))
            f.close()
        
        #
        # We adjust the two sides to be roughly-equal in magnitude
        #
        if (ratio < 1.0):
            lp1 = numpy.multiply(lp1,1.0/ratio)
        else:
            lp2 = numpy.multiply(lp2,ratio)
        
        #
        # Then compute the linearized average
        #
        avg = numpy.add(lp1,lp2)
        avg = numpy.divide(avg,2.0)
        
        #
        # Then back into log10 form
        #
        newplist = numpy.log10(avg)
        newplist = numpy.multiply(newplist,10.0)
        
        flist = [flist[0]]
        plist = [newplist]

    for x in range(0,len(flist)):
        
        #
        # Construct filename
        #
        fn = "%s-%04d%02d%02d-fft-%d.csv" % (pfx, t.tm_year,t.tm_mon,t.tm_mday,x)
        f = open (fn, "a")
        
        #
        # Determine GMT (UTC) time
        #
        gt = "%02d,%02d,%02d" % (t.tm_hour, t.tm_min, t.tm_sec)
        
        #
        # Scale frequency into MHz
        #
        fweq = "%g" % (flist[x]/1.0e6)
        
        #
        # Write header stuff
        #
        f.write (gt+","+sid+","+fweq+",")
        f.write (str(int(srate))+",")
        f.write(str(decln[di])+",")
        
        if (decisid != None):
            #
            # Compute where the Sun currently is
            #
            sun = ephem.Sun()
            sun.compute()
            
            #
            # Figure out our beam pointing--for a transit instrument, it's just
            #  LMST,DEC
            #
            beam = ephem.Equatorial(str(decisid),str(decln[di]))
            
            #
            # Suppress dark-slide writing if Sun is too close to our beam
            #
            sunbeam = False
            if (math.degrees(ephem.separation((beam.ra,beam.dec),(sun.ra,sun.dec))) <= 10.0):
                sunbeam = True
            
            #
            # Compute galactic coordinates of our beam
            #
            gp = ephem.Galactic(beam)
            glat = math.degrees(gp.lat)
            
            #
            # If the galactic latitude of the current observation is outside of
            #   the main galactic plane, we use it as a "cold sky" calibrator
            #   and "dark slide" to remove instrument artifacts.
            #
            # We also avoid writing dark-slide data when the Sun is in the beam
            #
            #
            if (sunbeam == False and (glat < -OUTSIDE_GP or glat > OUTSIDE_GP)):
                
                #
                # Form an index into the darkslides array of lists
                #
                ndx = int(decln[di])
                ndx += int(COVERAGE/2)
                
                #
                # Pick up the values
                #
                vs = darkslides[ndx]
                
                #
                # Initialize
                #
                if (dsinit[ndx] == False):
                    dsinit[ndx] = True
                    darkslides[ndx] = copy.deepcopy(plist[x])
                
                #
                # Add current values in
                #
                darkslides[ndx] = numpy.add(darkslides[ndx],plist[x])
                darkcounts[ndx] += 1
                
                vs = darkslides[ndx]
                
                #
                # Write out the darkslide file
                #
                df = open(pfx+"-darkslide-%02d.csv" % (int(decln[di])), "w")
                half = len(vs)/2
                half = int(half)
                full = len(vs)
                for dx in range(half,full):
                    val = vs[dx]/float(darkcounts[ndx])
                    df.write ("%-6.2f," % val)
                for dx in range(0,half):
                    val = vs[dx]/float(darkcounts[ndx])
                    df.write("%-6.2f" % val)
                    if (dx < half-1):
                        df.write(",")
                        
                df.write("\n")
                df.close()
                
                #
                # Reduce occasionally to prevent overflow
                #
                if (darkcounts[ndx] >= 20):
                    darkslides[ndx] = numpy.divide(darkslides[ndx],float(darkcounts[ndx]))
                    darkcounts[ndx] = 1                         
        #
        # Bumpeth the declination index
        #
        di += 1
        
        #
        # Write out the FFT data
        #
        half = len(plist[x])/2
        half = int(half)
        full = len(plist[x])
        y = plist[x]
        for i in range(half,full):
            f.write("%-6.2f," % y[i])
        for i in range(0,half):
            f.write("%-6.2f" % y[i])
            if (i < half-1):
                f.write(",")
        f.write ("\n")
        f.close()
        

#
# Determine current sidereal time
#
# Use the "ephem" Python library
#
def cur_sidereal(longitude,val):
    #
    # Convert longitude into format preferred by 'ephem' library
    #
    longstr = "%02d" % int(longitude)
    longstr = longstr + ":"
    longitude = abs(longitude)
    frac = longitude - int(longitude)
    frac *= 60
    mins = int(frac)
    longstr += "%02d" % mins
    longstr += ":00"
    
    #
    # Now get an observer object
    #
    x = ephem.Observer()
    
    #
    # Tell it that we're going to base everything on "today"
    #
    x.date = ephem.now()
    x.long = longstr
    
    #
    # Get the julian date, given the above
    #
    jdate = ephem.julian_date(x)
    
    #
    # Get sidereal time, turn into a list
    #
    tokens=str(x.sidereal_time()).split(":")
    hours=int(tokens[0])
    minutes=int(tokens[1])
    seconds=int(float(tokens[2]))
    
    #
    # Return in csv format
    #
    sidt = "%02d,%02d,%02d" % (hours, minutes, seconds)
    return ((sidt,jdate))

def logpwrdata(legend,datavals, frqvals, longit,decln,cs,prefix):
    global doephem
    t = time.gmtime()
    if (doephem):
        st = cur_sidereal(longit,0)[0]
    else:
        st = "??,??,??"
        
    
    #
    # Form filename
    #
    fn = "%s-%04d%02d%02d.csv" % (prefix, t.tm_year,t.tm_mon,t.tm_mday)
    
    #
    # Get UTC
    #
    gt = "%02d,%02d,%02d" % (t.tm_hour,t.tm_min,t.tm_sec)
    
    f = open (fn, "a")
    
    #
    # Write out header goo
    #
    ls = gt+","+st+","
    f.write(ls)
    for x in frqvals:
        sx = "%g" % (x/1.0e6)
        f.write(sx+",")
    f.write(str(decln)+",")
    f.write(legend+",")
    
    #
    # Write out data values
    #
    for x in datavals:
        sx = "%8g" % x
        f.write (sx+",")
    f.write("%d" % cs)
    f.write ("\n")
    f.close()

    return

if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option ("-a", "--alpha", dest="alpha", type="float", default=0.1)
    parser.add_option ("-p", "--port", dest="port", type="int", default=5552)
    parser.add_option ("-1", "--f1", dest="f1", type="float", default=101.1e6)
    parser.add_option ("-2", "--f2", dest="f2", type="float", default=101.1e6)
    parser.add_option ("-l", "--long", dest="longit", type="float", default=-76.03)
    parser.add_option ("-r", "--rate", dest="rate", type="int", default=5)
    parser.add_option ("-n", "--dlog", dest="log", action="store_true", default=False)
    parser.add_option ("-q", "--slog", dest="slog", action="store_true", default=False)
    parser.add_option ("-g", "--dgain", dest="dgain", type="float", default=10.0)
    parser.add_option ("-x", "--prefix", dest="prefix", type="string", default="GENERIC")
    parser.add_option ("-s", "--srate", dest="srate", type="float", default=int(2.56e6))
    parser.add_option ("-e", "--legend", dest="legend", type="string", default="A^2/B^2/A^2-B^2/A*B/CAL")
    parser.add_option ("-b", "--suppress", dest="suppress", action="store_true", default=False)
    parser.add_option ("-d", "--decln", dest="decln", type="string", default="-99")
    parser.add_option ("-f", "--fftsize", dest="fftsize", type="int", default=2048)
    parser.add_option ("-c", "--nchan", dest="nchan", type="int", default=2)
    parser.add_option ("-t", "--nhost", dest="nhost", type="int", default=1)
    parser.add_option ("-z", "--hostlist", dest="hostlist", type="string", default="")
    parser.add_option ("--caldev", dest="caldev", type="string", default="")
    parser.add_option ("--caltype", dest="caltype", type="choice", choices=["simple","bitwhacker"], default="simple")
    parser.add_option ("--calspeed", dest="calspeed", type="int", default=115200)
    parser.add_option ("--combine", dest="combine", action="store_true", default=False)

    (o, args) = parser.parse_args()
    
    if o.nchan <= 0 or o.nchan > 2:
        raise ValueError("nchan must be 1 or 2")

    declns = []
    
    #
    # Build list of declinations
    #
    if "," in o.decln:
        sd = o.decln.split(",")
        for d in sd:
            declns.append(float(d))
    else:
        fd = float(o.decln)
        declns = [fd]*(o.nhost*o.nchan)
    
    caldict = {}
    caldict["device"] = o.caldev
    caldict["speed"] = o.calspeed
    caldict["type"] = o.caltype
    
    #
    # The whole "suppress" thing needs to be re-thought
    #   
    if (o.suppress == False):
        newpid = os.fork()
        
        #
        # We run FFT logging in a separate process
        #
        if newpid == 0:
            hlist = o.hostlist.split(",")
            doit_fft(o.fftsize,o.alpha,o.rate*10,o.port+1,o.f1,o.f2,o.srate,
                o.longit,declns,o.slog,o.prefix,o.nchan,o.nhost,hlist,caldict,o.combine)
            os.exit(0)
        else:
            f=open("ra_detector_receiver-"+o.prefix+".pid", "w")
            f.write(str(newpid)+"\n")
            f.close()
            doit(o.alpha,o.rate,o.port,o.dgain,o.f1,o.f2,o.longit,declns,o.log,o.prefix,o.legend)
            os.waitpid(newpid)


    else:
        doit(o.alpha,o.rate,o.port,o.dgain,o.f1,o.f2,o.longit,declns,o.log,o.prefix,o.legend)
