// scripts/deploy-payment.js
const { ethers, upgrades } = require("hardhat");

async function main() {
    const [deployer] = await ethers.getSigners();
    
    console.log("Deploying KubeTEEPaymentV2 with account:", deployer.address);
    console.log("Account balance:", ethers.formatEther(await ethers.provider.getBalance(deployer.address)));
    
    // Configuration - update these for your deployment
    const USDC_ADDRESS = process.env.USDC_ADDRESS || "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"; // BASE USDC
    const TREASURY_ADDRESS = process.env.TREASURY_ADDRESS || deployer.address;
    
    console.log("\nDeployment Configuration:");
    console.log("- USDC Address:", USDC_ADDRESS);
    console.log("- Treasury Address:", TREASURY_ADDRESS);
    
    // Deploy as upgradeable proxy
    console.log("\nDeploying KubeTEEPaymentV2 as UUPS proxy...");
    const KubeTEEPaymentV2 = await ethers.getContractFactory("KubeTEEPaymentV2");
    
    const payment = await upgrades.deployProxy(
        KubeTEEPaymentV2,
        [USDC_ADDRESS, TREASURY_ADDRESS],
        {
            kind: "uups",
            initializer: "initialize"
        }
    );
    
    await payment.waitForDeployment();
    const proxyAddress = await payment.getAddress();
    const implementationAddress = await upgrades.erc1967.getImplementationAddress(proxyAddress);
    
    console.log("\n✅ Deployment Successful!");
    console.log("=====================================");
    console.log("Proxy Address:", proxyAddress);
    console.log("Implementation Address:", implementationAddress);
    console.log("=====================================");
    
    // Add deployer as initial operator
    console.log("\nAdding deployer as initial operator...");
    await payment.addOperator(deployer.address);
    console.log("✅ Deployer added as operator");
    
    // Verify configuration
    const config = await payment.getConfig();
    console.log("\nContract Configuration:");
    console.log("- USDC:", config.usdcAddress);
    console.log("- Treasury:", config.treasuryAddress);
    console.log("- Min Paid Users:", config._minPaidUsers.toString());
    console.log("- Commission BPS:", config._commissionBps.toString());
    
    console.log("\n🎉 KubeTEEPaymentV2 deployment complete!");
    console.log("\nNext steps:");
    console.log("1. Verify contract on block explorer");
    console.log("2. Add additional operators as needed");
    console.log("3. Update frontend/backend with proxy address");
    
    return {
        proxyAddress,
        implementationAddress
    };
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
