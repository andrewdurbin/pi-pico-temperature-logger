#Copyright (C) 2023 Andrew Durbin

#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.

#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>.

from typing import Callable
from machine import Pin, ADC
import uasyncio as asyncio
import network
import micropython
import userconstants

# Onboard led
watchdog_led = Pin("LED",Pin.OUT)
http_connection_led = Pin(20,Pin.OUT)
user_led = Pin(16,Pin.OUT)

temp_low_crit_thresh_led = Pin(2,Pin.OUT)
temp_low_warn_thresh_led = Pin(3,Pin.OUT)
temp_ok_thresh_led = Pin(4,Pin.OUT)
temp_high_warn_thresh_led = Pin(5,Pin.OUT)
temp_high_crit_thresh_led = Pin(6,Pin.OUT)

watchdog_led.value(0)
http_connection_led.value(0)
user_led.value(0)

temp_low_crit_thresh_led.value(0)
temp_low_warn_thresh_led.value(0)
temp_ok_thresh_led.value(0)
temp_high_warn_thresh_led.value(0)
temp_high_crit_thresh_led.value(0)

def blink_led(_func=None, *, led=watchdog_led):
    """ Define a decorator with an optional led argument.
    Keep the led on for the duration of the function decorated"""
    def decorator_blink_led(func):
        """ Would use functools...but seems unavailable in this env. """
        def wrapper_blink(*args,**kwargs):
            led.toggle()
            value = func(*args,*kwargs)
            return value
        return wrapper_blink
    if _func is None:
        return decorator_blink_led
    return decorator_blink_led(_func)

@blink_led(led=watchdog_led)
async def poll_wifi_status():
    """A short blink every second while waiting for wifi to connect"""
    await asyncio.sleep_ms(1000)

