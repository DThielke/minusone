import datetime
import io
import logging
import re
from typing import Optional

import discord
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import pytz
from discord import app_commands
from discord.ext import commands, tasks

from minusone.bot import DiscordBot

logger = logging.getLogger(__name__)


EMOJIS = {
    "fail": "❌",
    "upvote": "🔼",
    "downvote": "🔽",
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
    5: "5️⃣",
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
    9: "9️⃣",
    10: "🔟",
}


class Votes(
    commands.GroupCog,
    name="votes",
    group_name="votes",
    group_description="Commands related to MinusOne votes.",
):
    def __init__(self, bot: DiscordBot) -> None:
        self.bot = bot

        self.config: dict = self.bot.config["cogs"][self.__cog_name__.lower()]
        self.initial_votes = self.config["initial_votes"]

    async def cog_load(self):
        self._create_tables()
        self.reset_available_votes.start()

    async def cog_unload(self):
        self.reset_available_votes.cancel()

    # region Listeners

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        parsed_message = await self._parse_message(message)
        if parsed_message is not None:
            target, votes = parsed_message
            result = self._try_vote(
                message.created_at,
                message.author.id,
                target.id,
                votes,
            )
            if result > 0:
                await message.add_reaction(EMOJIS[abs(result)])
            elif result < 0:
                await message.add_reaction(EMOJIS[abs(result)])
            else:
                await message.add_reaction(EMOJIS["fail"])

        for auto_vote in self.config["auto_votes"]:
            if self._check_auto_vote(auto_vote, message):
                logger.info(
                    f"Detected '{auto_vote['contains']}'! Auto-voting for {auto_vote['user_id']} "
                    f"({auto_vote['votes']} points)"
                )
                self._record_vote(message.created_at, self.bot.user.id, message.author.id, auto_vote["votes"])

    # endregion

    # region Commands

    @commands.command(name="resetavailablevotes")
    @commands.is_owner()
    async def reset_available(self, ctx: commands.Context):
        """Reset available votes for all users"""
        self._reset_all_available_votes()
        await ctx.send("Reset available votes for all users")

    @app_commands.command(name="left")
    async def left(self, interaction: discord.Interaction):
        """Check how many votes you have left"""
        votes = self._get_available_votes(interaction.user.id)
        await interaction.response.send_message(f"You have {votes} votes left today.", ephemeral=True)

    @app_commands.command(name="tally")
    @app_commands.describe(user="whose votes to tally")
    async def tally(self, interaction: discord.Interaction, user: discord.User = None):
        """Check how many votes a user has received"""
        user = user or interaction.user
        tally = self._get_total_votes_for_user(user.id)
        await interaction.response.send_message(f"Current vote tally for <@{user.id}>: {tally}", ephemeral=True)

    @app_commands.command(name="leaderboard")
    @app_commands.describe(
        public="show the leaderboard publicly?",
        limit="the number of users to show",
        received="show votes received (True) or issued (False)?",
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        public: Optional[bool] = False,
        limit: Optional[int] = 10,
        received: Optional[bool] = True,
    ):
        """Shows the current leaderboard"""
        await interaction.response.defer(ephemeral=not public)
        limit = min(limit, 50)
        top_data = self._get_leaderboard(limit, top=True, received=received)
        bottom_data = self._get_leaderboard(limit, top=False, received=received)
        user_count = self._get_user_count(received)
        if top_data.empty or bottom_data.empty:
            await interaction.followup.send("No leaderboard data available.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Leaderboard - Votes *{'Received' if received else 'Issued'}*", color=0x2CA453)
        top = []
        for i, row in enumerate(top_data.itertuples()):
            top.append(f"{i + 1}. {self.bot.get_user(row.user_id).mention} ({int(row.votes)} points)")
        top = "\n".join(top)
        bottom = []
        for i, row in enumerate(bottom_data.itertuples()):
            rank = user_count - len(bottom_data) + i + 1
            bottom.append(f"{rank}. {self.bot.get_user(row.user_id).mention} ({int(row.votes)} points)")
        bottom = "\n".join(bottom)
        embed.add_field(
            name=f"Top {len(top_data)} Users",
            value=top,
            inline=False,
        )
        embed.add_field(
            name=f"Bottom {len(bottom_data)} Users",
            value=bottom,
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=not public)

    @app_commands.command(name="grant")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def votes_grant(self, interaction: discord.Interaction, user: discord.User, votes: int):
        """Grant votes to a user"""
        self._add_available_votes(user.id, votes)
        await interaction.response.send_message(f"Granted {votes} votes to <@{user.id}>.", ephemeral=True)
        logger.warn(
            f"{interaction.user.name}#{interaction.user.discriminator} granted "
            f"{votes} votes to {user.name}#{user.discriminator}."
        )

    @app_commands.command(name="chart")
    @app_commands.describe(
        user="whose votes to chart",
        public="show the leaderboard publicly?",
    )
    async def votes_chart(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        public: Optional[bool] = False,
    ):
        """Plot the voting history of a user"""
        await interaction.response.defer(ephemeral=not public)
        user = user or interaction.user
        vote_history = self._get_vote_history_for_user(user.id)
        if vote_history.empty:
            await interaction.followup.send(f"<@{user.id}> has no voting history.", ephemeral=True)
            return

        ax = self._plot_vote_history(
            vote_history,
            title=f"{user.name}'{'s' if user.name[-1] != 's' else ''} Rating",
        )
        image = self._plot_to_discord_file(ax)
        await interaction.followup.send(file=image, ephemeral=not public)

    # endregion

    # region Tasks

    @tasks.loop(time=datetime.time(hour=4, tzinfo=pytz.timezone("US/Eastern")))
    async def reset_available_votes(self):
        logger.info("Resetting available votes...")
        reset = False
        while not reset:
            try:
                self._reset_all_available_votes()
                reset = True
            except Exception as e:
                logger.error(e)
        logger.info("Available votes reset.")

    # endregion

    # region Message Parsing

    async def _parse_message(self, message: discord.Message):
        content = message.content
        cleaned = re.sub(r"<@(.*?)>", "", content).strip()[:10]

        match = re.match(r"^([+-]\d+)(?=\s.*$|$)", cleaned)
        if match is None:
            return
        vote = int(match.group(1))
        if vote == 0:
            return

        if len(message.mentions) == 1 and message.type == discord.MessageType.default:
            # direct mention
            target = message.mentions[0]
        elif self._is_reply(message):
            # reply
            target = message.reference.resolved.author
        elif self._is_trial_channel(message):
            # trial private channel
            target = await self.get_trial_user_id(message.channel)
            if not target:
                return
        else:
            return

        return target, vote

    def _is_reply(self, message: discord.Message):
        return message.type == discord.MessageType.reply and (
            len(message.mentions) == 0
            or (len(message.mentions) == 1 and message.mentions[0].id == message.reference.resolved.author.id)
        )

    def _is_trial_channel(self, message: discord.Message):
        return message.channel.category_id == self.config["trial_category_id"]

    def _check_auto_vote(self, config: dict, message: discord.Message):
        if config["user_id"] and message.author.id != config["user_id"]:
            return False
        if config["channel_id"] and message.channel.id != config["channel_id"]:
            return False
        if config["contains"] and not config["contains"] in message.content:
            return False
        if config["votes"] == 0:
            return False
        return True

    # endregion

    # region Plotting

    def _timeseries_to_ohlc(self, x: pd.Series, freq: str = "D"):
        ohlc = x.resample(freq).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
            }
        )
        nan = ohlc["open"].isna()
        ohlc["close"] = ohlc["close"].ffill()
        ohlc.loc[nan, "open"] = ohlc.loc[nan, "close"]
        ohlc.loc[nan, "high"] = ohlc.loc[nan, "close"]
        ohlc.loc[nan, "low"] = ohlc.loc[nan, "close"]
        return ohlc

    def _plot_ohlc(self, ohlc: pd.DataFrame, ax: plt.Axes = None, title=None, ewma_span=22):
        _, ax = plt.subplots()

        if ohlc.index.freq.is_anchored():
            t0 = pd.Timestamp.now() + ohlc.index.freq
            bar_width_offset = pd.DateOffset(seconds=(t0 + ohlc.index.freq - t0).total_seconds() * 0.4)
        else:
            bar_width_offset = ohlc.index.freq * 0.5

        color = "#2CA453"
        prev_close = 0
        for bar in ohlc.itertuples():
            t = bar.Index
            if bar.close > prev_close:
                color = "#2CA453"
            elif bar.close < prev_close:
                color = "#F04730"
            ax.plot([t, t], [bar.low, bar.high], color=color, lw=2, solid_capstyle="round")
            ax.plot(
                [t, t - bar_width_offset],
                [bar.open, bar.open],
                color=color,
                lw=2,
                solid_capstyle="round",
            )
            ax.plot(
                [t, t + bar_width_offset],
                [bar.close, bar.close],
                color=color,
                lw=2,
                solid_capstyle="round",
            )
            prev_close = bar.close
        ax.plot(
            ohlc.index,
            ohlc["close"].ewm(span=ewma_span).mean(),
            color="dodgerblue",
            lw=2,
            alpha=0.5,
        )

        locator = mdates.AutoDateLocator(minticks=3, maxticks=10)
        formatter = mdates.ConciseDateFormatter(locator)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))

        if title:
            ax.set_title(title, loc="left", fontsize="large")

        ax.get_figure().tight_layout()
        return ax

    def _get_plot_frequency(self, span: pd.Timedelta, max_bars: int):
        seconds = span.total_seconds()

        if seconds / (7 * 24 * 60 * 60) > max_bars:
            freq = "M"
        if seconds / (24 * 60 * 60) > max_bars:
            freq = "W"
        elif seconds / (12 * 60 * 60) > max_bars:
            freq = "D"
        elif seconds / (6 * 60 * 60) > max_bars:
            freq = "12H"
        elif seconds / (60 * 60) > max_bars:
            freq = "6H"
        elif seconds / 60 > max_bars:
            freq = "H"
        elif seconds > max_bars:
            freq = "T"
        else:
            freq = "S"

        return freq

    def _plot_vote_history(self, vote_history: pd.DataFrame, title: Optional[str] = None):
        vote_history.loc[len(vote_history)] = pd.Series(
            {"timestamp": vote_history["timestamp"].min() - pd.DateOffset(seconds=1), "votes": 0}
        )
        vote_history.loc[len(vote_history)] = pd.Series({"timestamp": pd.Timestamp.utcnow(), "votes": 0})
        vote_history = vote_history.sort_values("timestamp")
        span = vote_history["timestamp"].max() - vote_history["timestamp"].min()
        freq = self._get_plot_frequency(span, max_bars=50)
        ohlc = self._timeseries_to_ohlc(vote_history.set_index("timestamp")["votes"].sort_index().cumsum(), freq=freq)
        ohlc = ohlc.tz_convert(self.config["chart_timezone"])
        with plt.style.context(f"minusone.resources.{self.config['mpl_stylesheet']}"):
            ax = self._plot_ohlc(ohlc, title=title)
        return ax

    def _plot_to_discord_file(self, ax: plt.Axes):
        buffer = io.BytesIO()
        ax.get_figure().savefig(buffer, format="png")
        buffer.seek(0)
        return discord.File(buffer, filename="chart.png")

    # endregion

    # region Database

    def _create_votes_per_user(self):
        """Create the votes_per_user table"""
        query = """
            CREATE TABLE IF NOT EXISTS votes_per_user (
                user_id INTEGER PRIMARY KEY,
                votes INTEGER NOT NULL
            )
        """
        self.bot.database.execute(query)

    def _create_vote_history(self):
        """Create the vote_history table"""
        query = """
            CREATE TABLE IF NOT EXISTS vote_history (
                vote_id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                source_user_id INTEGER NOT NULL,
                target_user_id INTEGER NOT NULL,
                votes INTEGER NOT NULL
            )
        """
        self.bot.database.execute(query)

    def _create_tables(self):
        """Create all tables in the database"""
        self._create_votes_per_user()
        self._create_vote_history()

    def _initialize_user(self, user_id):
        """Initialize a user with a certain amount of votes per day"""
        query = f"""
            INSERT INTO votes_per_user (user_id, votes)
            VALUES ({user_id}, {self.initial_votes})
        """
        self.bot.database.execute(query)

    def _get_available_votes(self, user_id):
        """Get the number of votes a user has left"""
        query = f"""
            SELECT votes
            FROM votes_per_user
            WHERE user_id = {user_id}
        """
        result = self.bot.database.execute(query).fetchone()
        if result is None:
            self._initialize_user(user_id)
            return self.initial_votes
        return result[0]

    def _record_vote(self, timestamp, source_user_id, target_user_id, votes):
        """Record a vote in the database"""
        query = f"""
            INSERT INTO vote_history (timestamp, source_user_id, target_user_id, votes)
            VALUES ('{timestamp}', {source_user_id}, {target_user_id}, {votes})
        """
        self.bot.database.execute(query)

    def _add_available_votes(self, user_id, votes):
        """Add to a user's available votes"""
        query = f"""
            UPDATE votes_per_user
            SET votes = MAX(votes + {votes}, 0)
            WHERE user_id = {user_id}
        """
        self.bot.database.execute(query)

    def _get_leaderboard(self, limit=10, top=True, received=True):
        """Get the leaderboard"""
        query = f"""
            SELECT {'target_user_id' if received else 'source_user_id'}, SUM(votes) AS votes
            FROM vote_history
            GROUP BY {'target_user_id' if received else 'source_user_id'}
            ORDER BY votes {'DESC' if top else 'ASC'}
            LIMIT {limit}
        """
        cursor = self.bot.database.execute(query)
        results = cursor.fetchall()
        df = pd.DataFrame(results, columns=["user_id", "votes"])
        df = df.sort_values("votes", ascending=False)
        return df

    def _get_user_count(self, received=True):
        """Get the number of users"""
        query = f"""
            SELECT COUNT(DISTINCT {'target_user_id' if received else 'source_user_id'})
            FROM vote_history
        """
        result = self.bot.database.execute(query).fetchone()
        return result[0]

    def _try_vote(self, timestamp, source_user_id, target_user_id, votes):
        """Try to vote for a user"""
        available_votes = self._get_available_votes(source_user_id)
        if available_votes < abs(votes):
            votes = available_votes if votes > 0 else -available_votes
        if votes == 0:
            return 0
        self._record_vote(timestamp, source_user_id, target_user_id, votes)
        self._add_available_votes(source_user_id, -abs(votes))
        logger.info(
            f"User {self.bot.get_user(source_user_id)} gave {self.bot.get_user(target_user_id)} {votes} "
            f"votes out of {available_votes} left"
        )
        return votes

    def _get_total_votes_for_user(self, user_id):
        """Get the total number of votes for a user"""
        query = f"""
            SELECT SUM(votes)
            FROM vote_history
            WHERE target_user_id = {user_id}
        """
        cursor = self.bot.database.execute(query)
        if cursor.rowcount == 0:
            return 0
        return cursor.fetchone()[0]

    def _get_vote_history_for_user(self, user_id):
        """Get the vote history for a user"""
        query = f"""
            SELECT timestamp, source_user_id, votes
            FROM vote_history
            WHERE target_user_id = {user_id}
            ORDER BY timestamp
        """
        cursor = self.bot.database.execute(query)
        results = cursor.fetchall()
        df = pd.DataFrame(results, columns=["timestamp", "source_user_id", "votes"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], yearfirst=True, utc=True, format="ISO8601")
        return df

    def _reset_all_available_votes(self):
        """Reset all available votes"""
        query = f"""
            UPDATE votes_per_user
            SET votes = {self.initial_votes}
        """
        self.bot.database.execute(query)

    # endregion


async def setup(bot: commands.Bot):
    await bot.add_cog(Votes(bot))
