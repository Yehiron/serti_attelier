import pytest
from django.test import Client

from apps.core.models import SiteSettings


@pytest.mark.django_db
def test_seo_settings_defaults_and_public_contract():
    settings = SiteSettings.objects.create()
    assert len(settings.seo_home_description_es) <= 160
    assert len(settings.seo_home_description_en) <= 160
    assert settings.business_locality == "Armenia"
    assert settings.business_region == "Quindío"
    assert settings.business_country == "CO"
    assert settings.appointment_only is True
    assert settings.service_area == "Colombia"
    assert settings.opening_hours_es and settings.opening_hours_en
    assert settings.seo_home_title_es and settings.seo_home_title_en
    response = Client().get("/api/v1/site/settings", {"locale": "es"})
    assert response.status_code == 200
    data = response.json()
    assert data["seo_home_description"] == settings.seo_home_description_es
    assert data["business_locality"] == "Armenia"
    assert "streetAddress" not in data and "geo" not in data
