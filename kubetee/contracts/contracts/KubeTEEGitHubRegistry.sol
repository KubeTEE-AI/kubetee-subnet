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
 * The validator loads all GitHubLinked events on startup into an in-memory cache.
 */
contract KubeTEEGitHubRegistry is 
    Initializable, 
    OwnableUpgradeable, 
    UUPSUpgradeable 
{
    /// @notice Validator whitelist - only whitelisted validators can link GitHub accounts
    mapping(address => bool) public isValidator;
    
    /**
     * @notice Emitted when a hotkey is linked to a GitHub account
     * @param hotkeyHash Indexed hash of the hotkey for efficient filtering (keccak256)
     * @param hotkey Full Bittensor SS58 hotkey value
     * @param mechanismId Mechanism ID (0 = bounty system, etc.)
     * @param githubUsername The GitHub username being linked
     * @param validator Address of the validator who performed the link
     * @param timestamp Block timestamp when the link was created
     */
    event GitHubLinked(
        string indexed hotkeyHash,
        string hotkey,
        uint256 mechanismId,
        string githubUsername,
        address validator,
        uint256 timestamp
    );
    
    /// @notice Emitted when a validator is added to the whitelist
    event ValidatorAdded(address indexed validator);
    
    /// @notice Emitted when a validator is removed from the whitelist
    event ValidatorRemoved(address indexed validator);
    
    /// @notice Restricts function access to whitelisted validators only
    modifier onlyValidator() {
        require(isValidator[msg.sender], "Only validators");
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
     * @dev Required by UUPS pattern, restricted to owner
     * @param newImplementation Address of the new implementation contract
     */
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
    
    /**
     * @notice Add a validator to the whitelist
     * @dev Only the contract owner can add validators
     * @param validator Address of the validator to add
     */
    function addValidator(address validator) external onlyOwner {
        require(validator != address(0), "Invalid validator address");
        require(!isValidator[validator], "Already a validator");
        isValidator[validator] = true;
        emit ValidatorAdded(validator);
    }
    
    /**
     * @notice Remove a validator from the whitelist
     * @dev Only the contract owner can remove validators
     * @param validator Address of the validator to remove
     */
    function removeValidator(address validator) external onlyOwner {
        require(isValidator[validator], "Not a validator");
        isValidator[validator] = false;
        emit ValidatorRemoved(validator);
    }
    
    /**
     * @notice Link a Bittensor hotkey to a GitHub account
     * @dev Emits GitHubLinked event, no storage writes for gas efficiency
     *      Only whitelisted validators can call this function
     * @param hotkey Bittensor SS58 hotkey to link
     * @param mechanismId Mechanism ID (0 = bounty system, 1 = open source, etc.)
     * @param githubUsername GitHub username to link to the hotkey
     */
    function linkGitHub(
        string calldata hotkey,
        uint256 mechanismId,
        string calldata githubUsername
    ) external onlyValidator {
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
