from configparser import ConfigParser
from typing import Union
import nextcord
from nextcord.ext import commands
import os, re

class Babel():
  """babel is a translation system for discord bots
  babel gets strings from language files in the babel folder. to create a new language, follow the format."""
  path = 'babel/'
  langs = {}

  def __init__(self, config:ConfigParser):
    self.config = config
    self.conditional = re.compile(r'{([a-z]*?)\?(.*?)\|(.*?)}')
    self.configreference = re.compile(r'{c\:([a-z_]*?)\/([a-z_]*?)}')
    self.prefixreference = re.compile(r'{p\:(local|global)}')
    self.load()
  
  def load(self):
    self.defaultlang = self.config.get('language', 'default', fallback='en')
    # defaultlang is the requested language to default new users to

    if os.path.isfile(self.path):
      os.remove(self.path)
    if not os.path.exists(self.path) or not os.path.exists(self.path+self.defaultlang+'.ini'):
      raise Exception(f"The path {self.path} must exist and contain a complete {self.defaultlang}.ini.")
    
    for langfile in os.scandir(self.path):
      langfile = langfile.name
      if langfile[-4:] == '.ini':
        langname = langfile[:-4]
        self.langs[langname] = ConfigParser(comment_prefixes='@', allow_no_value=True) # create a configparser that should preserve comments
        self.langs[langname].read(self.path+langfile)
        if 'meta' not in self.langs[langname]:
          self.langs[langname].add_section('meta')
        self.langs[langname].set('meta', 'language', langname)
        with open(self.path+langfile, 'w', encoding='utf-8') as f:
          self.langs[langname].write(f)
    
    # baselang is the root language file that should be considered the most complete.
    self.baselang = self.defaultlang
    while self.langs[self.baselang].get('meta', 'inherit', fallback=''):
      newbaselang = self.langs[self.baselang].get('meta', 'inherit')
      if newbaselang in self.langs:
        self.baselang = newbaselang
      else:
        print("WARNING: unable to resolve language dependancy chain.")
  
  def reload(self):
    self.langs = {}
    self.load()

  def resolve_lang(self, ctx:Union[commands.Context, tuple], debug=False):
    langs = []
    dbg_origins = []
    if isinstance(ctx, commands.Context):
      authorid = ctx.author.id
      guildid = ctx.guild.id if isinstance(ctx.channel, nextcord.abc.GuildChannel) else None
    else:
      authorid = ctx[0]
      guildid = ctx[1] if len(ctx)>1 else None
    
    if str(authorid) in self.config['language']:
      nl = self.config.get('language', str(authorid))
      if nl not in self.langs and '_' in nl:
        # guess that the non-superset version of the language is what it would've inherited from
        nl = nl.split('_')[1]
      if nl in self.langs:
        langs.append(nl)
        if debug: dbg_origins.append('author')
        nl = self.langs[langs[-1]].get('meta', 'inherit', fallback=None)
        while nl and nl not in langs and nl in self.langs:
          langs.append(nl)
          if debug: dbg_origins.append('inherit author')
          nl = self.langs[langs[-1]].get('meta', 'inherit', fallback=None)
    if guildid and str(guildid) in self.config['language']:
      nl = self.config.get('language', str(guildid))
      if nl not in self.langs and '_' in nl:
        nl = nl.split('_')[1]
      if nl not in langs and nl in self.langs:
        langs.append(nl)
        if debug: dbg_origins.append('guild')
        nl = self.langs[langs[-1]].get('meta', 'inherit', fallback=None)
        while nl and nl not in langs and nl in self.langs:
          langs.append(nl)
          if debug: dbg_origins.append('inherit guild')
          nl = self.langs[langs[-1]].get('meta', 'inherit', fallback=None)
    
    if self.defaultlang not in langs:
      langs.append(self.defaultlang)
      if debug: dbg_origins.append('default')
    if self.baselang not in langs:
      langs.append(self.baselang)
      if debug: dbg_origins.append('default')

    if not debug:
      return langs
    else:
      return langs, dbg_origins

  def __call__(self, ctx:Union[commands.Context, tuple], scope:str, key:str, **values):
    reqlangs = self.resolve_lang(ctx)

    match = None
    for reqlang in reqlangs:
      if reqlang in self.langs:
        if scope in self.langs[reqlang]:
          if key in self.langs[reqlang][scope]:
            if len(self.langs[reqlang][scope][key]) > 0:
              match = self.langs[reqlang][scope][key]
              break
    
    if match is None:
      return "{MISSING STRING}"
    
    # Fill in values in the string
    for k,v in values.items():
      match = match.replace('{'+k+'}', str(v))
    
    # Fill in prefixes
    prefixqueries = self.prefixreference.findall(match)
    for prefixquery in prefixqueries:
      if prefixquery == 'local' and isinstance(ctx.channel, nextcord.TextChannel):
        match = match.replace('{p:'+prefixquery+'}', self.config.get('prefix', str(ctx.guild.id), fallback=self.config['main']['prefix_short']))
      else:
        match = match.replace('{p:'+prefixquery+'}', self.config['main']['prefix_short'])
    
    # Fill in conditionals
    conditionalqueries = self.conditional.findall(match)
    for conditionalquery in conditionalqueries:
      if conditionalquery[0] in values:
        if values[conditionalquery[0]]:
          replace = conditionalquery[1]
        else:
          replace = conditionalquery[2]
        match=match.replace('{'+conditionalquery[0]+'?'+conditionalquery[1]+'|'+conditionalquery[2]+'}', replace)

    # Fill in config queries
    configqueries = self.configreference.findall(match)
    for configquery in configqueries:
      if configquery[0] in self.config:
        if configquery[1] in self.config[configquery[0]]:
          match = match.replace('{c:'+configquery[0]+'/'+configquery[1]+'}', self.config[configquery[0]][configquery[1]])

    return match
  
  def list_scope_key_pairs(self, lang):
    pairs = set()
    inheritlang = lang
    while inheritlang and inheritlang in self.langs:
      for scope in self.langs[inheritlang].keys():
        if scope == 'meta': continue
        for key, value in self.langs[inheritlang][scope].items():
          if value:
            pairs.add(f'{scope}/{key}')
      inheritlang = self.langs[inheritlang].get('meta', 'inherit', fallback='')
    return pairs

  def calculate_coverage(self, lang:str):
    langvals = self.list_scope_key_pairs(lang)
    basevals = self.list_scope_key_pairs(self.defaultlang) #TODO: don't run this every time.

    return int((len(langvals) / max(len(basevals), 1)) * 100)