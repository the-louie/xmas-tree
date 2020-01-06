import time
import spidev
import math
import random
import datetime

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

def gradient(f1, f2, f3, ph1, ph2, ph3, i, c=128, w=127, l=100):
    r = (math.sin(f1 * i + ph1) * 0.5 + 0.5) * 255
    g = (math.sin(f2 * i + ph2) * 0.5 + 0.5) * 255
    b = (math.sin(f3 * i + ph3) * 0.5 + 0.5) * 255
    return [math.floor(r), math.floor(g), math.floor(b)]

def color_cycle(n):
    # kickis j: 63 [248, 40, 2]
    for Q in range(n):
        for j in range(418):
            z = gradient(0.3, 0.3, 0.3, 0, 2, 3, j * 0.1)
            spi.xfer2(z * 100)
            time.sleep(0.1)

def color_cycle_no_blue(n):
    for Q in range(n):
        for j in range(418):
            z = gradient(0.3, 0.3, 0.3, 0, 2, 3, j * 0.1)
            z[2] = 0
            spi.xfer2(z * 100)
            time.sleep(0.1)

def blinka(n):
    for i in range(n):
        a = [248,40,2]*100
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

def color_random(n):
    for i in range(n):
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

while True:
    now = datetime.datetime.now()
    seconds = (now - midnight).seconds

    # don't run between 00:00 and 06:00
    if seconds > 6*3600:
        color_cycle_without_blue(8)
        blinka(1800)
        color_random(400)
