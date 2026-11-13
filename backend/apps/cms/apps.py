from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cms"
    verbose_name = _("Contenido")

    def ready(self):
        from django.db.models.signals import m2m_changed, post_delete, post_save

        from apps.catalog.models import (
            Category,
            Collection,
            CollectionPiece,
            Piece,
            PieceImage,
            Stone,
        )
        from apps.core.models import SiteSettings

        from .invalidation import catalog_relations_changed, live_saved, publication_saved
        from .models import (
            BrandPublication,
            HomePublication,
            MenuPublication,
            PageRevision,
            PersonalizationService,
        )

        for model in (HomePublication, PageRevision, MenuPublication, BrandPublication):
            post_save.connect(
                publication_saved, sender=model, dispatch_uid=f"cms.publish.{model.__name__}"
            )
        for model in (
            SiteSettings,
            PersonalizationService,
            Category,
            Collection,
            Stone,
            Piece,
            PieceImage,
            CollectionPiece,
        ):
            post_save.connect(live_saved, sender=model, dispatch_uid=f"cms.live.{model.__name__}")
            post_delete.connect(
                live_saved, sender=model, dispatch_uid=f"cms.delete.{model.__name__}"
            )

        for relation in (Piece.collections, Piece.stones, Piece.materials):
            m2m_changed.connect(
                catalog_relations_changed,
                sender=relation.through,
                dispatch_uid=f"cms.relations.{relation.through._meta.label}",
            )
