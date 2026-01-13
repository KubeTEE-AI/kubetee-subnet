// SPDX-License-Identifier: MIT
pragma solidity ^0.8.22;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";

/**
 * @title KubeTEEGitHubRegistry
 * @notice Links Bittensor hotkeys to GitHub accounts via events
 * @dev Upgradeable (UUPS pattern), events-based storage for gas efficiency
 *
 * This contract uses events as the primary storage mechanism instead of mappings.
 * This approach reduces gas costs from ~20,000 per write (storage) to ~2,000 per emit.
 *
 * Access Control:
 * - Admin (owner): Full rights - can add/remove operators, upgrade contract
 * - Operator: Can emit events and perform logic operations (linkGitHub)
 */
contract KubeTEEGitHubRegistry is
    Initializable,
    OwnableUpgradeable,
    UUPSUpgradeable
{
    /// @notice Operator whitelist - operators can emit events and perform logic operations
    mapping(address => bool) public isOperator;

    /**
     * @notice Emitted when a hotkey is linked to a GitHub account
     * @param hotkeyHash Indexed hash of the hotkey for efficient filtering (keccak256)
     * @param hotkey Full Bittensor SS58 hotkey value
     * @param mechanismId Mechanism ID (0 = bounty system, etc.)
     * @param githubUsername The GitHub username being linked
     * @param operator Address of the operator who performed the link
     * @param timestamp Block timestamp when the link was created
     */
    event GitHubLinked(
        string indexed hotkeyHash,
        string hotkey,
        uint256 mechanismId,
        string githubUsername,
        address operator,
        uint256 timestamp
    );

    /// @notice Emitted when an operator is added
    event OperatorAdded(address indexed operator);

    /// @notice Emitted when an operator is removed
    event OperatorRemoved(address indexed operator);

    /// @notice Restricts function access to operators only
    modifier onlyOperator() {
        require(isOperator[msg.sender], "Only operators");
        _;
    }

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /**
     * @notice Initializes the contract (replaces constructor for upgradeable contracts)
     * @dev Can only be called once due to initializer modifier
     */
    function initialize() public initializer {
        __Ownable_init(msg.sender);
        __UUPSUpgradeable_init();
    }

    /**
     * @notice Authorizes contract upgrades
     * @dev Required by UUPS pattern, restricted to admin (owner)
     * @param newImplementation Address of the new implementation contract
     */
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}

    /**
     * @notice Add an operator
     * @dev Only the admin (owner) can add operators
     * @param operator Address of the operator to add
     */
    function addOperator(address operator) external onlyOwner {
        require(operator != address(0), "Invalid operator address");
        require(!isOperator[operator], "Already an operator");
        isOperator[operator] = true;
        emit OperatorAdded(operator);
    }

    /**
     * @notice Remove an operator
     * @dev Only the admin (owner) can remove operators
     * @param operator Address of the operator to remove
     */
    function removeOperator(address operator) external onlyOwner {
        require(isOperator[operator], "Not an operator");
        isOperator[operator] = false;
        emit OperatorRemoved(operator);
    }

    /**
     * @notice Link a Bittensor hotkey to a GitHub account
     * @dev Emits GitHubLinked event, no storage writes for gas efficiency
     *      Only operators can call this function
     * @param hotkey Bittensor SS58 hotkey to link
     * @param mechanismId Mechanism ID (0 = bounty system, 1 = open source, etc.)
     * @param githubUsername GitHub username to link to the hotkey
     */
    function linkGitHub(
        string calldata hotkey,
        uint256 mechanismId,
        string calldata githubUsername
    ) external onlyOperator {
        require(bytes(hotkey).length > 0, "Empty hotkey");
        require(bytes(githubUsername).length > 0, "Empty GitHub username");

        emit GitHubLinked(
            hotkey,              // Will be hashed for indexing
            hotkey,              // Full value stored in event data
            mechanismId,
            githubUsername,
            msg.sender,
            block.timestamp
        );
    }
}
