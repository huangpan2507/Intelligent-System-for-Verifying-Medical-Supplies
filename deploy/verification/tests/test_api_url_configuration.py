import httpx
import pytest
from langflow.verification.configuration import ManifestConfiguration, RecognitionConfiguration
from langflow.verification.pipeline import Pipeline
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("configuration", "values"),
    [
        (RecognitionConfiguration, {"model_api_url": "file:///tmp/model"}),
        (RecognitionConfiguration, {"model_api_url": "/v1/recognitions"}),
        (RecognitionConfiguration, {"model_api_url": "https://user:password@model.test/api"}),
        (RecognitionConfiguration, {"model_api_url": "https://model.test/api#fragment"}),
        (RecognitionConfiguration, {"model_api_url": "https://model.test/{request_id}"}),
        (RecognitionConfiguration, {"model_api_url": "https://model.test/has space"}),
        (ManifestConfiguration, {"series_url": "https://imaging.test/series"}),
        (ManifestConfiguration, {"series_url": "https://imaging.test/{series_id}"}),
        (ManifestConfiguration, {"images_url": "https://imaging.test/{study_id}"}),
        (ManifestConfiguration, {"images_url": "https://{series_id}.test/images"}),
        (ManifestConfiguration, {"images_url": "https://imaging.test/{series_id.__class__}"}),
        (ManifestConfiguration, {"images_url": "https://imaging.test/{series_id!r}"}),
        (ManifestConfiguration, {"images_url": "https://imaging.test/{series_id:>10}"}),
        (ManifestConfiguration, {"images_url": "https://imaging.test/{series_id"}),
    ],
)
def test_invalid_endpoint_configuration(configuration, values):
    with pytest.raises(ValidationError):
        configuration.model_validate(values)


def test_endpoint_templates_support_query_ids_and_blank_fallback():
    configuration = ManifestConfiguration(
        series_url=" https://imaging.test/api/series?study={study_id} ",
        images_url="https://imaging.test/api/images?series={series_id}",
    )
    assert configuration.series_url == "https://imaging.test/api/series?study={study_id}"
    assert ManifestConfiguration(series_url="  ").series_url == ""
    assert RecognitionConfiguration(model_api_url="  ").model_api_url == ""


@pytest.mark.parametrize(
    ("url", "authenticated"),
    [
        ("http://upstream/custom/model", True),
        ("http://upstream:80/custom/model", True),
        ("http://different-service/model", False),
        ("http://upstream:8080/model", False),
        ("https://upstream/model", False),
    ],
)
async def test_url_override_does_not_forward_deployment_token_to_other_origins(settings, url, authenticated):
    requests = []

    def receive(request):
        requests.append(request)
        return httpx.Response(200, json={"items": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as http:
        await Pipeline(settings, http).upstream(settings.imaging_url, "", url=url)
    assert len(requests) == 1
    assert str(requests[0].url) == str(httpx.URL(url))
    assert ("authorization" in requests[0].headers) is authenticated
