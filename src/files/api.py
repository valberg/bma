"""The API of fileness."""
import logging
import uuid

import magic
from audios.models import Audio
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from documents.models import Document
from guardian.shortcuts import get_objects_for_user
from ninja import Query
from ninja import Router
from ninja.files import UploadedFile
from pictures.models import Picture
from utils.api import FileApiResponseType
from utils.schema import ApiMessageSchema
from videos.models import Video

from .filters import FileFilters
from .models import BaseFile
from .models import FileTypeChoices
from .schema import FileUpdateRequestSchema
from .schema import MultipleFileRequestSchema
from .schema import MultipleFileResponseSchema
from .schema import SingleFileRequestSchema
from .schema import SingleFileResponseSchema
from .schema import UploadRequestSchema

logger = logging.getLogger("bma")


# initialise API router
router = Router()

# https://django-ninja.rest-framework.com/guides/input/query-params/#using-schema
query: Query = Query(...)  # type: ignore[type-arg]


############## UPLOAD #########################################################
@router.post(
    "/upload/",
    response={
        201: SingleFileResponseSchema,
        403: ApiMessageSchema,
        422: ApiMessageSchema,
    },
    summary="Upload a new file.",
)
def upload(request: HttpRequest, f: UploadedFile, metadata: UploadRequestSchema) -> FileApiResponseType:
    """API endpoint for file uploads."""
    # make sure the uploading user is in the creators group
    creator_group, created = Group.objects.get_or_create(name=settings.BMA_CREATOR_GROUP_NAME)
    if creator_group not in request.user.groups.all():  # type: ignore[union-attr]
        return 403, {"message": "Missing upload permissions"}

    # find the filetype using libmagic by reading the first bit of the file
    mime = magic.from_buffer(f.read(512), mime=True)

    if mime in settings.ALLOWED_PICTURE_TYPES:
        from pictures.models import Picture as Model
    elif mime in settings.ALLOWED_VIDEO_TYPES:
        from videos.models import Video as Model
    elif mime in settings.ALLOWED_AUDIO_TYPES:
        from audios.models import Audio as Model
    elif mime in settings.ALLOWED_DOCUMENT_TYPES:
        from documents.models import Document as Model
    else:
        return 422, {"message": "File type not supported"}

    uploaded_file = Model(
        uploader=request.user,  # type: ignore[misc]
        original=f,
        original_filename=str(f.name),
        file_size=f.size,
        **metadata.dict(),
    )

    if not uploaded_file.title:
        # title defaults to the original filename
        uploaded_file.title = uploaded_file.original_filename

    if not uploaded_file.thumbnail_url:
        # thumbnail url was not specified, use the default for the filetype
        uploaded_file.thumbnail_url = settings.DEFAULT_THUMBNAIL_URLS[uploaded_file.filetype]

    try:
        uploaded_file.full_clean()
    except ValidationError:
        return 422, {"message": "Validation error"}

    # save everything
    uploaded_file.save()

    # if the filetype is picture then use the pictures large_thumbnail as thumbnail,
    # this has to be done after .save() to ensure the uuid filename and
    # full path is passed to the imagekit namer
    if (
        uploaded_file.filetype == "picture"
        and uploaded_file.thumbnail_url == settings.DEFAULT_THUMBNAIL_URLS["picture"]
    ):
        # use the large_thumbnail size as default
        uploaded_file.thumbnail_url = uploaded_file.large_thumbnail.url
        uploaded_file.save(update_fields=["thumbnail_url", "updated"])

    # assign permissions (publish_basefile and unpublish_basefile are assigned after moderation)
    uploaded_file.add_initial_permissions()

    # all good
    return 201, {"bma_response": uploaded_file, "message": f"File {uploaded_file.uuid} uploaded OK!"}


