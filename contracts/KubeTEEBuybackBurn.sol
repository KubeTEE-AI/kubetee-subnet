// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title KubeTEE Buyback & Burn Contract
 * @author KubeTEE AI
 * @notice Automated daily USDC → TAO → Alpha → Burn mechanism
 * @dev Deployed on BASE L2, uses Chainlink Automation for scheduling
 * 
 * ═══════════════════════════════════════════════════════════════════════════
 *                         TOKENOMICS MECHANISM
 * ═══════════════════════════════════════════════════════════════════════════
 * 
 * PURPOSE:
 * Convert reseller USDC revenue to TAO, then to subnet Alpha token, then BURN.
 * This creates deflationary pressure on Alpha, rewarding long-term holders.
 * 
 * DAILY FLOW:
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │ STEP 1: Collect USDC                                                    │
 * │ ─────────────────────────────────────────────────────────────────────── │
 * │ USDC accumulates from KubeTEEReseller.sol payments                      │
 * │ KubeTEE Owner transfers USDC to this contract daily                     │
 * └─────────────────────────────────────────────────────────────────────────┘
 *                                    │
 *                                    ▼
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │ STEP 2: Swap USDC → wTAO (on BASE via Uniswap/Aerodrome)               │
 * │ ─────────────────────────────────────────────────────────────────────── │
 * │ Use DEX aggregator (1inch, 0x, or direct Uniswap)                       │
 * │ Slippage protection: max 2%                                             │
 * └─────────────────────────────────────────────────────────────────────────┘
 *                                    │
 *                                    ▼
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │ STEP 3: Bridge wTAO → Native TAO (via bridge)                          │
 * │ ─────────────────────────────────────────────────────────────────────── │
 * │ Initiate bridge transfer to Bittensor network                           │
 * │ (Off-chain bot monitors and completes on Bittensor side)               │
 * └─────────────────────────────────────────────────────────────────────────┘
 *                                    │
 *                                    ▼
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │ STEP 4: Swap TAO → Alpha (on Bittensor via subnet AMM)                 │
 * │ ─────────────────────────────────────────────────────────────────────── │
 * │ Use native Bittensor subnet liquidity pool                              │
 * │ (Executed by off-chain bot on Bittensor)                               │
 * └─────────────────────────────────────────────────────────────────────────┘
 *                                    │
 *                                    ▼
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │ STEP 5: BURN Alpha                                                      │
 * │ ─────────────────────────────────────────────────────────────────────── │
 * │ Send Alpha to burn address: 5C4hrfjw9DjXZTzV3MwzrrAr9P1MJhSrvWGWqi1eSuyUpnhM │
 * │ (Polkadot/Substrate null address)                                       │
 * └─────────────────────────────────────────────────────────────────────────┘
 * 
 * AUTOMATION:
 * - Chainlink Automation (Keepers) triggers daily at 00:00 UTC
 * - Fallback: Manual trigger by owner
 * 
 * ═══════════════════════════════════════════════════════════════════════════
 */

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

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

