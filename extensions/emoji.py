import nextcord
from nextcord.ext import commands
import re, random

class Emoji(commands.Cog):
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    # ensure config file has required data
    if not bot.config.has_section('emoji'):
      bot.config.add_section('emoji')
    else:
      if 'emojicmd_names' in bot.config['emoji']:
        self.emojicmd.update(aliases=bot.config['emoji']['emojicmd_names'].split(' '))
  
  @commands.command()
  async def emoji(self, ctx:commands.Context, *, emojiname:str):
    matches = [e for e in self.bot.emojis if emojiname.replace(':','') == e.name]
    if matches:
      await ctx.reply(matches[0])
    else:
      await ctx.reply(self.bot.babel(ctx, 'emoji', 'not_found'))
  
  @commands.command()
  async def emojicmd(self, ctx:commands.Context):
    """posts a random emoji matching a provided template in """
    if 'emojicmd_names' in self.bot.config['emoji'] and\
       'emojicmd_templates' in self.bot.config['emoji'] and\
       'emojicmd_servers' in self.bot.config['emoji']:
      names = self.bot.config['emoji']['emojicmd_names'].split(' ')
      templates = self.bot.config['emoji']['emojicmd_templates'].split(' ')
      servers = self.bot.config['emoji']['emojicmd_servers'].split(' ')
      if ctx.invoked_with in names:
        template = templates[names.index(ctx.invoked_with)]
        server = int(servers[names.index(ctx.invoked_with)])
        emojipool = [e for e in self.bot.emojis if e.guild_id == server and re.match(template, e.name) and e.is_usable()]
        await ctx.reply(random.choice(emojipool))

def setup(bot):
  bot.add_cog(Emoji(bot))