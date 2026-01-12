"""
Merkle Tree Anchoring Service

Handles public anchoring for verification.
This turns "a trustworthy project" into "a system that doesn't require trust."

Strategy:
- Phase 1: Daily Merkle root → Git repo + transparency page
- Phase 2: Weekly blockchain anchor (Ethereum/Bitcoin) for maximum credibility

KEY CAPABILITY:
    "Given event_id, prove it is in anchor X"
    
This function becomes incredibly powerful later.
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4


@dataclass
class MerkleNode:
    """A node in the Merkle tree."""
    hash: str
    left: Optional["MerkleNode"] = None
    right: Optional["MerkleNode"] = None
    event_id: Optional[UUID] = None  # Only leaf nodes have event_id


@dataclass
class MerkleProof:
    """
    Proof that an event is included in a Merkle root.
    
    Contains the sibling hashes needed to recompute the root.
    This proof is self-contained and can be verified by anyone.
    """
    event_id: UUID
    event_hash: str
    proof_hashes: list[str]
    proof_directions: list[str]  # "left" or "right" for each step
    merkle_root: str
    batch_id: UUID
    batch_created_at: str  # ISO timestamp
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "event_id": str(self.event_id),
            "event_hash": self.event_hash,
            "proof_hashes": self.proof_hashes,
            "proof_directions": self.proof_directions,
            "merkle_root": self.merkle_root,
            "batch_id": str(self.batch_id),
            "batch_created_at": self.batch_created_at,
        }
    
    def to_json(self) -> str:
        """Serialize to JSON for storage/transmission."""
        return json.dumps(self.to_dict(), sort_keys=True)
    
    @classmethod
    def from_dict(cls, data: dict) -> "MerkleProof":
        """Deserialize from dictionary."""
        return cls(
            event_id=UUID(data["event_id"]),
            event_hash=data["event_hash"],
            proof_hashes=data["proof_hashes"],
            proof_directions=data["proof_directions"],
            merkle_root=data["merkle_root"],
            batch_id=UUID(data["batch_id"]),
            batch_created_at=data["batch_created_at"],
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "MerkleProof":
        """Deserialize from JSON."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class AnchorBatch:
    """
    A batch of events that have been anchored together.
    
    Contains:
    - Which events (by ID and hash)
    - Sequence range covered
    - Merkle root
    - External anchor references (once published)
    """
    id: UUID
    
    # Events in this batch
    event_ids: list[UUID]
    event_hashes: list[str]
    
    # Sequence range (inclusive) - for quick lookups
    sequence_start: int
    sequence_end: int
    
    # The anchor
    merkle_root: str
    created_at: datetime
    
    # Public anchor references (populated after publishing)
    git_commit_hash: Optional[str] = None
    git_repo_url: Optional[str] = None
    blockchain_tx_hash: Optional[str] = None
    blockchain_network: Optional[str] = None
    transparency_url: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/serialization."""
        return {
            "id": str(self.id),
            "event_count": len(self.event_ids),
            "event_ids": [str(eid) for eid in self.event_ids],
            "sequence_range": f"{self.sequence_start}-{self.sequence_end}",
            "merkle_root": self.merkle_root,
            "created_at": self.created_at.isoformat(),
            "git_commit_hash": self.git_commit_hash,
            "git_repo_url": self.git_repo_url,
            "blockchain_tx_hash": self.blockchain_tx_hash,
            "blockchain_network": self.blockchain_network,
            "transparency_url": self.transparency_url,
        }
    
    def to_json(self) -> str:
        """Serialize to JSON for logging."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class VerificationResult:
    """
    Complete verification result for an event.
    
    This is the answer to: "Prove event X is in anchor Y"
    """
    verified: bool
    event_id: UUID
    event_hash: str
    batch_id: UUID
    merkle_root: str
    proof: Optional[MerkleProof]
    external_anchors: dict  # git, blockchain references
    message: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "verified": self.verified,
            "event_id": str(self.event_id),
            "event_hash": self.event_hash,
            "batch_id": str(self.batch_id),
            "merkle_root": self.merkle_root,
            "proof": self.proof.to_dict() if self.proof else None,
            "external_anchors": self.external_anchors,
            "message": self.message,
        }


