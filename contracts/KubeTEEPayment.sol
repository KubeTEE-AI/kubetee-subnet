// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title KubeTEEPayment
 * @notice Pull-based payment contract for KubeTEE AI platform on BASE L2
 * @dev Handles user registration, affiliate tracking, and hourly billing
 * 
 * Key features:
 * - Pull-based billing: Contract pulls USDC from user wallet (requires approval)
 * - Affiliate system: 50% revenue share with 2-user minimum requirement
 * - Graceful failure: Emits events on insufficient balance instead of reverting
 */
contract KubeTEEPayment is Ownable {
    IERC20 public immutable usdc;
    
    /// @notice Minimum paid users required for affiliate to receive commissions
    uint256 public constant MIN_PAID_USERS = 2;
    
    /// @notice Commission rate in basis points (5000 = 50%)
    uint256 public constant COMMISSION_BPS = 5000;
    
    // ============ State Variables ============
    
    /// @notice User → Affiliate mapping (set once at registration, immutable)
    mapping(address => address) public userAffiliate;
    
    /// @notice User → Is registered
    mapping(address => bool) public isRegistered;
    
    /// @notice Affiliate → Count of users who have made at least one payment
    mapping(address => uint256) public affiliatePaidUsers;
    
    /// @notice Affiliate → Pending commissions (held until 2-user minimum reached)
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
    
    // ============ Constructor ============
    
    /**
     * @notice Deploy KubeTEEPayment contract
     * @param _usdc Address of USDC token on BASE L2
     */
    constructor(address _usdc) Ownable(msg.sender) {
        usdc = IERC20(_usdc);
    }
    
    // ============ User Registration ============
    
    /**
     * @notice Register a new user with optional affiliate attribution
     * @dev Called by kubeteectl CLI after user approves USDC spending
     * @param user Address of the user being registered
     * @param affiliate Address of the affiliate (address(0) if none)
     */
    function registerUser(address user, address affiliate) external onlyOwner {
        require(!isRegistered[user], "Already registered");
        require(user != affiliate, "Cannot self-refer");
        
        isRegistered[user] = true;
        if (affiliate != address(0)) {
            userAffiliate[user] = affiliate;
        }
        
        emit UserRegistered(user, affiliate);
    }
    
    // ============ Payment Processing ============
    
    /**
     * @notice Process hourly payment by pulling USDC from user wallet
     * @dev Called by KubeTEE billing system every hour
     * @param user Address of the user being billed
     * @param amount Amount of USDC to charge (in wei, 6 decimals)
     * 
     * Payment flow:
     * 1. Check user balance and allowance
     * 2. Pull USDC from user wallet
     * 3. Track first payment for affiliate qualification
     * 4. Split payment: 50% to affiliate (if qualified), remainder to KubeTEE
     * 5. Hold commission if affiliate not yet qualified (< 2 paid users)
     */
    function processPayment(address user, uint256 amount) external onlyOwner {
        require(isRegistered[user], "User not registered");
        require(amount > 0, "Amount must be > 0");
        
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
            if (affiliatePaidUsers[affiliate] == MIN_PAID_USERS) {
                _releasePending(affiliate);
            }
        }
        
        // Calculate and distribute payment
        if (affiliate != address(0)) {
            uint256 commission = (amount * COMMISSION_BPS) / 10000;
            uint256 kubeteeShare = amount - commission;
            
            if (affiliatePaidUsers[affiliate] >= MIN_PAID_USERS) {
                // Affiliate qualified → pay commission immediately
                usdc.transfer(affiliate, commission);
                emit PaymentProcessed(user, amount, affiliate, commission);
            } else {
                // Affiliate not yet qualified → hold commission in contract
                pendingCommissions[affiliate] += commission;
                emit PaymentProcessed(user, amount, affiliate, 0);
            }
            usdc.transfer(owner(), kubeteeShare);
        } else {
            // No affiliate → 100% to KubeTEE
            usdc.transfer(owner(), amount);
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
     * @return qualified Whether affiliate has reached 2-user minimum
     */
    function getAffiliateStatus(address affiliate) external view returns (
        uint256 paidUsers,
        uint256 pending,
        bool qualified
    ) {
        return (
            affiliatePaidUsers[affiliate],
            pendingCommissions[affiliate],
            affiliatePaidUsers[affiliate] >= MIN_PAID_USERS
        );
    }
}
