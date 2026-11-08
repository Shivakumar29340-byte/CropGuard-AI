
from blockchain import (
    load_blockchain,
    generate_record_hash,
    register_record,
    verify_record
)

w3, contract, account = load_blockchain()

print("Ganache connected:", w3.is_connected())
print("Chain ID:", w3.eth.chain_id)
print("Contract:", contract.address)

# Use a reserved test ID, not an existing farm record ID.
test_id = 999999

test_data = {
    "crop": "Tomato",
    "disease": "Early blight",
    "test": "CropGuard blockchain test"
}

record_hash = generate_record_hash(test_data)

registered = register_record(test_id, record_hash)

print("\nRegistration result:")
print(registered)

verification = verify_record(test_id, record_hash)

print("\nVerification result:")
print(verification)
