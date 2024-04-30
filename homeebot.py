import time
from datetime import datetime

import requests
import schedule
import loguru
from pymee import Homee
import asyncio
import logging

# Set debug level so we get verbose logs
logging.getLogger("pymee").setLevel(logging.DEBUG)

homee_ip = "<IP>"
homee_username = '<USERNAME>'
homee_password = '<PASSWORD>'

class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Retrieve context where the logging call occurred, this happens to be in the 6th frame upward
        logger_opt = loguru.logger.opt(depth=6, exception=record.exc_info)
        logger_opt.log(record.levelno, record.getMessage())


logging.getLogger("pymee").addHandler(InterceptHandler())

class MyHomee(Homee):
    homeegrams = []
    _queue_empty_event = asyncio.Event()

    async def send(self, msg: str):
        """Send a raw string message to homee."""

        if not self.connected or self.shouldClose:
            return

        await self._message_queue.put(msg)
        self._queue_empty_event.clear()

    async def on_message(self, msg: dict):
        if msg is not None and len(msg) > 0 and "all" in msg and "homeegrams" in msg.get("all"):
            self.homeegrams = msg.get("all").get("homeegrams")

        if self._message_queue.empty():
            loguru.logger.debug("empty queue")
            self._queue_empty_event.set()

    async def on_connected(self):
        """Called once the websocket connection has been established."""
        if self.retries > 0:
            loguru.logger.warning("Homee %s Reconnected after %s retries", self.device, self.retries)
        else:
            loguru.logger.debug("on_connected")

    async def on_disconnected(self):
        """Called after the websocket connection has been closed."""
        if not self.shouldClose:
            loguru.logger.warning("Homee %s Disconnected", self.device)
        else:
            loguru.logger.debug("disconnected")


    async def on_error(self, error: str = None):
        """Called after an error has occurred."""
        loguru.logger.error("An error occurred: %s", error)

    def wait_until_queue_empty(self):
        """Returns a coroutine that runs until the connection has been closed."""
        return self._queue_empty_event.wait()

    async def activate_homeegram(self, homeegram_id:int):
        loguru.logger.debug(f"activate homeegram {homeegram_id}")
        await self.send(f"PUT:homeegrams/{homeegram_id}?active=1")


    async def deactivate_homeegram(self, homeegram_id:int):
        loguru.logger.debug(f"deactivate homeegram {homeegram_id}")
        await self.send(f"PUT:homeegrams/{homeegram_id}?active=0")


def get_holidays(country_code='DE'):
    try:
        url = f'https://date.nager.at/api/v3/PublicHolidays/{datetime.now().year}/{country_code}'
        loguru.logger.debug(f"call {url}")
        response = requests.get(url)
        return response.json()
    except Exception as e:
        loguru.logger.error(e)
        return None

def is_holiday():
    try:
        holidays = get_holidays()
        today = datetime.now().strftime('%Y-%m-%d')

        for holiday in holidays:
            if holiday['date'] == today and "DE-NW" in holiday["counties"]:
                return True
        return False
    except Exception as e:
        loguru.logger.error(e)
        return False # Fallback kein Feiertag


async def main():
    loguru.logger.info("Running HomeeBot...")
    # Create an instance of Homee
    homee = MyHomee(homee_ip, homee_username, homee_password)

    # Connect and start listening on a new task
    homeeTask = homee.start()

    # Wait until the connection is live and all data has been received
    await homee.wait_until_connected()

    # Do something here...

    loguru.logger.info(f"homeegramms: {len(homee.homeegrams)}")

    isHoliday = is_holiday()
    if isHoliday:
        loguru.logger.info("Today is a holiday")
    else:
        loguru.logger.info("No Holiday")

    morgenschaltung = None
    morgenschaltungUrlaub = None
    for homeegram in homee.homeegrams:
        if homeegram["name"] == "Morgenschaltung%20" or homeegram["name"] == "Morgenschaltung":
             loguru.logger.debug(f"{homeegram['id']}: {homeegram['name']} -> {homeegram['active']}")
             morgenschaltung = homeegram
        if homeegram["name"] == "Morgenschaltung%20Urlaub" or homeegram["name"] == "Morgenschaltung Urlaub":
             loguru.logger.debug(f"{homeegram['id']}: {homeegram['name']} -> {homeegram['active']}")
             morgenschaltungUrlaub = homeegram
    if isHoliday:
        loguru.logger.info("holiday, activate Urlaubsschaltung")
        await homee.activate_homeegram(morgenschaltungUrlaub["id"])
        await homee.deactivate_homeegram(morgenschaltung["id"])
    elif not morgenschaltung['active']:
        loguru.logger.info("Morgenschaltung is not active and no holiday, reactivate")
        await homee.activate_homeegram(morgenschaltung["id"])
        await homee.deactivate_homeegram(morgenschaltungUrlaub["id"])


    # Close the connection and wait until we are disconnected
    await homee.wait_until_queue_empty()

    homee.disconnect()
    await homee.wait_until_disconnected()


# Schedule the execution of main() every day at 00:05
schedule.every().day.at("00:05").do(lambda: asyncio.run(main()))
asyncio.run(main()) # run einmal beim start direkt

# # Run the scheduler continuously
while True:
    schedule.run_pending()
    loguru.logger.debug("sleep 60s")
    time.sleep(60)  # Check every minute

