#!/usr/bin/env python
import socket
import numpy
import os
import struct
import binascii
from optparse import OptionParser
import operator

doephem=True
try:
    import ephem
except:
    doephem=False
import time
import math
import sys

def doit(a,lograte,port,dcgain,frq1,frq2,longit,logf,prefix,legend):

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



def doit_fft(fftsize,a,lograte,port,frq1,frq2,srate,longit,logf,prefix):

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    host = "0.0.0.0"
    sock.bind ((host,port))
    sock.listen(1)
    c, addr = sock.accept()

    fcnt = 0
    avg_fft1 = [0.0]*fftsize
    avg_fft2 = [0.0]*fftsize

    fft1 = bytearray(fftsize*4)
    fft2 = bytearray(fftsize*4)
    x = 0
    then = int(time.time())
    now = then
    while True:
        for w in [1,2]:
            if w == 1:
                v = memoryview(fft1)
            if w == 2:
                v = memoryview(fft2)

            toread = fftsize*4
            while toread:
                nbytes = c.recv_into (v, toread)
                if nbytes <= 0:
                     sys.exit()
                v = v[nbytes:]
                toread -= nbytes

        f1 = struct.unpack_from('%df' % fftsize, buffer(fft1))
        f2 = struct.unpack_from('%df' % fftsize, buffer(fft2))
        fcnt = fcnt + 1

        avg_fft1 = map(operator.add, f1, avg_fft1)
        avg_fft2 = map(operator.add, f2, avg_fft2)

        now = int(time.time())
        if (now-then) >= 5:
            if (logf):
                divisor = [float(fcnt)]*fftsize
                avg_fft1 = map(operator.div, avg_fft1, divisor)
                avg_fft2 = map(operator.div, avg_fft2, divisor)
                logfftdata ([frq1,frq2],[avg_fft1,avg_fft2],longit,lograte,prefix)
                fcnt = 0

            then = now

lastfftlogged = time.time()
def logfftdata (flist,plist,longit,rate,pfx):
    global lastfftlogged
    global doephem
    t = time.gmtime()
    if (doephem):
        sid = cur_sidereal (longit, 0)[0]
    else:
        sid = "??,??,??"

    t2 = time.time()
    if ((t2 - lastfftlogged) < rate):
        return

    lastfftlogged = t2

    for x in range(0,len(flist)):
        fn = "%s-%04d%02d%02d-fft-%d.csv" % (pfx, t.tm_year,t.tm_mon,t.tm_mday,x)
        f = open (fn, "a")
        gt = "%02d,%02d,%02d" % (t.tm_hour, t.tm_min, t.tm_sec)
        fweq = "%g" % (flist[x]/1.0e6)
        f.write (gt+","+sid+","+fweq+",")
        for i in range((len(plist[x])/2)-1,len(plist[x])):
            y = plist[x]
            f.write("%g" % y[i])
            if (i < len(plist[x])-1):
                f.write(",")
        for i in range(0,len(plist[x])/2):
            y = plist[x]
            f.write("%g" % y[i])
            if (i < (len(plist[x])/2)-1):
                f.write(",")
        f.write ("\n")
        f.close()

def shift(seq, n, v):
    l = len(seq)
    x = [v]+seq[n-1:l-1]
    return x

def writefile(dat,fn,incr):
    f = open ("tmptp.dat", "w")
    for q in range(0,len(dat)):
        s = "%d %f\n" % (q*incr,dat[q])
        f.write(s)
    f.close()
    os.rename ("tmptp.dat", fn)

def cur_sidereal(longitude,val):
    longstr = "%02d" % int(longitude)
    longstr = longstr + ":"
    longitude = abs(longitude)
    frac = longitude - int(longitude)
    frac *= 60
    mins = int(frac)
    longstr += "%02d" % mins
    longstr += ":00"
    x = ephem.Observer()
    x.date = ephem.now()
    x.long = longstr
    jdate = ephem.julian_date(x)
    tokens=str(x.sidereal_time()).split(":")
    hours=int(tokens[0])
    minutes=int(tokens[1])
    seconds=int(float(tokens[2]))
    sidt = "%02d,%02d,%02d" % (hours, minutes, seconds)
    return ((sidt,jdate))

partracker = 0
def logpwrdata(legend,datavals, frqvals, longit,cs,prefix):
    global partracker
    global doephem
    t = time.gmtime()
    if (doephem):
        st = cur_sidereal(longit,0)[0]
    else:
        st = "??,??,??"
    fn = "%s-%04d%02d%02d.csv" % (prefix, t.tm_year,t.tm_mon,t.tm_mday)
    gt = "%02d,%02d,%02d" % (t.tm_hour,t.tm_min,t.tm_sec)
    f = open (fn, "a")
    ls = gt+","+st+","
    f.write(ls)
    for x in frqvals:
        sx = "%g" % (x/1.0e6)
        f.write(sx+",")
    f.write(legend+",")
    for x in datavals:
        sx = "%8g" % x
        f.write (sx+",")
    f.write("%d" % cs)
    f.write ("\n")
    partracker -= 1
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
    parser.add_option ("-s", "--srate", dest="srate", type="int", default=int(2.56e6))
    parser.add_option ("-e", "--legend", dest="legend", type="string", default="A^2/B^2/A^2-B^2/A*B/CAL")
    parser.add_option ("-z", "--suppress", dest="suppress", action="store_true", default=False)

    (o, args) = parser.parse_args()

    if (o.suppress == False):
        newpid = os.fork()
        if newpid == 0:
            doit_fft(2048,o.alpha,o.rate*10,o.port+1,o.f1,o.f2,o.srate,o.longit,o.slog,o.prefix)
            os.exit(0)
        else:
            f=open("ra_detector_receiver-"+o.prefix+".pid", "w")
            f.write(str(newpid)+"\n")
            f.close()
            doit(o.alpha,o.rate,o.port,o.dgain,o.f1,o.f2,o.longit,o.log,o.prefix,o.legend)
            os.waitpid(newpid)


    else:
        doit(o.alpha,o.rate,o.port,o.dgain,o.f1,o.f2,o.longit,o.log,o.prefix,o.legend)