class MerkleTree:
    """
    Merkle tree implementation for event anchoring.
    
    The Merkle root is a single hash that commits to all events
    in the batch. Individual events can prove their inclusion
    without revealing other events.
    """
    
    def __init__(self, hashes: list[str], event_ids: Optional[list[UUID]] = None):
        """
        Build a Merkle tree from a list of hashes.
        
        Args:
            hashes: List of event hashes (leaf nodes)
            event_ids: Optional list of corresponding event IDs
        """
        if not hashes:
            raise ValueError("Cannot create Merkle tree with no hashes")
        
        self._leaves = hashes
        self._event_ids = event_ids or [None] * len(hashes)
        self._root = self._build_tree(hashes, self._event_ids)
    
    @staticmethod
    def _hash_pair(left: str, right: str) -> str:
        """Hash two nodes together."""
        combined = f"{left}{right}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()
    
    def _build_tree(
        self, 
        hashes: list[str], 
        event_ids: list[Optional[UUID]]
    ) -> MerkleNode:
        """Recursively build the Merkle tree."""
        # Create leaf nodes
        nodes = [
            MerkleNode(hash=h, event_id=eid) 
            for h, eid in zip(hashes, event_ids)
        ]
        
        # If odd number, duplicate last node
        if len(nodes) % 2 == 1:
            nodes.append(MerkleNode(hash=nodes[-1].hash))
        
        # Build tree bottom-up
        while len(nodes) > 1:
            next_level = []
            for i in range(0, len(nodes), 2):
                left = nodes[i]
                right = nodes[i + 1]
                parent_hash = self._hash_pair(left.hash, right.hash)
                parent = MerkleNode(
                    hash=parent_hash,
                    left=left,
                    right=right
                )
                next_level.append(parent)
            
            # Handle odd number at this level
            if len(next_level) > 1 and len(next_level) % 2 == 1:
                next_level.append(MerkleNode(hash=next_level[-1].hash))
            
            nodes = next_level
        
        return nodes[0]
    
    @property
    def root_hash(self) -> str:
        """Get the Merkle root hash."""
        return self._root.hash
    
    def get_proof_hashes(self, event_hash: str) -> Optional[tuple[list[str], list[str]]]:
        """
        Generate proof hashes and directions for an event hash.
        
        Returns (proof_hashes, proof_directions) or None if not found.
        """
        try:
            index = self._leaves.index(event_hash)
        except ValueError:
            return None
        
        proof_hashes = []
        proof_directions = []
        
        current_index = index
        level_hashes = self._leaves.copy()
        
        # Handle odd number of leaves
        if len(level_hashes) % 2 == 1:
            level_hashes.append(level_hashes[-1])
        
        while len(level_hashes) > 1:
            # Find sibling
            if current_index % 2 == 0:
                sibling_index = current_index + 1
                proof_directions.append("right")
            else:
                sibling_index = current_index - 1
                proof_directions.append("left")
            
            proof_hashes.append(level_hashes[sibling_index])
            
            # Move to next level
            next_level = []
            for i in range(0, len(level_hashes), 2):
                combined = self._hash_pair(level_hashes[i], level_hashes[i + 1])
                next_level.append(combined)
            
            # Handle odd number at this level
            if len(next_level) > 1 and len(next_level) % 2 == 1:
                next_level.append(next_level[-1])
            
            level_hashes = next_level
            current_index = current_index // 2
        
        return proof_hashes, proof_directions
    
    @staticmethod
    def verify_proof(
        event_hash: str,
        proof_hashes: list[str],
        proof_directions: list[str],
        expected_root: str
    ) -> bool:
        """
        Verify a Merkle proof.
        
        Anyone can verify that an event was included in a batch
        without needing access to other events.
        """
        current_hash = event_hash
        
        for sibling_hash, direction in zip(proof_hashes, proof_directions):
            if direction == "left":
                current_hash = MerkleTree._hash_pair(sibling_hash, current_hash)
            else:
                current_hash = MerkleTree._hash_pair(current_hash, sibling_hash)
        
        return current_hash == expected_root


