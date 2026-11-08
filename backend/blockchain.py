
import json
import hashlib
from pathlib import Path

from web3 import Web3


# =====================================================
# FILE PATHS
# =====================================================

BASE_DIR = Path(__file__).resolve().parent

CONFIG_FILE = BASE_DIR / "blockchain_config.json"

ARTIFACT_FILE = (
    BASE_DIR / "artifacts" / "CropGuardRecords.json"
)


# =====================================================
# LOAD BLOCKCHAIN CONNECTION
# =====================================================

def load_blockchain():

    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            "blockchain_config.json not found."
        )

    if not ARTIFACT_FILE.exists():
        raise FileNotFoundError(
            "Smart contract artifact not found. "
            "Compile and deploy the contract first."
        )

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    with open(ARTIFACT_FILE, "r", encoding="utf-8") as f:
        artifact = json.load(f)

    rpc_url = config["rpc_url"]

    w3 = Web3(
        Web3.HTTPProvider(rpc_url)
    )

    if not w3.is_connected():
        raise ConnectionError(
            "Cannot connect to Ganache. "
            "Check that Ganache is running."
        )

    contract_address = Web3.to_checksum_address(
        config["contract_address"]
    )

    deployer_address = Web3.to_checksum_address(
        config["deployer_address"]
    )

    contract = w3.eth.contract(
        address=contract_address,
        abi=artifact["abi"]
    )

    return w3, contract, deployer_address


# =====================================================
# GENERATE RECORD HASH
# =====================================================

def generate_record_hash(record_data):

    if isinstance(record_data, dict):

        record_data = json.dumps(
            record_data,
            sort_keys=True,
            separators=(",", ":")
        )

    if isinstance(record_data, str):

        record_data = record_data.encode("utf-8")

    return hashlib.sha256(record_data).hexdigest()


# =====================================================
# REGISTER RECORD ON BLOCKCHAIN
# =====================================================

def register_record(record_id, record_hash):

    w3, contract, account = load_blockchain()

    hash_bytes = bytes.fromhex(
        record_hash.removeprefix("0x")
    )

    if len(hash_bytes) != 32:
        raise ValueError(
            "Record hash must be exactly 32 bytes."
        )

    # Check whether the record already exists.

    existing = contract.functions.getRecord(
        int(record_id)
    ).call()

    if existing[2]:

        raise ValueError(
            f"Record {record_id} is already registered."
        )

    # Send transaction to Ganache.

    tx_hash = contract.functions.registerRecord(
        int(record_id),
        hash_bytes
    ).transact({
        "from": account,
        "gas": 300000
    })

    # Wait for transaction confirmation.

    receipt = w3.eth.wait_for_transaction_receipt(
        tx_hash,
        timeout=120
    )

    if receipt.status != 1:

        raise RuntimeError(
            "Blockchain transaction failed."
        )

    return {
        "success": True,
        "record_id": int(record_id),
        "record_hash": record_hash,
        "transaction_hash": receipt.transactionHash.hex(),
        "block_number": receipt.blockNumber,
        "contract_address": contract.address,
        "chain_id": w3.eth.chain_id
    }


# =====================================================
# VERIFY RECORD ON BLOCKCHAIN
# =====================================================

def verify_record(record_id, expected_hash):

    w3, contract, account = load_blockchain()

    hash_bytes = bytes.fromhex(
        expected_hash.removeprefix("0x")
    )

    if len(hash_bytes) != 32:

        raise ValueError(
            "Record hash must be exactly 32 bytes."
        )

    # Verify record using the smart contract.

    result = contract.functions.verifyRecord(
        int(record_id),
        hash_bytes
    ).call()

    return {
        "exists": bool(result[0]),
        "valid": bool(result[1]),
        "stored_hash": result[2].hex(),
        "timestamp": result[3],
        "chain_id": w3.eth.chain_id,
        "contract_address": contract.address
    }
