from __future__ import annotations

from app.main import app


def _schema() -> dict:
    app.openapi_schema = None
    return app.openapi()


class TestOpenAPIContract:
    def test_repair_submit_documents_supported_request_bodies_and_errors(self) -> None:
        operation = _schema()["paths"]["/api/v1/repair-requests"]["post"]

        request_content = operation["requestBody"]["content"]
        assert {
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
        }.issubset(request_content)
        multipart_schema = request_content["multipart/form-data"]["schema"]
        assert {"asset_id", "fault_description"}.issubset(multipart_schema["required"])
        assert "images" in multipart_schema["properties"]

        response_codes = set(operation["responses"])
        assert {"201", "401", "403", "404", "409", "413", "415", "422", "503"}.issubset(
            response_codes
        )

    def test_image_endpoint_documents_binary_image_response(self) -> None:
        operation = _schema()["paths"]["/api/v1/images/{image_id}"]["get"]

        response = operation["responses"]["200"]
        assert response["headers"]["Cache-Control"]["schema"]["type"] == "string"
        content = response["content"]
        assert content["image/jpeg"]["schema"] == {"type": "string", "format": "binary"}
        assert content["image/png"]["schema"] == {"type": "string", "format": "binary"}
        assert "application/json" not in content

    def test_users_list_documents_filters_and_paginated_response(self) -> None:
        operation = _schema()["paths"]["/api/v1/users"]["get"]

        parameters = {param["name"]: param for param in operation["parameters"]}
        assert {"page", "per_page", "role", "department", "q"}.issubset(parameters)
        assert parameters["role"]["schema"]["$ref"] == "#/components/schemas/UserRole"
        assert operation["responses"]["200"]["content"]["application/json"]["schema"][
            "$ref"
        ] == "#/components/schemas/PaginatedListResponse_UserRead_"
