#!/usr/bin/env python
import socket
import numpy
import os
import struct
import binascii
from optparse import OptionParser

doephem=True
try:
    import ephem
except:
    doephem=False
    print "We failed to import the 'ephem' package.  Please consider installing it."
    print "Without this package, there will be no LMST timestamps in the logging"
import time
import math
import sys

def doit(a,lograte,portlist,freqlist,longit,prefix,nchan,fftsize):
    
    abar = 1.0-a
    ports = portlist.split(",")
    freqs = freqlist.split(",")
    wind = numpy.hamming(fftsize)
    fftouts = [0.0]*((fftsize/2)+1)
    fftins = []
    fftincnt = [0]*nchan
    for x in range(0,nchan):
        fftins.append([0.0]*fftsize)
    
    socks = []
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        host = "0.0.0.0"
        sock.bind ((host,int(port)))
        sock.listen(1)
        c, addr = sock.accept()
        socks.append(c)
    
    df1 = bytearray(nchan*4)
    last = time.time()
    while True:
        if ((time.time() - last) > lograte):
            logpsrdata (freqs,fftouts,longit,lograte,prefix)
            last = time.time()
        for sockfd in socks:
            v = memoryview(df1)
            
            # Read a float, put it where it belongs (v is a memoryview of df1)  
            toread = nchan*4
            while toread:
                nbytes = sockfd.recv_into (v, toread)
                if nbytes <= 0:
                    sys.exit()
                v = v[nbytes:]
                toread -= nbytes
                
            #
            # Once we've read all nchan values,
            #  we build up a buffer for each channel
            #     
            d1 = struct.unpack_from('%df' % nchan, buffer(df1))
            
            lograwdata(prefix,d1)
            
            #
            # For each detector channel
            #
            for x in range(0,nchan):
                l = fftins[x]
                c = fftincnt[x]
                l[c] = d1[x]
                fftins[x] = l
                fftincnt[x] = fftincnt[x] + 1
                 
                #
                # Time to do an FFT on this channels detector output
                #
                if (fftincnt[x] >= fftsize):
                    # Reset counter
                    fftincnt[x] = 0

                    #
                    # Do a forward, 1d, real, FFT, applying window function on input (Hamming, in this case)
                    #
                    fo = numpy.fft.rfft(fftins[x]*wind)
                    
                    #
                    # Add fft for this detector channel to IIR integrator, using numpy vector add
                    #
                    q = numpy.multiply(numpy.abs(fo),a)
                    z = numpy.multiply(fftouts,abar)
                    fftouts = numpy.add(q,z)
            

            

def logpsrdata (flist,plist,longit,rate,pfx):
    global doephem
    t = time.gmtime()
    if (doephem):
        sid = cur_sidereal (longit, 0)[0]
    else:
        sid = "??,??,??"
        
    fn = "%s-%04d%02d%02d-pfft.csv" % (pfx, t.tm_year,t.tm_mon,t.tm_mday)
    f = open (fn, "a")
    gt = "%02d,%02d,%02d" % (t.tm_hour, t.tm_min, t.tm_sec)
    fweq = ""
    nfreq = len(flist)
    for freq in flist:
        fweq = fweq + freq
        nfreq -= 1
        if nfreq > 0:
            fweq += "/"
        
    f.write (gt+","+sid+","+fweq+",")
    for i in range(0,len(plist)):
        f.write("%g" % plist[i])
        if (i < len(plist)-1):
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

tobelogged=[] 
def lograwdata(prefix,datavals):
    global tobelogged
    
    tobelogged += datavals
    
    if (len(tobelogged) >= 20000):
        t = time.gmtime()
        fn = "%s-%04d%02d%02d-raw.dat" % (prefix, t.tm_year,t.tm_mon,t.tm_mday)
        f = open (fn, "ab")
        buf = struct.pack('f'*len(tobelogged), *tobelogged)
        f.write(buf)
        f.close()
        tobelogged = []

    return

if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option ("-a", "--alpha", dest="alpha", type="float", default=0.1)
    parser.add_option ("-p", "--portlist", dest="portlist", type="string", default="5552")
    parser.add_option ("-f", "--freqlist", dest="freqlist", type="string", default="101.1")
    parser.add_option ("-l", "--long", dest="longit", type="float", default=-76.03)
    parser.add_option ("-r", "--rate", dest="rate", type="int", default=90)
    parser.add_option ("-x", "--prefix", dest="prefix", type="string", default="GENERIC")
    parser.add_option ("-n", "--nchan", dest="nchan", type="int", default=40)
    parser.add_option( "-s", "--fftsize", dest="fftsize", type="int", default=16384)
    
    (o, args) = parser.parse_args()
    doit(o.alpha,o.rate,o.portlist,o.freqlist,o.longit,o.prefix,o.nchan,o.fftsize)
