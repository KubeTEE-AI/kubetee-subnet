const { ethers, upgrades } = require("hardhat");

async function main() {
    console.log("Deploying KubeTEEGitHubRegistry...");
    
    const [deployer] = await ethers.getSigners();
    console.log("Deploying with account:", deployer.address);
    console.log("Account balance:", (await ethers.provider.getBalance(deployer.address)).toString());
    
    // Get the contract factory
    const Registry = await ethers.getContractFactory("KubeTEEGitHubRegistry");
    
    // Deploy as upgradeable proxy (UUPS pattern)
    const registry = await upgrades.deployProxy(Registry, [], { 
        initializer: 'initialize',
        kind: 'uups'
    });
    
    await registry.waitForDeployment();
    
    const address = await registry.getAddress();
    console.log("KubeTEEGitHubRegistry deployed to:", address);
    
    // Get implementation address for verification
    const implementationAddress = await upgrades.erc1967.getImplementationAddress(address);
    console.log("Implementation address:", implementationAddress);
    
    console.log("\nDeployment complete!");
    console.log("Proxy address:", address);
    console.log("Use this proxy address for all interactions.");
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
