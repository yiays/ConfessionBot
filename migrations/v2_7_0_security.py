"""
  This script deletes all shuffles so that the new system is always used
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from config import Config


def migrate(config:Config):
  print(" - Deleting all server shuffle & ban data...")

  for key in config['confessions']:
    if key.endswith('_shuffle') or key.endswith('_banned'):
      config.remove_option('confessions', key)

  print(" - Shuffle deletion complete!")