############## LIST ###########################################################
@router.get(
    "/",
    response={200: MultipleFileResponseSchema},
    summary="Return a list of metadata for files.",
    auth=None,
)
def file_list(request: HttpRequest, filters: FileFilters = query) -> FileApiResponseType:  # noqa: C901,PLR0912
    """Return a list of metadata for files."""
    # start out with a list of all permitted files and filter from there
    files = BaseFile.bmanager.get_permitted(user=request.user).all()

    if filters.albums:
        files = files.filter(memberships__album__in=filters.albums, memberships__period__contains=timezone.now())

    if filters.approved:
        files = files.filter(approved=filters.approved)

    if filters.published:
        files = files.filter(published=filters.published)

    if filters.deleted:
        files = files.filter(deleted=filters.deleted)

    if filters.filetypes:
        query = Q()
        for filetype in filters.filetypes:
            # this could probably be more clever somehow
            if filetype == FileTypeChoices.picture:
                query |= Q(instance_of=Picture)
            elif filetype == FileTypeChoices.video:
                query |= Q(instance_of=Video)
            elif filetype == FileTypeChoices.audio:
                query |= Q(instance_of=Audio)
            elif filetype == FileTypeChoices.document:
                query |= Q(instance_of=Document)
        files = files.filter(query)

    if filters.uploaders:
        files = files.filter(uploader__in=filters.uploaders)

    if filters.licenses:
        files = files.filter(license__in=filters.licenses)

    if filters.size:
        files = files.filter(file_size=filters.size)

    if filters.size_lt:
        files = files.filter(file_size__lt=filters.size_lt)

    if filters.size_gt:
        files = files.filter(file_size__gt=filters.size_gt)

    if filters.search:
        # we search title and description fields for now
        files = files.filter(title__icontains=filters.search) | files.filter(
            description__icontains=filters.search,
        )

    if filters.sorting:
        if filters.sorting.endswith("_asc"):
            # remove _asc
            files = files.order_by(f"{filters.sorting[:-4]}")
        else:
            # remove _desc and add -
            files = files.order_by(f"-{filters.sorting[:-5]}")

    if filters.offset:
        files = files[filters.offset :]

    if filters.limit:
        files = files[: filters.limit]

    return 200, {"bma_response": files}


############## GENERIC FILE ACTION ############################################
def api_file_action(
    request: HttpRequest,
    file_uuids: list[uuid.UUID] | uuid.UUID,
    permission: str,
    action: str,
    *,
    check: bool,
) -> FileApiResponseType:
    """Perform an action on one or more files."""
    if isinstance(file_uuids, uuid.UUID):
        single = True
        file_uuids = [file_uuids]
    else:
        single = False
    file_filter: dict[str, str | list[str]] = {"uuid__in": [str(u) for u in file_uuids]}
    db_files = get_objects_for_user(request.user, permission, klass=BaseFile.bmanager.filter(**file_filter))
    db_uuids = list(db_files.values_list("uuid", flat=True))
    logger.debug(
        f"user {request.user} wants to {action} {len(file_uuids)} files, has perm {permission} for {len(db_uuids)}"
    )
    if len(file_uuids) != db_files.count():
        errors = len(file_uuids) - db_files.count()
        return 403, {"message": f"No permission to {action} {errors} of {len(file_uuids)} files)"}
    if check:
        return 202, {"message": "OK"}
    updated = getattr(db_files, action)()
    logger.debug(f"{action} {updated} OK")
    db_files = BaseFile.objects.filter(
        uuid__in=db_uuids,
    )
    if single:
        db_files = db_files.get()
    return 200, {"bma_response": db_files, "message": f"{action} {len(db_uuids)} files OK"}


############## APPROVE ########################################################
def approve(request: HttpRequest, uuids: list[uuid.UUID] | uuid.UUID, *, check: bool) -> FileApiResponseType:
    """Approve one or more files."""
    return api_file_action(
        request,
        uuids,
        "approve_basefile",
        action="approve",
        check=check,
    )


@router.patch(
    "/{file_uuid}/approve/",
    response={
        200: SingleFileResponseSchema,
        202: ApiMessageSchema,
        403: ApiMessageSchema,
    },
    summary="Approve a single file.",
)
def approve_file(
    request: HttpRequest, file_uuid: SingleFileRequestSchema, *, check: bool = False
) -> FileApiResponseType:
    """API endpoint to approve a single file."""
    return approve(request, file_uuid.file_uuid, check=check)


