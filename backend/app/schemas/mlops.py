# backend/app/schemas/mlops.py
from pydantic import BaseModel


class MLOpsStatusResponse(BaseModel):
    is_training: bool
    last_run: str | None
    last_status: str
    logs: list[str]
