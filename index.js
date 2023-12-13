const ws281x = require('@gbkwiatt/node-rpi-ws281x-native');

const channel = ws281x(100, { stripType: 'ws2812' });

const colorArray = channel.array;

const rgbBlackAll = channel.array.map(() => 0)

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const gradient = (f1, f2, f3, ph1, ph2, ph3, i, dr=1, dg=1, db=1) => {
    r = Math.max((Math.sin(f1 * i + ph1) * 0.5 + 0.5) * 255 * dr, 255)
    g = Math.max((Math.sin(f2 * i + ph2) * 0.5 + 0.5) * 255 * dg, 255)
    b = Math.max((Math.sin(f3 * i + ph3) * 0.5 + 0.5) * 255 * db, 255)
    return [Math.floor(r), Math.floor(g), Math.floor(b)]
}

const colorcycle_no_blue = async (count) => {
    for (let j=0; j<channel.count; j++) {
        colorArray[j] = gradient(0.3, 0.3, 0.3, 0, 2, 3, (j + count) * 0.1, 1, 1, 0)
    }
    await sleep(100);
    ws281x.render();
}

const blink_random_slow = async (count) => {
    colorArray = rgbBlackAll.map(() => 0xff1902) // clear all
    for (let n = 0; n<=2; n++) { // blink n lights
        colorArray[Math.floor(Math.random()* channel.count)] = 0xb4b4b4
    }
    ws281x.render()
    await sleep(10)

    colorArray = rgbBlackAll.map(() => 0xff1902) // clear all
    ws281x.render()
    await sleep(100)
}


const modes = [
    colorcycle_no_blue,
    blink_random_slow,
]
let activeMode = Math.floor(Math.random() * modes.length)

const main = async () => {
    let startTime = new Date().getTime()
    let count = 0
    while (true) {
        await modes[activeMode](count)
        count = (count + 1) // FIXME: behövs detta? --> // % channel.count

        // Switch modes every 30s
        if (new Date().getTime() - startTime > 30000) {
            startTime = new Date().getTime()
            activeMode = Math.floor(Math.random() * modes.length)
            console.log(`Switched to mode ${activeMode}`)
        }
    }
}


main()