class AnchorService:
    """
    Service for creating and managing anchor batches.
    
    KEY CAPABILITY:
        prove_event(event_id) → VerificationResult
        
    This is the function that matters.
    
    Phase 1: Creates anchor batches with Merkle roots
    Phase 2: Publishes to external services (Git, blockchain)
    """
    
    def __init__(self):
        self._batches: list[AnchorBatch] = []
        
        # Index: event_id → batch_id (for fast lookups)
        self._event_to_batch: dict[UUID, UUID] = {}
        
        # Index: event_id → event_hash
        self._event_to_hash: dict[UUID, str] = {}
    
    def create_batch(
        self, 
        event_ids: list[UUID], 
        event_hashes: list[str],
        sequence_start: int,
        sequence_end: int,
    ) -> AnchorBatch:
        """
        Create a new anchor batch from a list of events.
        
        Args:
            event_ids: List of event IDs to include
            event_hashes: Corresponding event hashes
            sequence_start: First sequence number in batch
            sequence_end: Last sequence number in batch
        
        Returns:
            AnchorBatch with Merkle root computed
        """
        if len(event_ids) != len(event_hashes):
            raise ValueError("event_ids and event_hashes must have same length")
        
        if not event_ids:
            raise ValueError("Cannot create empty anchor batch")
        
        # Check for duplicate anchoring
        for eid in event_ids:
            if eid in self._event_to_batch:
                existing_batch = self._event_to_batch[eid]
                raise ValueError(
                    f"Event {eid} is already anchored in batch {existing_batch}"
                )
        
        tree = MerkleTree(event_hashes, event_ids)
        
        batch = AnchorBatch(
            id=uuid4(),
            event_ids=event_ids,
            event_hashes=event_hashes,
            sequence_start=sequence_start,
            sequence_end=sequence_end,
            merkle_root=tree.root_hash,
            created_at=datetime.now(timezone.utc),
        )
        
        # Update indexes
        for eid, ehash in zip(event_ids, event_hashes):
            self._event_to_batch[eid] = batch.id
            self._event_to_hash[eid] = ehash
        
        self._batches.append(batch)
        
        # Log the batch creation
        self._log_batch_created(batch)
        
        return batch
    
    def _log_batch_created(self, batch: AnchorBatch) -> None:
        """Log batch creation for audit trail."""
        # In production, this would write to a file/database
        # For now, it's a hook for logging
        pass
    
    # ================================================================
    # THE KEY FUNCTION: Prove an event is in an anchor
    # ================================================================
    
    def prove_event(self, event_id: UUID) -> Optional[VerificationResult]:
        """
        THE KEY FUNCTION.
        
        Given an event_id, generate a complete proof that it is
        included in a specific anchor batch.
        
        This proof is:
        - Self-contained (includes everything needed to verify)
        - Independently verifiable (anyone can check it)
        - Linked to external anchors (Git, blockchain)
        
        Returns None if event is not yet anchored.
        """
        # Look up which batch contains this event
        batch_id = self._event_to_batch.get(event_id)
        if batch_id is None:
            return None
        
        batch = self.get_batch(batch_id)
        if batch is None:
            return None
        
        event_hash = self._event_to_hash.get(event_id)
        if event_hash is None:
            return None
        
        # Generate the Merkle proof
        tree = MerkleTree(batch.event_hashes, batch.event_ids)
        proof_data = tree.get_proof_hashes(event_hash)
        
        if proof_data is None:
            return VerificationResult(
                verified=False,
                event_id=event_id,
                event_hash=event_hash,
                batch_id=batch_id,
                merkle_root=batch.merkle_root,
                proof=None,
                external_anchors={},
                message="Failed to generate proof (event not found in tree)",
            )
        
        proof_hashes, proof_directions = proof_data
        
        # Verify the proof works
        verified = MerkleTree.verify_proof(
            event_hash,
            proof_hashes,
            proof_directions,
            batch.merkle_root
        )
        
        # Build complete proof object
        proof = MerkleProof(
            event_id=event_id,
            event_hash=event_hash,
            proof_hashes=proof_hashes,
            proof_directions=proof_directions,
            merkle_root=batch.merkle_root,
            batch_id=batch_id,
            batch_created_at=batch.created_at.isoformat(),
        )
        
        # Collect external anchor references
        external_anchors = {}
        if batch.git_commit_hash:
            external_anchors["git"] = {
                "commit_hash": batch.git_commit_hash,
                "repo_url": batch.git_repo_url,
            }
        if batch.blockchain_tx_hash:
            external_anchors["blockchain"] = {
                "tx_hash": batch.blockchain_tx_hash,
                "network": batch.blockchain_network,
            }
        if batch.transparency_url:
            external_anchors["transparency_log"] = batch.transparency_url
        
        return VerificationResult(
            verified=verified,
            event_id=event_id,
            event_hash=event_hash,
            batch_id=batch_id,
            merkle_root=batch.merkle_root,
            proof=proof,
            external_anchors=external_anchors,
            message="Event is anchored and proof verified" if verified else "Proof verification failed",
        )
    
    def verify_proof(self, proof: MerkleProof) -> bool:
        """
        Verify a Merkle proof.
        
        This can be called by anyone with just the proof object.
        No access to the anchor service's internal state needed.
        """
        return MerkleTree.verify_proof(
            proof.event_hash,
            proof.proof_hashes,
            proof.proof_directions,
            proof.merkle_root
        )
    
    def get_batch_for_event(self, event_id: UUID) -> Optional[AnchorBatch]:
        """Get the anchor batch containing a specific event."""
        batch_id = self._event_to_batch.get(event_id)
        if batch_id is None:
            return None
        return self.get_batch(batch_id)
    
    def is_event_anchored(self, event_id: UUID) -> bool:
        """Check if an event has been anchored."""
        return event_id in self._event_to_batch
    
    def get_unanchored_events(
        self, 
        all_event_ids: list[UUID]
    ) -> list[UUID]:
        """Get list of events that haven't been anchored yet."""
        return [eid for eid in all_event_ids if eid not in self._event_to_batch]
    
    # ================================================================
    # Batch management
    # ================================================================
    
    def get_batch(self, batch_id: UUID) -> Optional[AnchorBatch]:
        """Get a specific anchor batch."""
        return next((b for b in self._batches if b.id == batch_id), None)
    
    def get_all_batches(self) -> list[AnchorBatch]:
        """Get all anchor batches."""
        return self._batches.copy()
    
    def get_batches_in_range(
        self, 
        start_date: datetime, 
        end_date: datetime
    ) -> list[AnchorBatch]:
        """Get batches created within a date range."""
        return [
            b for b in self._batches 
            if start_date <= b.created_at <= end_date
        ]
    
    # ================================================================
    # Publishing (Phase 2)
    # ================================================================
    
    def set_git_anchor(
        self, 
        batch_id: UUID, 
        commit_hash: str, 
        repo_url: str
    ) -> None:
        """Record that a batch was published to Git."""
        batch = self.get_batch(batch_id)
        if batch:
            batch.git_commit_hash = commit_hash
            batch.git_repo_url = repo_url
    
    def set_blockchain_anchor(
        self, 
        batch_id: UUID, 
        tx_hash: str, 
        network: str
    ) -> None:
        """Record that a batch was published to blockchain."""
        batch = self.get_batch(batch_id)
        if batch:
            batch.blockchain_tx_hash = tx_hash
            batch.blockchain_network = network
    
    def set_transparency_url(self, batch_id: UUID, url: str) -> None:
        """Record the transparency log URL for a batch."""
        batch = self.get_batch(batch_id)
        if batch:
            batch.transparency_url = url
    
    async def publish_to_git(self, batch: AnchorBatch, repo_path: str) -> str:
        """
        Publish an anchor to a Git repository.
        
        Phase 1 implementation: Create a signed commit with the Merkle root.
        
        Returns the commit hash.
        """
        # Implementation would:
        # 1. Write anchor data to a file
        # 2. Create a signed commit
        # 3. Push to remote
        # 
        # For now, this is a placeholder
        raise NotImplementedError("Git publishing not yet implemented")
    
    async def publish_to_blockchain(
        self, 
        batch: AnchorBatch, 
        network: str = "ethereum"
    ) -> str:
        """
        Publish an anchor to a blockchain.
        
        Phase 2 implementation: Write Merkle root to chain.
        
        Returns the transaction hash.
        """
        # Implementation would:
        # 1. Create a transaction with the Merkle root as data
        # 2. Sign and broadcast
        # 3. Wait for confirmation
        #
        # For now, this is a placeholder
        raise NotImplementedError("Blockchain anchoring not yet implemented")
