# spitest.py
# A brief demonstration of the Raspberry Pi SPI interface, using the Sparkfun
# Pi Wedge breakout board and a SparkFun Serial 7 Segment display:
# https://www.sparkfun.com/products/11629

import time
import spidev
import math
import random
import datetime
from colorutils import Color, ArithmeticModel


# We only have SPI bus 0 available to us on the Pi
bus = 0

#Device is the chip select pin. Set to 0 or 1, depending on the connections
device = 1

# Enable SPI
spi = spidev.SpiDev()

# Open a connection to a specific bus and device (chip select pin)
spi.open(bus, device)

# Set SPI speed and mode
spi.max_speed_hz = 500000
spi.mode = 0

# Clear display
msg = [0] * 300
spi.xfer2(msg)



kickis_fav = [255,25,2]

def a(n):
    a = [
       [ 255, 0, 0 ],
       [ 0, 255, 0 ],
       [ 0, 0, 255 ],
       [ 255, 0, 255 ]
    ]

    for j in range(n):
        print('a', j, n)
        for i in range(40):
            N = ((j + i) % len(a))
            c = a[N]
            spi.xfer2(c * 3)
        time.sleep(0.1)
        j += 1

def b(n):
    b = [
        [ 255, 0, 0 ],
        [ 0, 255, 0 ],
        [ 0, 0, 255 ]
    ]
    for j in range(n):
        print('b', j, n)
        spi.xfer2(b[j % len(b)] * 40 * 3)
        time.sleep(0.1)

# mask
def masken(n):
    b = [255, 255, 255]
    for j in range(n):
        print('c', j, n)
        for i in range(100):
            w = [0,0,0]*i
            for z in range(10):
                P = math.floor(255/(((10-z)*2)+1))
                w += [P,P,P]
            w += [0,0,0] * (100-i-10)
            spi.xfer2(w)
            time.sleep(0.01)

def masken2(n):
    b = kickis_fav
    for j in range(n):
        print('c', j, n)
        for i in range(100):
            w = kickis_fav*i
            for z in range(15):
                #P = math.floor(255/(((10-z)*2)+1))
                #w += [P,P,P]
                w += [255,50,3]
            w += kickis_fav * (100-i-10)
            spi.xfer2(w)
            time.sleep(0.05)

def gradient(f1, f2, f3, ph1, ph2, ph3, i, c=128, w=127, l=100):
    r = (math.sin(f1 * i + ph1) * 0.5 + 0.5) * 255
    g = (math.sin(f2 * i + ph2) * 0.5 + 0.5) * 255
    b = (math.sin(f3 * i + ph3) * 0.5 + 0.5) * 255
    return [math.floor(r), math.floor(g), math.floor(b)]

def kickis(n):
    # kickis j: 63 [248, 40, 2]
    for Q in range(n):
        for j in range(418):
            z = gradient(0.3, 0.3, 0.3, 0, 2, 3, j * 0.1)
            spi.xfer2(z * 100)
            time.sleep(0.1)

def kickis_utan_bla(n):
    # kickis j: 63 [248, 40, 2]
    for Q in range(n):
        for j in range(418):
            z = gradient(0.3, 0.3, 0.3, 0, 2, 3, j * 0.1)
            z[2] = 0
            spi.xfer2(z * 100)
            time.sleep(0.1)

def blinka(n):
    for i in range(n):
        a = kickis_fav*100
        z = (random.randint(0,97) * 3)
        a[z] = 200
        a[z+1] = 200
        a[z+2]=80
        z = (random.randint(0,97) * 3)
        a[z] = 200
        a[z+1] = 200
        a[z+2]=80
        spi.xfer2(a)
        time.sleep(0.04)
#        a = [248,40,2]*100
#        spi.xfer2(a)
#        time.sleep(0.02)

def blinka_slow(n):
    for i in range(n):
        a = kickis_fav*100
        if n % 100 == 0:
          z = (random.randint(0,97) * 3)
          a[z] = 180 #200
          a[z+1] = 180 #200
          a[z+2]= 180 #40
        spi.xfer2(a)
        time.sleep(0.05)
        a = kickis_fav*100
        spi.xfer2(a)
        time.sleep(2)

def kicki2(n):
    for i in range(n):
        #a = [random.randint(0, 255)]*255
        a = []
        for j in range(300):
            a.append(random.randint(0,255))
        spi.xfer2(a)
        time.sleep(0.5)

def f(n):
    c = [
        255,0,0,
        0,0,0,
        0,0,0,
        0,255,0,
        0,0,0,
        0,0,0,
        0,255,255,
        0,0,0,
        0,0,0
    ]
    for j in range(n):
        print('f', j, n)
        P=[]
        for i in range(100*3):
            P.append(c[(i+(j*3)) % len(c)])

        spi.xfer2(P)
        time.sleep(0.5)

def kicki_test():
    first = [255,25,2]
    second =[255,30,2]
    while True:
        a = first*100
        print(first)
        spi.xfer2(a)
        time.sleep(1)
        a = second*100
        print(second)
        spi.xfer2(a)
        time.sleep(1)



while True:
    now = datetime.datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seconds = (now - midnight).seconds
    if seconds > 6*3600:
        #kickis(2)
        masken2(60)
        blinka_slow(1800)
    else:
        masken(60)
        blinka(1800)
        kicki2(400)
        kickis_utan_bla(8)
        blinka(1000)
