#!/bin/bash
# =============================================================================
# KubeTEE Buyback & Burn Automation Setup
# =============================================================================
#
# This script sets up the complete buyback automation:
# 1. Deploys smart contracts to BASE
# 2. Registers Chainlink Automation
# 3. Deploys Bittensor buyback bot
#
# Usage: ./setup_automation.sh
#
# =============================================================================

set -e

echo "=============================================="
echo "KubeTEE Buyback & Burn Automation Setup"
echo "=============================================="

# Check requirements
check_requirements() {
    echo "Checking requirements..."
    
    if ! command -v forge &> /dev/null; then
        echo "❌ Foundry (forge) not found. Install: curl -L https://foundry.paradigm.xyz | bash"
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker not found. Please install Docker."
        exit 1
    fi
    
    if ! command -v btcli &> /dev/null; then
        echo "❌ Bittensor CLI not found. Install: pip install bittensor"
        exit 1
    fi
    
    echo "✅ All requirements met"
}

# Deploy contracts to BASE
deploy_contracts() {
    echo ""
    echo "Step 1: Deploying contracts to BASE..."
    echo "--------------------------------------"
    
    if [ -z "$DEPLOYER_PRIVATE_KEY" ]; then
        echo "❌ DEPLOYER_PRIVATE_KEY not set"
        echo "   Export your deployer private key:"
        echo "   export DEPLOYER_PRIVATE_KEY=0x..."
        exit 1
    fi
    
    if [ -z "$KUBETEE_OWNER" ]; then
        echo "❌ KUBETEE_OWNER not set"
        echo "   Export your KubeTEE owner address:"
        echo "   export KUBETEE_OWNER=0x..."
        exit 1
    fi
    
    # BASE mainnet
    RPC_URL=${BASE_RPC_URL:-"https://mainnet.base.org"}
    USDC_ADDRESS=${USDC_ADDRESS:-"0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"}
    EPOCH_DURATION=${EPOCH_DURATION:-3600}
    
    echo "Network: BASE Mainnet"
    echo "USDC: $USDC_ADDRESS"
    echo "Owner: $KUBETEE_OWNER"
    
    # Deploy KubeTEEReseller
    echo ""
    echo "Deploying KubeTEEReseller.sol..."
    RESELLER_ADDRESS=$(forge create \
        --rpc-url $RPC_URL \
        --private-key $DEPLOYER_PRIVATE_KEY \
        contracts/KubeTEEReseller.sol:KubeTEEReseller \
        --constructor-args $USDC_ADDRESS $KUBETEE_OWNER $EPOCH_DURATION \
        --json | jq -r '.deployedTo')
    
    echo "✅ KubeTEEReseller deployed: $RESELLER_ADDRESS"
    
    # Deploy KubeTEEBuybackBurn
    UNISWAP_ROUTER=${UNISWAP_ROUTER:-"0x2626664c2603336E57B271c5C0b26F421741e481"}  # Uniswap V3 on BASE
    BITTENSOR_SWAP_ADDRESS=${BITTENSOR_SWAP_ADDRESS:-"5..."}  # Your Bittensor address for TAO→Alpha
    
    echo ""
    echo "Deploying KubeTEEBuybackBurn.sol..."
    BUYBACK_ADDRESS=$(forge create \
        --rpc-url $RPC_URL \
        --private-key $DEPLOYER_PRIVATE_KEY \
        contracts/KubeTEEBuybackBurn.sol:KubeTEEBuybackBurn \
        --constructor-args $USDC_ADDRESS $UNISWAP_ROUTER "$BITTENSOR_SWAP_ADDRESS" \
        --json | jq -r '.deployedTo')
    
    echo "✅ KubeTEEBuybackBurn deployed: $BUYBACK_ADDRESS"
    
    # Save addresses
    cat > .env.contracts << EOF
# KubeTEE Contract Addresses (BASE)
KUBETEE_RESELLER_CONTRACT=$RESELLER_ADDRESS
KUBETEE_BUYBACK_CONTRACT=$BUYBACK_ADDRESS
USDC_ADDRESS=$USDC_ADDRESS
KUBETEE_OWNER=$KUBETEE_OWNER
EOF
    
    echo ""
    echo "✅ Addresses saved to .env.contracts"
}

