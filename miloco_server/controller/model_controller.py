# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Third-party model controller
Implements CRUD interfaces for third-party models
"""

from fastapi import APIRouter, Depends
from miloco_server.service.manager import get_manager
from miloco_server.schema.common_schema import NormalResponse
from miloco_server.schema.model_schema import ModelsList, ThirdPartyModelCreate, ThirdPartyModelInfo, ThirdPartyModelVendor, ModelPurposeInfo, ModelLoadRequest
from miloco_server.middleware import verify_token
import logging
from miloco_server.utils.local_models import ModelPurpose
from typing import Optional

logger = logging.getLogger(name=__name__)

router = APIRouter(prefix="/model", tags=["Models"])

manager = get_manager()


@router.post("", summary="Create third-party model", response_model=NormalResponse)
async def create_third_party_model(
    model: ThirdPartyModelCreate,
    current_user: str = Depends(verify_token)
):
    """
    Create third-party model
    - Requires admin permissions
    - Model name must be unique
    """
    logger.info("Create third party model API called - User: %s, Model names: %s", current_user, model.model_names)
    model_id = await manager.model_service.create_third_party_model(model)
    logger.info("Third party model created successfully - Model ID: %s", model_id)
    return NormalResponse(
        code=0,
        message="Third-party model created successfully",
        data={"model_id": model_id}
    )


@router.get("", summary="Get all models", response_model=NormalResponse)
async def get_all_models(
    current_user: str = Depends(verify_token)
):
    """
    Get all third-party models
    - Requires login
    """
    logger.info("Get all third party models API called - User: %s", current_user)

    models: ModelsList = await manager.model_service.get_all_models()

    logger.info("Third party models list retrieved successfully - Count: %s", len(models.models))
    return NormalResponse(
        code=0,
        message=f"Third-party models retrieved successfully, total {len(models.models)} records",
        data=models
    )


@router.get("/model_purposes", summary="Get all model purpose types", response_model=NormalResponse)
async def get_all_model_purposes(
    current_user: str = Depends(verify_token)
):
    """
    Get all model purpose types
    - Requires login
    """
    logger.info("Get all model purposes API called - User: %s", current_user)

    purposes = [ModelPurposeInfo(type=purpose.value) for purpose in ModelPurpose]
    return NormalResponse(
        code=0,
        message="Model purpose types retrieved successfully",
        data=purposes
    )


@router.put("/{model_id}", summary="Update third-party model", response_model=NormalResponse)
async def update_third_party_model(model_id: str,
                                   model: ThirdPartyModelInfo,
                                   current_user: str = Depends(verify_token)):
    """
    Update third-party model
    - Requires admin permissions
    - Model name must be unique (cannot conflict with other models)
    """
    logger.info(
        "Update third party model API called - User: %s, Model ID: %s", current_user, model_id
    )
    model.id = model_id
    await manager.model_service.update_third_party_model(model)

    logger.info(
        "Third party model updated successfully - Model ID: %s", model_id)
    return NormalResponse(code=0, message="Third-party model updated successfully", data=None)


@router.delete("/{model_id}", summary="Delete third-party model", response_model=NormalResponse)
async def delete_third_party_model(
    model_id: str,
    current_user: str = Depends(verify_token)
):
    """
    Delete third-party model
    - Requires admin permissions
    """
    logger.info(
        "Delete third party model API called - User: %s, Model ID: %s", current_user, model_id)

    manager.model_service.delete_third_party_model(model_id)

    logger.info(
        "Third party model deleted successfully - Model ID: %s", model_id)
    return NormalResponse(
        code=0,
        message="Third-party model deleted successfully",
        data=None
    )

@router.post("/get_vendor_models", summary="Get vendor models", response_model=NormalResponse)
async def get_vendor_models(
    request: ThirdPartyModelVendor,
    current_user: str = Depends(verify_token)
):
    """
    Get vendor models
    - Requires login
    - Pass vendor API base_url and api_key
    """
    logger.info("Get vendor models API called - User: %s, base_url: %s", current_user, request.base_url)

    # Call manager to get vendor models
    result = await manager.model_service.get_vendor_models(request.base_url, request.api_key)

    count = result.get("count", 0)
    logger.info("Vendor models retrieved successfully - Count: %s", count)
    return NormalResponse(
        code=0,
        message=f"Vendor models retrieved successfully, total {count} models",
        data=result
    )


@router.get("/set_current_model",
           summary="Set current model for purpose scenario", response_model=NormalResponse)
async def set_current_model(purpose: str,
                            model_id: Optional[str] = None,
                            current_user: str = Depends(verify_token)):
    """
    Set current model for purpose scenario
    - Requires admin permissions
    - model_id: Optional, if not provided, will clear the model for this purpose
    """
    logger.info("Set current model API called - User: %s, Model ID: %s",
                current_user, model_id if model_id else "None")

    purpose = ModelPurpose(purpose)
    await manager.model_service.set_current_model(model_id, purpose)

    logger.info("Current model set successfully - Model ID: %s, Purpose: %s",
                model_id if model_id else "None", purpose)
    return NormalResponse(code=0, message="Current model set successfully", data=None)


@router.post("/load", summary="load/unload local model", response_model=NormalResponse)
async def load_or_unload_local_model(request: ModelLoadRequest,
                                     current_user: str = Depends(verify_token)
                                     ):
    """
    load/unload local model
    - Requires admin permissions
    - loaded: True to load, False to unload
    - model_name: model name
    """
    logger.info(
        "Load or unload local model API called - User: %s, Model ID: %s, Loaded: %s",
        current_user, request.local_model_name, request.load)

    await manager.model_service.load_or_unload_local_model(request.local_model_name, request.load)
    return NormalResponse(code=0, message="Load/Unload local model successfully", data=None)


@router.get("/get_cuda_info", summary="get CUDA info", response_model=NormalResponse)
async def get_cuda_info(current_user: str = Depends(verify_token)):
    """
    get CUDA info
    - Requires admin permissions
    """
    logger.info("Get CUDA info API called - User: %s", current_user)
    result = await manager.model_service.get_local_cuda_info()
    return NormalResponse(code=0, message="Get CUDA info successfully", data=result)
