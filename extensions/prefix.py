import nextcord
from nextcord.ext import commands
from typing import Dict, Pattern, Union
import re, asyncio

class Prefix(commands.Cog):
  """a prototype service for commandless bots"""
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    if not bot.config.getboolean('extensions', 'auth', fallback=False):
      raise Exception("'auth' must be enabled to use 'admin'")
    self.auth = bot.cogs['Auth']
    # ensure config file has required data
    if not bot.config.has_section('prefix'):
      bot.config.add_section('prefix')
    self.fallback_prefix = bot.command_prefix
    bot.command_prefix = self.check_prefix

  def check_prefix(self, bot, message:nextcord.Message):
    if isinstance(message.channel, nextcord.TextChannel):
      if str(message.channel.guild.id) in self.bot.config['prefix'] and len(self.bot.config['prefix'][str(message.channel.guild.id)]):
        return [self.bot.config['prefix'][str(message.guild.id)]] + commands.when_mentioned(bot, message)
    return self.fallback_prefix(bot, message)
  
  @commands.group()
  @commands.guild_only()
  async def prefix(self, ctx:commands.Context):
    if ctx.invoked_subcommand is None:
      raise commands.errors.BadArgument
    else:
      self.auth.admins(ctx)
  @prefix.command(name='set')
  async def prefix_set(self, ctx:commands.Context, prefix:str, guild:int=0):
    prefix = prefix.strip(' ')
    if guild:
      self.auth.authusers(ctx)
      self.bot.config['prefix'][str(guild)] = prefix
    else:
      self.bot.config['prefix'][str(ctx.guild.id)] = prefix
    self.bot.config.save()
    await ctx.reply(self.bot.babel(ctx, 'prefix', 'set_success', prefix=prefix))
  @prefix.command(name='unset')
  async def prefix_unset(self, ctx:commands.Context, guild:int=0):
    if guild:
      self.auth.authusers(ctx)
      self.bot.config.remove_option('prefix', str(guild))
    else:
      self.bot.config.remove_option('prefix', str(ctx.guild.id))
    self.bot.config.save()
    await ctx.reply(self.bot.babel(ctx, 'prefix', 'unset_success'))
  @prefix.command(name='get')
  async def prefix_get(self, ctx:commands.Context):
    await ctx.reply(self.bot.babel(ctx, 'prefix', 'get', prefix=self.bot.config.get('prefix', str(ctx.guild.id), fallback='')))

def setup(bot):
  bot.add_cog(Prefix(bot))