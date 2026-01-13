"""
KubeTEE CLI - GitHub Linking Command.

Provides the `link-github` command for miners to link their Bittensor
hotkey to their GitHub account via a public gist.

Usage:
    kubetee link-github --gist-url https://gist.github.com/user/abc123 --mechanism-id 3
"""

import json
import sys
import time
from typing import Optional

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# ASCII Art Banner
KUBETEE_BANNER = r"""
██╗  ██╗██╗   ██╗██████╗ ███████╗████████╗███████╗███████╗
██║ ██╔╝██║   ██║██╔══██╗██╔════╝╚══██╔══╝██╔════╝██╔════╝
█████╔╝ ██║   ██║██████╔╝█████╗     ██║   █████╗  █████╗
██╔═██╗ ██║   ██║██╔══██╗██╔══╝     ██║   ██╔══╝  ██╔══╝
██║  ██╗╚██████╔╝██████╔╝███████╗   ██║   ███████╗███████╗
╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝╚══════╝"""

KUBETEE_SUBTITLE = "Confidential AI Computing on Bittensor | Subnet 62"


def show_banner():
    """Display the KubeTEE ASCII banner with rich formatting."""
    console = Console()
    console.print(KUBETEE_BANNER, style="bold green")
    console.print(KUBETEE_SUBTITLE, style="dim white")
    console.print()

# Mechanism ID to name mapping
MECHANISM_NAMES = {
    0: "infrastructure",
    1: "opensource",
    2: "referral",
    3: "bounty",
}


def get_mechanism_name(mechanism_id: int) -> str:
    """Get human-readable name for a mechanism ID."""
    return MECHANISM_NAMES.get(mechanism_id, f"mechanism_{mechanism_id}")


def load_wallet(wallet_name: str, wallet_hotkey: str):
    """
    Load a Bittensor wallet.
    
    Args:
        wallet_name: Name of the wallet (coldkey name).
        wallet_hotkey: Name of the hotkey.
    
    Returns:
        A bittensor wallet instance.
    
    Raises:
        click.ClickException: If wallet cannot be loaded.
    """
    try:
        import bittensor as bt
        
        wallet = bt.wallet(name=wallet_name, hotkey=wallet_hotkey)
        
        # Verify hotkey exists
        if not wallet.hotkey_file.exists_on_device():
            raise click.ClickException(
                f"Hotkey '{wallet_hotkey}' not found for wallet '{wallet_name}'. "
                f"Expected at: {wallet.hotkey_file.path}"
            )
        
        return wallet
        
    except ImportError:
        raise click.ClickException(
            "Bittensor is not installed. Install with: pip install bittensor"
        )
    except Exception as e:
        raise click.ClickException(f"Failed to load wallet: {e}")


def sign_message(wallet, message: str) -> str:
    """
    Sign a message with the wallet's hotkey using sr25519.
    
    Args:
        wallet: Bittensor wallet instance.
        message: Message string to sign.
    
    Returns:
        Hex-encoded signature string prefixed with 0x.
    """
    try:
        # Get the keypair from the wallet
        keypair = wallet.hotkey
        
        # Sign the message bytes
        message_bytes = message.encode("utf-8")
        signature = keypair.sign(message_bytes)
        
        # Convert signature to hex string
        if isinstance(signature, bytes):
            return "0x" + signature.hex()
        else:
            # Some versions return different types
            return "0x" + bytes(signature).hex()
        
    except Exception as e:
        raise click.ClickException(f"Failed to sign message: {e}")


def make_link_request(
    validator_url: str,
    hotkey: str,
    mechanism_id: int,
    gist_url: str,
    message: str,
    signature: str,
    timeout: int = 30
) -> dict:
    """
    Send the link request to the validator API.
    
    Args:
        validator_url: Base URL of the validator API.
        hotkey: SS58 hotkey address.
        mechanism_id: Mechanism ID (0-3).
        gist_url: URL to the public gist.
        message: JSON message that was signed.
        signature: Hex signature of the message.
        timeout: Request timeout in seconds.
    
    Returns:
        Response dictionary from the API.
    
    Raises:
        click.ClickException: If request fails.
    """
    endpoint = f"{validator_url.rstrip('/')}/api/github/link"
    
    payload = {
        "hotkey": hotkey,
        "mechanism_id": mechanism_id,
        "gist_url": gist_url,
        "message": message,
        "signature": signature,
    }
    
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(endpoint, json=payload)
            
            # Try to parse JSON response
            try:
                result = response.json()
            except json.JSONDecodeError:
                raise click.ClickException(
                    f"Invalid response from validator: {response.text[:200]}"
                )
            
            return result
            
    except httpx.ConnectError:
        raise click.ClickException(
            f"Failed to connect to validator at {validator_url}. "
            "Is the validator running?"
        )
    except httpx.TimeoutException:
        raise click.ClickException(
            f"Request to validator timed out after {timeout} seconds."
        )
    except httpx.HTTPError as e:
        raise click.ClickException(f"HTTP error: {e}")


