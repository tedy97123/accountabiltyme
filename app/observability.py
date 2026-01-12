"""
Observability Module - Logging, Metrics, and Tracing

Provides:
- Structured JSON logging with request IDs
- Request/response logging middleware
- Metrics collection (append latency, event counts, etc.)
- Health check utilities

Configuration:
- ACCOUNTABILITYME_LOG_LEVEL: DEBUG, INFO, WARNING, ERROR (default: INFO)
- ACCOUNTABILITYME_LOG_FORMAT: json, text (default: json in production)
- ACCOUNTABILITYME_PRODUCTION: Enable production mode

Usage:
    from app.observability import get_logger, RequestContextMiddleware
    
    logger = get_logger(__name__)
    logger.info("Processing claim", claim_id=str(claim_id), action="declare")
"""

import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# Context variables for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
editor_id_var: ContextVar[str] = ContextVar("editor_id", default="")


# ============================================================
# CONFIGURATION
# ============================================================

def _is_production() -> bool:
    return os.environ.get("ACCOUNTABILITYME_PRODUCTION", "").lower() in ("1", "true", "yes")


def _get_log_level() -> int:
    level_str = os.environ.get("ACCOUNTABILITYME_LOG_LEVEL", "INFO").upper()
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return levels.get(level_str, logging.INFO)


def _use_json_logging() -> bool:
    format_str = os.environ.get("ACCOUNTABILITYME_LOG_FORMAT", "").lower()
    if format_str == "json":
        return True
    if format_str == "text":
        return False
    return _is_production()


# ============================================================
# STRUCTURED LOGGING
# ============================================================

class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    
    Output format:
    {
        "timestamp": "2024-01-15T10:30:00.000Z",
        "level": "INFO",
        "logger": "app.api.routes_editor",
        "message": "Processing claim",
        "request_id": "abc-123",
        "editor_id": "uuid-456",
        "claim_id": "uuid-789",
        ...extra fields...
    }
    """
    
    def format(self, record: logging.LogRecord) -> str:
        import json
        
        # Base log data
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add request context if available
        request_id = request_id_var.get()
        if request_id:
            log_data["request_id"] = request_id
        
        editor_id = editor_id_var.get()
        if editor_id:
            log_data["editor_id"] = editor_id
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "created", "levelname", "levelno",
                "pathname", "filename", "module", "lineno", "funcName",
                "exc_info", "exc_text", "stack_info", "message"
            ):
                # Skip private attributes and standard LogRecord fields
                if not key.startswith("_"):
                    try:
                        # Ensure JSON serializable
                        json.dumps(value)
                        log_data[key] = value
                    except (TypeError, ValueError):
                        log_data[key] = str(value)
        
        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Human-readable formatter for development."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Add request context to message
        prefix = ""
        request_id = request_id_var.get()
        if request_id:
            prefix = f"[{request_id[:8]}] "
        
        # Format timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        # Base message
        msg = f"{timestamp} {record.levelname:8} {prefix}{record.name}: {record.getMessage()}"
        
        # Add exception if present
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        
        return msg


class ContextLogger(logging.LoggerAdapter):
    """
    Logger adapter that automatically includes context fields.
    
    Usage:
        logger = get_logger(__name__)
        logger.info("Claim declared", claim_id=str(claim_id), status="declared")
    """
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        # Extract extra fields from kwargs
        extra = kwargs.get("extra", {})
        
        # Move non-standard kwargs to extra
        for key in list(kwargs.keys()):
            if key not in ("exc_info", "stack_info", "stacklevel", "extra"):
                extra[key] = kwargs.pop(key)
        
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str) -> ContextLogger:
    """
    Get a structured logger for the given name.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        ContextLogger instance with structured output
    """
    logger = logging.getLogger(name)
    return ContextLogger(logger, {})


def setup_logging() -> None:
    """
    Configure logging for the application.
    
    Call this once at application startup.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(_get_log_level())
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create handler with appropriate formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(_get_log_level())
    
    if _use_json_logging():
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(TextFormatter())
    
    root_logger.addHandler(handler)
    
    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# ============================================================
# REQUEST CONTEXT MIDDLEWARE
# ============================================================

