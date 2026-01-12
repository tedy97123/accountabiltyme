"""
Anchor Batch Scheduler

Automatically creates anchor batches for events that haven't been anchored yet.

CONFIGURATION:
- ACCOUNTABILITYME_ANCHOR_BATCH_SIZE: Events per batch (default: 100)
- ACCOUNTABILITYME_ANCHOR_INTERVAL_SECONDS: Seconds between checks (default: 3600)
- ACCOUNTABILITYME_ANCHOR_ENABLED: Enable auto-anchoring (default: false)

USAGE:
    # Start the scheduler in the background
    scheduler = AnchorScheduler(ledger, anchor_service)
    scheduler.start()
    
    # Or manually trigger anchoring
    batches = scheduler.create_pending_batches()
    
    # Stop gracefully
    scheduler.stop()
"""

import asyncio
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID
import logging

from .anchor import AnchorService, AnchorBatch

if TYPE_CHECKING:
    from .ledger import LedgerService
    from ..db.store import EventStore

logger = logging.getLogger(__name__)


@dataclass
class AnchorConfig:
    """Configuration for the anchor scheduler."""
    batch_size: int = 100  # Events per batch
    interval_seconds: int = 3600  # 1 hour
    enabled: bool = False
    min_events_to_anchor: int = 1  # Minimum events before creating batch
    
    @classmethod
    def from_env(cls) -> "AnchorConfig":
        """Load configuration from environment variables."""
        return cls(
            batch_size=int(os.environ.get("ACCOUNTABILITYME_ANCHOR_BATCH_SIZE", "100")),
            interval_seconds=int(os.environ.get("ACCOUNTABILITYME_ANCHOR_INTERVAL_SECONDS", "3600")),
            enabled=os.environ.get("ACCOUNTABILITYME_ANCHOR_ENABLED", "").lower() in ("1", "true", "yes"),
            min_events_to_anchor=int(os.environ.get("ACCOUNTABILITYME_ANCHOR_MIN_EVENTS", "1")),
        )


