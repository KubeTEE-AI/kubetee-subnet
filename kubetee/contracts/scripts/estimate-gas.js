/**
 * Estimate gas costs for contract deployment
 * Usage: npx hardhat run scripts/estimate-gas.js --network <network>
 */

const { ethers, upgrades } = require("hardhat");

async function main() {
  console.log("Estimating gas costs for KubeTEEGitHubRegistry deployment...\n");

  const [deployer] = await ethers.getSigners();
  const network = await ethers.provider.getNetwork();

  console.log("Network:", network.name, `(chainId: ${network.chainId})`);
  console.log("Deployer:", deployer.address);

  // Get current gas price
  const feeData = await ethers.provider.getFeeData();
  const gasPrice = feeData.gasPrice;
  console.log("Current gas price:", ethers.formatUnits(gasPrice, "gwei"), "gwei\n");

  // Get deployer balance
  const balance = await ethers.provider.getBalance(deployer.address);
  console.log("Deployer balance:", ethers.formatEther(balance), "TAO\n");

  // Estimate deployment gas
  const KubeTEEGitHubRegistry = await ethers.getContractFactory("KubeTEEGitHubRegistry");
  
  // Estimate implementation deployment
  const deployTx = await KubeTEEGitHubRegistry.getDeployTransaction();
  const implGas = await ethers.provider.estimateGas({
    data: deployTx.data,
  });
  
  console.log("Estimated gas costs:");
  console.log("====================");
  console.log("Implementation deployment:", implGas.toString(), "gas");
  
  // Proxy deployment is approximately 400k gas for UUPS
  const proxyGas = 400000n;
  console.log("Proxy deployment (approx):", proxyGas.toString(), "gas");
  
  // Initialization is approximately 100k gas
  const initGas = 100000n;
  console.log("Initialization (approx):", initGas.toString(), "gas");
  
  const totalGas = implGas + proxyGas + initGas;
  console.log("Total estimated gas:", totalGas.toString(), "gas\n");
  
  // Calculate cost in TAO
  const totalCost = totalGas * gasPrice;
  console.log("Estimated total cost:", ethers.formatEther(totalCost), "TAO");
  
  // Add 20% buffer for safety
  const costWithBuffer = totalCost * 120n / 100n;
  console.log("Recommended (with 20% buffer):", ethers.formatEther(costWithBuffer), "TAO\n");
  
  // Check if deployer has enough balance
  if (balance < costWithBuffer) {
    console.log("⚠️  WARNING: Deployer balance may be insufficient!");
    console.log("   Current balance:", ethers.formatEther(balance), "TAO");
    console.log("   Recommended:", ethers.formatEther(costWithBuffer), "TAO");
    console.log("   Shortfall:", ethers.formatEther(costWithBuffer - balance), "TAO");
  } else {
    console.log("✅ Deployer has sufficient balance for deployment");
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
