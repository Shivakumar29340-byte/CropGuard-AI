
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract CropGuardRecords {

    address public owner;

    struct FarmRecord {
        bytes32 recordHash;
        uint256 timestamp;
        bool exists;
    }

    mapping(uint256 => FarmRecord) private farmRecords;

    event RecordRegistered(
        uint256 indexed recordId,
        bytes32 recordHash,
        uint256 timestamp
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can register records");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function registerRecord(
        uint256 recordId,
        bytes32 recordHash
    ) public onlyOwner {
        require(recordId > 0, "Invalid record ID");
        require(recordHash != bytes32(0), "Invalid record hash");
        require(!farmRecords[recordId].exists, "Record already registered");

        farmRecords[recordId] = FarmRecord({
            recordHash: recordHash,
            timestamp: block.timestamp,
            exists: true
        });

        emit RecordRegistered(
            recordId,
            recordHash,
            block.timestamp
        );
    }

    function verifyRecord(
        uint256 recordId,
        bytes32 expectedHash
    ) public view returns (
        bool exists,
        bool valid,
        bytes32 storedHash,
        uint256 timestamp
    ) {
        FarmRecord memory record = farmRecords[recordId];

        exists = record.exists;
        storedHash = record.recordHash;
        timestamp = record.timestamp;
        valid = exists && storedHash == expectedHash;
    }

    function getRecord(
        uint256 recordId
    ) public view returns (
        bytes32 recordHash,
        uint256 timestamp,
        bool exists
    ) {
        FarmRecord memory record = farmRecords[recordId];

        return (
            record.recordHash,
            record.timestamp,
            record.exists
        );
    }
}