contract KubeTEEBuybackBurn is Ownable, ReentrancyGuard, Pausable, AutomationCompatibleInterface {
    using SafeERC20 for IERC20;

    // =========================================================================
    // CONSTANTS & STATE
    // =========================================================================
    
    /// @notice USDC token on BASE
    IERC20 public immutable usdc;
    
    /// @notice wTAO token on BASE (if available, otherwise use bridge)
    IERC20 public wtao;
    
    /// @notice Uniswap V3 Router on BASE
    ISwapRouter public swapRouter;
    
    /// @notice wTAO Bridge contract
    IWTAOBridge public wtaoBridge;
    
    /// @notice Bittensor address to receive TAO for Alpha swap
    string public bittensorSwapAddress;
    
    /// @notice Bittensor burn address (Substrate null address)
    string public constant BURN_ADDRESS = "5C4hrfjw9DjXZTzV3MwzrrAr9P1MJhSrvWGWqi1eSuyUpnhM";
    
    /// @notice Minimum USDC to trigger buyback ($100)
    uint256 public minBuybackAmount = 100 * 1e6;
    
    /// @notice Maximum slippage in basis points (200 = 2%)
    uint256 public maxSlippageBps = 200;
    
    /// @notice Interval between buybacks (24 hours)
    uint256 public buybackInterval = 24 hours;
    
    /// @notice Last buyback timestamp
    uint256 public lastBuybackTime;
    
    /// @notice Total USDC converted (lifetime)
    uint256 public totalUsdcConverted;
    
    /// @notice Total wTAO acquired (lifetime)
    uint256 public totalWtaoAcquired;
    
    /// @notice Uniswap pool fee tier (3000 = 0.3%)
    uint24 public poolFee = 3000;

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
    
    event ConfigUpdated(string param, uint256 value);
    event AddressUpdated(string param, address value);

    // =========================================================================
    // CONSTRUCTOR
    // =========================================================================
    
    /**
     * @notice Deploy buyback contract
     * @param _usdc USDC address on BASE
     * @param _swapRouter Uniswap V3 Router address
     * @param _bittensorSwapAddress Bittensor address for TAO → Alpha swap
     */
    constructor(
        address _usdc,
        address _swapRouter,
        string memory _bittensorSwapAddress
    ) Ownable(msg.sender) {
        require(_usdc != address(0), "Invalid USDC");
        require(_swapRouter != address(0), "Invalid router");
        
        usdc = IERC20(_usdc);
        swapRouter = ISwapRouter(_swapRouter);
        bittensorSwapAddress = _bittensorSwapAddress;
        
        lastBuybackTime = block.timestamp;
    }

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
        require(usdcBalance >= minBuybackAmount, "Insufficient USDC");
        require(block.timestamp >= lastBuybackTime + buybackInterval, "Too soon");
        require(!paused(), "Paused");
        
        _executeBuyback(usdcBalance);
    }

    // =========================================================================
    // BUYBACK EXECUTION
    // =========================================================================
    
    /**
     * @notice Execute buyback - swap USDC to wTAO
     * @param usdcAmount Amount of USDC to swap
     */
    function _executeBuyback(uint256 usdcAmount) internal nonReentrant {
        require(address(wtao) != address(0), "wTAO not configured");
        
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
            _bridgeTooBittensor(wtaoReceived);
        }
    }
    
    /**
     * @notice Bridge wTAO to Bittensor
     * @param amount Amount of wTAO to bridge
     */
    function _bridgeTooBittensor(uint256 amount) internal {
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
        return usdcAmount * 5 / 1000; // Simplified, use quoter in production
    }

    // =========================================================================
    // MANUAL TRIGGERS
    // =========================================================================
    
    /**
     * @notice Manual buyback trigger (owner only)
     * @dev Use when Chainlink Automation unavailable
     */
    function manualBuyback() external onlyOwner whenNotPaused {
        uint256 usdcBalance = usdc.balanceOf(address(this));
        require(usdcBalance >= minBuybackAmount, "Insufficient USDC");
        
        _executeBuyback(usdcBalance);
    }
    
    /**
     * @notice Manual bridge trigger (owner only)
     * @dev Bridge any wTAO sitting in contract
     */
    function manualBridge() external onlyOwner {
        require(address(wtaoBridge) != address(0), "Bridge not configured");
        uint256 wtaoBalance = wtao.balanceOf(address(this));
        require(wtaoBalance > 0, "No wTAO to bridge");
        
        _bridgeTooBittensor(wtaoBalance);
    }
    
    /**
     * @notice Deposit USDC for next buyback cycle
     * @param amount Amount of USDC to deposit
     */
    function depositUsdc(uint256 amount) external {
        usdc.safeTransferFrom(msg.sender, address(this), amount);
    }

    // =========================================================================
    // CONFIGURATION
    // =========================================================================
    
    function setWtao(address _wtao) external onlyOwner {
        wtao = IERC20(_wtao);
        emit AddressUpdated("wtao", _wtao);
    }
    
    function setWtaoBridge(address _bridge) external onlyOwner {
        wtaoBridge = IWTAOBridge(_bridge);
        emit AddressUpdated("wtaoBridge", _bridge);
    }
    
    function setSwapRouter(address _router) external onlyOwner {
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
        require(_slippage <= 500, "Max 5% slippage");
        maxSlippageBps = _slippage;
        emit ConfigUpdated("maxSlippageBps", _slippage);
    }
    
    function setBuybackInterval(uint256 _interval) external onlyOwner {
        require(_interval >= 1 hours, "Min 1 hour");
        buybackInterval = _interval;
        emit ConfigUpdated("buybackInterval", _interval);
    }
    
    function setPoolFee(uint24 _fee) external onlyOwner {
        poolFee = _fee;
    }
    
    function pause() external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }

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
        // Approximate buyback count
        _buybackCount = _totalUsdcConverted > 0 
            ? _totalUsdcConverted / minBuybackAmount 
            : 0;
    }

    // =========================================================================
    // EMERGENCY
    // =========================================================================
    
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
    
    receive() external payable {}
}

