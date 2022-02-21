from array import array
import asyncio, re, time
from typing import Optional, Union
import disnake
from disnake.ext import commands
from disnake.enums import TextInputStyle

class CHANNEL_TYPE:
	invalid = -2
	none = -1
	untraceable = 0
	traceable = 1
	vetting = 2
	feedback = 3

class PendingConfession:
	def __init__(self, input:Optional[str]=None, *, vetmessage:disnake.Message=None, choicemsg:disnake.Message=None, targetchannel:disnake.TextChannel=None, content:str=None, image:Optional[str]=None):
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
		elif input == '':
			pass
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

			
class PendingConfessionButtons(disnake.ui.View):
    def __init__(self, confessor: disnake.Member):
        super().__init__(timeout=None)
        self.add_item(
            disnake.ui.Button(
                label="✅",
                style=disnake.ButtonStyle.blurple,
                custom_id=f"pending_confession_approve_{confessor.id}"
            )
        )
        self.add_item(
            disnake.ui.Button(
                label="❎",
                style=disnake.ButtonStyle.blurple,
                custom_id=f"pending_confession_deny_{confessor.id}"
            )
        )
			

class ConfessionModal(disnake.ui.Modal):
	def __init__(self):
		components = [
			disnake.ui.TextInput(
				label="Type your confession here:",
				placeholder="Your confession here",
				custom_id="confession",
				style=TextInputStyle.paragraph,
			)
		]
		super().__init__(
			title="Anonymous Confession",
			custom_id="confession_modal",
			components=components
		)

	async def callback(self, interaction):
		embed=disnake.Embed(
			title="Anonymous Confession",
			description=interaction.text_values["confession"],
			color=disnake.Color.blurple()
		)
		await interaction.response.send_message("Your confession was confession posted ✅", ephemeral=True)
		await interaction.channel.send(embed=embed)

        # else:

            # targetchannel self.listavailablechannels(interaction.author)
            # anonid = self.get_anonid(targetchannel.guild.id, interaction.author.id)

            # embed = self.generate_confession(anonid if lead else '', lead, interaction.text_values["confession"])

            # vettingchannel = self.findvettingchannel(targetchannel.guild)

            # if vettingchannel:
            #     vetembed = self.generate_confession(anonid, lead if lead else f"**[Anon-*{anonid}*]**", interaction.text_values["confession"])

            #     vetmessage = await vettingchannel.send(self.bot.babel(None,targetchannel.guild.id,),'confessions','vetmessagecta',channel=targetchannel.mention,embed=vetembed)

            #     # Store pending message details for handling after vetting
            #     pendingconfession = PendingConfession(
            #         vetmessage=vetmessage,
            #         targetchannel=targetchannel,
            #         content=interaction.text_values["confession"],
            #     )
                
            #     self.bot.config['confessions']['pending_vetting_'+str(vetmessage.id)] = str(pendingconfession)
                
            #     # Store offline in case of restarts or power failures
            #     self.bot.config.save()
                
            #     return

            #     await self.send_confession(anonid, interaction.channel, vettingchannel, embed, view=PendingConfessionButtons(confessor=interaction.author))
            
            # else:
            #     try:
            #         await self.send_confession(anonid, interaction.channel, targetchannel, embed)
            #     except:
            #         await interaction.channel.send("Error")
			
