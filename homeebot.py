from datetime import datetime, timedelta

import requests
import loguru
from pymee import Homee
import asyncio
import logging

# Set debug level so we get verbose logs
#logging.getLogger("pymee").setLevel(logging.DEBUG)

homee_ip = "<IP>"
homee_username = "<USERNAME>"
homee_password = "<PASSWORD>"


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
        """Returns a coroutine that runs until the queue is empty."""
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

def is_public_holiday(date = datetime.now()):
    try:
        holidays = get_holidays()
        today = date.strftime('%Y-%m-%d')

        for holiday in holidays:
            if holiday is not None and holiday['date'] == today and ("counties" in holiday and (holiday["counties"] is None or "DE-NW" in holiday["counties"])):
                return True
        return False
    except Exception as e:
        loguru.logger.error(e)
        return False # Fallback kein Feiertag


def is_bridge_day():
    today = datetime.now()
    next_day = today + timedelta(days=1)
    last_day = today - timedelta(days=1)

    if today.weekday() == 0: # Monday
        return is_public_holiday(next_day)
    elif today.weekday() == 3: # Thursday
        return is_public_holiday(last_day)
    else:
        return False


def heartBeat():
    logging.info("send heartBeat")
    try:
        result = requests.get(heartbeat_url)
        if not result.status_code == 200 and result.text == "ok":
            logging.error("error sending heartbeat " + str(result))
    except Exception:
        logging.error("could not send heartbeat")



async def main():
    lastRun = None
    while True:
        timeNow = datetime.now()
        if (lastRun is None or ((timeNow - lastRun).total_seconds() > 60 * 60)
                and 0 <= timeNow.hour < 1 and 5 <= timeNow.minute >= 10):  # alle 24h zwischen 00:05 und 00:10
            await run()
            lastRun = timeNow

        loguru.logger.debug("sleep 60s")
        await asyncio.sleep(60)


async def run():
    loguru.logger.info("Running HomeeBot...")
    # Create an instance of Homee
    homee = MyHomee(homee_ip, homee_username, homee_password)

    # Connect and start listening on a new task
    homeeTask = homee.start()

    # Wait until the connection is live and all data has been received
    await homee.wait_until_connected()

    # Do something here...

    loguru.logger.info(f"homeegramms: {len(homee.homeegrams)}")

    isHoliday = is_public_holiday()
    isBridgeDay = is_bridge_day()
    if isHoliday:
        loguru.logger.info("Today is a holiday")
    elif isBridgeDay:
        loguru.logger.info("Today is a bridge day")
    else:
        loguru.logger.info("No holiday")
        loguru.logger.info("No bridge day")

    morgenschaltung = None
    morgenschaltungUrlaub = None
    for homeegram in homee.homeegrams:
        if homeegram["name"] == "Morgenschaltung%20(1)" or homeegram["name"] == "Morgenschaltung (1)":
             loguru.logger.debug(f"{homeegram['id']}: {homeegram['name']} -> {homeegram['active']}")
             morgenschaltung = homeegram
        if homeegram["name"] == "Morgenschaltung%20Urlaub (1)" or homeegram["name"] == "Morgenschaltung Urlaub (1)":
             loguru.logger.debug(f"{homeegram['id']}: {homeegram['name']} -> {homeegram['active']}")
             morgenschaltungUrlaub = homeegram
    if isHoliday or isBridgeDay:
        loguru.logger.info("holiday, activate Urlaubsschaltung")
        await homee.activate_homeegram(morgenschaltungUrlaub["id"])
        await homee.deactivate_homeegram(morgenschaltung["id"])
    elif not morgenschaltung['active'] or morgenschaltungUrlaub['active']:
        loguru.logger.info("Morgenschaltung is not active and no holiday, reactivate")
        await homee.activate_homeegram(morgenschaltung["id"])
        await homee.deactivate_homeegram(morgenschaltungUrlaub["id"])


    # Close the connection and wait until we are disconnected
    await homee.wait_until_queue_empty()

    homee.disconnect()
    await homee.wait_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