@router.patch(
    "/approve/",
    response={
        200: MultipleFileResponseSchema,
        202: ApiMessageSchema,
        403: ApiMessageSchema,
    },
    summary="Approve multiple files.",
)
def approve_files(
    request: HttpRequest, payload: MultipleFileRequestSchema, *, check: bool = False
) -> FileApiResponseType:
    """API endpoint to approve multiple files."""
    uuids = payload.dict()["files"]
    return approve(request, uuids, check=check)


############## UNAPPROVE ######################################################
def unapprove(request: HttpRequest, uuids: list[uuid.UUID] | uuid.UUID, *, check: bool) -> FileApiResponseType:
    """Unapprove one or more files."""
    return api_file_action(
        request,
        uuids,
        "unapprove_basefile",
        action="unapprove",
        check=check,
    )


@router.patch(
    "/{file_uuid}/unapprove/",
    response={
        200: SingleFileResponseSchema,
        202: ApiMessageSchema,
        403: ApiMessageSchema,
    },
    summary="Unapprove a single file.",
)
def unapprove_file(
    request: HttpRequest, file_uuid: SingleFileRequestSchema, *, check: bool = False
) -> FileApiResponseType:
    """API endpoint to unapprove a single file."""
    return unapprove(request, file_uuid.file_uuid, check=check)


@router.patch(
    "/unapprove/",
    response={
        200: MultipleFileResponseSchema,
        202: ApiMessageSchema,
        403: ApiMessageSchema,
    },
    summary="Unapprove multiple files.",
)
def unapprove_files(
    request: HttpRequest, payload: MultipleFileRequestSchema, *, check: bool = False
) -> FileApiResponseType:
    """API endpoint to unapprove multiple files."""
    uuids = payload.dict()["files"]
    return unapprove(request, uuids, check=check)


############## PUBLISH ########################################################
def publish(request: HttpRequest, uuids: list[uuid.UUID] | uuid.UUID, *, check: bool) -> FileApiResponseType:
    """Publish a list of files."""
    return api_file_action(
        request,
        uuids,
        "publish_basefile",
        action="publish",
        check=check,
    )


@router.patch(
    "/{file_uuid}/publish/",
    response={
        200: SingleFileResponseSchema,
        202: ApiMessageSchema,
        403: ApiMessageSchema,
    },
    summary="Publish a single file.",
)
def publish_file(
    request: HttpRequest, file_uuid: SingleFileRequestSchema, *, check: bool = False
) -> FileApiResponseType:
    """API endpoint to publish a single file."""
    return publish(request, file_uuid.file_uuid, check=check)


@router.patch(
    "/publish/",
    response={
        200: MultipleFileResponseSchema,
        202: ApiMessageSchema,
        403: ApiMessageSchema,
    },
    summary="Publish multiple files.",
)
def publish_files(request: HttpRequest, data: MultipleFileRequestSchema, *, check: bool = False) -> FileApiResponseType:
    """Publish multiple files."""
    files = data.dict()["files"]
    return publish(request, files, check=check)


############## UNPUBLISH ########################################################
def unpublish(request: HttpRequest, uuids: list[uuid.UUID] | uuid.UUID, *, check: bool) -> FileApiResponseType:
    """Unpublish a list of files."""
    return api_file_action(
        request,
        uuids,
        "unpublish_basefile",
        action="unpublish",
        check=check,
    )


@router.patch(
    "/{file_uuid}/unpublish/",
    response={
        200: SingleFileResponseSchema,
        202: ApiMessageSchema,
        403: ApiMessageSchema,
    },
    summary="Unpublish a single file.",
)
def unpublish_file(
    request: HttpRequest, file_uuid: SingleFileRequestSchema, *, check: bool = False
) -> FileApiResponseType:
    """API endpoint to unpublish a single file."""
    return unpublish(request, file_uuid.file_uuid, check=check)


