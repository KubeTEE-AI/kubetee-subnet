"""
KubeTEE CLI Module.

Command-line interface tools for the KubeTEE subnet.
Provides commands for:
    - Linking GitHub accounts to Bittensor wallets (`link-github`)
    - Checking link status (`status`)

Usage:
    kubetee link-github --gist-url https://gist.github.com/user/abc --mechanism-id 3
    kubetee status --hotkey 5Grwva...

Environment Variables:
    KUBETEE_WALLET - Default wallet name
    KUBETEE_WALLET_HOTKEY - Default hotkey name
    KUBETEE_VALIDATOR - Validator API URL
    KUBETEE_HOTKEY_ADDRESS - SS58 hotkey address
"""

from kubetee.cli.github import cli, main, link_github, status

__all__ = ["cli", "main", "link_github", "status"]
