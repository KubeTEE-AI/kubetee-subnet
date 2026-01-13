"""
GitHub Verification Logic for KubeTEE Subnet.

Implements the 6 validation checks that the validator performs before writing
a GitHub link to the contract.

Validation Checks:
    [A] Hotkey registered on subnet (hotkey_not_registered)
    [B] Signature valid - signed by hotkey (invalid_signature)
    [C] Gist exists and is public (gist_not_found)
    [D] HOTKEY.md file exists in gist with valid hotkey (hotkey_md_missing, invalid_hotkey_format)
    [E] All hotkeys match: claimed == signed == gist (hotkey_mismatch)
    [F] GitHub user exists (github_user_not_found)
"""

from dataclasses import dataclass
from typing import Optional, Any
import re
import json
import logging

import httpx
from substrateinterface import Keypair

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of the GitHub link verification process."""
    
    success: bool
    github_username: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class GitHubVerifier:
    """
    Performs 6 validation checks for GitHub linking.
    
    This class verifies that a miner can legitimately link their Bittensor
    hotkey to a GitHub account by checking:
    
    1. The hotkey is registered on the subnet
    2. The signature is valid (signed by the claimed hotkey)
    3. The gist exists and is public
    4. The gist contains a valid HOTKEY.md file
    5. All hotkeys match (claimed, signed, and in gist)
    6. The GitHub user exists
    """
    
    GITHUB_API_BASE = "https://api.github.com"
    
    # SS58 address pattern for Bittensor hotkeys (starts with 5, 48 chars)
    HOTKEY_PATTERN = re.compile(r"5[A-Za-z0-9]{47}")
    
    # Pattern to extract hotkey from HOTKEY.md content
    HOTKEY_MD_PATTERN = re.compile(r"hotkey:\s*(5[A-Za-z0-9]{47})")
    
    # Pattern to extract gist ID from URL
    GIST_URL_PATTERN = re.compile(
        r"https?://gist\.github\.com/([^/]+)/([a-f0-9]+)"
    )
    
    def __init__(
        self,
        github_token: Optional[str] = None,
        timeout: float = 30.0
    ):
        """
        Initialize the GitHubVerifier.
        
        Args:
            github_token: Optional GitHub personal access token for higher rate limits.
            timeout: HTTP request timeout in seconds.
        """
        self.github_token = github_token
        self.timeout = timeout
    
    def _get_http_headers(self) -> dict[str, str]:
        """Get HTTP headers for GitHub API requests."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "KubeTEE-GitHub-Verifier/1.0"
        }
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"
        return headers
    
    async def verify_link_request(
        self,
        claimed_hotkey: str,
        gist_url: str,
        message: str,
        signature: str,
        subtensor: Any,  # bittensor.subtensor
        netuid: int
    ) -> VerificationResult:
        """
        Run all 6 validation checks.
        
        Args:
            claimed_hotkey: The SS58 hotkey the miner claims to own.
            gist_url: URL to the public GitHub gist containing HOTKEY.md.
            message: The message that was signed (JSON with hotkey and timestamp).
            signature: Hex-encoded signature of the message.
            subtensor: Bittensor subtensor instance for querying registration.
            netuid: Network UID of the subnet.
        
        Returns:
            VerificationResult with:
            - success=True, github_username if all pass
            - success=False, error_code, error_message if any fail
        """
        # [A] Check if hotkey is registered on subnet
        logger.info(f"[A] Checking subnet registration for hotkey: {claimed_hotkey[:16]}...")
        is_registered = await self.verify_subnet_registration(
            claimed_hotkey, subtensor, netuid
        )
        if not is_registered:
            return VerificationResult(
                success=False,
                error_code="hotkey_not_registered",
                error_message=f"Hotkey {claimed_hotkey} is not registered on subnet {netuid}"
            )
        
        # Extract hotkey from signed message for comparison
        try:
            message_data = json.loads(message)
            signed_hotkey = message_data.get("hotkey")
            if not signed_hotkey:
                return VerificationResult(
                    success=False,
                    error_code="invalid_message_format",
                    error_message="Message does not contain 'hotkey' field"
                )
        except json.JSONDecodeError:
            return VerificationResult(
                success=False,
                error_code="invalid_message_format",
                error_message="Message is not valid JSON"
            )
        
        # [B] Verify cryptographic signature matches hotkey
        logger.info(f"[B] Verifying signature...")
        is_valid_signature = self.verify_signature(message, signature, claimed_hotkey)
        if not is_valid_signature:
            return VerificationResult(
                success=False,
                error_code="invalid_signature",
                error_message="Signature verification failed - signature does not match hotkey"
            )
        
        # [C, D] Verify gist exists, is public, and contains HOTKEY.md
        logger.info(f"[C,D] Verifying gist: {gist_url}")
        gist_success, github_username, hotkey_in_gist = await self.verify_gist(gist_url)
        
        if not gist_success:
            # github_username contains error_code, hotkey_in_gist contains error_message
            return VerificationResult(
                success=False,
                error_code=github_username,
                error_message=hotkey_in_gist
            )
        
        # [E] Check all hotkeys match: claimed == signed == gist
        logger.info(f"[E] Verifying hotkey match...")
        if claimed_hotkey != signed_hotkey:
            return VerificationResult(
                success=False,
                error_code="hotkey_mismatch",
                error_message=f"Claimed hotkey ({claimed_hotkey[:16]}...) does not match signed hotkey ({signed_hotkey[:16]}...)"
            )
        
        if claimed_hotkey != hotkey_in_gist:
            return VerificationResult(
                success=False,
                error_code="hotkey_mismatch",
                error_message=f"Claimed hotkey ({claimed_hotkey[:16]}...) does not match hotkey in gist ({hotkey_in_gist[:16]}...)"
            )
        
        # [F] Verify GitHub user exists
        logger.info(f"[F] Verifying GitHub user: {github_username}")
        user_exists = await self.verify_github_user(github_username)
        if not user_exists:
            return VerificationResult(
                success=False,
                error_code="github_user_not_found",
                error_message=f"GitHub user '{github_username}' not found"
            )
        
        # All checks passed!
        logger.info(f"All verification checks passed for {claimed_hotkey[:16]}... -> {github_username}")
        return VerificationResult(
            success=True,
            github_username=github_username
        )
    
    async def verify_subnet_registration(
        self,
        hotkey: str,
        subtensor: Any,
        netuid: int
    ) -> bool:
        """
        [A] Check if hotkey is registered on subnet.
        
        Args:
            hotkey: SS58 address of the hotkey.
            subtensor: Bittensor subtensor instance.
            netuid: Network UID of the subnet.
        
        Returns:
            True if hotkey is registered, False otherwise.
        """
        try:
            # Get all UIDs registered on the subnet
            # subtensor.get_uid_for_hotkey_on_subnet returns the UID or None
            uid = subtensor.get_uid_for_hotkey_on_subnet(
                hotkey_ss58=hotkey,
                netuid=netuid
            )
            return uid is not None
        except Exception as e:
            logger.error(f"Error checking subnet registration: {e}")
            return False
    
    def verify_signature(
        self,
        message: str,
        signature: str,
        expected_hotkey: str
    ) -> bool:
        """
        [B] Verify cryptographic signature matches hotkey.
        
        Uses sr25519 signature verification via substrateinterface.
        
        Args:
            message: The message that was signed.
            signature: Hex-encoded signature (with or without 0x prefix).
            expected_hotkey: The SS58 address that should have signed the message.
        
        Returns:
            True if signature is valid and matches the hotkey, False otherwise.
        """
        try:
            # Create keypair from SS58 address for verification
            keypair = Keypair(ss58_address=expected_hotkey)
            
            # Normalize signature (remove 0x prefix if present)
            sig = signature
            if sig.startswith("0x"):
                sig = sig[2:]
            
            # Convert hex signature to bytes
            signature_bytes = bytes.fromhex(sig)
            
            # Encode message as bytes
            message_bytes = message.encode("utf-8")
            
            # Verify the signature
            is_valid = keypair.verify(message_bytes, signature_bytes)
            return is_valid
            
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False
    
    async def verify_gist(
        self,
        gist_url: str
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        [C, D] Verify gist exists, is public, and contains HOTKEY.md.
        
        Args:
            gist_url: URL to the GitHub gist.
        
        Returns:
            On success: (True, github_username, hotkey_in_gist)
            On failure: (False, error_code, error_message)
        """
        # Parse gist URL to extract username and gist ID
        match = self.GIST_URL_PATTERN.match(gist_url)
        if not match:
            return (
                False,
                "gist_not_found",
                f"Invalid gist URL format: {gist_url}"
            )
        
        github_username = match.group(1)
        gist_id = match.group(2)
        
        # Fetch gist from GitHub API
        api_url = f"{self.GITHUB_API_BASE}/gists/{gist_id}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    api_url,
                    headers=self._get_http_headers()
                )
                
                # Handle rate limiting
                if response.status_code == 403:
                    remaining = response.headers.get("X-RateLimit-Remaining", "0")
                    if remaining == "0":
                        return (
                            False,
                            "rate_limited",
                            "GitHub API rate limit exceeded. Please try again later."
                        )
                
                # Gist not found or not public
                if response.status_code == 404:
                    return (
                        False,
                        "gist_not_found",
                        f"Gist not found or not public: {gist_url}"
                    )
                
                if response.status_code != 200:
                    return (
                        False,
                        "gist_not_found",
                        f"Failed to fetch gist: HTTP {response.status_code}"
                    )
                
                gist_data = response.json()
                
        except httpx.TimeoutException:
            return (
                False,
                "gist_not_found",
                "Timeout while fetching gist from GitHub"
            )
        except httpx.RequestError as e:
            return (
                False,
                "gist_not_found",
                f"Network error while fetching gist: {e}"
            )
        
        # Check if gist is public
        if gist_data.get("public") is False:
            return (
                False,
                "gist_not_found",
                "Gist is not public"
            )
        
        # Get the actual owner (may differ from URL if forked)
        gist_owner = gist_data.get("owner", {}).get("login")
        if gist_owner:
            github_username = gist_owner
        
        # Look for HOTKEY.md file in the gist
        files = gist_data.get("files", {})
        hotkey_file = files.get("HOTKEY.md")
        
        if hotkey_file is None:
            return (
                False,
                "hotkey_md_missing",
                "Gist does not contain HOTKEY.md file"
            )
        
        # Get file content
        content = hotkey_file.get("content", "")
        
        # Check if content is truncated and we need to fetch raw URL
        if hotkey_file.get("truncated"):
            raw_url = hotkey_file.get("raw_url")
            if raw_url:
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        raw_response = await client.get(
                            raw_url,
                            headers=self._get_http_headers()
                        )
                        if raw_response.status_code == 200:
                            content = raw_response.text
                except Exception as e:
                    logger.warning(f"Failed to fetch truncated file content: {e}")
        
        # Extract hotkey from content
        hotkey_in_gist = self.extract_hotkey_from_content(content)
        
        if hotkey_in_gist is None:
            return (
                False,
                "invalid_hotkey_format",
                "HOTKEY.md does not contain a valid hotkey. Expected format: 'hotkey: 5...'"
            )
        
        return (True, github_username, hotkey_in_gist)
    
    async def verify_github_user(self, username: str) -> bool:
        """
        [F] Verify GitHub user exists.
        
        Args:
            username: GitHub username to verify.
        
        Returns:
            True if user exists, False otherwise.
        """
        api_url = f"{self.GITHUB_API_BASE}/users/{username}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    api_url,
                    headers=self._get_http_headers()
                )
                
                # Handle rate limiting gracefully
                if response.status_code == 403:
                    remaining = response.headers.get("X-RateLimit-Remaining", "0")
                    if remaining == "0":
                        logger.warning("GitHub API rate limit exceeded during user verification")
                        # In case of rate limiting, we might want to be lenient
                        # and assume the user exists (since we already verified the gist)
                        return True
                
                return response.status_code == 200
                
        except httpx.TimeoutException:
            logger.error(f"Timeout while verifying GitHub user: {username}")
            return False
        except httpx.RequestError as e:
            logger.error(f"Network error while verifying GitHub user: {e}")
            return False
    
    def extract_hotkey_from_content(self, content: str) -> Optional[str]:
        """
        Parse hotkey from HOTKEY.md content.
        
        Expected format: hotkey: 5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY
        
        Args:
            content: The raw content of the HOTKEY.md file.
        
        Returns:
            The extracted hotkey if found and valid, None otherwise.
        """
        match = self.HOTKEY_MD_PATTERN.search(content)
        if match:
            hotkey = match.group(1)
            # Validate it's a properly formatted SS58 address
            if self.HOTKEY_PATTERN.fullmatch(hotkey):
                return hotkey
        return None
