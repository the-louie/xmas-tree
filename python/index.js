const leds = require("rpi-ws2801");
const LEDCOUNT = 100;

leds.connect(LEDCOUNT);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
function log() { now = new Date(); console.log(now.toLocaleDateString(), now.toLocaleTimeString(), ...arguments); }


const gradient = (f1, f2, f3, ph1, ph2, ph3, i, dr=1, dg=1, db=1) => {
    r = Math.max((Math.sin(f1 * i + ph1) * 0.5 + 0.5) * 255 * dr, 255)
    g = Math.max((Math.sin(f2 * i + ph2) * 0.5 + 0.5) * 255 * dg, 255)
    b = Math.max((Math.sin(f3 * i + ph3) * 0.5 + 0.5) * 255 * db, 255)
    return [Math.floor(r), Math.floor(g), Math.floor(b)]
}

const colorcycle_no_blue = async (count) => {
    for (let j=0; j<LEDCOUNT; j++) {
        leds.setColor(j, gradient(0.3, 0.3, 0.3, 0, 2, 3, (j + count) * 0.1, 1, 1, 0));
    }
    await sleep(100);
    leds.update();
}

const blink_random_slow = async (count) => {
    leds.fill(0xFF, 0x19, 0x02);
    for (let n = 0; n<=2; n++) { // blink n lights
        leds.setColor(Math.floor(Math.random()* LEDCOUNT), 0xb4b4b4);

    }
    leds.update();
    await sleep(10)

    leds.fill(0xFF, 0x19, 0x02);

    leds.update();
    await sleep(100)
}


const modes = [
    colorcycle_no_blue,
    blink_random_slow,
]
let activeMode = Math.floor(Math.random() * modes.length)
log(`Number of modes: ${modes.length}`)
log(`Starting mode: ${activeMode}`)

const main = async () => {
    let startTime = new Date().getTime()
    let count = 0
    while (true) {
        await modes[activeMode](count)
        count = (count + 1) // FIXME: behövs detta? --> // % LEDCOUNT

        // Switch modes every 30s
        if (new Date().getTime() - startTime > 30000) {
            startTime = new Date().getTime()
            activeMode = Math.floor(Math.random() * modes.length)
            log(`Switched to mode ${activeMode}`)
        }
    }
}


main()
