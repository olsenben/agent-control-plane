def log_reward(run_id: str, metadata: dict) -> dict:
    return {"schema": "agent.reward.v1", "run_id": run_id, **metadata, "status": "stub"}
