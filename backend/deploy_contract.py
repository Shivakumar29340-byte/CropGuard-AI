
import json
from pathlib import Path
from web3 import Web3

BASE_DIR = Path(__file__).resolve().parent

RPC_URL = "http://127.0.0.1:7547"

ARTIFACT_PATH = BASE_DIR / "artifacts" / "CropGuardRecords.json"
CONFIG_PATH = BASE_DIR / "blockchain_config.json"


def deploy_contract():
    print("Connecting to Ganache...")

    if not ARTIFACT_PATH.exists():
        raise FileNotFoundError(
            "Contract artifact not found. Compile the smart contract first."
        )

    with open(ARTIFACT_PATH, "r", encoding="utf-8") as file:
        artifact = json.load(file)

    if not artifact.get("abi") or not artifact.get("bytecode"):
        raise ValueError("Contract ABI or bytecode is missing from artifact.")

    web3 = Web3(Web3.HTTPProvider(RPC_URL))

    if not web3.is_connected():
        raise ConnectionError(
            "Cannot connect to Ganache. Check that Ganache is running on port 7546."
        )

    accounts = web3.eth.accounts

    if not accounts:
        raise RuntimeError("No Ganache accounts found.")

    deployer = Web3.to_checksum_address(accounts[0])

    print("Ganache connected successfully!")
    print("RPC URL:", RPC_URL)
    print("Chain ID:", web3.eth.chain_id)
    print("Deployer:", deployer)

    contract_factory = web3.eth.contract(
        abi=artifact["abi"],
        bytecode=artifact["bytecode"]
    )

    print("\nDeploying CropGuard smart contract...")

    tx_hash = contract_factory.constructor().transact({
        "from": deployer,
        "gas": 3000000
    })

    print("Transaction sent:", tx_hash.hex())
    print("Waiting for confirmation...")

    receipt = web3.eth.wait_for_transaction_receipt(
        tx_hash,
        timeout=120
    )

    if receipt.status != 1 or not receipt.contractAddress:
        raise RuntimeError("Smart contract deployment failed.")

    contract_address = Web3.to_checksum_address(
        receipt.contractAddress
    )

    config = {
        "rpc_url": RPC_URL,
        "chain_id": web3.eth.chain_id,
        "contract_address": contract_address,
        "deployer_address": deployer
    }

    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=4)

    print("\n====================================")
    print("CROPGUARD CONTRACT DEPLOYED!")
    print("====================================")
    print("RPC URL:", RPC_URL)
    print("Chain ID:", web3.eth.chain_id)
    print("Contract Address:", contract_address)
    print("Transaction Hash:", tx_hash.hex())
    print("Block Number:", receipt.blockNumber)
    print("Configuration saved:", CONFIG_PATH)
    print("====================================")


if __name__ == "__main__":
    deploy_contract()