class AnchorScheduler:
    """
    Scheduler for automatic anchor batch creation.
    
    Runs in the background and periodically creates anchor batches
    for unanchored events.
    """
    
    def __init__(
        self,
        ledger: "LedgerService",
        anchor_service: Optional[AnchorService] = None,
        config: Optional[AnchorConfig] = None,
    ):
        """
        Initialize the anchor scheduler.
        
        Args:
            ledger: LedgerService instance to get events from
            anchor_service: AnchorService instance (or creates new one)
            config: Configuration (or loads from environment)
        """
        self._ledger = ledger
        self._anchor_service = anchor_service or AnchorService()
        self._config = config or AnchorConfig.from_env()
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Track last anchored sequence
        self._last_anchored_sequence = -1
        self._load_last_anchored_sequence()
    
    def _load_last_anchored_sequence(self) -> None:
        """Load the last anchored sequence from existing batches."""
        batches = self._anchor_service.get_all_batches()
        if batches:
            self._last_anchored_sequence = max(b.sequence_end for b in batches)
    
    @property
    def anchor_service(self) -> AnchorService:
        """Get the anchor service."""
        return self._anchor_service
    
    @property
    def config(self) -> AnchorConfig:
        """Get the configuration."""
        return self._config
    
    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running
    
    def start(self) -> None:
        """Start the background scheduler."""
        if not self._config.enabled:
            logger.info("Anchor scheduler disabled (set ACCOUNTABILITYME_ANCHOR_ENABLED=1 to enable)")
            return
        
        if self._running:
            logger.warning("Anchor scheduler already running")
            return
        
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        logger.info(
            f"Anchor scheduler started (batch_size={self._config.batch_size}, "
            f"interval={self._config.interval_seconds}s)"
        )
    
    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background scheduler."""
        if not self._running:
            return
        
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        
        self._running = False
        logger.info("Anchor scheduler stopped")
    
    def _run_loop(self) -> None:
        """Background thread main loop."""
        while not self._stop_event.is_set():
            try:
                self.create_pending_batches()
            except Exception as e:
                logger.exception(f"Error creating anchor batches: {e}")
            
            # Wait for interval or stop signal
            self._stop_event.wait(timeout=self._config.interval_seconds)
    
    def create_pending_batches(self) -> List[AnchorBatch]:
        """
        Create anchor batches for all unanchored events.
        
        Returns list of created batches.
        """
        events = self._ledger.get_events()
        
        if not events:
            return []
        
        # Find events that need anchoring
        start_seq = self._last_anchored_sequence + 1
        unanchored = [e for e in events if e.sequence_number >= start_seq]
        
        if len(unanchored) < self._config.min_events_to_anchor:
            logger.debug(f"Not enough events to anchor ({len(unanchored)} < {self._config.min_events_to_anchor})")
            return []
        
        created_batches = []
        
        # Create batches of configured size
        for i in range(0, len(unanchored), self._config.batch_size):
            batch_events = unanchored[i:i + self._config.batch_size]
            
            if not batch_events:
                continue
            
            # Extract IDs and hashes
            event_ids = [e.event_id for e in batch_events]
            event_hashes = [e.event_hash for e in batch_events]
            seq_start = batch_events[0].sequence_number
            seq_end = batch_events[-1].sequence_number
            
            try:
                batch = self._anchor_service.create_batch(
                    event_ids=event_ids,
                    event_hashes=event_hashes,
                    sequence_start=seq_start,
                    sequence_end=seq_end,
                )
                
                self._last_anchored_sequence = seq_end
                created_batches.append(batch)
                
                logger.info(
                    f"Created anchor batch {batch.id}: "
                    f"events {seq_start}-{seq_end}, "
                    f"root={batch.merkle_root[:16]}..."
                )
                
            except ValueError as e:
                logger.warning(f"Skipping batch creation: {e}")
        
        return created_batches
    
    def anchor_event(self, event_id: UUID) -> Optional[AnchorBatch]:
        """
        Ensure a specific event is anchored.
        
        If the event isn't in a batch yet, creates a batch including it.
        
        Returns the batch containing the event, or None if event not found.
        """
        # Check if already anchored
        existing = self._anchor_service.get_batch_for_event(event_id)
        if existing:
            return existing
        
        # Find the event
        events = self._ledger.get_events()
        target_event = next((e for e in events if e.event_id == event_id), None)
        
        if not target_event:
            return None
        
        # Create batch up to this event
        seq = target_event.sequence_number
        batch_events = [e for e in events if self._last_anchored_sequence < e.sequence_number <= seq]
        
        if not batch_events:
            return None
        
        event_ids = [e.event_id for e in batch_events]
        event_hashes = [e.event_hash for e in batch_events]
        
        batch = self._anchor_service.create_batch(
            event_ids=event_ids,
            event_hashes=event_hashes,
            sequence_start=batch_events[0].sequence_number,
            sequence_end=batch_events[-1].sequence_number,
        )
        
        self._last_anchored_sequence = batch_events[-1].sequence_number
        
        return batch
    
    def get_anchor_status(self) -> dict:
        """Get current anchoring status."""
        events = self._ledger.get_events()
        batches = self._anchor_service.get_all_batches()
        
        total_events = len(events)
        anchored_events = sum(len(b.event_ids) for b in batches)
        
        return {
            "enabled": self._config.enabled,
            "running": self._running,
            "total_events": total_events,
            "anchored_events": anchored_events,
            "pending_events": total_events - anchored_events,
            "batch_count": len(batches),
            "last_anchored_sequence": self._last_anchored_sequence,
            "batch_size": self._config.batch_size,
            "interval_seconds": self._config.interval_seconds,
        }


# Convenience function for creating a scheduler from app state
def create_anchor_scheduler(ledger: "LedgerService") -> AnchorScheduler:
    """Create an anchor scheduler with default configuration."""
    return AnchorScheduler(ledger=ledger)
