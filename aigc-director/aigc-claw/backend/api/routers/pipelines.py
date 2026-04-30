from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.schemas.pipelines import (
    ActionTransferPipelineRequest,
    DigitalHumanPipelineRequest,
    GenericPipelineRequest,
    StandardPipelineRequest,
)
from pipelines.api_media import list_api_workflows
from pipelines.events import task_event_stream
from pipelines.runner import PIPELINE_REGISTRY, run_pipeline_task
from pipelines.storage import create_task, delete_task, list_tasks, load_task

router = APIRouter(tags=["Pipelines"])


def _start_task(background_tasks: BackgroundTasks, pipeline: str, params: dict):
    if pipeline not in PIPELINE_REGISTRY:
        raise HTTPException(404, f"Pipeline not found: {pipeline}")
    metadata = create_task(pipeline=pipeline, input_params=params)
    background_tasks.add_task(run_pipeline_task, metadata["task_id"], pipeline, params)
    return {
        "task_id": metadata["task_id"],
        "pipeline": pipeline,
        "status": metadata["status"],
        "metadata_url": f"/api/tasks/{metadata['task_id']}",
        "output_dir": metadata["output_dir"],
    }


@router.get("/api/pipelines")
async def get_pipelines():
    return {
        "pipelines": [
            {
                "id": "standard",
                "aliases": ["quick_create"],
                "name": "Artistic Short Video",
                "description": "Split narration by periods, generate one image per segment, and assemble either an image-concat short video or dynamic image-to-video clips.",
            },
            {
                "id": "action_transfer",
                "name": "Action Transfer",
                "description": "Use an image, a reference video, and a prompt to call an API video-edit/action-transfer model.",
            },
            {
                "id": "digital_human",
                "name": "Digital Human",
                "description": "Generate a talking-head/product-promotion video with API reference-to-video models.",
            },
        ]
    }


@router.get("/api/pipelines/api-workflows")
async def get_api_workflows(
    media_type: Optional[str] = Query(None, pattern="^(image|video)$"),
    ability: Optional[str] = Query(None),
    verified_only: bool = False,
):
    required = [ability] if ability else None
    return {
        "workflows": list_api_workflows(
            media_type=media_type,
            required_adapter_abilities=required,
            verified_only=verified_only,
        )
    }


@router.get("/api/models")
async def get_api_models(
    media_type: Optional[str] = Query(None, pattern="^(image|video)$"),
    ability: Optional[str] = Query(None),
    verified_only: bool = False,
):
    required = [ability] if ability else None
    workflows = list_api_workflows(
        media_type=media_type,
        required_adapter_abilities=required,
        verified_only=verified_only,
    )
    return {
        "models": [
            {
                "id": workflow["model"],
                "label": workflow.get("display_name") or workflow["model"],
                "provider": workflow.get("provider"),
                "media_type": workflow.get("media_type"),
                "ability_type": workflow.get("ability_type"),
                "ability_types": workflow.get("ability_types", []),
                "adapter_ability_types": workflow.get("adapter_ability_types", []),
                "input_modalities": workflow.get("input_modalities", []),
                "adapter_input_modalities": workflow.get("adapter_input_modalities", []),
                "api_contract_verified": workflow.get("api_contract_verified", False),
                "capabilities": workflow.get("capabilities", {}),
            }
            for workflow in workflows
        ]
    }


@router.post("/api/pipelines/standard/tasks")
async def start_standard_pipeline(req: StandardPipelineRequest, background_tasks: BackgroundTasks):
    return _start_task(background_tasks, "standard", req.model_dump(exclude_none=True))


@router.post("/api/pipelines/action_transfer/tasks")
async def start_action_transfer_pipeline(req: ActionTransferPipelineRequest, background_tasks: BackgroundTasks):
    return _start_task(background_tasks, "action_transfer", req.model_dump(exclude_none=True))


@router.post("/api/pipelines/digital_human/tasks")
async def start_digital_human_pipeline(req: DigitalHumanPipelineRequest, background_tasks: BackgroundTasks):
    return _start_task(background_tasks, "digital_human", req.model_dump(exclude_none=True))


@router.post("/api/pipelines/{pipeline}/tasks")
async def start_generic_pipeline(pipeline: str, req: GenericPipelineRequest, background_tasks: BackgroundTasks):
    normalized = "standard" if pipeline == "quick_create" else pipeline
    return _start_task(background_tasks, normalized, req.params)


@router.get("/api/tasks")
async def get_tasks(limit: int = Query(100, ge=1, le=500)):
    return {"tasks": list_tasks(limit=limit)}


@router.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    metadata = load_task(task_id)
    if not metadata:
        raise HTTPException(404, "Task not found")
    return metadata


@router.delete("/api/tasks/{task_id}")
async def remove_task(task_id: str):
    if not delete_task(task_id):
        raise HTTPException(404, "Task not found")
    return {"success": True}


@router.get("/api/tasks/{task_id}/events")
async def subscribe_task_events(task_id: str):
    metadata = load_task(task_id)
    if not metadata:
        raise HTTPException(404, "Task not found")
    initial_event = {
        "type": "snapshot",
        "task_id": task_id,
        "status": metadata.get("status"),
        "progress": metadata.get("progress", 0),
    }
    return StreamingResponse(
        task_event_stream(task_id, initial_event=initial_event),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
