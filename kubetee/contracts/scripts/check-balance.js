/**
 * Check wallet balance on the specified network
 * Usage: npx hardhat run scripts/check-balance.js --network <network>
 */

const { ethers } = require("hardhat");

async function main() {
  console.log("Checking wallet balance...\n");

  const [signer] = await ethers.getSigners();
  const network = await ethers.provider.getNetwork();

  console.log("Network:", network.name, `(chainId: ${network.chainId})`);
  console.log("Address:", signer.address);

  // Get balance
  const balance = await ethers.provider.getBalance(signer.address);
  console.log("\nBalance:", ethers.formatEther(balance), "TAO");

  // Get current gas price
  const feeData = await ethers.provider.getFeeData();
  console.log("Current gas price:", ethers.formatUnits(feeData.gasPrice, "gwei"), "gwei");

  // Get transaction count (nonce)
  const nonce = await ethers.provider.getTransactionCount(signer.address);
  console.log("Transaction count (nonce):", nonce);

  // Get pending nonce
  const pendingNonce = await ethers.provider.getTransactionCount(signer.address, "pending");
  if (pendingNonce !== nonce) {
    console.log("Pending nonce:", pendingNonce);
    console.log("⚠️  There are pending transactions!");
  }

  // Estimate how many simple transactions can be made
  const simpleGas = 21000n;
  const maxSimpleTx = balance / (simpleGas * feeData.gasPrice);
  console.log("\nEstimated simple transfers possible:", Math.floor(Number(maxSimpleTx)));

  // Estimate if enough for contract deployment (~2M gas)
  const deploymentGas = 2000000n;
  const deploymentCost = deploymentGas * feeData.gasPrice;
  
  console.log("\nDeployment estimate (2M gas):", ethers.formatEther(deploymentCost), "TAO");
  
  if (balance >= deploymentCost) {
    console.log("✅ Sufficient balance for typical contract deployment");
  } else {
    console.log("❌ Insufficient balance for deployment");
    console.log("   Shortfall:", ethers.formatEther(deploymentCost - balance), "TAO");
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
