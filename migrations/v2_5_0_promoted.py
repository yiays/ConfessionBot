"""
  This script deletes botmods (promoted) from config as this is no longer supported
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from config import Config


def migrate(config:Config):
  print(" - Deleting all botmod data...")

  for key in config['confessions']:
    if key.endswith('_promoted'):
      config.remove_option('confessions', key)

  print(" - Shuffle deletion complete!")
