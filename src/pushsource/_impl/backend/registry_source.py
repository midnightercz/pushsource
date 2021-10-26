import logging

from ..source import Source
from ..model import (
    ContainerImagePushItem,
    SourceContainerImagePushItem,
    ContainerImagePullInfo,
    ContainerImageTagPullSpec,
    ContainerImageDigestPullSpec,
)
from ..utils.containers import (
    get_manifest,
    inspect,
    MT_S2_V2,
    MT_S2_V1,
    MT_S2_V1_SIGNED,
    MT_S2_LIST,
)

from ..helpers import list_argument

LOG = logging.getLogger("pushsource")


class RegistrySource(Source):
    """Uses URIs of container images as source for push items."""

    def __init__(
        self,
        image,
        dest=None,
        dest_signing_key=None,
    ):
        """Create a new source.

        Parameters:
            reposs str,
                Comma separated string with destination(s) repo(s) to fill in for push
                items created by this source. If omitted, all push items have
                empty destinations.

            image (list[str])
                String with references to container images with tags+dest tags
                Format <scheme>:<host>/<namespace>/<repo>:<tag>:<destination_tag>:<destination_tag>
                Example: https:registry.redhat.io/ubi:8:latest:8:8.1

            signing_key (list[str])
                GPG signing key ID(s). If provided, will be signed with those.
        """
        self._images = ["https://%s" % x for x in image.split(",")]
        self._repos = dest.split(",")
        self._signing_keys = list_argument(dest_signing_key)
        self._inspected = {}
        self._manifests = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def _push_item_from_registry_uri(self, uri, signing_key):
        schema, rest = uri.split("://")
        host, rest = rest.split("/", 1)
        repo, src_tag = rest.split(":", 1)
        source_uri = "%s/%s:%s" % (host, repo, src_tag)
        if source_uri not in self._inspected:
            self._inspected[source_uri] = inspect(
                "%s://%s" % (schema, host), repo, src_tag
            )
        if self._inspected[source_uri].get("source"):
            klass = SourceContainerImagePushItem
        else:
            klass = ContainerImagePushItem

        if source_uri not in self._manifests:
            manifest_details = get_manifest(
                "%s://%s" % (schema, host),
                repo,
                src_tag,
                manifest_types=[MT_S2_LIST],
            )
            self._manifests[source_uri] = manifest_details
        manifest_details = self._manifests[source_uri]
        content_type, _, _ = manifest_details
        if content_type not in [MT_S2_V2, MT_S2_V1, MT_S2_V1_SIGNED, MT_S2_LIST]:
            raise ValueError("Unsupported manifest type:%s" % content_type)

        pull_info = ContainerImagePullInfo(
            digest_specs=[
                ContainerImageDigestPullSpec(
                    registry=host,
                    repository=repo,
                    digest=self._inspected[source_uri]["digest"],
                    media_type=content_type,
                )
            ],
            media_types=[content_type],
            tag_specs=[
                ContainerImageTagPullSpec(
                    registry=host,
                    repository=repo,
                    tag=src_tag,
                    media_types=[content_type],
                )
            ],
        )
        return klass(
            name=source_uri,
            dest=self._repos,
            dest_signing_key=signing_key,
            src=source_uri,
            source_tags=[src_tag],
            labels=self._inspected[source_uri].get("config").get("labels", {}),
            arch=(self._inspected[source_uri].get("config", {}) or {})
            .get("labels", {})
            .get("architecture"),
            pull_info=pull_info,
        )

    def __iter__(self):
        for key in self._signing_keys:
            for uri in self._images:
                yield self._push_item_from_registry_uri(uri, key)


Source._register_backend_builtin("registry", RegistrySource)
