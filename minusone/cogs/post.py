import asyncio
import io
import logging
from collections import defaultdict
from typing import Optional

import discord
import pandas as pd
from discord import app_commands
from discord.ext import commands
from matplotlib import pyplot as plt

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

        self.ctx_menu = app_commands.ContextMenu(name="Edit Post", callback=self.edit_context_menu)
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    # region Commands

    @app_commands.command(name="create")
    @app_commands.checks.has_any_role("OEM Officer", "OEM Strat Squad")
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
                silent=source_message.flags.silent,
            )
            await interaction.response.send_message(f"Created post: {new_message.jump_url}", ephemeral=True)

    @app_commands.command(name="edit")
    @app_commands.checks.has_any_role("OEM Officer", "OEM Strat Squad")
    @app_commands.describe(destination="link to message to edit")
    @app_commands.describe(source="link to message with new content")
    @app_commands.describe(keep_embeds="keep embeds from the source message")
    async def edit(self, interaction: discord.Interaction, destination: str, source: str, keep_embeds: bool = True):
        """Edits an existing bot post"""
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
        if dest_channel is None:
            dest_channel = await self.bot.fetch_channel(dest_channel_id)
        try:
            if dest_channel.archived:
                await dest_channel.edit(archived=False)
        except AttributeError:
            pass
        dest_message = await dest_channel.fetch_message(dest_message_id)
        embeds = dest_message.embeds if keep_embeds else []
        for attachment in source_message.attachments:
            embed = discord.Embed(url="http://dummy.url")
            embed.set_image(url=attachment.url)
            embeds.append(embed)
        await dest_message.edit(content=source_message.content, embeds=embeds)
        await interaction.response.send_message(
            f"Edited post: {dest_message.jump_url}", ephemeral=True, suppress_embeds=True
        )

        changelog_channel = self.bot.get_channel(self.config["changelog_channel_id"])
        await changelog_channel.send(
            f"{interaction.user.name} edited post: {dest_message.jump_url}. Original Content:\n\n"
            f"{source_message.content}",
            silent=True,
            suppress_embeds=True,
        )

    async def edit_context_menu(self, interaction: discord.Interaction, message: discord.Message):
        """Edits an existing bot post"""
        if message.author != self.bot.user:
            await interaction.user.send("Can only edit posts by the bot.", ephemeral=True, delete_after=5)
            return

        bot_message = await interaction.user.send(
            f"Editing post: {message.jump_url}. You have 10 minutes to reply with new content.", suppress_embeds=True
        )
        await interaction.response.send_message(
            f"Edit started. Reply here: {bot_message.jump_url}.",
            ephemeral=True,
            suppress_embeds=True,
            delete_after=600,
        )
        try:
            reply = await self.bot.wait_for(
                "message", timeout=600, check=lambda m: m.author == interaction.user and not m.guild
            )
            keep_embeds = True  # TODO: make configurable
            embeds = message.embeds if keep_embeds else []
            for attachment in message.attachments:
                embed = discord.Embed(url="http://dummy.url")
                embed.set_image(url=attachment.url)
                embeds.append(embed)
            await message.edit(content=reply.content, embeds=embeds)
            await interaction.delete_original_response()
            await interaction.user.send("Edit complete.")

            changelog_channel = self.bot.get_channel(self.config["changelog_channel_id"])
            await changelog_channel.send(
                f"{interaction.user.name} edited post: {message.jump_url}. Original Content:\n\n{reply.content}",
                silent=True,
                suppress_embeds=True,
            )
        except asyncio.TimeoutError:
            await interaction.user.send("Edit timed out.")
            return

    @app_commands.command(name="count")
    @app_commands.checks.has_any_role("OEM Officer")
    async def count(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        start_date: str,
        limit: int = 100000,
        moving_average: int = 7,
    ):
        await interaction.response.defer(ephemeral=True)
        counts = defaultdict(int)
        counts[pd.to_datetime(start_date).date()] = 0
        counts[pd.Timestamp.today().date()] = 0
        async for message in interaction.channel.history(limit=limit, after=pd.Timestamp(start_date).to_pydatetime()):
            if message.author == user:
                counts[message.created_at.date()] += 1
        counts = pd.Series(counts)
        counts.index = pd.to_datetime(counts.index)
        counts = counts.resample("D").last().fillna(0)
        counts = pd.DataFrame(
            {
                "Daily": counts,
                f"{moving_average}d Moving Average": counts.rolling(moving_average).mean(),
            }
        )
        with plt.style.context(f"minusone.resources.{self.config['mpl_stylesheet']}"):
            ax = counts.plot(color=["dodgerblue", "orange"])
            ax.set_title(f"Message Count for {user.name}", loc="left", fontsize="large")
            plt.legend(loc="upper left")
            plt.tight_layout()
        image = self._plot_to_discord_file(ax)
        await interaction.followup.send(file=image, ephemeral=True)

    # endregion

    def _plot_to_discord_file(self, ax: plt.Axes):
        buffer = io.BytesIO()
        ax.get_figure().savefig(buffer, format="png")
        buffer.seek(0)
        return discord.File(buffer, filename="chart.png")


async def setup(bot: commands.Bot):
    await bot.add_cog(Post(bot))
