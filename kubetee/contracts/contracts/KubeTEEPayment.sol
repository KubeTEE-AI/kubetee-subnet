// SPDX-License-Identifier: MIT
pragma solidity ^0.8.22;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/**
 * @title KubeTEEPayment
 * @notice Pull-based payment contract for KubeTEE AI platform on BASE L2
 * @dev Upgradeable (UUPS pattern), uses Admin/Operator access control model
 * 
 * Access Control:
 * - Admin (owner): Full rights - add/remove operators, upgrade contract, configure settings
 * - Operator: Can register users and process payments
 * 
 * Key features:
 * - Pull-based billing: Contract pulls USDC from user wallet (requires approval)
 * - Affiliate system: 50% revenue share with 2-user minimum requirement
 * - Graceful failure: Emits events on insufficient balance instead of reverting
 * - UUPS Upgradeability: Safe proxy pattern for future upgrades
 */
contract KubeTEEPayment is
    Initializable,
    OwnableUpgradeable,
    UUPSUpgradeable,
    ReentrancyGuardUpgradeable
{
    // ============ State Variables ============
    
    /// @notice USDC token address (configurable for upgrades)
    IERC20 public usdc;
    
    /// @notice Operator whitelist - operators can process payments
    mapping(address => bool) public isOperator;
    
    /// @notice Minimum paid users required for affiliate to receive commissions
    uint256 public minPaidUsers;
    
    /// @notice Commission rate in basis points (5000 = 50%)
    uint256 public commissionBps;
    
    /// @notice Treasury address to receive KubeTEE's share
    address public treasury;
    
    /// @notice User → Affiliate mapping (set once at registration, immutable)
    mapping(address => address) public userAffiliate;
    
    /// @notice User → Is registered
    mapping(address => bool) public isRegistered;
    
    /// @notice Affiliate → Count of users who have made at least one payment
    mapping(address => uint256) public affiliatePaidUsers;
    
    /// @notice Affiliate → Pending commissions (held until min users reached)
    mapping(address => uint256) public pendingCommissions;
    
    /// @notice User → Has made first payment (counts toward affiliate's paid users)
    mapping(address => bool) public userHasPaid;
    
    // ============ Events ============
    
    event UserRegistered(address indexed user, address indexed affiliate);
    event PaymentProcessed(
        address indexed user, 
        uint256 amount, 
        address indexed affiliate, 
        uint256 commission
    );
    event CommissionsReleased(address indexed affiliate, uint256 amount);
    event InsufficientBalance(
        address indexed user, 
        uint256 required, 
        uint256 available
    );
    event OperatorAdded(address indexed operator);
    event OperatorRemoved(address indexed operator);
    event TreasuryUpdated(address indexed newTreasury);
    event ConfigUpdated(string param, uint256 value);
    
    // ============ Errors ============
    
    error OnlyOperator();
    error InvalidAddress();
    error AlreadyRegistered();
    error CannotSelfRefer();
    error UserNotRegistered();
    error AmountMustBePositive();
    error AlreadyOperator();
    error NotOperator();
    
    // ============ Modifiers ============
    
    /// @notice Restricts function access to operators only
    modifier onlyOperator() {
        if (!isOperator[msg.sender]) revert OnlyOperator();
        _;
    }
    
    // ============ Constructor ============
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    // ============ Initializer ============
    
    /**
     * @notice Initializes the contract (replaces constructor for upgradeable contracts)
     * @param _usdc Address of USDC token on BASE L2
     * @param _treasury Address to receive KubeTEE's share of payments
     */
    function initialize(address _usdc, address _treasury) public initializer {
        if (_usdc == address(0) || _treasury == address(0)) revert InvalidAddress();
        
        __Ownable_init(msg.sender);
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        
        usdc = IERC20(_usdc);
        treasury = _treasury;
        minPaidUsers = 2;       // Default: 2 paid users required
        commissionBps = 5000;   // Default: 50% commission
    }
    
    // ============ Upgrade Authorization ============
    
    /**
     * @notice Authorizes contract upgrades
     * @dev Required by UUPS pattern, restricted to admin (owner)
     * @param newImplementation Address of the new implementation contract
     */
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
    
    // ============ Admin Functions ============
    
    /**
     * @notice Add an operator
     * @dev Only the admin (owner) can add operators
     * @param operator Address of the operator to add
     */
    function addOperator(address operator) external onlyOwner {
        if (operator == address(0)) revert InvalidAddress();
        if (isOperator[operator]) revert AlreadyOperator();
        isOperator[operator] = true;
        emit OperatorAdded(operator);
    }
    
    /**
     * @notice Remove an operator
     * @dev Only the admin (owner) can remove operators
     * @param operator Address of the operator to remove
     */
    function removeOperator(address operator) external onlyOwner {
        if (!isOperator[operator]) revert NotOperator();
        isOperator[operator] = false;
        emit OperatorRemoved(operator);
    }
    
    /**
     * @notice Update treasury address
     * @param _treasury New treasury address
     */
    function setTreasury(address _treasury) external onlyOwner {
        if (_treasury == address(0)) revert InvalidAddress();
        treasury = _treasury;
        emit TreasuryUpdated(_treasury);
    }
    
    /**
     * @notice Update USDC token address (for migrations)
     * @param _usdc New USDC address
     */
    function setUsdc(address _usdc) external onlyOwner {
        if (_usdc == address(0)) revert InvalidAddress();
        usdc = IERC20(_usdc);
    }
    
    /**
     * @notice Update minimum paid users for affiliate qualification
     * @param _minPaidUsers New minimum
     */
    function setMinPaidUsers(uint256 _minPaidUsers) external onlyOwner {
        minPaidUsers = _minPaidUsers;
        emit ConfigUpdated("minPaidUsers", _minPaidUsers);
    }
    
    /**
     * @notice Update commission rate
     * @param _commissionBps New commission in basis points
     */
    function setCommissionBps(uint256 _commissionBps) external onlyOwner {
        require(_commissionBps <= 10000, "Max 100%");
        commissionBps = _commissionBps;
        emit ConfigUpdated("commissionBps", _commissionBps);
    }
    
    // ============ Operator Functions ============
    
    /**
     * @notice Register a new user with optional affiliate attribution
     * @dev Called by operators (e.g., kubeteectl CLI backend)
     * @param user Address of the user being registered
     * @param affiliate Address of the affiliate (address(0) if none)
     */
    function registerUser(address user, address affiliate) external onlyOperator {
        if (isRegistered[user]) revert AlreadyRegistered();
        if (user == affiliate) revert CannotSelfRefer();
        
        isRegistered[user] = true;
        if (affiliate != address(0)) {
            userAffiliate[user] = affiliate;
        }
        
        emit UserRegistered(user, affiliate);
    }
    
    /**
     * @notice Process hourly payment by pulling USDC from user wallet
     * @dev Called by operators (billing system)
     * @param user Address of the user being billed
     * @param amount Amount of USDC to charge (in wei, 6 decimals)
     * 
     * Payment flow:
     * 1. Check user balance and allowance
     * 2. Pull USDC from user wallet
     * 3. Track first payment for affiliate qualification
     * 4. Split payment: commission to affiliate (if qualified), remainder to treasury
     * 5. Hold commission if affiliate not yet qualified
     */
    function processPayment(address user, uint256 amount) external onlyOperator nonReentrant {
        if (!isRegistered[user]) revert UserNotRegistered();
        if (amount == 0) revert AmountMustBePositive();
        
        // Check user has sufficient balance and allowance
        uint256 userBalance = usdc.balanceOf(user);
        uint256 userAllowance = usdc.allowance(user, address(this));
        
        if (userBalance < amount || userAllowance < amount) {
            // Emit event instead of reverting - billing job handles suspension
            emit InsufficientBalance(
                user, 
                amount, 
                userBalance < userAllowance ? userBalance : userAllowance
            );
            return;
        }
        
        // Pull USDC from user wallet
        require(usdc.transferFrom(user, address(this), amount), "Transfer failed");
        
        address affiliate = userAffiliate[user];
        
        // First payment → increment affiliate's paid user count
        if (!userHasPaid[user] && affiliate != address(0)) {
            userHasPaid[user] = true;
            affiliatePaidUsers[affiliate]++;
            
            // Release pending commissions if affiliate just reached minimum
            if (affiliatePaidUsers[affiliate] == minPaidUsers) {
                _releasePending(affiliate);
            }
        }
        
        // Calculate and distribute payment
        if (affiliate != address(0)) {
            uint256 commission = (amount * commissionBps) / 10000;
            uint256 treasuryShare = amount - commission;
            
            if (affiliatePaidUsers[affiliate] >= minPaidUsers) {
                // Affiliate qualified → pay commission immediately
                usdc.transfer(affiliate, commission);
                emit PaymentProcessed(user, amount, affiliate, commission);
            } else {
                // Affiliate not yet qualified → hold commission in contract
                pendingCommissions[affiliate] += commission;
                emit PaymentProcessed(user, amount, affiliate, 0);
            }
            usdc.transfer(treasury, treasuryShare);
        } else {
            // No affiliate → 100% to treasury
            usdc.transfer(treasury, amount);
            emit PaymentProcessed(user, amount, address(0), 0);
        }
    }
    
    // ============ Internal Functions ============
    
    /**
     * @notice Release pending commissions to affiliate
     * @param affiliate Address of the affiliate
     */
    function _releasePending(address affiliate) internal {
        uint256 pending = pendingCommissions[affiliate];
        if (pending > 0) {
            pendingCommissions[affiliate] = 0;
            usdc.transfer(affiliate, pending);
            emit CommissionsReleased(affiliate, pending);
        }
    }
    
    // ============ View Functions ============
    
    /**
     * @notice Get user status including balance and allowance
     * @param user Address of the user
     * @return registered Whether user is registered
     * @return affiliate Address of user's affiliate (address(0) if none)
     * @return hasPaid Whether user has made at least one payment
     * @return balance User's USDC balance
     * @return allowance User's USDC allowance for this contract
     */
    function getUserStatus(address user) external view returns (
        bool registered,
        address affiliate,
        bool hasPaid,
        uint256 balance,
        uint256 allowance
    ) {
        return (
            isRegistered[user],
            userAffiliate[user],
            userHasPaid[user],
            usdc.balanceOf(user),
            usdc.allowance(user, address(this))
        );
    }
    
    /**
     * @notice Get affiliate status
     * @param affiliate Address of the affiliate
     * @return paidUsers Number of users who have made at least one payment
     * @return pending Amount of commissions held (released when qualified)
     * @return qualified Whether affiliate has reached minimum paid users
     */
    function getAffiliateStatus(address affiliate) external view returns (
        uint256 paidUsers,
        uint256 pending,
        bool qualified
    ) {
        return (
            affiliatePaidUsers[affiliate],
            pendingCommissions[affiliate],
            affiliatePaidUsers[affiliate] >= minPaidUsers
        );
    }
    
    /**
     * @notice Get contract configuration
     */
    function getConfig() external view returns (
        address usdcAddress,
        address treasuryAddress,
        uint256 _minPaidUsers,
        uint256 _commissionBps
    ) {
        return (
            address(usdc),
            treasury,
            minPaidUsers,
            commissionBps
        );
    }
}
