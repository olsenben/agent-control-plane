"""Transaction-control production package. Broker/UI wiring lives elsewhere."""

from agent_control.transaction.admission.pin import FROZEN_C_HASH, verify_frozen_c_pin
from agent_control.transaction.config import TransactionControlConfig, load_transaction_control_config

__all__ = [
    "FROZEN_C_HASH",
    "TransactionControlConfig",
    "load_transaction_control_config",
    "verify_frozen_c_pin",
]