async def wifi_connect(ssid:str, passwd:str):
    """Connect to the requested WIFI network"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid,passwd)
    while wlan.status() != 3:
        await poll_wifi_status()
    print(f"Connected: {wlan.ifconfig()[0]}")

class PicoServer():
    """Implement a uasyncio http server, and a temperature logger from the Pi Pico temp sensor"""
    watchdog_val = 0
    temp_f_latest = 0
    # So the first value set with min() overrides it
    temp_f_min = 1000
    temp_f_max = 0

    # Seconds in each threshold
    thresh_times = [ 0, 0, 0, 0, 0 ]

    @blink_led(led=watchdog_led)
    def watchdog(self):
        """The forever repeating watchdog task, just up a value, and blink a led"""
        self.watchdog_val = self.watchdog_val + 1
        
    def format_times(self, idx:int) -> str:
        """Pass in an index to the temp cache, return a stringified version of the seconds value"""
        seconds = self.thresh_times[idx]
        # ...micropython also missing datetime module
        minutes,seconds = divmod(seconds,60)
        hours,minutes = divmod(minutes,60)
        days,hours = divmod(hours,24)
        weeks,days = divmod(days,7)
        out = f"{seconds} secs"
        if minutes > 0:
            out = f"{minutes} mins " + out
        if hours > 0:
            out = f"{hours} hours " + out
        if days > 0:
            out = f"{days} days " + out
        if weeks > 0:
            out = f"{weeks} weeks " + out
        return out

    async def watchdog_loop(self):
        """Never exiting watchdog task"""
        while True:
            self.watchdog()
            await asyncio.sleep_ms(200)

    def get_route(self, path:str) -> Callable:
        """Returns a callable generating an html response for the path given"""
        paths = {
            '/': self.index_page,
            '/method=%22post%22?toggle_led=On': self.led_on,
            '/method=%22post%22?toggle_led=Off': self.led_off,
            '/garden_temps': self.garden_temp_page,
            '/notfound': self.not_found
        }
        if path not in paths:
            return paths['/notfound']
        return paths[path]

    def __init__(self):
        self.temp_f_latest = 0

    def read_temp(self) -> (int, int):
        """ Returns a tuple of (Celcius, Farenheit) """
        adc = ADC(4)
        # Normalize the raw 0-65535 adc output value to 0-3.3 voltage scale
        volts = adc.read_u16() * (3.3/65535)
        # Sensor outputs 27 degrees Celcius at 0.706 Volts and decreases 1.721 mV per degree Celcius
        # See See https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf
        temp_c = 27 - (volts - 0.706)/0.001721
        # Standard unit conversion
        return (temp_c, 32 + (1.8 * temp_c))

    async def cache_temp(self):
        """ Read onboard temp """
        while True:
            temp_now = self.read_temp()
            self.temp_f_latest = temp_now[1]
            self.temp_f_min = min(self.temp_f_min,self.temp_f_latest)
            self.temp_f_max = max(self.temp_f_max,self.temp_f_latest)
            # Calculate threshold temp is in
            thresh_leds = [
                temp_low_crit_thresh_led,
                temp_low_warn_thresh_led,
                temp_ok_thresh_led,
                temp_high_warn_thresh_led,
                temp_high_crit_thresh_led
            ]

            thresholds = [
                (-40,32),
                (32,37),
                (37,60),
                (60,85),
                (86,176)
            ]

            on_item = list(filter(lambda range: (range[0]<self.temp_f_latest<range[1]), thresholds))
            on_idx = thresholds.index(on_item[0])
            for led,idx in enumerate(thresh_leds):
                led.value(idx==on_idx)
                if idx == on_idx:
                    self.thresh_times[idx] = self.thresh_times[idx] + 1

            # Its not necessary to poll it quicker than it can be read by a human
            await asyncio.sleep_ms(1000)

    async def index_page(self,method,path,reader,writer):
        """Return the basic index page """    
        del method, path, reader
        writer.write('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
        writer.write("<!DOCTYPE html><html>")
        writer.write("<head><title>Micro Python Server Version 0.2.1</title></head>")
        writer.write("<body>")
        writer.write("<h1>uasyncio Server</h1>")
        writer.write(f"<p>Current Pi Pico Temp Sensor: {self.temp_f_latest} degrees F (Min:{self.temp_f_min} Max:{self.temp_f_max})</p>")
        #Need to rework this...
        writer.write("<h2>Control User Led:</h2>")
        writer.write("<form action=\"\" method=\"post\"><input type=\"submit\" name=\"toggle_led\" value=\"On\" /></form>")
        writer.write("<form action=\"\" method=\"post\"><input type=\"submit\" name=\"toggle_led\" value=\"Off\" /></form>")
        writer.write("<a href=\"/garden_temps\">See Historical Temperature</a>")
        writer.write("</body>")
        writer.write("</html>")
        await writer.wait_closed()

    async def garden_temp_page(self,method,path,reader,writer):
        """Return the HTML temperature history table"""
        del method, path, reader
        writer.write('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
        writer.write("<!DOCTYPE html><html>")
        writer.write("<head><title>Micro Python Server</title></head>")
        writer.write("<body>")
        html = """
        <style type="text/css">
        .tg  {border-collapse:collapse;border-spacing:0;}
        .tg td{border-color:black;border-style:solid;border-width:1px;font-family:Arial, sans-serif;font-size:14px;
          overflow:hidden;padding:10px 5px;word-break:normal;}
        .tg th{border-color:black;border-style:solid;border-width:1px;font-family:Arial, sans-serif;font-size:14px;
          font-weight:normal;overflow:hidden;padding:10px 5px;word-break:normal;}
        .tg .tg-0lax{text-align:left;vertical-align:top}
        </style>
        """ + """
        <table class="tg">
        <thead>
          <tr>
            <th class="tg-0lax">Threshold</th>
            <th class="tg-0lax">Range</th>
            <th class="tg-0lax">Time in Range</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="tg-0lax">Freezing</td>
            <td class="tg-0lax">-40 to 32F</td>
            <td class="tg-0lax">{self.format_times(0)}</td>
          </tr>
          <tr>
            <td class="tg-0lax">'Areas of Frost'<br></td>
            <td class="tg-0lax">32 to 37F</td>
            <td class="tg-0lax">{self.format_times(1)}</td>
          </tr>
          <tr>
            <td class="tg-0lax">Frost or Cold</td>
            <td class="tg-0lax">37 to 60F</td>
            <td class="tg-0lax">{self.format_times(2)}</td>
          </tr>
          <tr>
            <td class="tg-0lax">Cool Weather Vegetables</td>
            <td class="tg-0lax">60 to 85F</td>
            <td class="tg-0lax">{self.format_times(3)}</td>
          </tr>
          <tr>
            <td class="tg-0lax">Hot enough for anything else</td>
            <td class="tg-0lax">86F+</td>
            <td class="tg-0lax">{self.format_times(4)}</td>
          </tr>
        </tbody>
        </table>
        """
        writer.write(html)
        writer.write("</body>")
        writer.write("</html>")
        await writer.wait_closed()

    async def led_on(self,method,path,reader,writer):
        """Turn the led on and continue to the index page"""
        user_led.value(1)
        await self.index_page(method,path,reader,writer)

    async def led_off(self,method,path,reader,writer):
        """Turn the led off and continue to the index page"""
        user_led.value(0)
        await self.index_page(method,path,reader,writer)

    async def not_found(self,method,path,reader,writer):
        """Return a basic page for HTTP404"""
        del method, path, reader
        writer.write('HTTP/1.0 404 Not Found\r\nContent-type: text/html\r\n\r\n')
        html = """
            <!DOCTYPE html><html>
            <head><title>Micro Python Server</title></head>
            <body><h1>Bad Path</h1><p>you shouldn't be here</p></body>
            </html>
        """
        writer.write(html)
        await writer.wait_closed()

    @blink_led(led=http_connection_led)
    async def handle_client(self,reader,writer):
        """Handle an http client connection"""
        req = None
        method=""
        path=""
        while req != "\r\n":
            req = (await reader.readline()).decode("utf8")
            if req is not None and "HTTP/1.1" in req:
                req_type=req.split(" ")
                method=req_type[0]
                path=req_type[1]
                print(f"Req {method} {path}")
        route=self.get_route(path)
        await route(method,path,reader,writer)

async def http_server_start(coroutine,port):
    """Start an http server on the requested port"""
    loop = asyncio.get_event_loop()
    loop.create_task(asyncio.start_server(coroutine, '0.0.0.0', port))
    print(f"Server Started on port {port}")
    loop.run_forever()

async def main_loop():
    """Start a watchdog, http server, and temp sensor reader"""
    server=PicoServer()
    tasks = [
        asyncio.create_task(server.watchdog_loop()),
        asyncio.create_task(http_server_start(server.handle_client,80)),
        asyncio.create_task(server.cache_temp())
    ]
    await asyncio.gather(*tasks, return_exceptions=False)

asyncio.run(wifi_connect(userconstants.SSID,userconstants.PASSWORD))
asyncio.run(main_loop())
