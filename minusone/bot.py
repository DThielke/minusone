import logging
import os

import discord
from discord.ext import commands

from minusone import cogs
from minusone.database import Database

logger = logging.getLogger()


class DiscordBot(commands.Bot):
    def __init__(self, config: dict, **kwargs) -> None:
        self.database = None  # type: Database
        self.config = config

        for key in ["bot", "database"]:
            if key not in config:
                raise ValueError(f"Config is missing required key: {key}")

        intents = discord.Intents.default()
        for intent in config["bot"]["intents"]:
            intents.__setattr__(intent, True)

        super().__init__(command_prefix=config["bot"]["command_prefix"], intents=intents, **kwargs)

    async def on_ready(self):
        for guild in self.guilds:
            logger.info(f"{self.user} is connected to: {guild.name}(id: {guild.id})")

    async def close(self):
        if self.database is not None:
            self.database.disconnect()
        logger.info("Database connection closed")
        super().close()

    async def setup_hook(self):
        await super().setup_hook()

        self.database = Database(self.config["database"]["path"])
        self.database.connect()
        logger.info("Database connection established")

        cogs_dir = os.path.dirname(os.path.abspath(cogs.__file__))
        cog_names = [
            f"minusone.cogs.{filename[:-3]}"
            for filename in os.listdir(cogs_dir)
            if filename.endswith(".py") and filename != "__init__.py"
        ]
        for cog in cog_names:
            await self.load_extension(cog)
            logger.info(f"Loaded cog: {cog}")
