
import json
import hashlib
from pathlib import Path

from web3 import Web3


BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "blockchain_config.json"
ARTIFACT_FILE = BASE_DIR / "artifacts" / "CropGuardRecords.json"


def load_blockchain():
    """Connect to Ganache and load the deployed smart contract."""

    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Blockchain configuration not found: {CONFIG_FILE}"
        )

    if not ARTIFACT_FILE.exists():
        raise FileNotFoundError(
            f"Contract artifact not found: {ARTIFACT_FILE}"
        )

    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        config = json.load(file)

    with open(ARTIFACT_FILE, "r", encoding="utf-8") as file:
        artifact = json.load(file)

    rpc_url = config.get("rpc_url")
    contract_address = config.get("contract_address")
    deployer_address = config.get("deployer_address")

    if not rpc_url or not contract_address or not deployer_address:
        raise ValueError(
            "Blockchain configuration must contain rpc_url, "
            "contract_address and deployer_address."
        )

    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))

    if not w3.is_connected():
        raise ConnectionError(
            "Cannot connect to Ganache. Start Ganache and check the RPC URL."
        )

    account = Web3.to_checksum_address(deployer_address)
    contract_address = Web3.to_checksum_address(contract_address)

    if not w3.eth.get_code(contract_address):
        raise RuntimeError(
            "No smart contract found at the configured contract address."
        )

    contract = w3.eth.contract(
        address=contract_address,
        abi=artifact["abi"]
    )

    return w3, contract, account


def generate_record_hash(record_data):
    """Generate a SHA-256 hash for a record."""

    if isinstance(record_data, dict):
        record_data = json.dumps(
            record_data,
            sort_keys=True,
            separators=(",", ":")
        )

    if isinstance(record_data, str):
        record_data = record_data.encode("utf-8")

    if not isinstance(record_data, bytes):
        raise TypeError("Record data must be a dictionary, string or bytes.")

    return hashlib.sha256(record_data).hexdigest()


def normalize_hash(record_hash):
    """Convert a 64-character SHA-256 hash into 32 bytes."""

    value = str(record_hash).strip().removeprefix("0x")

    try:
        hash_bytes = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError("Record hash is not valid hexadecimal.") from exc

    if len(hash_bytes) != 32:
        raise ValueError("Record hash must be exactly 32 bytes.")

    return hash_bytes


def register_record(record_id, record_hash):
    """Register a detection record hash on the smart contract."""

    w3, contract, account = load_blockchain()

    record_id = int(record_id)
    if record_id <= 0:
        raise ValueError("Record ID must be a positive integer.")

    hash_bytes = normalize_hash(record_hash)

    existing = contract.functions.getRecord(record_id).call()

    if bool(existing[2]):
        existing_hash = bytes(existing[1]).hex()

        if existing_hash.lower() == hash_bytes.hex().lower():
            return {
                "success": True,
                "already_registered": True,
                "record_id": record_id,
                "record_hash": hash_bytes.hex(),
                "transaction_hash": None,
                "block_number": None,
                "contract_address": contract.address
            }

        raise ValueError(
            f"Record ID {record_id} is already registered with another hash."
        )

    tx_hash = contract.functions.registerRecord(
        record_id,
        hash_bytes
    ).transact({
        "from": account,
        "gas": 300000
    })

    receipt = w3.eth.wait_for_transaction_receipt(
        tx_hash,
        timeout=120
    )

    if receipt.status != 1:
        raise RuntimeError("Blockchain registration transaction failed.")

    return {
        "success": True,
        "already_registered": False,
        "record_id": record_id,
        "record_hash": hash_bytes.hex(),
        "transaction_hash": receipt.transactionHash.hex(),
        "block_number": receipt.blockNumber,
        "contract_address": contract.address
    }


def verify_record(record_id, expected_hash):
    """Verify a record hash against the smart contract."""

    w3, contract, account = load_blockchain()

    record_id = int(record_id)
    hash_bytes = normalize_hash(expected_hash)

    result = contract.functions.verifyRecord(
        record_id,
        hash_bytes
    ).call()

    exists = bool(result[0])
    valid = bool(result[1])

    stored_hash = result[2]
    if isinstance(stored_hash, bytes):
        stored_hash = stored_hash.hex()
    else:
        stored_hash = str(stored_hash).removeprefix("0x")

    timestamp = int(result[3])

    return {
        "exists": exists,
        "valid": valid,
        "stored_hash": stored_hash,
        "timestamp": timestamp,
        "contract_address": contract.address,
        "chain_id": w3.eth.chain_id
    }
