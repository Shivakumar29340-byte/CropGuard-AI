
const fs = require("fs");
const path = require("path");
const solc = require("solc");

const contractPath = path.join(
    __dirname,
    "contracts",
    "CropGuardRecords.sol"
);

if (!fs.existsSync(contractPath)) {
    console.error("ERROR: CropGuardRecords.sol not found!");
    process.exit(1);
}

const source = fs.readFileSync(contractPath, "utf8");

const input = {
    language: "Solidity",
    sources: {
        "CropGuardRecords.sol": {
            content: source
        }
    },
    settings: {
        evmVersion: "paris",
        optimizer: {
            enabled: true,
            runs: 200
        },
        outputSelection: {
            "*": {
                "*": ["abi", "evm.bytecode.object"]
            }
        }
    }
};

const output = JSON.parse(solc.compile(JSON.stringify(input)));

if (output.errors) {
    output.errors.forEach(error => {
        console.log(error.formattedMessage);
    });

    if (output.errors.some(error => error.severity === "error")) {
        process.exit(1);
    }
}

const contract =
    output.contracts["CropGuardRecords.sol"]["CropGuardRecords"];

const artifact = {
    contractName: "CropGuardRecords",
    abi: contract.abi,
    bytecode: "0x" + contract.evm.bytecode.object
};

const artifactsDir = path.join(__dirname, "artifacts");

if (!fs.existsSync(artifactsDir)) {
    fs.mkdirSync(artifactsDir);
}

fs.writeFileSync(
    path.join(artifactsDir, "CropGuardRecords.json"),
    JSON.stringify(artifact, null, 2)
);

console.log("Smart contract compiled successfully!");
console.log("Artifact saved in backend/artifacts/CropGuardRecords.json");
