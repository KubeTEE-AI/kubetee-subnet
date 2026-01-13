// SPDX-License-Identifier: MIT
pragma solidity ^0.8.22;

import "./KubeTEEGitHubRegistry.sol";

/**
 * @title KubeTEEGitHubRegistryV2
 * @notice Upgraded version of KubeTEEGitHubRegistry for testing upgradeability
 * @dev This is a stub contract used to verify the UUPS upgrade pattern works correctly
 */
contract KubeTEEGitHubRegistryV2 is KubeTEEGitHubRegistry {
    /**
     * @notice Returns the contract version
     * @return Version string "2.0.0"
     */
    function version() public pure returns (string memory) {
        return "2.0.0";
    }
}