class Confessions(commands.Cog):


	@commands.slash_command(
		description="Send a confession"
	)
	async def confess(self, interaction):
		await interaction.response.send_modal(modal=ConfessionModal())



	# """Note that commands in this module have generic names which may clash with other commands
	# or not make any sense outside of a confessions bot."""

	channel_icons = {CHANNEL_TYPE.untraceable: '🙈', CHANNEL_TYPE.traceable: '👁', CHANNEL_TYPE.feedback: '📢'}

	def __init__(self, bot:commands.Bot):
		self.bot = bot
		if not bot.config.getboolean('extensions', 'auth', fallback=False):
			raise Exception("'auth' must be enabled to use 'confessions'")
		# ensure config file has required data
		if not bot.config.has_section('confessions'):
			bot.config.add_section('confessions')
		if 'starttime' not in bot.config['confessions']:
			bot.config['confessions']['starttime'] = '?'
		if 'confession_cooldown' not in bot.config['confessions']:
			bot.config['confessions']['confession_cooldown'] = 1
		if 'anonid_generator' not in bot.config['confessions']:
			bot.config['confessions']['anonid_generator'] = '#import\nanonid = hex(uuid)[-6:]'
			print("WARNING: you should define a more advanced algorithm for hiding user ids. (config[confessions][anonid_generator])")
		self.initiated = set()
		self.ignore = set()
		self.confession_cooldown = dict()

	def get_anonid(self, guildid:int, userid:int):
		offset = self.bot.config.getint('confessions', str(guildid)+'_shuffle', fallback=0)
		loc = {'uuid' : guildid+userid+offset, 'anonid' : None}
		exec(self.bot.config['confessions']['anonid_generator'], None, loc)
		return loc['anonid']

	def generate_list(self, user:disnake.User, matches:array, vetting:bool, enum:bool=False):
		return ',\n'.join([(str(i+1)+':' if enum else '') + f'{self.channel_icons[c[1]]}<#{c[0].id}>'+(' ('+c[0].guild.name+')' if not isinstance(user, disnake.Member) else '') for i,c in enumerate(matches)]) +\
						('\n'+self.bot.babel((user.id,),'confessions','vetting') if vetting else '')

	def scanguild(self, member:disnake.Member):
		matches = []
		vetting = False
		save = False
		for channel in member.guild.channels:
			# Backwards compatibility (v1.x): add server id to confession channel config
			if '?_'+str(channel.id) in self.bot.config['confessions']:
				save = True
				self.bot.config['confessions'][str(member.guild.id)+'_'+str(channel.id)] = self.bot.config['confessions']['?_'+str(channel.id)]
				self.bot.config.remove_option('confessions', '?_'+str(channel.id))
			if str(member.guild.id)+'_'+str(channel.id) in self.bot.config['confessions']:
				chtype = int(self.bot.config['confessions'][str(member.guild.id)+'_'+str(channel.id)])
				if chtype == CHANNEL_TYPE.vetting:
					vetting = True
					continue
				if chtype == CHANNEL_TYPE.feedback:
					matches.append((channel, chtype))
					continue
				if channel.permissions_for(member).read_messages:
					matches.append((channel, chtype))
					continue
		
		if save:
			self.bot.config.save()
		
		return matches, vetting

	def listavailablechannels(self, user:Union[disnake.User, disnake.Member]):
		if isinstance(user, disnake.Member):
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
		if anonid:
			embed = disnake.Embed(colour=disnake.Colour(int(anonid,16)),description=lead+content)
		else:
			embed = disnake.Embed(description=lead+' '+content)
		if image:
			embed.set_image(url=image)
		return embed

	async def send_confession(self, anonid:str, choicechannel:disnake.DMChannel, targetchannel:disnake.TextChannel, embed:disnake.Embed):
		""" Sends confessions through, plus the copious amounts of error handling """
		# check if user was banned
		if [i for i in self.bot.config.get('confessions', str(targetchannel.guild.id)+'_banned', fallback='').split(',') if anonid in i[-6:]]:
			await choicechannel.send(self.bot.babel((choicechannel.recipient.id,),'confessions','nosendbanned'))
			return

		try:
			await targetchannel.send(embed=embed)
		except disnake.errors.Forbidden:
			try:
				await targetchannel.send(self.bot.babel((None, targetchannel.guild.id,), 'confessions', 'missingperms', perm='Embed Messages'))
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
	async def vetting_reaction(self, data:disnake.RawReactionActionEvent):
		if data.event_type == 'REACTION_ADD' and data.member and data.member != self.bot.user and\
				'pending_vetting_'+str(data.message_id) in self.bot.config['confessions']:
			if (data.member.guild_permissions.ban_members or \
					str(data.member.id) in self.bot.config.get('confessions', str(data.member.guild.id)+'_promoted', fallback='').split(',')) and \
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
						await channel.send(self.bot.babel((data.member.id, data.member.guild.id,), 'confessions', 'vettingrequiredmissing'))
				else:
					await self.on_confession_vetted(vetmessage, pendingconfession, data.emoji, data.member)
			else:
				channel = await self.bot.fetch_channel(data.channel_id)
				message = await channel.fetch_message(data.message_id)
				await message.remove_reaction(data.emoji, data.member)
        
	async def on_confession_vetted(self, vetmessage:disnake.Message, pendingconfession:PendingConfession, emoji:disnake.Emoji, voter:disnake.Member):
		anonid = self.get_anonid(pendingconfession.targetchannel.guild.id, pendingconfession.choicemsg.channel.recipient.id)
		lead = ""
		if self.bot.config.getint('confessions', str(pendingconfession.targetchannel.guild.id)+'_'+str(pendingconfession.targetchannel_id)) != CHANNEL_TYPE.untraceable:
			lead = f"**[Anon-*{anonid}*]**"

		embed = self.generate_confession(anonid if lead else '', lead, pendingconfession.content, pendingconfession.image)
		accepted = True if str(emoji) == '✅' else False
		
		self.bot.config.remove_option('confessions', 'pending_vetting_'+str(vetmessage.id))
		self.bot.config.save()
		
		await vetmessage.edit(content=self.bot.babel((voter.id, voter.guild.id,), 'confessions', 'vetaccepted' if accepted else 'vetdenied', channel=pendingconfession.targetchannel.mention), embed=embed)
		await pendingconfession.choicemsg.remove_reaction('💭', self.bot.user)
		await pendingconfession.choicemsg.add_reaction('✅' if accepted else '❎')
		if accepted:
			await self.send_confession(anonid, pendingconfession.choicechannel, pendingconfession.targetchannel, embed)

	@commands.Cog.listener('on_ready')
	async def reaction_catchup(self):
		changed = 0
		for option in (o for o in self.bot.config['confessions'] if o.startswith('pending_vetting_')):
			pendingconfession = PendingConfession(self.bot.config['confessions'][option])
			try:
				targetchannel = await self.bot.fetch_channel(pendingconfession.targetchannel_id)
				vetchannel = self.findvettingchannel(targetchannel.guild)
				vetmessage = await vetchannel.fetch_message(int(option[16:]))
			except Exception as e:
				print("Failed to fetch required channels or guilds related to a confession (catchup);\n"+str(e))
				pendingconfession.failures += 1
				if pendingconfession.failures > 5:
					self.bot.config.remove_option('confessions', option)
					changed += 1
				else:
					self.bot.config['confessions'][option] = str(pendingconfession)
					changed += 1
				
				# optimization to reduce the number of writes
				if changed > 100:
					self.bot.config.save()
					changed = 0
			if changed:
				self.bot.config.save()
				changed = 0
			else:
				for reaction in vetmessage.reactions:
					async for voter in reaction.users():
						if voter != self.bot.user:
							if isinstance(voter, disnake.Member):
								data = disnake.RawReactionActionEvent({'message_id':vetmessage.id, 'channel_id':vetchannel.id, 'user_id':voter.id}, reaction.emoji, 'REACTION_ADD')
								await self.vetting_reaction(data)

	@commands.Cog.listener('on_message')
	async def confession_request(self, msg:disnake.Message):
		ctx = await self.bot.get_context(msg)
		if ctx.prefix is not None:
			return
		if isinstance(msg.channel, disnake.DMChannel) and\
				msg.author != self.bot.user:
			if msg.channel in self.ignore:
				self.ignore.remove(msg.channel)
				return
			if msg.author in self.confession_cooldown and self.confession_cooldown[msg.author] > time.time():
				return
			else:
				self.confession_cooldown[msg.author] = time.time() + self.bot.config.getint('confessions', 'confession_cooldown', fallback=1)
			
			if 'Log' in self.bot.cogs:
				await self.bot.cogs['Log'].log_misc(msg)

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
					if msg.channel in self.ignore:
						self.ignore.remove(msg.channel)
					return
				choice = int(choicemsg.content) - 1
			else:
				choicemsg = msg

			targetchannel = matches[choice][0]
			anonid = self.get_anonid(targetchannel.guild.id, msg.author.id)
			lead = ""
			if self.bot.config.getint('confessions', str(targetchannel.guild.id)+'_'+str(targetchannel.id)) != CHANNEL_TYPE.untraceable:
				lead = f"**[Anon-*{anonid}*]**"

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
			
			embed = self.generate_confession(anonid if lead else '', lead, msg.content, image)

			vettingchannel = self.findvettingchannel(targetchannel.guild)
			status = '💭' if vettingchannel else '✅'
			
			await choicemsg.add_reaction(status)

			if vettingchannel:
				vetembed = self.generate_confession(anonid, lead if lead else f"**[Anon-*{anonid}*]**", msg.content, image)

				vetmessage = await vettingchannel.send(self.bot.babel((None,targetchannel.guild.id,),'confessions','vetmessagecta',channel=targetchannel.mention),embed=vetembed)
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
			await ctx.reply(self.bot.babel(ctx,'confessions','inaccessiblelocal' if isinstance(ctx.author, disnake.Member) else 'inaccessible'))
		else:
			await ctx.reply((self.bot.babel(ctx,'confessions','listtitlelocal') if isinstance(ctx.author, disnake.Member) else self.bot.babel(ctx,'confessions','listtitle')) + '\n'+self.generate_list(ctx.author, matches, vetting))

	@commands.guild_only()
	@commands.command()
	async def shuffle(self, ctx, one:str = None):
		if str(ctx.author.id) not in self.bot.config.get('confessions', str(ctx.guild.id)+'_promoted', fallback='').split(','):
			self.bot.cogs['Auth'].mods(ctx)
		if one:
			await ctx.reply(self.bot.babel(ctx, 'confessions', 'shuffleobsoleteone'))
		else:
			if str(ctx.guild.id)+'_banned' in self.bot.config['confessions']:
				msg = await ctx.reply(self.bot.babel(ctx, 'confessions', 'shufflebanresetwarning'))
				def check(m):
					return m.channel == ctx.channel and m.author == ctx.author and m.content.lower() == 'yes'
				try:
					await self.bot.wait_for('message', check=check, timeout=30)
				except asyncio.TimeoutError:
					await ctx.send(self.bot.babel(ctx, 'confessions', 'timeouterror'))
				else:
					self.bot.config.remove_option('confessions', str(ctx.guild.id)+'_banned')
			
			shuffle = self.bot.config.getint('confessions', str(ctx.guild.id)+'_shuffle', fallback=0)
			self.bot.config.set('confessions', str(ctx.guild.id)+'_shuffle', str(shuffle + 1))
			self.bot.config.save()

			await ctx.reply(self.bot.babel(ctx, 'confessions', 'shufflesuccess'))

	@commands.guild_only()
	@commands.command()
	async def imagesupport(self, ctx:commands.Context, cmd:str):
		self.bot.cogs['Auth'].admins(ctx)
		if cmd=='enable':
			if self.bot.config.getboolean('confessions', str(ctx.guild.id)+'_imagesupport', fallback=True):
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'imagesupportalreadyenabled'))
			else:
				self.bot.config['confessions'][str(ctx.guild.id)+'_imagesupport'] = 'True'
				self.bot.config.save()
				await ctx.reply(self.bot.babel('confessions', 'imagesupportenabled'))
		elif cmd=='disable':
			if not self.bot.config.getboolean('confessions', str(ctx.guild.id)+'_imagesupport', fallback=True):
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'imagesupportalreadydisabled'))
			else:
				self.bot.config['confessions'][str(ctx.guild.id)+'_imagesupport'] = 'False'
				self.bot.config.save()
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'imagesupportdisabled'))

	@commands.guild_only()
	@commands.command()
	async def ban(self, ctx:commands.Context, anonid:str=None):
		if str(ctx.author.id) not in self.bot.config.get('confessions', str(ctx.guild.id)+'_promoted', fallback='').split(','):
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

		modlist = self.bot.config.get('confessions', str(ctx.guild.id)+'_promoted', fallback='')
		if target is None:
			if modlist:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmodlist') + '\n```\n' + '\n'.join(modlist.split(',')) + '```')
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
				if str(botmodee.id) in modlist.split(','):
					self.bot.config['confessions'][str(ctx.guild.id)+'_promoted'] = modlist.replace(str(botmodee.id)+',','')
					self.bot.config.save()
					await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmoddemotesuccess', user=botmodee.name))
				else:
					await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmoddemoteerr'))
			else:
				if str(botmodee.id) not in modlist.split(','):
					self.bot.config['confessions'][str(ctx.guild.id)+'_promoted'] = modlist + str(botmodee.id)+','
					self.bot.config.save()
					await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmodsuccess', user=botmodee.name))
				else:
					await ctx.reply(self.bot.babel(ctx, 'confessions', 'rebotmoderr'))
		else:
			raise commands.BadArgument()

	@commands.Cog.listener('on_guild_leave')
	async def guild_cleanup(self, guild:disnake.Guild):
		for option in self.bot.config['confessions']:
			if option.startswith(str(guild.id)+'_'):
				self.bot.config.remove_option('confessions', option)
		self.bot.config.save()

	@commands.Cog.listener('on_guild_channel_delete')
	async def channel_cleanup(self, channel:disnake.TextChannel):
		for option in self.bot.config['confessions']:
			if option == str(channel.guild.id)+'_'+str(channel.id):
				self.bot.config.remove_option('confessions', option)
				break
		self.bot.config.save()


    # @commands.slash_command(
	# 	description="Send a confession to a confession channel"
	# )
    # @commands.guild_only()
    # async def confess_to(self, interaction, channel: disnake.TextChannel):
    #     await interaction.response.send_modal(modal=ConfessionModal())

def setup(bot):
	bot.add_cog(Confessions(bot))
