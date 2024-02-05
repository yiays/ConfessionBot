import asyncio
import disnake
from disnake.ext import commands

class ReactRoles(commands.Cog):
  """allows admins to set up messages where reacting grants users roles"""
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    if not bot.config.getboolean('extensions', 'auth', fallback=False):
      raise AssertionError("'auth' must be enabled to use 'reactroles'")
    if not bot.config.getboolean('extensions', 'help', fallback=False):
      print(Warning("'help' is a recommended extension for 'reactroles'"))
    # ensure config file has required data
    if not bot.config.has_section('reactroles'):
      bot.config.add_section('reactroles')
    msglist = 'list[disnake.abc.Messageable]'
    self.watching:msglist = []

  #TODO: make it possible for admins to add more reaction roles or delete them later
  #TODO: notice if the rr prompt is deleted during setup

  @commands.Cog.listener("on_ready")
  async def fetch_tracking_messages(self):
    """ Request the message once so we'll be notified if reactions change """
    search = [k for k in self.bot.config['reactroles'].keys()]
    for chid,msgid in set([(rr.split('_')[0], rr.split('_')[1]) for rr in search]):
      try:
        ch = await self.bot.fetch_channel(chid)
        msg = await ch.fetch_message(msgid)
        self.watching.append(msg)
      except Exception as e:
        print(f"failed to get reactionrole message {msgid} from channel {chid}. {e}")
    await self.catchup()

  @commands.Cog.listener("on_message_delete")
  async def revoke_tracking_message(self, message):
    """ Remove message from config so it won't attempt to load it again """
    if message in self.watching:
      matches = [
        k for k in self.bot.config['reactroles'].keys() if k.split('_')[1] == str(message.id)
      ]
      for k in matches:
        self.bot.config.remove_option('reactroles',k)
      #TODO: (low priority) maybe remove deleted message from self.watching?

  @commands.Cog.listener("on_raw_reaction_add")
  async def reactrole_add(self, data:disnake.RawReactionActionEvent):
    """ Grant the user their role """
    if isinstance(data.member, disnake.Member):
      emojiid = data.emoji if data.emoji.is_unicode_emoji() else data.emoji.id
      if f"{data.channel_id}_{data.message_id}_{emojiid}_roles" in self.bot.config['reactroles']:
        channel = await self.bot.fetch_channel(data.channel_id)
        roleids = [int(r) for r in self.bot.config['reactroles'][f"{data.channel_id}_{data.message_id}_{emojiid}_roles"].split(' ')]
        roles = []
        for roleid in roleids:
          try:
            roles.append(channel.guild.get_role(roleid))
          except Exception as e:
            print("failed to get role for reactrole: "+str(e))
        await data.member.send(self.bot.babel(data.member, 'reactroles', 'role_granted', roles=', '.join([role.name for role in roles])))
        await data.member.add_roles(*roles, reason='reactroles')

  @commands.Cog.listener("on_raw_reaction_remove")
  async def reactrole_remove(self, data:disnake.RawReactionActionEvent):
    """ Take back roles """
    if data.guild_id:
      guild = await self.bot.fetch_guild(data.guild_id)
      member = await guild.fetch_member(data.user_id)
      emojiid = data.emoji if data.emoji.is_unicode_emoji() else data.emoji.id
      if f"{data.channel_id}_{data.message_id}_{emojiid}_roles" in self.bot.config['reactroles']:
        channel = await self.bot.fetch_channel(data.channel_id)
        roleids = [int(r) for r in self.bot.config['reactroles'][f"{data.channel_id}_{data.message_id}_{emojiid}_roles"].split(' ')]
        roles = []
        for roleid in roleids:
          try:
            roles.append(channel.guild.get_role(roleid))
          except Exception as e:
            print("failed to get role for reactrole: "+str(e))
        await member.send(self.bot.babel(member, 'reactroles', 'role_taken', roles=', '.join([role.name for role in roles])))
        await member.remove_roles(*roles, reason='reactroles')
  
  async def catchup(self):
    #TODO: give and take roles as needed to catch up to reality
    pass

  @commands.command(aliases=['reactionrole', 'rr', 'reactroles', 'reactionroles'])
  @commands.guild_only()
  async def reactrole(self, ctx:commands.Context, *, prompt:str):
    """react role setup interface"""
    self.bot.cogs['Auth'].admins(ctx.message)

    target = await ctx.reply(prompt)
    tmp = None

    emojis = []
    try:
      while len(emojis) < 10:
        tmp = await ctx.reply(self.bot.babel(ctx, 'reactroles', 'setup1', canstop=len(emojis) > 0))
        reaction, _ = await self.bot.wait_for('reaction_add', check=lambda r, u: u==ctx.author and r.message == target, timeout=30)

        if reaction.emoji not in emojis:
          await target.add_reaction(reaction)
          try:
            await target.remove_reaction(reaction, ctx.author)
          except:
            pass
          await tmp.delete()

          tmp = await ctx.reply(self.bot.babel(ctx, 'reactroles', 'setup2', emoji=str(reaction.emoji)))
          msg = await self.bot.wait_for('message', check=lambda m: m.channel == ctx.channel and m.author == ctx.author and len(m.role_mentions) > 0, timeout=30)
          emojiid = reaction.emoji if isinstance(reaction.emoji, str) else str(reaction.emoji.id)
          self.bot.config['reactroles'][f"{ctx.channel.id}_{target.id}_{emojiid}_roles"] = ' '.join([str(r.id) for r in msg.role_mentions])
          await tmp.delete()
          await msg.delete()
          
          emojis.append(reaction)
        else:
          try:
            await target.remove_reaction(reaction, ctx.author)
          except:
            pass
          await tmp.delete()
          tmp = await ctx.reply(self.bot.babel(ctx, 'reactroles', 'setup2_repeat'))
          await asyncio.sleep(5)
          await tmp.delete()

    except asyncio.TimeoutError:
      if len(emojis) == 0:
        try:
          await target.delete()
          if tmp is not None: await tmp.delete()
        except:
          pass
        await ctx.reply(self.bot.babel(ctx, 'reactroles', 'setup_cancel'))
      else:
        try:
          await tmp.delete()
        except:
          pass
        await ctx.reply(self.bot.babel(ctx, 'reactroles', 'setup_success'))
        self.watching.append(target)
    else:
      await ctx.reply(self.bot.babel(ctx, 'reactroles', 'setup_success'))
      self.watching.append(target)
    self.bot.config.save()


def setup(bot:commands.Bot):
  bot.add_cog(ReactRoles(bot))