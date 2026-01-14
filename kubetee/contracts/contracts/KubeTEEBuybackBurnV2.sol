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
 * @title KubeTEEBuybackBurnV2
 * @notice Automated daily USDC → TAO → Alpha → Burn mechanism
 * @dev Upgradeable (UUPS pattern), uses Admin/Operator access control model
 * 
 * Access Control:
 * - Admin (owner): Full rights - configure, emergency withdraw, upgrade
 * - Operator: Can trigger manual buyback/bridge operations
 * 
 * Tokenomics Mechanism:
 * Convert reseller USDC revenue to TAO, then to subnet Alpha token, then BURN.
 * This creates deflationary pressure on Alpha, rewarding long-term holders.
 * 
 * Daily Flow:
 * 1. USDC accumulates from KubeTEEReseller payments
 * 2. Swap USDC → wTAO (on BASE via Uniswap/Aerodrome)
 * 3. Bridge wTAO → Native TAO (via bridge)
 * 4. Swap TAO → Alpha (on Bittensor via subnet AMM)
 * 5. BURN Alpha
 * 
 * Automation:
 * - Chainlink Automation (Keepers) triggers daily
 * - Fallback: Manual trigger by operators
 */

// Chainlink Automation interface
interface AutomationCompatibleInterface {
    function checkUpkeep(bytes calldata checkData) external returns (bool upkeepNeeded, bytes memory performData);
    function performUpkeep(bytes calldata performData) external;
}

// Uniswap V3 Router interface (simplified)
interface ISwapRouter {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }
    
    function exactInputSingle(ExactInputSingleParams calldata params) external payable returns (uint256 amountOut);
}

// wTAO Bridge interface (simplified)
interface IWTAOBridge {
    function bridgeToBittensor(uint256 amount, string calldata bittensorAddress) external;
}

