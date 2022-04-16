"""
  Language - Internationalisation features powered by Babel
  Features: Rich translation, online editor
  Related: https://github.com/yiays/Babel-Translator
"""

import re
import disnake
from disnake.ext import commands

class Language(commands.Cog):
  """ Enables per-user and per-guild string translation of the bot """
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    # ensure config file has required data
    if not bot.config.has_section('language'):
      bot.config.add_section('language')

  @commands.slash_command()
  async def language(self, inter:disnake.ApplicationCommandInteraction):
    """
    Manage internationalisation settings for interactions with this account or any servers you manage
    """

  @language.sub_command(name='list')
  async def language_list(self, inter:disnake.ApplicationCommandInteraction):
    """
    Lists all available languages this bot can be translated to
    """
    embed = disnake.Embed(
      title = self.bot.babel(inter, 'language', 'list_title'),
      description = self.bot.babel(inter, 'language', 'set_howto')+\
      '\n'+self.bot.babel(inter, 'language', 'contribute_cta') if self.bot.config['language']['contribute_url'] else '',
      color = int(self.bot.config['main']['themecolor'], 16)
    )

    for langcode,language in self.bot.babel.langs.items():
      if prefix := self.bot.config['language']['prefix']:
        if not langcode.startswith(prefix):
          continue
      embed.add_field(
        name=language.get('meta', 'name') + ' (' + langcode.replace(prefix, '') + ')',
        value=language.get(
          'meta',
          'contributors',
          fallback=self.bot.babel(inter, 'language', 'unknown_contributors')
        ) + '\n' +\
        self.bot.babel(
          inter,
          'language',
          'coverage_label',
          coverage = self.bot.babel.calculate_coverage(langcode)
        )
      )

    await inter.send(embed=embed)

  @language.sub_command(name='get')
  async def language_get(self, inter:disnake.ApplicationCommandInteraction):
    """
    Get the language the bot is using with you right now and the reason why it was selected
    """
    langs, origins = self.bot.babel.resolve_lang(
      user_id=inter.author.id,
      guild_id=inter.guild_id,
      debug=True
    )

    embeds = []
    backup = False
    for lang, origin in zip(langs, origins):
      if lang.startswith(self.bot.config['language']['prefix']):
        embeds.append(disnake.Embed(
          title = f"{self.bot.babel.langs[lang].get('meta', 'name')} ({lang})",
          description = self.bot.babel(inter, 'language', 'origin_reason_'+origin, backup=backup),
          color = int(self.bot.config['main']['themecolor'], 16)
        ))
        backup = True

    await inter.send(embeds=embeds)

  @language.sub_command(name='set')
  async def language_set(
    self,
    inter:disnake.ApplicationCommandInteraction,
    language:str
  ):
    """
    Change the language that this bot uses with you or a server you manage

    Parameters
    ----------
    language: An ISO language code for your language and dialect
    """
    if not language == 'default' and re.match(r'[a-z]{2}(-[A-Z]{2})?$', language) is None:
      await inter.send(self.bot.babel(inter, 'language', 'set_failed_invalid_pattern'))
    else:
      if language != 'default':
        language = self.bot.config.get('language', 'prefix', fallback='')+language
      if (
        isinstance(inter.author, disnake.User) or
        not inter.author.guild_permissions.administrator
      ):
        usermode = True
        if language == 'default':
          self.bot.config.remove_option('language', str(inter.author.id))
        else:
          self.bot.config.set('language', str(inter.author.id), language)
      else:
        usermode = False
        if language == 'default':
          self.bot.config.remove_option('language', str(inter.guild.id))
        else:
          self.bot.config.set('language', str(inter.guild.id), language)
      self.bot.config.save()
      if language == 'default' or language in self.bot.babel.langs.keys():
        await inter.send(self.bot.babel(
          inter,
          'language',
          'unset_success' if language == 'default' else 'set_success',
          language = (
            self.bot.babel.langs[self.bot.babel.defaultlang].get('meta', 'name')
            if language == 'default' else
            self.bot.babel.langs[language].get('meta', 'name')
          ),
          usermode = usermode)
        )
      else:
        await inter.send(
          self.bot.babel(inter, 'language', 'set_warning_no_match')+'\n'+\
          self.bot.babel(inter, 'language', 'contribute_cta')
        )
  @language_set.autocomplete('language')
  def language_set_ac(self, _:disnake.MessageCommandInteraction, search:str):
    """ Suggests languages that are already available """
    matches = []
    prefix = self.bot.config['language']['prefix']
    for lang in self.bot.babel.langs.keys():
      if lang.startswith(prefix) and search in lang:
        matches.append(lang.replace(prefix, ''))
    return ['default'] + matches

def setup(bot):
  """ Bind this cog to the bot """
  bot.add_cog(Language(bot))