def display_success(hotkey: str, github_username: str, mechanism_id: int, 
                    status: str, tx_hash: Optional[str]):
    """Display a success message."""
    mechanism_name = get_mechanism_name(mechanism_id)
    
    click.echo()
    click.secho("✅ GitHub linked successfully!", fg="green", bold=True)
    click.echo(f"   Hotkey: {hotkey[:16]}...{hotkey[-8:]}")
    click.echo(f"   GitHub: {github_username}")
    click.echo(f"   Mechanism: {mechanism_name} ({mechanism_id})")
    click.echo(f"   Status: {status}")
    if tx_hash:
        click.echo(f"   Transaction: {tx_hash}")
    click.echo()


def display_error(error_code: str, error_message: str):
    """Display an error message."""
    click.echo()
    click.secho("❌ Failed to link GitHub", fg="red", bold=True)
    click.echo(f"   Error: {error_code}")
    click.echo(f"   Message: {error_message}")
    click.echo()


class KubeTEEGroup(click.Group):
    """Custom Click group that shows ASCII banner on help."""

    def format_help(self, ctx, formatter):
        """Override to show banner before help text."""
        show_banner()
        super().format_help(ctx, formatter)


@click.group(cls=KubeTEEGroup)
@click.version_option(version="0.1.0", prog_name="kubetee")
def cli():
    """
    KubeTEE CLI - Miner tools for subnet 62.

    Use these commands to interact with the KubeTEE subnet,
    including linking your GitHub account to your miner hotkey.

    NVIDIA Inception Program | Confidential Computing Consortium
    """
    pass


