// SPDX-License-Identifier: MIT
pragma solidity ^0.8.22;

/**
 * @title MockWTAOBridge
 * @notice Mock wTAO Bridge for testing purposes
 */
contract MockWTAOBridge {
    event BridgeInitiated(uint256 amount, string bittensorAddress);
    
    /**
     * @notice Mock bridge function - just emits an event for testing
     */
    function bridgeToBittensor(uint256 amount, string calldata bittensorAddress) external {
        emit BridgeInitiated(amount, bittensorAddress);
    }
}
