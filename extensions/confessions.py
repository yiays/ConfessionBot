from array import array
import asyncio, re
from typing import Optional, Union
import discord
from discord.ext import commands

class CHANNEL_TYPE:
	invalid = -2
	none = -1
	untraceable = 0
	traceable = 1
	vetting = 2
	feedback = 3

class PendingConfession:
	def __init__(self, input:Optional[str]=None, *, vetmessage:discord.Message=None, choicemsg:discord.Message=None, targetchannel:discord.TextChannel=None, content:str=None, image:Optional[str]=None):
		if input:
			self.offline = True
			self.vetmessage = vetmessage
			lines = input.splitlines()
			self.choicechannel_id = int(lines[0])
			self.choicemsg_id = int(lines[1])
			self.targetchannel_id = int(lines[2])
			self.image = lines[3] if len(lines[3]) else None
			self.failures = int(lines[4])
			self.content = '\n'.join(lines[5:])
		else:
			self.offline = False
			self.choicechannel = choicemsg.channel
			self.choicemsg = choicemsg
			self.targetchannel = targetchannel
			self.content = content
			self.image = image if image else None
			self.failures = 0
			self.vetmessage = vetmessage
	
	def __str__(self) -> str:
		if self.offline:
			return \
				str(self.choicechannel_id) + '\n' + \
				str(self.choicemsg_id) + '\n' + \
				str(self.targetchannel_id) + '\n' + \
				(str(self.image) if self.image else '') + '\n' + \
				str(self.failures) + '\n' + \
				str(self.content)
		else:
			return \
				str(self.choicechannel.id) + '\n' + \
				str(self.choicemsg.id) + '\n' + \
				str(self.targetchannel.id) + '\n' + \
				(str(self.image) if self.image else '') + '\n' + \
				str(self.failures) + '\n' + \
				str(self.content)
	
	async def fetch(self, bot:commands.Bot):
		if self.offline:
			self.choicechannel = await bot.fetch_channel(self.choicechannel_id)
			self.choicemsg = await self.choicechannel.fetch_message(self.choicemsg_id)
			self.targetchannel = await bot.fetch_channel(self.targetchannel_id)
			self.offline = False

