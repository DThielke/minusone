from typing import Literal, Optional

import discord
from discord.ext import commands


class Admin(commands.Cog, name="admin"):
    """Admin-only commands"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="sync")
    @commands.is_owner()
    async def sync(
        ctx: commands.Context,
        guilds: commands.Greedy[discord.Object],
        spec: Optional[Literal["~", "*", "^"]] = None,
    ) -> None:
        """Sync commands with Discord"""
        if not guilds:
            if spec == "~":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "^":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                synced = []
            else:
                synced = await ctx.bot.tree.sync()
            await ctx.send(f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild'}")
            return
        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1
        await ctx.send(f"Synced the tree to {ret}/{len(guilds)}")

    @commands.command(name="load")
    @commands.is_owner()
    async def load(self, ctx: commands.Context, cog: str) -> None:
        """Load a cog"""
        await self.bot.load_extension(f"minusone.cogs.{cog}")
        await ctx.send(f"Loaded {cog}")

    @commands.command(name="unload")
    @commands.is_owner()
    async def unload(self, ctx: commands.Context, cog: str) -> None:
        """Unload a cog"""
        await self.bot.unload_extension(f"minusone.cogs.{cog}")
        await ctx.send(f"Unloaded {cog}")

    @commands.command(name="reload")
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, cog: str) -> None:
        """Reload a cog"""
        await self.bot.reload_extension(f"minusone.cogs.{cog}")
        await ctx.send(f"Reloaded {cog}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
