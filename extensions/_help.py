"""
  Help - User support and documentation
  Features: data-driven formatting based on config and translation files
  Recommended cogs: any cogs that have featured commands
"""

import re
from typing import Union, Optional
import disnake
from disnake.ext import commands

class Help(commands.Cog):
  """the user-friendly documentation core"""
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    # ensure config file has required data
    if not bot.config.has_section('help'):
      bot.config.add_section('help')
    if 'customstatus' not in bot.config['help']:
      bot.config['help']['customstatus'] = ''
    if 'helpurl' not in bot.config['help']:
      bot.config['help']['helpurl'] = ''
    if 'helpurlvideoexamples' not in bot.config['help']:
      bot.config['help']['helpurlvideoexamples'] = ''
    if 'serverinv' not in bot.config['help']:
      bot.config['help']['serverinv'] = ''
    if 'feedbackchannel' not in bot.config['help']:
      bot.config['help']['feedbackchannel'] = ''
    if 'highlight_sections' not in bot.config['help']:
      bot.config['help']['highlight_sections'] = '💡 learn'
    if 'learn_highlights' not in bot.config['help']:
      bot.config['help']['learn_highlights'] = 'help'
    if 'future_commands' not in bot.config['help']:
      bot.config['help']['future_commands'] = ''
    if 'obsolete_commands' not in bot.config['help']:
      bot.config['help']['obsolete_commands'] = ''
    if 'hidden_commands' not in bot.config['help']:
      bot.config['help']['hidden_commands'] = ''
    if 'changelog' not in bot.config['help']:
      bot.config['help']['changes'] = '> '+bot.config['main']['ver']+'\n- No changes yet!'

  @commands.Cog.listener('on_connect')
  async def on_starting(self):
    """ make the bot appear busy if it isn't ready to handle commands """
    if not self.bot.is_ready():
      await self.bot.change_presence(status=disnake.Status.dnd)

  @commands.Cog.listener('on_ready')
  async def set_status(self, status:disnake.Status=None, message:str=None):
    """ appear online and add help command information to the status """
    if message is None:
      if self.bot.config['help']['customstatus']:
        message = self.bot.config['help']['customstatus']
      else:
        message = self.bot.config['main']['prefix_short']+'help'
    status = disnake.Status.online if status is None else status
    activity = disnake.Game(message)
    await self.bot.change_presence(status=status, activity=activity)

  def find_command(self, command:str) -> Union[commands.Command, commands.InvokableSlashCommand]:
    """ search currently enabled commands for an instance of the string """
    for cmd in self.bot.slash_commands:
      if command == cmd.name:
        return cmd
    for cmd in self.bot.commands:
      if command == cmd.name or command in cmd.aliases:
        return cmd
    return None

  def get_docs(self, ctx:Union[commands.Context,tuple], cmd:str):
    """ find documentation for this command in babel """
    matchedcommand = self.find_command(cmd)
    # return usage information for a specific command
    if matchedcommand:
      for reflang in self.bot.babel.resolve_lang(ctx.author.id, ctx.guild.id if ctx.guild else None):
        reflang = self.bot.babel.langs[reflang]
        for key in reflang.keys():
          if f'command_{matchedcommand.name}_help' in reflang[key]:
            docsrc = self.bot.babel(
              ctx,
              key,
              f'command_{matchedcommand.name}_help',
              cmd=cmd
            ).splitlines()
            docs = '**'+docsrc[0]+'**'
            if len(docsrc) > 1:
              docs += '\n'+docsrc[1]
            if len(docsrc) > 2:
              for line in docsrc[2:]:
                docs += '\n*'+line+'*'
            return docs
    return None

  @commands.slash_command(name='help')
  async def slash_help(
    self, inter:disnake.ApplicationCommandInteraction, command:Optional[str]
  ):
    """
    Learn how to use this bot

    Parameters
    ----------
    command: Search for a specific command's documentation
    """
    await self.help(inter, command)

  @commands.command(aliases=['?','??'])
  async def help(
    self,
    ctx:Union[commands.Context, disnake.ApplicationCommandInteraction],
    command:Optional[str]=None,
    **kwargs
  ):
    """finds usage information in babel and sends them
    highlights some commands if command is None"""

    if command:
      docs = self.get_docs(ctx, command)
      if docs is not None:
        # we found the documentation
        await ctx.send(docs, **kwargs)
      elif self.find_command(command) is not None:
        # the command definitely exists, but there's no documentation
        await ctx.send(self.bot.babel(ctx, 'help', 'no_docs'), **kwargs)
      else:
        # the command doesn't exist right now, figure out why.
        if command in self.bot.config['help']['future_commands'].split(', '):
          # this command will be coming soon according to config
          await ctx.send(self.bot.babel(ctx, 'help', 'future_command'), **kwargs)
        elif command in self.bot.config['help']['obsolete_commands'].split(', '):
          # this command is obsolete according to config
          await ctx.send(self.bot.babel(ctx, 'help', 'obsolete_command'), **kwargs)
        elif command in re.split(r', |>', self.bot.config['help']['moved_commands']):
          # this command has been renamed and requires a new syntax
          moves = re.split(r', |>', self.bot.config['help']['moved_commands'])
          target = moves.index(command)
          if target % 2 == 0:
            await ctx.send(
              self.bot.babel(ctx, 'help', 'moved_command', cmd=moves[target + 1]),
              **kwargs
            )
          else:
            print(
              "WARNING: bad config. in help/moved_command:\n"
              f"{moves[target-1]} is now {moves[target]} but {moves[target]} doesn't exist."
            )
            await ctx.send(self.bot.babel(ctx, 'help', 'no_command'), **kwargs)
        else:
          await ctx.send(self.bot.babel(ctx, 'help', 'no_command'), **kwargs)

    else:
      # show the generic help embed with a variety of featured commands
      if isinstance(ctx.channel, disnake.TextChannel) and\
         str(ctx.channel.guild.id) in self.bot.config['prefix'] and\
         len(self.bot.config['prefix'][str(ctx.channel.guild.id)]):
        longprefix = None
      else:
        longprefix = self.bot.config['main']['prefix_long']
      embed = disnake.Embed(
        title = f"{self.bot.config['main']['botname']} help",
        description = self.bot.babel(
          ctx, 'help', 'introduction',
          longprefix = longprefix,
          videoexamples = self.bot.config.getboolean('help','helpurlvideoexamples'),
          serverinv = self.bot.config['help']['serverinv']
        ),
        color = int(self.bot.config['main']['themecolor'], 16),
        url = self.bot.config['help']['helpurl'] if self.bot.config['help']['helpurl'] else '')

      sections = self.bot.config['help']['highlight_sections'].split(', ')
      for section in sections:
        hcmds = []
        for hcmd in self.bot.config['help'][section.split()[1]+'_highlights'].split(', '):
          if self.find_command(hcmd):
            hcmds.append(hcmd)
          else:
            hcmds.append(hcmd+'❌')
        embed.add_field(name = section, value = '```'+', '.join(hcmds)+'```', inline = False)

      embed.set_footer(text = self.bot.babel(ctx, 'help', 'creator_footer'),
                       icon_url = self.bot.user.avatar.url)

      await ctx.send(
        self.bot.babel(ctx, 'help', 'helpurl_cta') if self.bot.config['help']['helpurl'] else "",
        embed=embed,
        **kwargs
      )
  @slash_help.autocomplete('command')
  def ac_command(self, _:disnake.ApplicationCommandInteraction, command:str):
    """ find any commands that contain the provided string """
    matches = []
    hide = self.bot.config.get('help', 'hidden_commands', fallback='').split(', ')
    for cmd in self.bot.slash_commands:
      if command in cmd.name and cmd.name not in matches and cmd.name not in hide:
        matches.append(cmd.name)
    for cmd in self.bot.commands:
      if command in cmd.name and cmd.name not in matches and cmd.name not in hide:
        matches.append(cmd.name)
      else:
        for alias in cmd.aliases:
          if command in alias and cmd.name not in matches and cmd.name not in hide:
            matches.append(cmd.name)
    return matches

  @commands.slash_command()
  async def about(self, inter:disnake.ApplicationCommandInteraction):
    """
    General information about this bot, including an invite link
    """

    embed = disnake.Embed(
      title = self.bot.babel(inter, 'help', 'about_title'),
      description = self.bot.babel(inter, 'help', 'bot_description'),
      color = int(self.bot.config['main']['themecolor'], 16),
      url = self.bot.config['help']['helpurl'] if self.bot.config['help']['helpurl'] else ''
    )

    embed.add_field(
      name = self.bot.babel(inter, 'help', 'about_field1_title'),
      value = self.bot.babel(
        inter,
        'help',
        'about_field1_value',
        cmds=len(self.bot.commands),
        guilds=len(self.bot.guilds)
      ),
      inline = False
    )
    embed.add_field(
      name = self.bot.babel(inter, 'help', 'about_field2_title'),
      value = self.bot.babel(
        inter,
        'help',
        'about_field2_value',
        longprefix=self.bot.config['main']['prefix_long']
      ),
      inline = False
    )
    embed.add_field(
      name = self.bot.babel(inter, 'help', 'about_field3_title'),
      value = self.bot.babel(
        inter,
        'help',
        'about_field3_value',
        videoexamples=self.bot.config.getboolean('help','helpurlvideoexamples'),
        serverinv=self.bot.config['help']['serverinv']
      ),
      inline = False
    )
    embed.add_field(
      name = self.bot.babel(inter, 'help', 'about_field4_title'),
      value = self.bot.babel(inter, 'help', 'about_field4_value'),
      inline = False
    )
    embed.add_field(
      name = self.bot.babel(inter, 'help', 'about_field5_title'),
      value = self.bot.babel(
        inter,
        'help',
        'about_field5_value',
        invite=f'https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&scope=bot%20applications.commands&permissions=0'
      ),
      inline = False
    )

    embed.set_footer(
      text = self.bot.babel(inter, 'help', 'creator_footer'),
      icon_url = self.bot.user.avatar.url
    )

    await inter.send(
      self.bot.babel(inter, 'help', 'helpurl_cta') if self.bot.config['help']['helpurl'] else "",
      embed=embed
    )

  @commands.slash_command()
  async def changes(self, inter:disnake.ApplicationCommandInteraction, search:str):
    """
    See what's changed in recent updates

    Parameters
    ----------
    search: Find the version a change occured in, or search for a version number
    """
    changes = self.bot.config['help']['changelog'].splitlines()
    fchanges = ["**"+i.replace('> ','')+"**" if i.startswith('> ') else i for i in changes]
    versions = {v.replace('> ',''):i for i,v in enumerate(changes) if v.startswith('> ')}
    versionlist = list(versions.keys())
    if search is None or search.replace('v','') not in versionlist:
      search = self.bot.config['main']['ver']
    if search not in versionlist:
      search = versionlist[-1]

    start = versions[search]
    end = start + 15
    changelog = '\n'.join(fchanges[start:end])
    if end < len(fchanges):
      changelog += "\n..."

    logurl = (
      self.bot.config['help']['helpurl']+"changes.html#"+search.replace('.','')
      if self.bot.config['help']['helpurl'] else ''
    )

    embed = disnake.Embed(
      title = self.bot.babel(inter, 'help', 'changelog_title'),
      description = self.bot.babel(inter, 'help', 'changelog_description', ver=search) +\
        '\n\n' + changelog,
      color = int(self.bot.config['main']['themecolor'], 16),
      url = logurl
    )
    embed.set_footer(
      text = self.bot.babel(inter, 'help', 'creator_footer'),
      icon_url = self.bot.user.avatar.url
    )

    await inter.send(
      self.bot.babel(inter, 'help', 'changelog_cta', logurl=logurl) if logurl else None,
      embed=embed
    )
  @changes.autocomplete('search')
  def ac_version(self, _:disnake.ApplicationCommandInteraction, search:str):
    """ find any matching versions """
    matches = []
    iver = '0'
    for line in self.bot.config['help']['changelog'].splitlines():
      if line.startswith('> '):
        iver = line[2:]
      if search.lower() in line.lower() and iver not in matches:
        matches.append(iver)
    return matches

  @commands.slash_command()
  async def feedback(
    self,
    inter:disnake.ApplicationCommandInteraction,
    feedback:str,
    screenshot:Optional[disnake.Attachment] = None
  ):
    """
    Send feedback to the developers

    Parameters
    ----------
    feedback: Your feedback, sent as a message to the developers of this bot
    screenshot: Any relevant screenshot or diagram that might communicate your idea
    """
    if self.bot.config['help']['feedbackchannel']:
      feedbackchannel = await self.bot.fetch_channel(self.bot.config['help']['feedbackchannel'])
      if feedbackchannel:
        embed = disnake.Embed(
          title = self.bot.babel(
            inter,
            'help',
            'feedback_title',
            author=f'{inter.author.name}#{inter.author.discriminator}',
            guild=inter.guild.name if inter.guild else ''
          ),
          description = feedback,
          color = int(self.bot.config['main']['themecolor'], 16)
        )
        if screenshot:
          embed.set_image(screenshot.url)
        await feedbackchannel.send(embed=embed)
        await inter.send(
          self.bot.babel(inter, 'help', 'feedback_success') +
          ('\n' + self.bot.babel(inter, 'help', 'feedback_cta'))
          if self.bot.config['help']['serverinv'] else ''
        )
      else:
        await inter.send(
          self.bot.babel(inter, 'help', 'feedback_failed') +
          ('\n' + self.bot.babel(inter, 'help', 'feedback_cta'))
          if self.bot.config['help']['serverinv'] else ''
        )
    else:
      await inter.send(self.bot.babel(
        inter,
        'help',
        'feedback_not_implemented',
        serverinv = self.bot.config['help']['serverinv']
      ))

def setup(bot:commands.Bot):
  """ Bind this cog to the bot """
  bot.add_cog(Help(bot))