class Confessions(commands.cog.Cog):
	"""Note that commands in this module have generic names which may clash with other commands
	or not make any sense outside of a confessions bot."""

	channel_types = CHANNEL_TYPE

	def __init__(self, bot:commands.Bot):
		self.bot = bot
		if not bot.config.getboolean('extensions', 'auth', fallback=False):
			raise Exception("'auth' must be enabled to use 'admin'")
		# ensure config file has required data
		if not bot.config.has_section('confessions'):
			bot.config.add_section('confessions')
		if 'starttime' not in bot.config['confessions']:
			bot.config['confessions']['starttime'] = '?'
		if 'anonid_generator' not in bot.config['confessions']:
			bot.config['confessions']['anonid_generator'] = '#import\nanonid = hex(uuid)[-6:]'
			print("WARNING: you should define a more advanced algorithm for hiding user ids. (config[confessions][anonid_generator])")
		self.initiated = set()
		self.ignore = set()
	
	def get_anonid(self, guildid:int, userid:int, offset:int):
		loc = {'uuid' : guildid+userid+offset, 'anonid' : None}
		exec(self.bot.config['confessions']['anonid_generator'], None, loc)
		return loc['anonid']

	def get_anon_details(self, channel:discord.TextChannel, authorid:int):
		lead="**undefined**: "
		anonid="facade"
		if self.bot.config.getint('confessions', str(channel.guild.id)+'_'+str(channel.id)) == CHANNEL_TYPE.untraceable:
			lead=""
		else:
			offset = self.bot.config.getint('shuffle', str(channel.guild.id), fallback=0) + self.bot.config.getint('shuffle', str(authorid), fallback=0)
			anonid = self.get_anonid(channel.guild.id,authorid,offset)
			lead=f"**[Anon-*{anonid}*]:** "
		return lead, anonid

	def generate_list(self, user:discord.User, matches:array, vetting:bool, enum:bool=False):
		channelicon = {CHANNEL_TYPE.untraceable: '🙈', CHANNEL_TYPE.traceable: '👁', CHANNEL_TYPE.feedback: '📢'}
		return ',\n'.join([(str(i+1)+':' if enum else '') + f'{channelicon[c[1]]}<#{c[0].id}>'+(' ('+c[0].guild.name+')' if not isinstance(user, discord.Member) else '') for i,c in enumerate(matches)]) +\
					 ('\n'+self.bot.babel((user.id,),'confessions','vetting') if vetting else '')
	
	def scanguild(self, member:discord.Member):
		matches = []
		vetting = False
		for channel in member.guild.channels:
			if str(member.guild.id)+'_'+str(channel.id) in self.bot.config['confessions']:
				chtype = int(self.bot.config['confessions'][str(member.guild.id)+'_'+str(channel.id)])
				if chtype == CHANNEL_TYPE.vetting:
					vetting = True
					continue
				if chtype == CHANNEL_TYPE.feedback:
					matches.append((channel, chtype))
					continue
				if member.permissions_in(channel).read_messages:
					matches.append((channel, chtype))
					continue
		
		return matches, vetting

	def listavailablechannels(self, user:Union[discord.User, discord.Member]):
		if isinstance(user, discord.Member):
			matches,vetting = self.scanguild(user)
		else:
			matches = []
			vetting = False
			for guild in self.bot.guilds:
				if member := guild.get_member(user.id):
					newmatches, newvetting = self.scanguild(member)
					matches += newmatches
					vetting = vetting or newvetting
		
		return matches, vetting
	
	def generate_confession(self, anonid:str, lead:str, content:str, image:Optional[str]):
		embed = discord.Embed(colour=discord.Colour(int(anonid,16)),description=lead+content)
		if image:
			embed.set_image(url=image)
		return embed

	async def send_confession(self, anonid:str, choicechannel:discord.DMChannel, targetchannel:discord.TextChannel, embed:discord.Embed):
		""" Sends confessions through, plus the copious amounts of error handling """
		# check if user was banned
		if [i for i in self.bot.config.get('confessions', str(targetchannel.guild.id)+'_banned', fallback='').split(',') if anonid in i[-6:]]:
			await choicechannel.send(self.bot.babel((choicechannel.recipient.id,),'confessions','nosendbanned'))
			return

		try:
			await targetchannel.send(embed=embed)
		except discord.errors.Forbidden:
			try:
				await targetchannel.send(self.bot.babel((None, targetchannel.guild.id), 'confessions', 'missingperms', perm='Embed Messages'))
				await choicechannel.send(self.bot.babel((choicechannel.recipient.id,), 'confessions', 'embederr'))
			except:
				await choicechannel.send(self.bot.babel((choicechannel.recipient.id,), 'confessions', 'missingchannelerr'))
		except Exception as e:
			await choicechannel.send(self.bot.babel((choicechannel.recipient.id,), 'confessions', 'missingchannelerr'))
			raise e

	def findvettingchannel(self, guild):
		for channel in guild.channels:
			if self.bot.config.getint('confessions', str(guild.id)+'_'+str(channel.id), fallback=CHANNEL_TYPE.none) == CHANNEL_TYPE.vetting:
				return channel
		return None

	@commands.Cog.listener('on_raw_reaction_add')
	async def vetting_reaction(self, data:discord.RawReactionActionEvent):
		if data.event_type == 'REACTION_ADD' and data.member and data.member != self.bot.user and\
			 'pending_vetting_'+str(data.message_id) in self.bot.config['confessions']:
			if (data.member.guild_permissions.ban_members or \
					str(data.member.id) in self.bot.config.get('confessions', str(data.member.guild.id)+'_promoted', fallback='').split(' ')) and \
					str(data.emoji) in ['✅','❎']:
				pendingconfession = PendingConfession(self.bot.config['confessions']['pending_vetting_'+str(data.message_id)])
				try:
					#TODO: this could be optimized with some refactoring
					await pendingconfession.fetch(self.bot)
					vetchannel = await self.bot.fetch_channel(data.channel_id)
					vetmessage = await vetchannel.fetch_message(data.message_id)
				except Exception as e:
					print("Failed to fetch required channels or guilds related to a confession (event);\n"+str(e))
					pendingconfession.failures += 1
					channel = await self.bot.fetch_channel(data.channel_id)
					if pendingconfession.failures > 5:
						self.bot.config.remove_option('confessions', 'pending_vetting_'+str(data.message_id))
						msg = await channel.fetch_message(data.message_id)
						await msg.delete()
					else:
						self.bot.config['confessions']['pending_vetting_'+str(data.message_id)] = str(pendingconfession)
						await channel.send(self.bot.babel((data.member.id, data.member.guild.id)), 'confessions', 'vettingrequiredmissing')
				else:
					await self.on_confession_vetted(vetmessage, pendingconfession, data.emoji, data.member)
			else:
				channel = await self.bot.fetch_channel(data.channel_id)
				message = await channel.fetch_message(data.message_id)
				await message.remove_reaction(data.emoji, data.member)
		
	async def on_confession_vetted(self, vetmessage:discord.Message, pendingconfession:PendingConfession, emoji:discord.Emoji, voter:discord.Member):
		lead, anonid = self.get_anon_details(pendingconfession.targetchannel, pendingconfession.choicechannel.recipient.id)
		embed = self.generate_confession(anonid, lead, pendingconfession.content, pendingconfession.image)
		accepted = True if str(emoji) == '✅' else False
		
		self.bot.config.remove_option('confessions', 'pending_vetting_'+str(vetmessage.id))
		self.bot.config.save()
		
		await vetmessage.edit(content=self.bot.babel((voter.id, voter.guild.id), 'confessions', 'vetaccepted' if accepted else 'vetdenied'), embed=embed)
		await pendingconfession.choicemsg.remove_reaction('💭', self.bot.user)
		await pendingconfession.choicemsg.add_reaction('✅' if accepted else '❎')
		await self.send_confession(anonid, pendingconfession.choicechannel, pendingconfession.targetchannel, embed)

	@commands.Cog.listener('on_ready')
	async def reaction_catchup(self):
		for option in (o for o in self.bot.config['confessions'] if o.startswith('pending_vetting_')):
			pendingconfession = PendingConfession(self.bot.config['confessions'][option])
			try:
				targetchannel = await self.bot.fetch_channel(pendingconfession.targetchannel_id)
				vetchannel = self.findvettingchannel(targetchannel.guild)
				vetmessage = await vetchannel.fetch_message(int(option[16:]))
			except Exception as e:
				print("Failed to fetch required channels or guilds related to a confession (catchup);\n"+str(e))
				pendingconfession.failures += 1
				self.bot.config['confessions'][option] = str(pendingconfession)
				self.bot.config.save()
			else:
				for reaction in vetmessage.reactions:
					async for voter in reaction.users():
						if voter != self.bot.user:
							if isinstance(voter, discord.Member):
								data = discord.RawReactionActionEvent({'message_id':vetmessage.id, 'channel_id':vetchannel.id, 'user_id':voter.id}, reaction.emoji, 'REACTION_ADD')
								await self.vetting_reaction(data)

	@commands.Cog.listener('on_message')
	async def confession_request(self, msg:discord.Message):
		ctx = await self.bot.get_context(msg)
		if ctx.prefix is not None:
			return
		if isinstance(msg.channel, discord.abc.PrivateChannel) and\
			 msg.author != self.bot.user:
			if msg.channel in self.ignore:
				self.ignore.remove(msg.channel)
				return
			
			if 'log' in self.bot.cogs:
				self.bot.cogs['log'].log_misc(msg)

			matches,vetting = self.listavailablechannels(msg.author)

			if not self.bot.is_ready():
				await msg.channel.send(self.bot.babel((msg.author.id,), 'confessions', 'cachebuilding', s=self.bot.config['confessions']['starttime']))

			if not matches:
				await msg.channel.send(self.bot.babel((msg.author.id,), 'confessions', 'inaccessible'))
				return
			
			choice = 0
			if (not self.bot.is_ready()) or len(matches) > 1:
				await msg.channel.send(self.bot.babel((msg.author.id,), 'confessions', 'multiplesendtargets'+('short' if msg.author in self.initiated else '')) + '\n' + \
															 self.generate_list(msg.author, matches, vetting, True))
				self.initiated.add(msg.author)
				self.ignore.add(msg.channel)
				try:
					choicemsg = await self.bot.wait_for('message', check=lambda m:m.channel == msg.channel and m.author == msg.author and m.content.isdigit(), timeout=30)
				except asyncio.TimeoutError:
					await msg.channel.send(self.bot.babel((msg.author.id,), 'confessions', 'timeouterror'))
					self.ignore.remove(msg.channel)
					return
				choice = int(choicemsg.content) - 1
			else:
				choicemsg = msg

			targetchannel = matches[choice][0]
			lead, anonid = self.get_anon_details(targetchannel, msg.author.id)

			# check if user was banned
			if [i for i in self.bot.config.get('confessions', str(targetchannel.guild.id)+'_banned', fallback='').split(',') if anonid == i]:
				await msg.channel.send(self.bot.babel((msg.author.id,),'confessions','nosendbanned'))
				return

			# check if the user wants to send an image and if it's allowed.
			image = None
			#TODO: also find links to images in message content
			if len(msg.attachments) and msg.attachments[0].width:
				if self.bot.config.getboolean('confessions', str(targetchannel.guild.id)+'_imagesupport', fallback=True):
					image = msg.attachments[0].url
				else:
					await msg.channel.send(self.bot.babel((msg.author.id,), 'confessions', 'nosendimages'))
					return
			
			# check if the message appears to be spam
			for spamflag in self.bot.config.get('confessions', 'spam_flags', fallback=None).splitlines():
				if re.match(spamflag, msg.content):
					await msg.channel.send(self.bot.babel((msg.author.id,), 'confessions', 'nospam'))
					return
			
			embed = self.generate_confession(anonid, lead, msg.content, image)

			vettingchannel = self.findvettingchannel(targetchannel.guild)
			status = '💭' if vettingchannel else '✅'
			
			await choicemsg.add_reaction(status)

			if vettingchannel:
				vlead, vanonid = self.get_anon_details(vettingchannel, msg.author.id)
				vembed = self.generate_confession(vanonid, vlead, msg.content, image)

				vetmessage = await vettingchannel.send(self.bot.babel((None,targetchannel.guild.id),'confessions','vetmessagecta',channel=targetchannel.mention),embed=vembed)
				await vetmessage.add_reaction('✅')
				await vetmessage.add_reaction('❎')

				# Store pending message details for handling after vetting
				pendingconfession = PendingConfession(vetmessage=vetmessage,
																							choicemsg=choicemsg,
																							targetchannel=targetchannel,
																							content=msg.content,
																							image=image)
				
				self.bot.config['confessions']['pending_vetting_'+str(vetmessage.id)] = str(pendingconfession)
				
				# Store offline in case of restarts or power failures
				self.bot.config.save()
				
				return

			await self.send_confession(anonid, msg.channel, targetchannel, embed)

	@commands.guild_only()
	@commands.command()
	async def set(self, ctx:commands.Context, mode:str):
		self.bot.cogs['Auth'].admins(ctx)
		type = CHANNEL_TYPE.__dict__.get(mode, CHANNEL_TYPE.invalid)
		if type==CHANNEL_TYPE.invalid:
			raise commands.BadArgument()
		elif type==CHANNEL_TYPE.none:
			wastype = self.bot.config.getint('confessions', str(ctx.guild.id)+'_'+str(ctx.channel.id), fallback=CHANNEL_TYPE.none)
			if wastype == CHANNEL_TYPE.none:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'unsetfailure'))
				return
			self.bot.config.remove_option('confessions', str(ctx.guild.id)+'_'+str(ctx.channel.id))
		else:
			self.bot.config['confessions'][str(ctx.guild.id)+'_'+str(ctx.channel.id)] = str(type)
		self.bot.config.save()

		await ctx.reply(self.bot.babel(ctx, 'confessions', ('setsuccess'+str(type) if type>=0 else 'unsetsuccess')) + \
										self.bot.babel(ctx, 'confessions', 'setundo' if type>=0 else 'unsetundo'))

	@commands.command()
	async def list(self, ctx):
		matches,vetting = self.listavailablechannels(ctx.author)
		# warn users when the channel list isn't complete
		if not self.bot.is_ready():
			#TODO: average ready time and report the real figure
			await ctx.reply(self.bot.babel(ctx,'confessions','cachebuilding', s=self.bot.config['confessions']['starttime']))
		elif len(matches) == 0:
			await ctx.reply(self.bot.babel(ctx,'confessions','inaccessiblelocal' if isinstance(ctx.author, discord.Member) else 'inaccessible'))
		else:
			await ctx.reply((self.bot.babel(ctx,'confessions','listtitlelocal') if isinstance(ctx.author, discord.Member) else self.bot.babel(ctx,'confessions','listtitle')) + \
											'\n'+self.generate_list(ctx.author, matches, vetting))
	
	@commands.guild_only()
	@commands.command()
	async def shuffle(self, ctx, one:str = None):
		self.bot.cogs['Auth'].admins(ctx)
		if one:
			await ctx.reply(self.bot.babel(ctx, 'confessions', 'shuffleobsoleteone'))
		else:
			if str(ctx.guild.id)+'_banned' in self.bot.config['confessions']:
				msg = await ctx.reply(self.bot.babel(ctx, 'confessions', 'shufflebanresetwarning'))
				def check(m):
					return m.channel == ctx.channel and m.author == ctx.author and m.content.lower() == 'yes'
				try:
					await msg.wait_for('message', check=check, timeout=30)
				except asyncio.TimeoutError:
					await ctx.send(self.bot.babel(ctx, 'confessions', 'timeouterror'))
				else:
					self.bot.config.remove_option('confessions', str(ctx.guild.id)+'_banned')
			
			shuffle = self.bot.config.getint('confessions',str(ctx.guild.id)+'_shuffle', fallback=0)
			self.bot.config.set('shuffle', str(ctx.guild.id), str(shuffle + 1))
			self.bot.config.save()

			ctx.reply(self.bot.babel(ctx, 'confessions', 'shufflesuccess'))
	
	@commands.guild_only()
	@commands.command()
	async def imagesupport(self, ctx:commands.Context, cmd:str):
		self.bot.cogs['Auth'].admins(ctx)
		if cmd=='enable':
			if self.bot.config.getboolean('confessions', str(ctx.guild.id)+'_imagesupport', fallback=True):
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'imagesupportalreadyenabled'))
			else:
				self.bot.config['confessions'][str(ctx.guild.id)+'_imagesupport'] = True
				self.bot.config.save()
				await ctx.reply('confessions', 'imagesupportenabled')
		elif cmd=='disable':
			if not self.bot.config.getboolean('confessions', str(ctx.guild.id)+'_imagesupport', fallback=True):
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'imagesupportalreadydisabled'))
			else:
				self.bot.config['confessions'][str(ctx.guild.id)+'_imagesupport'] = False
				self.bot.config.save()
				await ctx.reply(self.bot.babel('confessions', 'imagesupportdisabled'))

	@commands.guild_only()
	@commands.command()
	async def ban(self, ctx:commands.Context, anonid:str=None):
		if str(ctx.author.id) not in self.bot.config.get('confessions', str(ctx.guild.id)+'_promoted', fallback='').split(' '):
			self.bot.cogs['Auth'].mods(ctx)

		banlist = self.bot.config.get('confessions', str(ctx.guild.id)+'_banned', fallback='')
		if anonid is None:
			if banlist:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'banlist') + '\n```' + '\n'.join(banlist.split(',')) + '```')
			else:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'emptybanlist'))
			return
		
		unban = anonid.startswith('-')
		if unban: anonid = anonid[1:]
		
		anonid = anonid.lower()
		if len(anonid)>6:
			anonid = anonid[-6:]
		try: int(anonid, 16)
		except ValueError:
			await ctx.reply(self.bot.babel(ctx, 'confessions', 'invalidanonid'))
			return
		if anonid in banlist and not unban:
			await ctx.reply(self.bot.babel(ctx, 'confessions', 'doublebananonid'))
			return
		
		if unban:
			fullid = [i for i in banlist.split(',') if anonid in i][0]
			self.bot.config['confessions'][str(ctx.guild.id)+'_banned'] = banlist.replace(fullid+',','')
		else:
			self.bot.config['confessions'][str(ctx.guild.id)+'_banned'] = banlist + anonid + ','
		self.bot.config.save()

		await ctx.reply(self.bot.babel(ctx, 'confessions', ('un' if unban else '')+'bansuccess', user=anonid))
	
	@commands.guild_only()
	@commands.command()
	async def botmod(self, ctx:commands.Context, target:str=None):
		self.bot.cogs['Auth'].admins(ctx)

		modlist = self.bot.config.get(ctx, 'confessions', str(ctx.guild.id)+'_promoted', fallback='')
		if target is None:
			if modlist:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmodlist') + '\n```' + '\n'.join(modlist.split(' ')) + '```')
			else:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmodemptylist'))
		elif ctx.message.mentions:
			revoke = target.startswith('-')
			botmodee = [m for m in ctx.message.mentions if m != self.bot.user][0]
			if botmodee.bot:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmodboterr'))
				return
			if botmodee.guild_permissions.ban_members:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmodmoderr'))
				return

			if revoke:
				if str(botmodee.id) in modlist.split(' '):
					self.bot.config['confessions'][str(ctx.guild.id)+'_promoted'] = modlist.replace(str(botmodee.id)+' ')
					self.bot.config.save()
					await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmoddemotesuccess', user=botmodee.name))
				else:
					await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmoddemoteerr'))
			else:
				if str(botmodee.id) not in modlist.split(' '):
					self.bot.config['confessions'][str(ctx.guild.id)+'_promoted'] += str(botmodee.id)+' '
					self.bot.config.save()
					await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmodsuccess', user=botmodee.name))
				else:
					await ctx.reply(self.bot.babel(ctx, 'confessions', 'rebotmoderr'))
		else:
			raise commands.BadArgument()

	@commands.Cog.listener('on_guild_leave')
	async def guild_cleanup(self, guild:discord.Guild):
		for option in self.bot.config['confessions']:
			if option.startswith(str(guild.id)+'_'):
				self.bot.config.remove_option('confessions', option)
		self.bot.config.save()

	@commands.Cog.listener('on_guild_channel_delete')
	async def channel_cleanup(self, channel:discord.TextChannel):
		for option in self.bot.config['confessions']:
			if option == str(channel.guild.id)+'_'+str(channel.id):
				self.bot.config.remove_option('confessions', option)
				break
		self.bot.config.save()

def setup(bot):
	bot.add_cog(Confessions(bot))