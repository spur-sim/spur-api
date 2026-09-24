from typing import Any

from fastapi import APIRouter, Body
from pydantic import ValidationError

from spur.validation import ValidationResult, issues_from_validation_error, validate

from spur_api.schemas.project import ProjectEnvelope

router = APIRouter(prefix="/v1/validate", tags=["validate"])


@router.post("")
def validate_project(body: Any = Body(default=None)) -> ValidationResult:
    """Check a project without saving it, reporting every problem at once.

    Accepts any JSON, so an editor can check a draft that isn't valid yet.
    Always returns 200: an invalid project is a result, not an error. A
    project is valid if `POST /v1/projects` would accept it *and* it has no
    structural errors (unknown types, dangling references, duplicates, ...);
    saving itself only requires the former, so drafts can be saved.
    """
    result = validate(body)
    if not isinstance(body, dict):
        return result

    try:
        ProjectEnvelope.model_validate(body)
    except ValidationError as e:
        issues = issues_from_validation_error(e) + result.issues
        return ValidationResult(valid=False, issues=issues)
    return result
