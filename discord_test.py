"""One explicitly requested Discord test; no retailer access or state changes."""
import argparse
import asyncio
import os
from urllib.parse import urlsplit

from src.notifier import DiscordNotifier, DiscordDeliveryError

TITLE = '🧪 Pokémon Monitor — Discord delivery test'
LINES = [
    'This is a manual connection test, not a stock alert.',
    'No cart, checkout or payment actions were performed.',
    'If you can read this, the configured webhook is reaching this channel.',
]


async def send_test(webhook):
    parts = urlsplit(webhook)
    if (parts.scheme != 'https' or parts.hostname not in ('discord.com', 'discordapp.com')
            or parts.username or parts.password or not parts.path.startswith('/api/webhooks/')):
        raise ValueError('Set a valid DISCORD_WEBHOOK_URL repository Actions secret.')
    await DiscordNotifier().send(webhook, TITLE, LINES)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send', action='store_true', help='Explicitly send one test to the configured channel')
    args = parser.parse_args()
    if not args.send:
        print('No message sent. Use --send only when a Discord delivery test is requested.')
        return 0
    try:
        asyncio.run(send_test(os.getenv('DISCORD_WEBHOOK_URL', '').strip()))
    except (ValueError, DiscordDeliveryError) as exc:
        print(str(exc))
        return 1
    print('Discord accepted the test message. Confirm it appeared in the intended channel.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
