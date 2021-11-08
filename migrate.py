"""
  Migrates data from ConfessionBot v1.x to ConfessionBot 2.0
"""

from configparser import ConfigParser
import os, shutil

def migrate_translations():
  v1langs = {}
  v2langs = {}

  """ TODO: extras that need special code:
    cb/meta/*
    */meta/inherit
    help/*desc
    help/usagesummary
  """
  keymap = {
    'metadata/language': 'merely/meta/name',
    'metadata/langcode': 'merely/meta/language',
    'metadata/contributors': 'merely/meta/contributors',
    'introduction/hi': 'cb/ownerintro/message',
    'help/title': 'merely/help/title',
    'help/botowner': 'merely/help/creator_footer',
    'error/admindenied': 'merely/auth/not_admin',
    'error/moddenied': 'merely/auth/not_mod',
    'error/inaccessible': 'cb/confessions/inaccessible'
  }

  strmap = {
    '{botname}': '{c:main/botname}',
    '{prefix}': '{p:local}',
    'setlanguage': 'language',
    'setuntraceable': 'set untraceable',
    'setvetting': 'set vetting',
    'setfeedback': 'set feedback',
    'unset': 'set none',
    'setprefix': 'prefix',
    'enableimage': 'imagesupport enable',
    'disableimage': 'imagesupport disable',
    'promoted': 'a botmod',
    'promote': 'botmod',
    'unban ': 'ban -',
    'unban': 'ban'
  }

  for f in os.scandir('babel/v1.x/'):
    if f[-4:] == '.ini':
      langname = f[:-4]
      v1langs[langname] = ConfigParser(comment_prefixes='@', allow_no_value=True)
      v1langs[langname].read('babel/v1.x/'+f)

      shutil.copy('babel/en.ini', 'babel/'+langname+'.ini')
      v2langs[langname] = ConfigParser(comment_prefixes='@', allow_no_value=True)
      v2langs[langname].read('babel/'+f)

      shutil.copy('babel/confessionbot_en.ini', 'babel/confessionbot_'+langname+'.ini')
      v2langs['confessionbot_'+langname] = ConfigParser(comment_prefixes='@', allow_no_value=True)
      v2langs['confessionbot_'+langname].read('babel/confessionbot_'+f)

def migrate_config():
  pass

migrate_translations()
migrate_config()