import disnake
from disnake.ext import commands
import re

class Language(commands.Cog):
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    # ensure config file has required data
    if not bot.config.has_section('language'):
      bot.config.add_section('language')
  
  @commands.group()
  async def language(self, ctx:commands.Context):
    """user-facing setter/getter for guild/user language options"""
    if ctx.invoked_subcommand is None:
      await self.language_list(ctx)
  @language.command(name='list')
  async def language_list(self, ctx:commands.Context):
    embed = disnake.Embed(title = self.bot.babel(ctx, 'language', 'list_title'),
                          description = self.bot.babel(ctx, 'language', 'set_howto')+\
                          '\n'+self.bot.babel(ctx, 'language', 'contribute_cta') if self.bot.config['language']['contribute_url'] else '',
                          color = int(self.bot.config['main']['themecolor'], 16))
    
    for langcode,language in self.bot.babel.langs.items():
      if prefix := self.bot.config['language']['prefix']:
        if not langcode.startswith(prefix): continue
      embed.add_field(name=f"{language.get('meta', 'name')} ({langcode.replace(prefix, '')})",
                      value=f"{language.get('meta', 'contributors', fallback=self.bot.babel(ctx, 'language', 'unknown_contributors'))}\n"+\
                            self.bot.babel(ctx, 'language', 'coverage_label', coverage = self.bot.babel.calculate_coverage(langcode)))
    
    await ctx.reply(embed=embed)
  @language.command(name='get')
  async def language_get(self, ctx:commands.Context):
    langs, origins = self.bot.babel.resolve_lang(ctx, debug=True)

    language = self.bot.babel.langs[langs[0]]
    embed = disnake.Embed(title = f"{language.get('meta', 'name')} ({langs[0]})",
                          description = self.bot.babel(ctx, 'language', 'origin_reason_'+origins[0]),
                          color = int(self.bot.config['main']['themecolor'], 16))
    
    await ctx.reply(embed=embed)
  @language.command(name='set')
  async def language_set(self, ctx:commands.Context, langcode:str):
    if re.match(r'[a-z]{2}(-[A-Z]{2})?$', langcode) is None:
      await ctx.reply(self.bot.babel(ctx, 'language', 'set_failed_invalid_pattern'))
    else:
      langcode = self.bot.config.get('language', 'prefix', fallback='')+langcode
      if isinstance(ctx.channel, disnake.abc.PrivateChannel) or not ctx.author.guild_permissions.administrator:
        usermode = True
        self.bot.config.set('language', str(ctx.author.id), langcode)
      else:
        usermode = False
        self.bot.config.set('language', str(ctx.guild.id), langcode)
      self.bot.config.save()
      if langcode in self.bot.babel.langs.keys():
        await ctx.reply(self.bot.babel(ctx,
                                      'language',
                                      'set_success',
                                      language=self.bot.babel.langs[langcode].get('meta', 'name'),
                                      usermode=usermode))
      else:
        await ctx.reply(self.bot.babel(ctx, 'language', 'set_warning_no_match')+'\n'+self.bot.babel(ctx, 'language', 'contribute_cta'))

def setup(bot):
  bot.add_cog(Language(bot))