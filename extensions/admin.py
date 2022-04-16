import disnake, asyncio
from disnake.ext import commands

class Admin(commands.Cog):
  """powerful commands only for administrators"""
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    if not bot.config.getboolean('extensions', 'auth', fallback=False):
      raise Exception("'auth' must be enabled to use 'admin'")
    # ensure config file has required data
    if not bot.config.has_section('admin'):
      bot.config.add_section('admin')

  def check_delete(self, message:disnake.Message, strict:bool=False):
    return strict or\
      (message.author==self.bot.user or\
      message.content.lower().startswith(self.bot.config['main']['prefix_short']) or\
      message.content.startswith('<@'+str(self.bot.user.id)+'>') or\
      message.type == disnake.MessageType.pins_add or\
      (self.bot.config['main']['prefix_long'] and\
      message.content.lower().startswith(self.bot.config['main']['prefix_long']))
      )

  @commands.Cog.listener("on_message")
  async def janitor_autodelete(self, message):
    """janitor service, deletes messages after a time"""
    if f"{message.channel.id}_janitor" in self.bot.config['admin']:
      strict = self.bot.config.getint('admin', f"{message.channel.id}_janitor")
      if self.check_delete(message, strict):
        await asyncio.sleep(30)
        await message.delete()

  @commands.group()
  @commands.guild_only()
  async def janitor(self, ctx:commands.Context):
    """setter / getter for the janitor service"""

    if ctx.invoked_subcommand is None:
      raise commands.BadArgument
    else:
      self.bot.cogs['Auth'].admins(ctx.message)
  @janitor.command(name='join')
  async def janitor_join(self, ctx:commands.Context, strict=''):
    self.bot.config['admin'][f'{ctx.channel.id}_janitor'] = '1' if strict else '0'
    self.bot.config.save()
    await ctx.reply(self.bot.babel(ctx, 'admin', 'janitor_set_success'))
  @janitor.command(name='leave')
  async def janitor_leave(self, ctx:commands.Context):
    self.bot.config.remove_option('admin', f'{ctx.channel.id}_janitor')
    self.bot.config.save()
    await ctx.reply(self.bot.babel(ctx, 'admin', 'janitor_unset_success'))

  @commands.command()
  @commands.guild_only()
  async def clean(self, ctx:commands.Context, n_or_id:str, strict:str=None):
    """instant gratification janitor"""

    if n_or_id.isdigit():
      n = int(n_or_id)
      self.bot.cogs['Auth'].mods(ctx.message)
      deleted = await ctx.channel.purge(limit=n, check=lambda m:self.check_delete(m, strict))
      await ctx.reply(self.bot.babel(ctx, 'admin', 'clean_success', n=len(deleted)))
    elif '-' in n_or_id:
      start,end = n_or_id.split('-')
      start,end = int(start),int(end)
      self.bot.cogs['Auth'].mods(ctx.message)
      if start>end: start,end = end,start
      deleted = await ctx.channel.purge(limit=1000,
                                        check=lambda m: m.id>start and m.id<end and self.check_delete(m, strict),
                                        before=disnake.Object(end),
                                        after=disnake.Object(start))
      await ctx.reply(self.bot.babel(ctx, 'admin', 'clean_success', n=len(deleted)))


def setup(bot):
  bot.add_cog(Admin(bot))