class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that sets up request context for logging.
    
    Features:
    - Generates unique request ID for each request
    - Logs request/response with timing
    - Extracts editor ID from session if available
    """
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: RequestResponseEndpoint
    ) -> Response:
        # Generate request ID (use X-Request-ID header if provided)
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request_id_var.set(request_id)
        
        # Extract editor ID from session cookie if available
        from app.web.auth import read_session_cookie, SESSION_COOKIE
        cookie_val = request.cookies.get(SESSION_COOKIE)
        if cookie_val:
            session = read_session_cookie(cookie_val)
            if session:
                editor_id_var.set(session.editor_id)
        
        # Log request
        logger = get_logger("app.request")
        start_time = time.perf_counter()
        
        logger.debug(
            f"{request.method} {request.url.path}",
            method=request.method,
            path=request.url.path,
            query=str(request.query_params) if request.query_params else None,
            client_ip=request.client.host if request.client else None,
        )
        
        try:
            response = await call_next(request)
            
            # Log response
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_level = logging.INFO if response.status_code < 400 else logging.WARNING
            
            logger.log(
                log_level,
                f"{request.method} {request.url.path} -> {response.status_code}",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                f"{request.method} {request.url.path} -> 500",
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=round(duration_ms, 2),
                error=str(e),
            )
            raise
        
        finally:
            # Clear context
            request_id_var.set("")
            editor_id_var.set("")


# ============================================================
# METRICS
# ============================================================

@dataclass
class MetricsCollector:
    """
    Simple in-memory metrics collector.
    
    For production, replace with Prometheus, StatsD, or similar.
    """
    
    # Counters
    events_appended: int = 0
    requests_total: int = 0
    requests_failed: int = 0
    login_attempts: int = 0
    login_failures: int = 0
    
    # Gauges
    active_sessions: int = 0
    
    # Histograms (simplified as lists)
    append_latencies_ms: list = field(default_factory=list)
    request_latencies_ms: list = field(default_factory=list)
    
    def record_append(self, latency_ms: float) -> None:
        """Record an event append."""
        self.events_appended += 1
        self.append_latencies_ms.append(latency_ms)
        # Keep only last 1000 samples
        if len(self.append_latencies_ms) > 1000:
            self.append_latencies_ms = self.append_latencies_ms[-1000:]
    
    def record_request(self, latency_ms: float, success: bool) -> None:
        """Record a request."""
        self.requests_total += 1
        if not success:
            self.requests_failed += 1
        self.request_latencies_ms.append(latency_ms)
        if len(self.request_latencies_ms) > 1000:
            self.request_latencies_ms = self.request_latencies_ms[-1000:]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        def percentile(data: list, p: float) -> Optional[float]:
            if not data:
                return None
            sorted_data = sorted(data)
            idx = int(len(sorted_data) * p)
            return sorted_data[min(idx, len(sorted_data) - 1)]
        
        return {
            "events_appended": self.events_appended,
            "requests_total": self.requests_total,
            "requests_failed": self.requests_failed,
            "login_attempts": self.login_attempts,
            "login_failures": self.login_failures,
            "active_sessions": self.active_sessions,
            "append_latency_p50_ms": percentile(self.append_latencies_ms, 0.5),
            "append_latency_p95_ms": percentile(self.append_latencies_ms, 0.95),
            "append_latency_p99_ms": percentile(self.append_latencies_ms, 0.99),
            "request_latency_p50_ms": percentile(self.request_latencies_ms, 0.5),
            "request_latency_p95_ms": percentile(self.request_latencies_ms, 0.95),
        }


# Global metrics instance
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector."""
    return _metrics


# ============================================================
# HEALTH CHECKS
# ============================================================

@dataclass
class HealthStatus:
    """Health check result."""
    healthy: bool
    checks: Dict[str, Dict[str, Any]]
    duration_ms: float


def check_health(ledger=None, event_store=None) -> HealthStatus:
    """
    Run all health checks.
    
    Args:
        ledger: LedgerService instance
        event_store: EventStore instance
        
    Returns:
        HealthStatus with all check results
    """
    start = time.perf_counter()
    checks = {}
    all_healthy = True
    
    # Check 1: Basic liveness
    checks["liveness"] = {"status": "healthy"}
    
    # Check 2: Event store
    if event_store:
        try:
            head = event_store.get_head()
            checks["event_store"] = {
                "status": "healthy",
                "event_count": head.next_sequence,
                "last_hash": head.last_event_hash[:16] + "..." if head.last_event_hash else None,
            }
        except Exception as e:
            checks["event_store"] = {
                "status": "unhealthy",
                "error": str(e),
            }
            all_healthy = False
    
    # Check 3: Chain integrity (expensive, only if explicitly requested)
    if ledger and ledger.event_count > 0:
        try:
            is_valid = ledger.verify_chain_integrity()
            checks["chain_integrity"] = {
                "status": "healthy" if is_valid else "unhealthy",
                "valid": is_valid,
                "event_count": ledger.event_count,
            }
            if not is_valid:
                all_healthy = False
        except Exception as e:
            checks["chain_integrity"] = {
                "status": "unhealthy",
                "error": str(e),
            }
            all_healthy = False
    
    duration_ms = (time.perf_counter() - start) * 1000
    
    return HealthStatus(
        healthy=all_healthy,
        checks=checks,
        duration_ms=round(duration_ms, 2),
    )