contract KubeTEEBuybackBurnV2 is
    Initializable,
    OwnableUpgradeable,
    UUPSUpgradeable,
    ReentrancyGuardUpgradeable,
    PausableUpgradeable,
    AutomationCompatibleInterface
{
    using SafeERC20 for IERC20;

    // =========================================================================
    // STATE VARIABLES
    // =========================================================================
    
    /// @notice USDC token on BASE
    IERC20 public usdc;
    
    /// @notice wTAO token on BASE
    IERC20 public wtao;
    
    /// @notice Uniswap V3 Router on BASE
    ISwapRouter public swapRouter;
    
    /// @notice wTAO Bridge contract
    IWTAOBridge public wtaoBridge;
    
    /// @notice Bittensor address to receive TAO for Alpha swap
    string public bittensorSwapAddress;
    
    /// @notice Bittensor burn address (Substrate null address)
    string public constant BURN_ADDRESS = "5C4hrfjw9DjXZTzV3MwzrrAr9P1MJhSrvWGWqi1eSuyUpnhM";
    
    /// @notice Operator whitelist
    mapping(address => bool) public isOperator;
    
    /// @notice Minimum USDC to trigger buyback
    uint256 public minBuybackAmount;
    
    /// @notice Maximum slippage in basis points (200 = 2%)
    uint256 public maxSlippageBps;
    
    /// @notice Interval between buybacks (in seconds)
    uint256 public buybackInterval;
    
    /// @notice Last buyback timestamp
    uint256 public lastBuybackTime;
    
    /// @notice Total USDC converted (lifetime)
    uint256 public totalUsdcConverted;
    
    /// @notice Total wTAO acquired (lifetime)
    uint256 public totalWtaoAcquired;
    
    /// @notice Uniswap pool fee tier (3000 = 0.3%)
    uint24 public poolFee;

    // =========================================================================
    // EVENTS
    // =========================================================================
    
    event BuybackExecuted(
        uint256 indexed timestamp,
        uint256 usdcAmount,
        uint256 wtaoAmount
    );
    
    event BridgeInitiated(
        uint256 indexed timestamp,
        uint256 wtaoAmount,
        string bittensorAddress
    );
    
    event OperatorAdded(address indexed operator);
    event OperatorRemoved(address indexed operator);
    event ConfigUpdated(string param, uint256 value);
    event AddressUpdated(string param, address value);

    // =========================================================================
    // ERRORS
    // =========================================================================
    
    error OnlyOperator();
    error InvalidAddress();
    error AlreadyOperator();
    error NotOperator();
    error InsufficientUSDC();
    error TooSoon();
    error WtaoNotConfigured();
    error BridgeNotConfigured();
    error NoWtaoToBridge();
    error MaxSlippageExceeded();
    error MinIntervalNotMet();

    // =========================================================================
    // MODIFIERS
    // =========================================================================
    
    modifier onlyOperator() {
        if (!isOperator[msg.sender] && msg.sender != owner()) revert OnlyOperator();
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
     * @notice Initialize the buyback contract
     * @param _usdc USDC address on BASE
     * @param _swapRouter Uniswap V3 Router address
     * @param _bittensorSwapAddress Bittensor address for TAO → Alpha swap
     */
    function initialize(
        address _usdc,
        address _swapRouter,
        string memory _bittensorSwapAddress
    ) public initializer {
        if (_usdc == address(0) || _swapRouter == address(0)) revert InvalidAddress();
        
        __Ownable_init(msg.sender);
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        __Pausable_init();
        
        usdc = IERC20(_usdc);
        swapRouter = ISwapRouter(_swapRouter);
        bittensorSwapAddress = _bittensorSwapAddress;
        
        minBuybackAmount = 100 * 1e6;   // $100 USDC
        maxSlippageBps = 200;            // 2%
        buybackInterval = 24 hours;
        poolFee = 3000;                  // 0.3%
        lastBuybackTime = block.timestamp;
    }
    
    function _authorizeUpgrade(address) internal override onlyOwner {}

    // =========================================================================
    // CHAINLINK AUTOMATION
    // =========================================================================
    
    /**
     * @notice Chainlink Automation check - determines if buyback should run
     * @return upkeepNeeded True if buyback conditions met
     * @return performData Empty (not used)
     */
    function checkUpkeep(bytes calldata) 
        external 
        view 
        override 
        returns (bool upkeepNeeded, bytes memory performData) 
    {
        uint256 usdcBalance = usdc.balanceOf(address(this));
        bool hasEnoughUsdc = usdcBalance >= minBuybackAmount;
        bool intervalPassed = block.timestamp >= lastBuybackTime + buybackInterval;
        bool notPaused = !paused();
        
        upkeepNeeded = hasEnoughUsdc && intervalPassed && notPaused;
        performData = "";
    }
    
    /**
     * @notice Chainlink Automation perform - executes the buyback
     * @dev Called by Chainlink nodes when checkUpkeep returns true
     */
    function performUpkeep(bytes calldata) external override {
        // Re-validate conditions
        uint256 usdcBalance = usdc.balanceOf(address(this));
        if (usdcBalance < minBuybackAmount) revert InsufficientUSDC();
        if (block.timestamp < lastBuybackTime + buybackInterval) revert TooSoon();
        if (paused()) revert("Paused");
        
        _executeBuyback(usdcBalance);
    }

    // =========================================================================
    // ADMIN FUNCTIONS
    // =========================================================================
    
    function addOperator(address operator) external onlyOwner {
        if (operator == address(0)) revert InvalidAddress();
        if (isOperator[operator]) revert AlreadyOperator();
        isOperator[operator] = true;
        emit OperatorAdded(operator);
    }
    
    function removeOperator(address operator) external onlyOwner {
        if (!isOperator[operator]) revert NotOperator();
        isOperator[operator] = false;
        emit OperatorRemoved(operator);
    }
    
    function setUsdc(address _usdc) external onlyOwner {
        if (_usdc == address(0)) revert InvalidAddress();
        usdc = IERC20(_usdc);
        emit AddressUpdated("usdc", _usdc);
    }
    
    function setWtao(address _wtao) external onlyOwner {
        wtao = IERC20(_wtao);
        emit AddressUpdated("wtao", _wtao);
    }
    
    function setWtaoBridge(address _bridge) external onlyOwner {
        wtaoBridge = IWTAOBridge(_bridge);
        emit AddressUpdated("wtaoBridge", _bridge);
    }
    
    function setSwapRouter(address _router) external onlyOwner {
        if (_router == address(0)) revert InvalidAddress();
        swapRouter = ISwapRouter(_router);
        emit AddressUpdated("swapRouter", _router);
    }
    
    function setBittensorSwapAddress(string calldata _address) external onlyOwner {
        bittensorSwapAddress = _address;
    }
    
    function setMinBuybackAmount(uint256 _amount) external onlyOwner {
        minBuybackAmount = _amount;
        emit ConfigUpdated("minBuybackAmount", _amount);
    }
    
    function setMaxSlippageBps(uint256 _slippage) external onlyOwner {
        if (_slippage > 500) revert MaxSlippageExceeded();
        maxSlippageBps = _slippage;
        emit ConfigUpdated("maxSlippageBps", _slippage);
    }
    
    function setBuybackInterval(uint256 _interval) external onlyOwner {
        if (_interval < 1 hours) revert MinIntervalNotMet();
        buybackInterval = _interval;
        emit ConfigUpdated("buybackInterval", _interval);
    }
    
    function setPoolFee(uint24 _fee) external onlyOwner {
        poolFee = _fee;
    }
    
    function pause() external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }
    
    /**
     * @notice Emergency withdraw (owner only)
     * @param token Token to withdraw (address(0) for ETH)
     * @param amount Amount to withdraw
     */
    function emergencyWithdraw(address token, uint256 amount) external onlyOwner {
        if (token == address(0)) {
            payable(owner()).transfer(amount);
        } else {
            IERC20(token).safeTransfer(owner(), amount);
        }
    }

    // =========================================================================
    // OPERATOR FUNCTIONS
    // =========================================================================
    
    /**
     * @notice Manual buyback trigger
     * @dev Available to operators when Chainlink Automation unavailable
     */
    function manualBuyback() external onlyOperator whenNotPaused {
        uint256 usdcBalance = usdc.balanceOf(address(this));
        if (usdcBalance < minBuybackAmount) revert InsufficientUSDC();
        
        _executeBuyback(usdcBalance);
    }
    
    /**
     * @notice Manual bridge trigger
     * @dev Bridge any wTAO sitting in contract
     */
    function manualBridge() external onlyOperator {
        if (address(wtaoBridge) == address(0)) revert BridgeNotConfigured();
        uint256 wtaoBalance = wtao.balanceOf(address(this));
        if (wtaoBalance == 0) revert NoWtaoToBridge();
        
        _bridgeToBittensor(wtaoBalance);
    }
    
    /**
     * @notice Deposit USDC for next buyback cycle
     * @param amount Amount of USDC to deposit
     */
    function depositUsdc(uint256 amount) external {
        usdc.safeTransferFrom(msg.sender, address(this), amount);
    }

    // =========================================================================
    // INTERNAL FUNCTIONS
    // =========================================================================
    
    /**
     * @notice Execute buyback - swap USDC to wTAO
     * @param usdcAmount Amount of USDC to swap
     */
    function _executeBuyback(uint256 usdcAmount) internal nonReentrant {
        if (address(wtao) == address(0)) revert WtaoNotConfigured();
        
        // Calculate minimum output with slippage protection
        uint256 expectedOutput = _getExpectedWtaoOutput(usdcAmount);
        uint256 minOutput = expectedOutput * (10000 - maxSlippageBps) / 10000;
        
        // Approve router
        usdc.safeIncreaseAllowance(address(swapRouter), usdcAmount);
        
        // Execute swap
        uint256 wtaoReceived = swapRouter.exactInputSingle(
            ISwapRouter.ExactInputSingleParams({
                tokenIn: address(usdc),
                tokenOut: address(wtao),
                fee: poolFee,
                recipient: address(this),
                deadline: block.timestamp + 300, // 5 minutes
                amountIn: usdcAmount,
                amountOutMinimum: minOutput,
                sqrtPriceLimitX96: 0
            })
        );
        
        // Update state
        lastBuybackTime = block.timestamp;
        totalUsdcConverted += usdcAmount;
        totalWtaoAcquired += wtaoReceived;
        
        emit BuybackExecuted(block.timestamp, usdcAmount, wtaoReceived);
        
        // Auto-bridge if bridge is configured
        if (address(wtaoBridge) != address(0)) {
            _bridgeToBittensor(wtaoReceived);
        }
    }
    
    /**
     * @notice Bridge wTAO to Bittensor
     * @param amount Amount of wTAO to bridge
     */
    function _bridgeToBittensor(uint256 amount) internal {
        wtao.safeIncreaseAllowance(address(wtaoBridge), amount);
        wtaoBridge.bridgeToBittensor(amount, bittensorSwapAddress);
        
        emit BridgeInitiated(block.timestamp, amount, bittensorSwapAddress);
    }
    
    /**
     * @notice Get expected wTAO output for given USDC amount
     * @dev In production, use Uniswap Quoter or oracle
     */
    function _getExpectedWtaoOutput(uint256 usdcAmount) internal pure returns (uint256) {
        // Placeholder: In production, query Uniswap quoter
        // Assuming TAO price ~$200, this gives rough estimate
        // 1 USDC = 0.005 TAO (at $200/TAO)
        return usdcAmount * 5 / 1000;
    }

    // =========================================================================
    // VIEW FUNCTIONS
    // =========================================================================
    
    /**
     * @notice Get current state
     */
    function getState() external view returns (
        uint256 usdcBalance,
        uint256 wtaoBalance,
        uint256 timeSinceLastBuyback,
        uint256 timeUntilNextBuyback,
        bool canExecute
    ) {
        usdcBalance = usdc.balanceOf(address(this));
        wtaoBalance = address(wtao) != address(0) ? wtao.balanceOf(address(this)) : 0;
        timeSinceLastBuyback = block.timestamp - lastBuybackTime;
        
        if (block.timestamp < lastBuybackTime + buybackInterval) {
            timeUntilNextBuyback = (lastBuybackTime + buybackInterval) - block.timestamp;
        } else {
            timeUntilNextBuyback = 0;
        }
        
        canExecute = usdcBalance >= minBuybackAmount && 
                     timeUntilNextBuyback == 0 && 
                     !paused();
    }
    
    /**
     * @notice Get lifetime statistics
     */
    function getStats() external view returns (
        uint256 _totalUsdcConverted,
        uint256 _totalWtaoAcquired,
        uint256 _lastBuybackTime,
        uint256 _buybackCount
    ) {
        _totalUsdcConverted = totalUsdcConverted;
        _totalWtaoAcquired = totalWtaoAcquired;
        _lastBuybackTime = lastBuybackTime;
        _buybackCount = _totalUsdcConverted > 0 
            ? _totalUsdcConverted / minBuybackAmount 
            : 0;
    }
    
    /**
     * @notice Get contract configuration
     */
    function getConfig() external view returns (
        address usdcAddress,
        address wtaoAddress,
        address swapRouterAddress,
        address wtaoBridgeAddress,
        uint256 _minBuybackAmount,
        uint256 _maxSlippageBps,
        uint256 _buybackInterval,
        uint24 _poolFee
    ) {
        return (
            address(usdc),
            address(wtao),
            address(swapRouter),
            address(wtaoBridge),
            minBuybackAmount,
            maxSlippageBps,
            buybackInterval,
            poolFee
        );
    }
    
    receive() external payable {}
}
