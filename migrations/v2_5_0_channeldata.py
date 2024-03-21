"""
  This script migrates server's set channels to a new, condensed format
  Introduced in v2.5.0
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from config import Config


def migrate(config:Config):
  print(" - Migrating channel data from pre-v2.5.0 to v2.5.0...")

  pattern = re.compile(r'\d+_\d+')
  newchanneldata:dict[str, list[str]] = {}

  for key in config['confessions']:
    if pattern.match(key):
      serverid, channelid = key.split('_')
      serverlist = newchanneldata.get(serverid, [])
      serverlist.append(f"{channelid}={config['confessions'][key]}")
      newchanneldata[serverid] = serverlist
      config.remove_option('confessions', key)

  for serverid in newchanneldata:
    config['confessions'][serverid+'_channels'] = ','.join(newchanneldata[serverid])

  print(" - Channel data migration complete!")
