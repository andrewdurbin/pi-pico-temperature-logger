# pi-pico-temperature-logger
Some experimenting with MicroPython on the Pi Pico.  Logs time in different temperature ranges for tracking frost in the garden.

Implements an http server on port 80 with two pages:
- '/': an index page with two buttons to control the 'User LED', current temperature, and a link to the temperature stats page.
- '/garden_temps': a datalogger page showing time in each temperature range
 
The http server is implemented via uasyncio and most of the rest of the program is implemented with python coroutines as well.

The web pages are basic currently, minimal to zero styling and evolving slowly when I have a few moments to modify it.

Installing:
This assumes an existing knowledge of installing micropython on a Pi Pico and deploying python to one.

1. In wifi_connect() set the ssid and passwd variables to something providing a dhcp server.
2. Connect LEDs to the following pins for showing current temp range:
	red - gpio 2
	red - gpio 3
	yellow - gpio 4
	green - gpio 5
	yellow - gpio 6

3. And two green leds to gpios 16 and 20 for a blink under http req and one controlled via buttons on the '/' path page.  

