import discord
from discord.ext import commands
import asyncio

class Premium(commands.cog.Cog):
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    # ensure config file has required data
    if not bot.config.has_section('premium'):
      bot.config.add_section('premium')
    if 'icon' not in bot.config['premium']:
      bot.config['premium']['icon'] = ''
    if 'patreon' not in bot.config['premium']:
      bot.config['premium']['patreon'] = ''
    if 'other' not in bot.config['premium']:
      bot.config['premium']['other'] = ''
    if 'restricted_commands' not in bot.config['premium']:
      bot.config['premium']['restricted_commands'] = ''
    if 'premium_role_guild' not in bot.config['premium'] or\
       not bot.config['premium']['premium_role_guild'] or\
       'premium_roles' not in bot.config['premium'] or\
       not bot.config['premium']['premium_roles']:
      bot.config['premium']['premium_role_guild'] = ''
      bot.config['premium']['premium_roles'] = ''
      raise Exception("You must provide a reference to a guild and role in order for premium to work!")
    if not bot.config.get('help', 'serverinv', fallback=''):
      raise Exception("You must have an invite to the support server with the supporter role in config[help][serverinv]!")
    bot.add_check(self.check_premium_command)

  #TODO: fetch the premium guild on ready

  def check_premium(self, user:discord.User):
    premiumguild = self.bot.get_guild(self.bot.config.getint('premium', 'premium_role_guild'))
    premiumroles = [premiumguild.get_role(int(i)) for i in self.bot.config.get('premium', 'premium_roles').split(' ')]
    if not premiumroles:
      raise Exception("The designated premium role was not found!")
    
    member = premiumguild.get_member(user.id)
    if isinstance(member, discord.Member):
      return list(set(premiumroles) & set(member.roles))
    else:
      return False

  def check_premium_command(self, ctx:commands.Context):
    if ctx.command.name in self.bot.config['premium']['restricted_commands'].split(' '):
      if self.check_premium(ctx.author):
        return True # user is premium
      else:
        embed = discord.Embed(title=self.bot.babel(ctx, 'premium', 'required_title'),
                              description=self.bot.babel(ctx, 'premium', 'required_error'))
        embed.url = self.bot.config['premium']['patreon'] if self.bot.config['premium']['patreon'] else self.bot.config['premium']['other']
        embed.set_thumbnail(url=self.bot.config['premium']['icon'])

        asyncio.ensure_future(ctx.reply(embed=embed))
        return False # user is not premium
    return True # command is not restricted
  
  @commands.command(aliases=['support'])
  async def premium(self, ctx:commands.Context):
    embed = discord.Embed(title=self.bot.babel(ctx, 'premium', 'name'),
                          description=self.bot.babel(ctx, 'premium', 'desc'))
    
    embed.url = self.bot.config['premium']['patreon'] if self.bot.config['premium']['patreon'] else self.bot.config['premium']['other']
    embed.set_thumbnail(url=self.bot.config['premium']['icon'])

    i = 1
    while f'feature_{i}' in self.bot.babel.langs[self.bot.babel.baselang]['premium']:
      embed.add_field(name=self.bot.babel(ctx, 'premium', f'feature_{i}'),
                      value=self.bot.babel(ctx, 'premium', f'feature_{i}_desc'),
                      inline=False)
      i += 1
    
    embed.set_footer(text=self.bot.babel(ctx, 'premium', 'fine_print'))

    await ctx.reply(self.bot.babel(ctx, 'premium', 'cta', link=embed.url), embed=embed)


def setup(bot):
  bot.add_cog(Premium(bot))