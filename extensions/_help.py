import disnake
from disnake.ext import commands
import asyncio
import re
from typing import Union

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
    if 'changelog' not in bot.config['help']:
      bot.config['help']['changes'] = '> '+bot.config['main']['ver']+'\n- No changes yet!'
    
    asyncio.ensure_future(self.set_status())
    
  @commands.Cog.listener('on_ready')
  async def set_status(self, status:disnake.Status=None, message:str=None):
    if self.bot.is_ready():
      if message is None:
        if self.bot.config['help']['customstatus']:
          message = self.bot.config['help']['customstatus']
        else:
          message = self.bot.config['main']['prefix_short']+'help'
      status = disnake.Status.online if status is None else status
      activity = disnake.Game(message)
      await self.bot.change_presence(status=status, activity=activity)
    else:
      # make the bot appear offline if it isn't ready to handle commands
      await self.bot.change_presence(status=disnake.Status.offline)

  def find_command(self, command:str):
    for cmd in self.bot.commands:
      if command == cmd.name or command in cmd.aliases:
        return cmd
    return None

  def get_docs(self, ctx:Union[commands.Context,tuple], cmd:str):
    matchedcommand = self.find_command(cmd)
    # return usage information for a specific command
    if matchedcommand:
      for reflang in self.bot.babel.resolve_lang(ctx):
        reflang = self.bot.babel.langs[reflang]
        for key in reflang.keys():
          if f'command_{matchedcommand.name}_help' in reflang[key]:
            docsrc = self.bot.babel(ctx, key, f'command_{matchedcommand.name}_help', cmd=cmd).splitlines()
            docs = '**'+docsrc[0]+'**'
            if len(docsrc) > 1:
              docs += '\n'+docsrc[1]
            if len(docsrc) > 2:
              for line in docsrc[2:]:
                docs += '\n*'+line+'*'
            return docs
    return None

  @commands.command(aliases=['?','??'])
  async def help(self, ctx:commands.Context, command:str=None):
    """finds usage information in babel and sends them
    highlights some commands if command is None"""
    
    if command:
      docs = self.get_docs(ctx, command)
      if docs is not None:
        # we found the documentation
        await ctx.reply(docs)
      elif self.find_command(command) is not None:
        # the command definitely exists, but there's no documentation
        await ctx.reply(self.bot.babel(ctx, 'help', 'no_docs'))
      else:
        # the command doesn't exist right now, figure out why.
        if command in self.bot.config['help']['future_commands'].split(', '):
          # this command will be coming soon according to config
          await ctx.reply(self.bot.babel(ctx, 'help', 'future_command'))
        elif command in self.bot.config['help']['obsolete_commands'].split(', '):
          # this command is obsolete according to config
          await ctx.reply(self.bot.babel(ctx, 'help', 'obsolete_command'))
        elif command in re.split(r', |>', self.bot.config['help']['moved_commands']):
          # this command has been renamed and requires a new syntax
          moves = re.split(r', |>', self.bot.config['help']['moved_commands'])
          target = moves.index(command)
          if target % 2 == 0:
            await ctx.reply(self.bot.babel(ctx, 'help', 'moved_command', cmd=moves[target + 1]))
          else:
            print(f"WARNING: bad config. in help/moved_command: {moves[target-1]} is now {moves[target]} but {moves[target]} doesn't exist.")
            await ctx.reply(self.bot.babel(ctx, 'help', 'no_command'))
        else:
          await ctx.reply(self.bot.babel(ctx, 'help', 'no_command'))

    else:
      # show the generic help embed with a variety of featured commands
      if str(ctx.author.id if isinstance(ctx.channel, disnake.DMChannel) else ctx.channel.guild.id) in self.bot.config['prefix'] and\
         len(self.bot.config['prefix'][str(ctx.channel.guild.id)]):
        longprefix = None
      else:
        longprefix = self.bot.config['main']['prefix_long']
      embed = disnake.Embed(title = f"{self.bot.config['main']['botname']} help",
                            description = self.bot.babel(ctx, 'help', 'introduction',
                                                         longprefix = longprefix,
                                                         videoexamples = self.bot.config.getboolean('help','helpurlvideoexamples'),
                                                         serverinv = self.bot.config['help']['serverinv']),
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
      
      await ctx.reply(self.bot.babel(ctx, 'help', 'helpurl_cta') if self.bot.config['help']['helpurl'] else "", embed=embed)

  @commands.command(aliases=['info','invite'])
  async def about(self, ctx:commands.Context):
    """information about this bot, including an invite link"""

    embed = disnake.Embed(title = self.bot.babel(ctx, 'help', 'about_title'),
                          description = self.bot.babel(ctx, 'help', 'bot_description'),
                          color = int(self.bot.config['main']['themecolor'], 16),
                          url = self.bot.config['help']['helpurl'] if self.bot.config['help']['helpurl'] else '')
    
    embed.add_field(name = self.bot.babel(ctx, 'help', 'about_field1_title'),
                    value = self.bot.babel(ctx, 'help', 'about_field1_value', cmds=len(self.bot.commands), guilds=len(self.bot.guilds)),
                    inline = False)
    embed.add_field(name = self.bot.babel(ctx, 'help', 'about_field2_title'),
                    value = self.bot.babel(ctx, 'help', 'about_field2_value', longprefix=self.bot.config['main']['prefix_long']),
                    inline = False)
    embed.add_field(name = self.bot.babel(ctx, 'help', 'about_field3_title'),
                    value = self.bot.babel(ctx, 'help', 'about_field3_value', videoexamples=self.bot.config.getboolean('help','helpurlvideoexamples'), serverinv=self.bot.config['help']['serverinv']),
                    inline = False)
    embed.add_field(name = self.bot.babel(ctx, 'help', 'about_field4_title'),
                    value = self.bot.babel(ctx, 'help', 'about_field4_value'),
                    inline = False)
    embed.add_field(name = self.bot.babel(ctx, 'help', 'about_field5_title'),
                    value = self.bot.babel(ctx, 'help', 'about_field5_value', invite=f'https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&scope=bot&permissions=0'),
                    inline = False)
    
    embed.set_footer(text = self.bot.babel(ctx, 'help', 'creator_footer'),
                     icon_url = self.bot.user.avatar.url)

    await ctx.reply(self.bot.babel(ctx, 'help', 'helpurl_cta') if self.bot.config['help']['helpurl'] else "", embed=embed)

  @commands.command(aliases=['changelog','change'])
  async def changes(self, ctx:commands.Context, ver=None):
    """lists 15 changelog entries from [ver]"""
    changes = self.bot.config['help']['changelog'].splitlines()
    fchanges = ["**"+i.replace('> ','')+"**" if i.startswith('> ') else i for i in changes]
    versions = {v.replace('> ',''):i for i,v in enumerate(changes) if v.startswith('> ')}
    versionlist = list(versions.keys())
    if ver == None or ver.replace('v','') not in versionlist: ver = self.bot.config['main']['ver']
    if ver not in versionlist: ver = versionlist[-1]

    start = versions[ver]
    end = start + 15
    changelog = '\n'.join(fchanges[start:end])
    if end < len(fchanges): changelog += "\n..."

    logurl = self.bot.config['help']['helpurl']+"changes.html#"+ver.replace('.','') if self.bot.config['help']['helpurl'] else ''

    embed = disnake.Embed(title = self.bot.babel(ctx, 'help', 'changelog_title'),
                          description = self.bot.babel(ctx, 'help', 'changelog_description', ver=ver) +\
                                        '\n\n' + changelog,
                          color = int(self.bot.config['main']['themecolor'], 16),
                          url = logurl)
    embed.set_footer(text = self.bot.babel(ctx, 'help', 'creator_footer'),
                     icon_url = self.bot.user.avatar.url)
    
    await ctx.reply(self.bot.babel(ctx, 'help', 'changelog_cta', logurl=logurl) if logurl else None, embed=embed)

  @commands.command()
  async def feedback(self, ctx:commands.Context, feedback:str):
    #TODO: add image support for screenshots
    if self.bot.config['help']['feedbackchannel']:
      feedbackchannel = await self.bot.fetch_channel(self.bot.config['help']['feedbackchannel'])
      if feedbackchannel:
        embed = disnake.Embed(title = self.bot.babel(ctx, 'help', 'feedback_title', author=f'{ctx.author.name}#{ctx.author.discriminator}', guild=ctx.guild.name if ctx.guild else ''),
                              description = feedback,
                              color = int(self.bot.config['main']['themecolor'], 16))
        await feedbackchannel.send(embed=embed)
        await ctx.reply(self.bot.babel(ctx, 'help', 'feedback_success')+\
                       ('\n' + self.bot.babel(ctx, 'help', 'feedback_cta')) if self.bot.config['help']['serverinv'] else '')
      else:
        await ctx.reply(self.bot.babel(ctx, 'help', 'feedback_failed')+\
                       ('\n' + self.bot.babel(ctx, 'help', 'feedback_cta')) if self.bot.config['help']['serverinv'] else '')
    else:
      await ctx.reply(self.bot.babel(ctx, 'help', 'feedback_not_implemented', serverinv = self.bot.config['help']['serverinv']))

def setup(bot):
  bot.add_cog(Help(bot))