@router.patch(
    "/unpublish/",
    response={
        200: MultipleFileResponseSchema,
        202: ApiMessageSchema,
        403: ApiMessageSchema,
    },
    summary="Unpublish multiple files.",
)
def unpublish_files(
    request: HttpRequest, data: MultipleFileRequestSchema, *, check: bool = False
) -> FileApiResponseType:
    """Unpublish multple files."""
    files = data.dict()["files"]
    return unpublish(request, files, check=check)


############## METADATA #######################################################
@router.get(
    "/{file_uuid}/",
    response={
        200: SingleFileResponseSchema,
        403: ApiMessageSchema,
        404: ApiMessageSchema,
    },
    summary="Return the metadata of a file.",
    auth=None,
)
def file_get(request: HttpRequest, file_uuid: uuid.UUID) -> FileApiResponseType:
    """Return a file object."""
    basefile = get_object_or_404(BaseFile, uuid=file_uuid)
    if basefile.permitted(user=request.user):
        return 200, {"bma_response": basefile}
    return 403, {"message": "Permission denied."}


@router.put(
    "/{file_uuid}/",
    response={
        200: SingleFileResponseSchema,
        202: ApiMessageSchema,
        403: ApiMessageSchema,
        404: ApiMessageSchema,
        422: ApiMessageSchema,
    },
    operation_id="files_api_file_update_put",
    summary="Replace the metadata of a file.",
)
@router.patch(
    "/{file_uuid}/",
    response={
        200: SingleFileResponseSchema,
        202: ApiMessageSchema,
        403: ApiMessageSchema,
        404: ApiMessageSchema,
        422: ApiMessageSchema,
    },
    operation_id="files_api_file_update_patch",
    summary="Update the metadata of a file.",
)
def file_update(
    request: HttpRequest,
    file_uuid: uuid.UUID,
    metadata: FileUpdateRequestSchema,
    *,
    check: bool = False,
) -> FileApiResponseType:
    """Update (PATCH) or replace (PUT) a file metadata object."""
    basefile = get_object_or_404(BaseFile, uuid=file_uuid)
    if not request.user.has_perm("change_basefile", basefile):
        return 403, {"message": "Permission denied."}
    if check:
        # check mode requested, don't change anything
        return 202, {"message": "OK"}
    if request.method == "PATCH":
        try:
            with transaction.atomic():
                # we are updating the object, we do not want defaults for absent fields
                BaseFile.objects.filter(uuid=basefile.uuid).update(
                    **metadata.dict(exclude_unset=True), updated=timezone.now()
                )
                basefile.refresh_from_db()
                basefile.full_clean()
        except ValidationError:
            return 422, {"message": "Validation error"}
    else:
        try:
            with transaction.atomic():
                # we are replacing the object, we do want defaults for absent fields
                BaseFile.objects.filter(uuid=basefile.uuid).update(
                    **metadata.dict(exclude_unset=False), updated=timezone.now()
                )
                basefile.refresh_from_db()
                basefile.full_clean()
        except ValidationError:
            return 422, {"message": "Validation error"}
    return 200, {"bma_response": basefile, "message": "File updated."}


############## DELETE #########################################################
@router.delete(
    "/{file_uuid}/",
    response={
        204: None,
        202: ApiMessageSchema,
        403: ApiMessageSchema,
        404: ApiMessageSchema,
    },
    summary="Soft-delete a file.",
)
def file_delete(
    request: HttpRequest, file_uuid: uuid.UUID, *, check: bool = False
) -> tuple[int, dict[str, str] | None]:
    """Mark a file for deletion."""
    basefile = get_object_or_404(BaseFile, uuid=file_uuid)
    if not request.user.has_perm("softdelete_basefile", basefile):
        return 403, {"message": "Permission denied."}
    if check:
        # check mode requested, don't change anything
        return 202, {"message": "OK"}
    # ok go but we don't let users fully delete files for now
    basefile.softdelete()
    return 204, None
