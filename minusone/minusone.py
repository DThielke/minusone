import json
import logging
import os

from dotenv import load_dotenv

from minusone.bot import DiscordBot

logger = logging.getLogger()


def load_config() -> dict:
    root_directory = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(root_directory, "config.json"), "r") as config_file:
        return json.load(config_file)


if __name__ == "__main__":
    load_dotenv()

    bot = DiscordBot(load_config())
    bot.run(token=os.getenv("DISCORD_TOKEN"), root_logger=True)
