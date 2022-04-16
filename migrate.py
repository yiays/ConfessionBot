"""
  Migrates data from ConfessionBot v1.x to ConfessionBot 2.0
"""

from configparser import ConfigParser
import os

def migrate_translations():
  print("migrate_translations():")

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
    'setlanguage/promo': 'merely/language/contribute_cta',
    'admin/diesuccess': 'merely/admin/die_success'
  }

  strmap = {
    '{botname}': '{c:main/botname}',
    '{prefix}': '{p:local}',
    '{version}': '{c:main/ver}',
    '{authorname}': '{c:main/creator}',
    'setlanguage': 'language',
    'setuntraceable': 'set untraceable',
    'setvetting': 'set vetting',
    'setfeedback': 'set feedback',
    'unset': 'set none',
    'setprefix': 'prefix',
    'enableimage': 'imagesupport enable',
    'disableimage': 'imagesupport disable',
    'a botmod': 'promoted',
    'botmod': 'promote',
    '`unban ': '`ban -',
    '`unban': '`ban'
  }

  refv2 = ConfigParser(comment_prefixes='@', allow_no_value=True)
  refv2.read('babel/en.ini', encoding='utf-8')
  refv2_cb = ConfigParser(comment_prefixes='@', allow_no_value=True)
  refv2_cb.read('babel/confessionbot_en.ini', encoding='utf-8')

  for langf in os.scandir('babel/v1.x/'):
    if str(langf.name)[-4:] == '.ini':
      langv1 = ConfigParser()
      langv1.read('babel/v1.x/'+langf.name, encoding='utf-8')

      langv2 = ConfigParser(comment_prefixes='@', allow_no_value=True)

      langv2_cb = ConfigParser(comment_prefixes='@', allow_no_value=True)

      def updatestr(str: str):
        for oldstr,newstr in strmap.items():
          str = str.replace(oldstr, newstr)
        return str

      langv2_cb.add_section('meta')
      for section in langv1.sections():
        for key in langv1[section]:
          if f'{section}/{key}' in keymap:
            dest = keymap[f'{section}/{key}'].split('/')
            tini = langv2 if dest[0] == 'merely' else langv2_cb
            rini = refv2 if dest[0] == 'merely' else refv2_cb
            
            oldstr = rini.get(dest[1], dest[2]).splitlines()
            newstr = updatestr(langv1[section][key]).splitlines()
            if len(newstr) == 1 and len(oldstr) > 1:
              newstr += oldstr[1:]

            # one-off patches
            if dest[0] == 'merely':
              if dest[1] != 'meta':
                newstr[0] = newstr[0].lower()
              if dest[1] == 'language' and dest[2] =='contrbute_cta':
                newstr[0] = newstr[0].replace('{url}', '{c:language/contribute_url}')
            elif dest[0] == 'cb':
              if dest[1] == 'ownerintro' and dest[2] == 'welcome':
                newstr[0].replace('{p:local}', '{p:global}')
              if dest[1] == 'confessions':
                if dest[2] == 'vettingrequiredmissing':
                  newstr[0] = "Unable to send an approved confession. "+newstr[0]
                if dest[2] == 'vetting':
                  newstr[0] = '**'+newstr[0]+'**'

            if not tini.has_section(dest[1]):
              tini.add_section(dest[1])
            tini.set(dest[1], dest[2], '\n'.join(newstr))
      
      with open('babel/v2.0/'+langf.name, 'w') as f:
        langv2['meta']['inherit'] = ''
        langv2.write(f)
      with open('babel/v2.0/confessionbot_'+langf.name, 'w') as f:
        for key in langv2['meta']:
          if key == 'inherit':
            langv2_cb['meta']['inherit'] = langv2['meta']['language']
          elif key == 'language':
            langv2_cb['meta']['language'] = 'confessionbot_'+langv2['meta']['language']
          else:
            langv2_cb['meta'][key] = langv2['meta'][key]
        langv2_cb.write(f)
      print("migrated the "+langf.name[:-4]+" translation.")

def migrate_config():
  print("migrate_config():")

  keymap = {
    'main/creator': 'main/creator',
    'main/token': 'main/token',
    'main/beta': 'main/beta',
    'main/starttime': 'confessions/starttime',
    'customprefix/*': 'prefix/{}',
    #'channels/*': 'confessions/?_{}', - unknown guild channels are no longer supported
    'banned/*': 'confessions/{}_banned',
    'shuffle/*': 'confessions/{}_shuffle',
    'imagesupport/*': 'confessions/{}_imagesupport',
    'promoted/*': 'confessions/{}_promoted'
  }

  refv2 = ConfigParser()
  refv2.read('config/config.factory.ini', encoding='utf-8')
  confv1 = ConfigParser()
  confv1.read('config/v1.x/config.ini', encoding='utf-8')
  confv2 = ConfigParser()
  confv2.read('config/config.factory.ini', encoding='utf-8')

  for section in confv1.sections():
    if section =='language':
      for key in confv1['language']:
        confv2['language'][key] = 'confessionbot_'+confv1['language'][key]
    elif section.startswith('pending_vetting_'):
      pass # pending confessions are no longer stored in this config
    elif f'{section}/*' in keymap:
      t = keymap[f'{section}/*'].split('/')
      tsect = t[0]
      topt = t[1]
      for key in confv1[section]:
        confv2[tsect][topt.format(key)] = confv1[section][key]
    else:
      for key in confv1[section]:
        if f'{section}/{key}' in keymap:
          t = keymap[f'{section}/{key}'].split('/')
          tsect = t[0]
          topt = t[1]
          confv2[tsect][topt] = confv1[section][key]
        else:
          print(f"'{section}/{key}' discarded.")
    print(f"'{section}' migrated!")
  
  if not os.path.isdir('config/v2.0'):
    os.mkdir('config/v2.0')
  with open('config/v2.0/config.ini', 'w', encoding='utf-8') as f:
    confv2.write(f)
  
  print("config migration complete!")

#migrate_translations()
migrate_config()