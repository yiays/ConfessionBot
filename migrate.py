"""
  Migrates data from ConfessionBot v1.x to ConfessionBot 2.0
"""

from configparser import ConfigParser
import os, shutil

def migrate_translations():
  """ TODO: extras that need special code:
    cb/meta/*
    */meta/inherit
    help/*desc
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
    'error/inaccessible': 'cb/confessions/inaccessible',
    'error/inaccessiblelocal': 'cb/confessions/inaccessiblelocal',
    'error/invalidanonid': 'cb/confessions/invalidanonid',
    'error/doublebananonid': 'cb/confessions/doublebananonid',
    'error/nomatchanonid': 'cb/confessions/nomatchanonid',
    'error/timeouterr': 'cb/confessions/timeouterr',
    'error/singlechannel': 'cb/confessions/singlechannel',
    'error/incorrectformat': 'cb/confessions/incorrectformat',
    'error/vettingrequiredmissing': 'cb/confessions/vettingrequiredmissing',
    'warning/cachebuilding': 'cb/confessions/cachebuilding',
    'warning/vetting': 'cb/confessions/vetting',
    'confessions/multipletargets': 'cb/confessions/multiplesendtargets',
    'confessions/multipletargetsshort': 'cb/confessions/multiplesendtargetsshort',
    'confessions/notargethelp': 'cb/confessions/nosendtargethelp',
    'confessions/banned': 'cb/confessions/nosendbanned',
    'confessions/noimages': 'cb/confessions/nosendimages',
    'set/successuntraceable': 'cb/confessions/setsuccess0',
    'set/successtraceable': 'cb/confessions/setsuccess1',
    'set/successvetting': 'cb/confessions/setsuccess2',
    'set/successfeedback': 'cb/confessions/setsuccess3',
    'set/calltoaction': 'cb/confessions/setcta',
    'set/undo': 'cb/confessions/setundo',
    'unset/success': 'cb/confessions/unsetsuccess1',
    'unset/successvetting': 'cb/confessions/unsetsuccess2',
    'unset/successfeedback': 'cb/confessions/unsetsuccess3',
    'unset/undo': 'cb/confessions/unsetundo',
    'list/success': 'cb/confessions/listtitle',
    'list/successlocal': 'cb/confessions/listtitlelocal',
    'ban/success': 'cb/confessions/bansuccess',
    'unban/success': 'cb/confessions/unbansuccess',
    'unban/list': 'cb/confessions/banlist',
    'unban/emptylist': 'cb/confessions/emptybanlist',
    'shuffle/banresetwarning': 'cb/confessions/shufflebanresetwarning',
    'shuffle/obsoleteone': 'cb/confessions/shuffleobsoleteone',
    'shuffle/successall': 'cb/confessions/shufflesuccess',
    'promote/repromoteerr': 'cb/confessions/rebotmoderr',
    'promote/modpromoteerr': 'cb/confessions/botmodmoderr',
    'demote/success': 'cb/confessions/botmoddemotesuccess',
    'demote/notpromotederr': 'cb/confessions/botmoddemoteerr',
    'demote/emptylist': 'cb/confessions/botmodemptylist',
    'enableimage/success': 'cb/confessions/imagesupportenabled',
    'enableimage/redoerr': 'cb/confessions/imagesupportalreadyenabled',
    'disableimage/success': 'cb/confessions/imagesupportdisabled',
    'disableimage/redoerr': 'cb/confessions/imagesupportalreadydisabled',
    'mod/vetmessage': 'cb/confessions/vetmessagecta',
    'mod/vetaccepted': 'cb/confessions/vetaccepted',
    'mod/vetdenied': 'cb/confessions/vetdenied',
    'setprefix/success': 'merely/prefix/set_success',
    'setlanguage/promo': 'merely/language/contribute_cta',
    'admin/diesuccess': 'merely/admin/die_success'
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
      langv1 = ConfigParser(comment_prefixes='@', allow_no_value=True)
      langv1.read('babel/v1.x/'+f)

      shutil.copy('babel/en.ini', 'babel/v2.0/'+f)
      langv2 = ConfigParser(comment_prefixes='@', allow_no_value=True)
      langv2.read('babel/v2.0/'+f)

      shutil.copy('babel/confessionbot_en.ini', 'babel/v2.0/confessionbot_'+f)
      langv2_cb = ConfigParser(comment_prefixes='@', allow_no_value=True)
      langv2_cb.read('babel/v2.0/confessionbot_'+f)

def migrate_config():
  pass

migrate_translations()
migrate_config()