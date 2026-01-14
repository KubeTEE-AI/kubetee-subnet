// SPDX-License-Identifier: MIT
pragma solidity ^0.8.22;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/PausableUpgradeable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/**
 * @title KubeTEEResellerV2
 * @notice SIMPLIFIED on-chain payment system for Resellers on BASE
 * @dev Upgradeable (UUPS pattern), uses Admin/Operator access control model
 * 
 * Access Control:
 * - Admin (owner): Full rights - add/remove operators, upgrade, pause, configure
 * - Operator: Can report usage and settle epochs
 * 
 * Design Philosophy:
 * - USDC only for maximum simplicity
 * - Zero volatility risk for resellers
 * - Wholesale discount: 50% of retail
 * - Epoch-based billing (hourly by default)
 */
contract KubeTEEResellerV2 is
    Initializable,
    OwnableUpgradeable,
    UUPSUpgradeable,
    ReentrancyGuardUpgradeable,
    PausableUpgradeable
{
    using SafeERC20 for IERC20;

    // =========================================================================
    // STATE VARIABLES
    // =========================================================================
    
    /// @notice USDC token on BASE (6 decimals)
    IERC20 public usdc;
    
    /// @notice Minimum deposit amount (default: $10 USDC)
    uint256 public minDeposit;
    
    /// @notice Wholesale rate in basis points (default: 5000 = 50%)
    uint256 public wholesaleRateBps;
    
    /// @notice Treasury address (receives payments)
    address public treasury;
    
    /// @notice Current epoch (incremented each settlement)
    uint256 public currentEpoch;
    
    /// @notice Epoch duration in seconds (default: 1 hour)
    uint256 public epochDuration;
    
    /// @notice Last epoch settlement timestamp
    uint256 public lastSettlement;
    
    /// @notice Operator whitelist
    mapping(address => bool) public isOperator;
    
    /// @notice Operator count
    uint256 public operatorCount;
    
    /// @notice Required confirmations for settlement
    uint256 public requiredConfirmations;

    // =========================================================================
    // RESELLER DATA
    // =========================================================================
    
    struct Reseller {
        address wallet;
        string rancherNamespace;    // e.g., "reseller-acme-corp"
        uint256 registeredAt;
        bool active;
        uint256 balance;            // Current available balance
        uint256 currentUsage;       // Usage this epoch (pending deduction)
        uint256 totalDeposited;     // Lifetime deposits
        uint256 totalSpent;         // Lifetime spending
        string name;                // Business name
    }
    
    /// @notice Reseller data by wallet
    mapping(address => Reseller) public resellers;
    
    /// @notice All reseller addresses (for iteration)
    address[] public resellerList;
    
    /// @notice Rancher namespace to wallet mapping
    mapping(string => address) public namespaceToWallet;

    // =========================================================================
    // EPOCH SETTLEMENT
    // =========================================================================
    
    struct EpochSettlement {
        uint256 totalUsage;
        uint256 confirmations;
        bool finalized;
        mapping(address => bool) confirmedBy;
    }
    
    mapping(uint256 => EpochSettlement) internal settlements;

    // =========================================================================
    // EVENTS
    // =========================================================================
    
    event ResellerRegistered(address indexed wallet, string namespace, string name);
    event ResellerDeactivated(address indexed wallet);
    event ResellerReactivated(address indexed wallet);
    event Deposited(address indexed wallet, uint256 amount, uint256 newBalance);
    event Withdrawn(address indexed wallet, uint256 amount);
    event UsageReported(uint256 indexed epoch, address indexed operator, address indexed reseller, uint256 amount);
    event EpochSettled(uint256 indexed epoch, uint256 totalTransferred, uint256 resellersCharged);
    event OperatorAdded(address indexed operator);
    event OperatorRemoved(address indexed operator);
    event TreasuryUpdated(address indexed newTreasury);
    event ConfigUpdated(string param, uint256 value);

    // =========================================================================
    // ERRORS
    // =========================================================================
    
    error OnlyOperator();
    error InvalidAddress();
    error AlreadyRegistered();
    error NamespaceTaken();
    error EmptyNamespace();
    error NotActiveReseller();
    error BelowMinDeposit();
    error InsufficientBalance();
    error AlreadyOperator();
    error NotOperator();
    error AlreadyReported();
    error EpochNotComplete();
    error AlreadySettled();
    error InvalidConfirmations();

    // =========================================================================
    // MODIFIERS
    // =========================================================================
    
    modifier onlyOperator() {
        if (!isOperator[msg.sender]) revert OnlyOperator();
        _;
    }

    // =========================================================================
    // CONSTRUCTOR & INITIALIZER
    // =========================================================================
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    /**
     * @notice Initialize the contract
     * @param _usdc USDC token address on BASE
     * @param _treasury Address to receive payments
     * @param _epochDuration Seconds per epoch (default: 3600 = 1 hour)
     */
    function initialize(
        address _usdc,
        address _treasury,
        uint256 _epochDuration
    ) public initializer {
        if (_usdc == address(0) || _treasury == address(0)) revert InvalidAddress();
        
        __Ownable_init(msg.sender);
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        __Pausable_init();
        
        usdc = IERC20(_usdc);
        treasury = _treasury;
        epochDuration = _epochDuration > 0 ? _epochDuration : 3600;
        minDeposit = 10 * 1e6;        // $10 USDC
        wholesaleRateBps = 5000;       // 50%
        currentEpoch = 1;
        lastSettlement = block.timestamp;
        requiredConfirmations = 1;
    }
    
    function _authorizeUpgrade(address) internal override onlyOwner {}

    // =========================================================================
    // ADMIN FUNCTIONS
    // =========================================================================
    
    function addOperator(address operator) external onlyOwner {
        if (operator == address(0)) revert InvalidAddress();
        if (isOperator[operator]) revert AlreadyOperator();
        
        isOperator[operator] = true;
        operatorCount++;
        
        // Auto-adjust required confirmations
        if (requiredConfirmations < operatorCount / 2 + 1) {
            requiredConfirmations = operatorCount / 2 + 1;
        }
        
        emit OperatorAdded(operator);
    }
    
    function removeOperator(address operator) external onlyOwner {
        if (!isOperator[operator]) revert NotOperator();
        
        isOperator[operator] = false;
        operatorCount--;
        
        // Adjust confirmations
        if (operatorCount > 0 && requiredConfirmations > operatorCount / 2 + 1) {
            requiredConfirmations = operatorCount / 2 + 1;
        }
        
        emit OperatorRemoved(operator);
    }
    
    function setTreasury(address _treasury) external onlyOwner {
        if (_treasury == address(0)) revert InvalidAddress();
        treasury = _treasury;
        emit TreasuryUpdated(_treasury);
    }
    
    function setRequiredConfirmations(uint256 _required) external onlyOwner {
        if (_required == 0 || _required > operatorCount) revert InvalidConfirmations();
        requiredConfirmations = _required;
        emit ConfigUpdated("requiredConfirmations", _required);
    }
    
    function setMinDeposit(uint256 _minDeposit) external onlyOwner {
        minDeposit = _minDeposit;
        emit ConfigUpdated("minDeposit", _minDeposit);
    }
    
    function setEpochDuration(uint256 _duration) external onlyOwner {
        require(_duration >= 1 hours, "Min 1 hour");
        epochDuration = _duration;
        emit ConfigUpdated("epochDuration", _duration);
    }
    
    function pause() external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }
    
    function deactivateReseller(address wallet) external onlyOwner {
        resellers[wallet].active = false;
        emit ResellerDeactivated(wallet);
    }
    
    function reactivateReseller(address wallet) external onlyOwner {
        require(resellers[wallet].registeredAt > 0, "Not registered");
        resellers[wallet].active = true;
        emit ResellerReactivated(wallet);
    }

    // =========================================================================
    // RESELLER FUNCTIONS
    // =========================================================================
    
    /**
     * @notice Register as a reseller
     * @param namespace Rancher namespace (e.g., "reseller-acme")
     * @param name Business name
     */
    function register(
        string calldata namespace,
        string calldata name
    ) external whenNotPaused {
        if (resellers[msg.sender].registeredAt != 0) revert AlreadyRegistered();
        if (bytes(namespace).length == 0) revert EmptyNamespace();
        if (namespaceToWallet[namespace] != address(0)) revert NamespaceTaken();
        
        resellers[msg.sender] = Reseller({
            wallet: msg.sender,
            rancherNamespace: namespace,
            registeredAt: block.timestamp,
            active: true,
            balance: 0,
            currentUsage: 0,
            totalDeposited: 0,
            totalSpent: 0,
            name: name
        });
        
        namespaceToWallet[namespace] = msg.sender;
        resellerList.push(msg.sender);
        
        emit ResellerRegistered(msg.sender, namespace, name);
    }
    
    /**
     * @notice Deposit USDC to reseller account
     * @param amount Amount in USDC (6 decimals)
     */
    function deposit(uint256 amount) external nonReentrant whenNotPaused {
        if (!resellers[msg.sender].active) revert NotActiveReseller();
        if (amount < minDeposit) revert BelowMinDeposit();
        
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        
        resellers[msg.sender].balance += amount;
        resellers[msg.sender].totalDeposited += amount;
        
        emit Deposited(msg.sender, amount, resellers[msg.sender].balance);
    }
    
    /**
     * @notice Withdraw unused USDC balance
     * @param amount Amount to withdraw
     */
    function withdraw(uint256 amount) external nonReentrant {
        Reseller storage r = resellers[msg.sender];
        if (!r.active) revert NotActiveReseller();
        
        // Must cover current epoch usage
        uint256 available = r.balance > r.currentUsage 
            ? r.balance - r.currentUsage 
            : 0;
        if (amount > available) revert InsufficientBalance();
        
        r.balance -= amount;
        usdc.safeTransfer(msg.sender, amount);
        
        emit Withdrawn(msg.sender, amount);
    }

    // =========================================================================
    // OPERATOR FUNCTIONS
    // =========================================================================
    
    /**
     * @notice Report reseller usage for current epoch
     * @param resellerWallets Array of reseller addresses
     * @param usageAmounts Array of usage amounts (USDC, 6 decimals)
     */
    function reportUsage(
        address[] calldata resellerWallets,
        uint256[] calldata usageAmounts
    ) external onlyOperator whenNotPaused {
        require(resellerWallets.length == usageAmounts.length, "Length mismatch");
        
        EpochSettlement storage s = settlements[currentEpoch];
        if (s.confirmedBy[msg.sender]) revert AlreadyReported();
        
        // Record usage for each reseller
        for (uint256 i = 0; i < resellerWallets.length; i++) {
            address wallet = resellerWallets[i];
            uint256 usage = usageAmounts[i];
            
            if (resellers[wallet].active && usage > 0) {
                resellers[wallet].currentUsage = usage;
                s.totalUsage += usage;
                
                emit UsageReported(currentEpoch, msg.sender, wallet, usage);
            }
        }
        
        // Mark operator as confirmed
        s.confirmedBy[msg.sender] = true;
        s.confirmations++;
        
        // Auto-settle if enough confirmations
        if (s.confirmations >= requiredConfirmations && !s.finalized) {
            _settleEpoch();
        }
    }
    
    /**
     * @notice Force settle current epoch (operator or admin)
     */
    function settleEpoch() external {
        bool isAdmin = msg.sender == owner();
        bool isOp = isOperator[msg.sender];
        bool timeElapsed = block.timestamp >= lastSettlement + epochDuration;
        
        if (!isAdmin && !isOp) revert OnlyOperator();
        if (!isAdmin && !timeElapsed) revert EpochNotComplete();
        
        _settleEpoch();
    }
    
    function _settleEpoch() internal {
        EpochSettlement storage s = settlements[currentEpoch];
        if (s.finalized) revert AlreadySettled();
        
        uint256 totalTransferred = 0;
        uint256 resellersCharged = 0;
        
        // Process each reseller
        for (uint256 i = 0; i < resellerList.length; i++) {
            address wallet = resellerList[i];
            Reseller storage r = resellers[wallet];
            
            if (!r.active || r.currentUsage == 0) continue;
            
            uint256 usage = r.currentUsage;
            
            if (r.balance >= usage) {
                r.balance -= usage;
                r.totalSpent += usage;
                r.currentUsage = 0;
                
                totalTransferred += usage;
                resellersCharged++;
            } else {
                // Insufficient balance - deactivate
                r.active = false;
                emit ResellerDeactivated(wallet);
            }
        }
        
        // Transfer total to treasury
        if (totalTransferred > 0) {
            usdc.safeTransfer(treasury, totalTransferred);
        }
        
        // Finalize
        s.finalized = true;
        currentEpoch++;
        lastSettlement = block.timestamp;
        
        emit EpochSettled(currentEpoch - 1, totalTransferred, resellersCharged);
    }

    // =========================================================================
    // VIEW FUNCTIONS
    // =========================================================================
    
    function getResellerInfo(address wallet) external view returns (
        string memory namespace,
        string memory name,
        bool active,
        uint256 balance,
        uint256 currentUsage,
        uint256 available,
        uint256 totalSpent
    ) {
        Reseller storage r = resellers[wallet];
        return (
            r.rancherNamespace,
            r.name,
            r.active,
            r.balance,
            r.currentUsage,
            r.balance > r.currentUsage ? r.balance - r.currentUsage : 0,
            r.totalSpent
        );
    }
    
    function getStats() external view returns (
        uint256 totalResellers,
        uint256 activeResellers,
        uint256 _currentEpoch,
        uint256 contractBalance,
        uint256 _operatorCount
    ) {
        uint256 active = 0;
        for (uint256 i = 0; i < resellerList.length; i++) {
            if (resellers[resellerList[i]].active) active++;
        }
        
        return (
            resellerList.length,
            active,
            currentEpoch,
            usdc.balanceOf(address(this)),
            operatorCount
        );
    }
    
    function getAllResellers() external view returns (address[] memory) {
        return resellerList;
    }
    
    function isReseller(address wallet) external view returns (bool) {
        return resellers[wallet].registeredAt > 0 && resellers[wallet].active;
    }
    
    function getSettlementInfo(uint256 epoch) external view returns (
        uint256 totalUsage,
        uint256 confirmations,
        bool finalized
    ) {
        EpochSettlement storage s = settlements[epoch];
        return (s.totalUsage, s.confirmations, s.finalized);
    }
    
    function hasOperatorConfirmed(uint256 epoch, address operator) external view returns (bool) {
        return settlements[epoch].confirmedBy[operator];
    }
}
