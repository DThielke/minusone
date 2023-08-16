import logging

import discord
from discord.ext import commands

from minusone.bot import DiscordBot

logger = logging.getLogger(__name__)


class Twitch(
    commands.GroupCog,
    name="twitch",
    group_name="twitch",
    group_description="Commands related to MinusOne Twitch integration.",
):
    def __init__(self, bot: DiscordBot) -> None:
        self.bot = bot

        self.config: dict = self.bot.config["cogs"][self.__cog_name__.lower()]

        self.stream_posts = {}  # type: dict[str, discord.Message]

    # region Listeners

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        stream = None
        for x in after.activities:
            if isinstance(x, discord.Streaming) and x.url is not None:
                stream = x
                break
        if stream is None and after.id in self.stream_posts:
            await self.cancel_stream(after)
        elif stream is not None and after.id not in self.stream_posts:
            if self.has_streamer_role(after):
                await self.announce_stream(after, stream)

    # endregion

    def has_streamer_role(self, user: discord.Member) -> bool:
        for role in user.roles:
            if role.name in self.config["streamer_roles"]:
                return True
        return False

    async def announce_stream(self, user: discord.Member, activity: discord.Streaming) -> None:
        logger.info(f"Announcing stream from {user.name}: {activity.url}")
        channel = self.bot.get_channel(self.config["stream_channel_id"])
        message = await channel.send(f"{user.display_name} ({activity.twitch_name}) is live: {activity.url}")
        self.stream_posts[user.id] = message
        logger.info(f"Streams: { {k: v.content for k, v in self.stream_posts.items()} }")

    async def cancel_stream(self, user: discord.Member) -> None:
        logger.info(f"Cancelling stream from {user.name}")
        await self.stream_posts.pop(user.id).delete()
        logger.info(f"Streams: { {k: v.content for k, v in self.stream_posts.items()} }")


async def setup(bot: commands.Bot):
    await bot.add_cog(Twitch(bot))
