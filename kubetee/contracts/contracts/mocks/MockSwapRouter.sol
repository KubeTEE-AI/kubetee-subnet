// SPDX-License-Identifier: MIT
pragma solidity ^0.8.22;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/**
 * @title MockSwapRouter
 * @notice Mock Uniswap V3 Router for testing purposes
 */
contract MockSwapRouter {
    IERC20 public outputToken;
    
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
    
    constructor(address _outputToken) {
        outputToken = IERC20(_outputToken);
    }
    
    /**
     * @notice Mock swap function that simulates a 1:0.005 USDC:wTAO rate
     */
    function exactInputSingle(ExactInputSingleParams calldata params) external payable returns (uint256 amountOut) {
        // Transfer input token from caller
        IERC20(params.tokenIn).transferFrom(msg.sender, address(this), params.amountIn);
        
        // Calculate output (mock rate: 1 USDC = 0.005 wTAO at ~$200/TAO)
        // USDC has 6 decimals, wTAO has 18 decimals
        // So 1 USDC (1e6) = 0.005 wTAO (5e15)
        amountOut = params.amountIn * 5e9; // Simplified conversion
        
        require(amountOut >= params.amountOutMinimum, "Insufficient output amount");
        
        // Transfer output token to recipient
        outputToken.transfer(params.recipient, amountOut);
        
        return amountOut;
    }
}
