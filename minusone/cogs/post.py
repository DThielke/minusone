import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from minusone.bot import DiscordBot

logger = logging.getLogger(__name__)


class Post(
    commands.GroupCog,
    name="post",
    group_name="post",
    group_description="Commands related to MinusOne posts.",
):
    def __init__(self, bot: DiscordBot) -> None:
        self.bot = bot

        self.config: dict = self.bot.config["cogs"][self.__cog_name__.lower()]

    # region Commands

    @app_commands.command(name="create")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(channel="link to of channel to post in")
    @app_commands.describe(message="link to message with content to post")
    @app_commands.describe(title="title of forum post, if appropriate")
    async def create(self, interaction: discord.Interaction, channel: str, message: str, title: Optional[str] = None):
        """Creates a new post in the specified channel"""
        try:
            dest_channel_id = int(channel.split("/")[-1])
        except ValueError:
            await interaction.response.send_message("Invalid channel link", ephemeral=True)
            return

        try:
            source_channel_id = int(message.split("/")[-2])
            source_message_id = int(message.split("/")[-1])
        except ValueError:
            await interaction.response.send_message("Invalid message link", ephemeral=True)
            return

        source_channel = self.bot.get_channel(source_channel_id)
        source_message = await source_channel.fetch_message(source_message_id)

        if len(source_message.content) > 2000:
            await interaction.response.send_message(
                f"Message content is too long [{len(source_message.content)}/2000]", ephemeral=True
            )
            return

        dest_channel = self.bot.get_channel(dest_channel_id)

        embeds = []
        for attachment in source_message.attachments:
            embed = discord.Embed(url="http://dummy.url")
            embed.set_image(url=attachment.url)
            embeds.append(embed)

        if isinstance(dest_channel, discord.ForumChannel):
            if title is None:
                await interaction.response.send_message("Forum posts require a title", ephemeral=True)
                return
            new_message = await dest_channel.create_thread(
                name=title,
                content=source_message.content,
                embeds=embeds,
            )
            await interaction.response.send_message(f"Created post: {new_message.message.jump_url}", ephemeral=True)
        else:
            new_message = await dest_channel.send(
                source_message.content,
                embeds=embeds,
            )
            await interaction.response.send_message(f"Created post: {new_message.jump_url}", ephemeral=True)

    @app_commands.command(name="edit")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(destination="link to message to edit")
    @app_commands.describe(source="link to message with new content")
    @app_commands.describe(keep_embeds="keep embeds from the source message")
    async def edit(self, interaction: discord.Interaction, destination: str, source: str, keep_embeds: bool = True):
        """Creates a new post in the specified channel"""
        try:
            dest_channel_id = int(destination.split("/")[-2])
            dest_message_id = int(destination.split("/")[-1])
        except ValueError:
            await interaction.response.send_message("Invalid destination message link", ephemeral=True)

        try:
            source_channel_id = int(source.split("/")[-2])
            source_message_id = int(source.split("/")[-1])
        except ValueError:
            await interaction.response.send_message("Invalid source message link", ephemeral=True)

        source_channel = self.bot.get_channel(source_channel_id)
        source_message = await source_channel.fetch_message(source_message_id)

        dest_channel = self.bot.get_channel(dest_channel_id)
        dest_message = await dest_channel.fetch_message(dest_message_id)
        embeds = dest_message.embeds if keep_embeds else []
        for attachment in source_message.attachments:
            embed = discord.Embed(url="http://dummy.url")
            embed.set_image(url=attachment.url)
            embeds.append(embed)
        await dest_message.edit(content=source_message.content, embeds=embeds)
        await interaction.response.send_message(f"Edited post: {dest_message.jump_url}", ephemeral=True)

    # endregion


async def setup(bot: commands.Bot):
    await bot.add_cog(Post(bot))