@cli.command("link-github")
@click.option(
    "--hotkey", "-h",
    envvar="KUBETEE_HOTKEY_ADDRESS",
    help="SS58 hotkey address (auto-derived from wallet if not provided)."
)
@click.option(
    "--mechanism-id", "-m",
    type=click.IntRange(0, 10),
    required=True,
    help="Mechanism ID (0=infra, 1=opensource, 2=referral, 3=bounty)."
)
@click.option(
    "--gist-url", "-g",
    required=True,
    help="URL to public gist containing HOTKEY.md file."
)
@click.option(
    "--wallet-name", "-w",
    envvar="KUBETEE_WALLET",
    default="default",
    show_default=True,
    help="Bittensor wallet name (coldkey name)."
)
@click.option(
    "--wallet-hotkey", "-k",
    envvar="KUBETEE_WALLET_HOTKEY",
    default="default",
    show_default=True,
    help="Wallet hotkey name."
)
@click.option(
    "--validator-url", "-v",
    envvar="KUBETEE_VALIDATOR",
    default="https://validator.kubetee.io",
    show_default=True,
    help="Validator API URL."
)
@click.option(
    "--timeout", "-t",
    type=int,
    default=30,
    show_default=True,
    help="Request timeout in seconds."
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be sent without making the request."
)
def link_github(
    hotkey: Optional[str],
    mechanism_id: int,
    gist_url: str,
    wallet_name: str,
    wallet_hotkey: str,
    validator_url: str,
    timeout: int,
    dry_run: bool
):
    """
    Link your GitHub account to your miner hotkey.
    
    Before running this command:
    
    \b
    1. Create a public gist on GitHub (https://gist.github.com)
    2. Add a file named HOTKEY.md with content:
       hotkey: YOUR_SS58_HOTKEY_ADDRESS
    3. Run this command with the gist URL
    
    \b
    Examples:
        # Basic usage with required options
        kubetee link-github -g https://gist.github.com/you/abc123 -m 3
        
        # Specify wallet explicitly
        kubetee link-github -g https://gist.github.com/you/abc123 -m 3 \\
            -w my_wallet -k my_hotkey
        
        # Use environment variables
        export KUBETEE_WALLET=my_wallet
        export KUBETEE_WALLET_HOTKEY=my_hotkey
        export KUBETEE_VALIDATOR=https://validator.kubetee.io
        kubetee link-github -g https://gist.github.com/you/abc123 -m 3
    
    \b
    Mechanism IDs:
        0 = Infrastructure providers
        1 = Open source contributors
        2 = Referral program
        3 = Bounty program
    """
    # Step 1: Load wallet
    click.echo(f"Loading wallet '{wallet_name}' with hotkey '{wallet_hotkey}'...")
    wallet = load_wallet(wallet_name, wallet_hotkey)
    
    # Step 2: Get hotkey address
    if hotkey:
        # Use provided hotkey, but validate it matches wallet
        wallet_hotkey_address = wallet.hotkey.ss58_address
        if hotkey != wallet_hotkey_address:
            click.secho(
                f"Warning: Provided hotkey doesn't match wallet hotkey. "
                f"Using wallet hotkey: {wallet_hotkey_address}",
                fg="yellow"
            )
            hotkey = wallet_hotkey_address
    else:
        hotkey = wallet.hotkey.ss58_address
    
    click.echo(f"Hotkey: {hotkey}")
    
    # Step 3: Create message to sign
    timestamp = int(time.time())
    message_dict = {
        "hotkey": hotkey,
        "timestamp": timestamp
    }
    message = json.dumps(message_dict, separators=(",", ":"))  # Compact JSON
    
    click.echo(f"Message: {message}")
    
    # Step 4: Sign message
    click.echo("Signing message with hotkey...")
    signature = sign_message(wallet, message)
    
    click.echo(f"Signature: {signature[:20]}...{signature[-16:]}")
    
    # Dry run - show what would be sent
    if dry_run:
        click.echo()
        click.secho("DRY RUN - Request that would be sent:", fg="cyan", bold=True)
        click.echo(f"  Endpoint: {validator_url}/api/github/link")
        click.echo(f"  Hotkey: {hotkey}")
        click.echo(f"  Mechanism ID: {mechanism_id}")
        click.echo(f"  Gist URL: {gist_url}")
        click.echo(f"  Message: {message}")
        click.echo(f"  Signature: {signature}")
        click.echo()
        return
    
    # Step 5: Send request to validator
    click.echo(f"Sending link request to {validator_url}...")
    
    result = make_link_request(
        validator_url=validator_url,
        hotkey=hotkey,
        mechanism_id=mechanism_id,
        gist_url=gist_url,
        message=message,
        signature=signature,
        timeout=timeout
    )
    
    # Step 6: Display result
    if result.get("success"):
        display_success(
            hotkey=hotkey,
            github_username=result.get("github_username", "unknown"),
            mechanism_id=mechanism_id,
            status=result.get("status", "unknown"),
            tx_hash=result.get("tx_hash")
        )
    else:
        display_error(
            error_code=result.get("error_code", "unknown_error"),
            error_message=result.get("error_message", "Unknown error occurred")
        )
        sys.exit(1)


@cli.command("status")
@click.option(
    "--hotkey", "-h",
    required=True,
    help="SS58 hotkey address to check."
)
@click.option(
    "--mechanism-id", "-m",
    type=click.IntRange(0, 10),
    default=3,
    show_default=True,
    help="Mechanism ID to check."
)
@click.option(
    "--validator-url", "-v",
    envvar="KUBETEE_VALIDATOR",
    default="https://validator.kubetee.io",
    show_default=True,
    help="Validator API URL."
)
def status(hotkey: str, mechanism_id: int, validator_url: str):
    """
    Check the GitHub link status for a hotkey.
    
    Example:
        kubetee status -h 5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY
    """
    endpoint = f"{validator_url.rstrip('/')}/api/github/status/{hotkey}"
    
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(endpoint, params={"mechanism_id": mechanism_id})
            result = response.json()
            
            click.echo()
            if result.get("is_linked"):
                click.secho("✅ Hotkey is linked", fg="green", bold=True)
                click.echo(f"   Hotkey: {hotkey[:16]}...{hotkey[-8:]}")
                click.echo(f"   GitHub: {result.get('github_username')}")
                click.echo(f"   Mechanism: {get_mechanism_name(mechanism_id)} ({mechanism_id})")
            else:
                click.secho("⚠️  Hotkey is not linked", fg="yellow", bold=True)
                click.echo(f"   Hotkey: {hotkey[:16]}...{hotkey[-8:]}")
                click.echo(f"   Mechanism: {get_mechanism_name(mechanism_id)} ({mechanism_id})")
            click.echo()
            
    except httpx.HTTPError as e:
        raise click.ClickException(f"Failed to check status: {e}")


def main():
    """Entry point for the kubetee CLI."""
    cli()


if __name__ == "__main__":
    main()