# Register Chainlink Automation
setup_chainlink() {
    echo ""
    echo "Step 2: Setting up Chainlink Automation..."
    echo "-------------------------------------------"
    
    echo "📋 Manual steps required:"
    echo ""
    echo "1. Go to https://automation.chain.link/"
    echo "2. Connect wallet and select BASE network"
    echo "3. Click 'Register new Upkeep'"
    echo "4. Select 'Custom logic' upkeep type"
    echo "5. Enter contract address: $BUYBACK_ADDRESS"
    echo "6. Fund with LINK tokens (recommend 10+ LINK)"
    echo "7. Set gas limit: 500000"
    echo ""
    echo "The contract implements AutomationCompatibleInterface:"
    echo "  - checkUpkeep: Returns true when buyback should run"
    echo "  - performUpkeep: Executes the buyback"
    echo ""
}

# Create Bittensor wallet
setup_bittensor_wallet() {
    echo ""
    echo "Step 3: Setting up Bittensor wallet..."
    echo "---------------------------------------"
    
    WALLET_NAME=${BT_WALLET_NAME:-"buyback"}
    
    if btcli wallet overview --wallet.name $WALLET_NAME 2>/dev/null; then
        echo "✅ Wallet '$WALLET_NAME' already exists"
    else
        echo "Creating new Bittensor wallet..."
        btcli wallet new_coldkey --wallet.name $WALLET_NAME --n-words 12
        btcli wallet new_hotkey --wallet.name $WALLET_NAME --wallet.hotkey default
        echo "✅ Wallet created"
    fi
    
    # Get address
    ADDRESS=$(btcli wallet overview --wallet.name $WALLET_NAME | grep -oP '5[A-Za-z0-9]{47}' | head -1)
    echo ""
    echo "Buyback wallet address: $ADDRESS"
    echo ""
    echo "⚠️  Fund this address with TAO for transaction fees"
    echo "    This is also the address that should receive bridged TAO"
}

# Deploy bot
deploy_bot() {
    echo ""
    echo "Step 4: Deploying Bittensor buyback bot..."
    echo "-------------------------------------------"
    
    # Create .env file
    cat > .env.buyback << EOF
# Bittensor Buyback Bot Config
BT_NETWORK=finney
KUBETEE_NETUID=${KUBETEE_NETUID:-0}
BT_WALLET_NAME=${BT_WALLET_NAME:-buyback}
BT_WALLET_HOTKEY=default

# Thresholds
MIN_TAO_THRESHOLD=0.1
MIN_ALPHA_THRESHOLD=0.1

# Check every 5 minutes
CHECK_INTERVAL=300

# Notifications (optional - Discord/Slack webhook)
NOTIFICATION_WEBHOOK=${NOTIFICATION_WEBHOOK:-}
EOF
    
    echo "✅ Config saved to .env.buyback"
    echo ""
    echo "Starting bot with docker-compose..."
    
    # Start bot
    docker-compose -f docker-compose.buyback.yml --env-file .env.buyback up -d
    
    echo "✅ Buyback bot started"
    echo ""
    echo "View logs: docker logs -f kubetee-buyback-bot"
}

# Main
main() {
    check_requirements
    
    echo ""
    echo "This script will:"
    echo "  1. Deploy smart contracts to BASE"
    echo "  2. Guide you through Chainlink Automation setup"
    echo "  3. Create Bittensor wallet for buyback operations"
    echo "  4. Deploy buyback bot"
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
    
    deploy_contracts
    setup_chainlink
    setup_bittensor_wallet
    deploy_bot
    
    echo ""
    echo "=============================================="
    echo "✅ Setup Complete!"
    echo "=============================================="
    echo ""
    echo "Next steps:"
    echo "  1. Complete Chainlink Automation registration"
    echo "  2. Fund buyback wallet with TAO"
    echo "  3. Configure wTAO bridge address in contract"
    echo "  4. Monitor: docker logs -f kubetee-buyback-bot"
    echo ""
}

main

