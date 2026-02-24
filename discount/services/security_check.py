"""
Plan-based API security: verify store/user has access before calling expensive APIs.
Zero-bypass: always enforced server-side at execution time.
"""
import logging
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

# Feature names must match Plan.FEATURE_FIELDS keys
FEATURE_AI_VOICE = "ai_voice"
FEATURE_VOICE_CLONING = "voice_cloning"
FEATURE_AUTO_REPLY = "auto_reply"
FEATURE_MULTI_MODAL = "multi_modal"
FEATURE_PERSONA_GALLERY = "persona_gallery"


def verify_plan_access(store, feature_required):
    """
    Before any call to an external paid API (ElevenLabs, OpenAI TTS, AI auto-reply),
    call this. If the store's plan does not allow the feature, raises PermissionDenied.

    Args:
        store: CustomUser (channel owner / account) that has .get_plan() and .is_feature_allowed().
        feature_required: str, one of FEATURE_AI_VOICE, FEATURE_VOICE_CLONING, FEATURE_AUTO_REPLY.

    Raises:
        PermissionDenied: if store has no plan or plan does not allow the feature.
    """
    if not store:
        logger.warning("verify_plan_access: no store provided for feature %s", feature_required)
        raise PermissionDenied("Account not found. Upgrade your plan to use this feature.")

    if hasattr(store, "is_feature_allowed"):
        if not store.is_feature_allowed(feature_required):
            logger.info("Plan access denied: store id=%s, feature=%s", getattr(store, "id", None), feature_required)
            raise PermissionDenied(
                "This feature is not included in your plan. Upgrade to Premium to unlock."
            )
        return

    # Fallback if store is a plan instance (e.g. in tests)
    if hasattr(store, "can_use_feature") and callable(store.can_use_feature):
        if not store.can_use_feature(feature_required):
            raise PermissionDenied("This feature is not included in your plan.")
        return

    logger.warning("verify_plan_access: store has no is_feature_allowed, denying feature %s", feature_required)
    raise PermissionDenied("Plan verification failed. Upgrade to use this feature.")
