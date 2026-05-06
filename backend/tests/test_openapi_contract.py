from __future__ import annotations

from pathlib import Path

from app.main import app

_ERROR_RESPONSE_REF = "#/components/schemas/ErrorResponse"
_API_DESIGN_DOC = Path(__file__).resolve().parents[2] / "docs/system-design/12-api-design.md"
_UUID_PARAM_ENDPOINTS = [
    ("get", "/api/v1/assets/{asset_id}", "asset_id"),
    ("patch", "/api/v1/assets/{asset_id}", "asset_id"),
    ("post", "/api/v1/assets/{asset_id}/assign", "asset_id"),
    ("post", "/api/v1/assets/{asset_id}/unassign", "asset_id"),
    ("post", "/api/v1/assets/{asset_id}/dispose", "asset_id"),
    ("get", "/api/v1/assets/{asset_id}/history", "asset_id"),
    ("get", "/api/v1/images/{image_id}", "image_id"),
    ("get", "/api/v1/repair-requests/{repair_request_id}", "repair_request_id"),
    ("post", "/api/v1/repair-requests/{repair_request_id}/approve", "repair_request_id"),
    ("post", "/api/v1/repair-requests/{repair_request_id}/reject", "repair_request_id"),
    (
        "patch",
        "/api/v1/repair-requests/{repair_request_id}/repair-details",
        "repair_request_id",
    ),
    ("post", "/api/v1/repair-requests/{repair_request_id}/complete", "repair_request_id"),
]

_PROTECTED_ENDPOINT_ERROR_CODES = {
    ("get", "/api/v1/auth/me"): {"401"},
    ("post", "/api/v1/auth/users"): {"401", "403", "409", "422", "503"},
    ("get", "/api/v1/users"): {"401", "403", "422", "503"},
    ("get", "/api/v1/assets"): {"401", "403", "422", "503"},
    ("post", "/api/v1/assets"): {"401", "403", "409", "422", "503"},
    ("get", "/api/v1/assets/mine"): {"401", "403", "422", "503"},
    ("get", "/api/v1/assets/{asset_id}"): {"401", "403", "404", "422", "503"},
    ("patch", "/api/v1/assets/{asset_id}"): {
        "401",
        "403",
        "404",
        "409",
        "422",
        "503",
    },
    ("post", "/api/v1/assets/{asset_id}/assign"): {
        "401",
        "403",
        "404",
        "409",
        "422",
        "503",
    },
    ("post", "/api/v1/assets/{asset_id}/unassign"): {
        "401",
        "403",
        "404",
        "409",
        "422",
        "503",
    },
    ("post", "/api/v1/assets/{asset_id}/dispose"): {
        "401",
        "403",
        "404",
        "409",
        "422",
        "503",
    },
    ("get", "/api/v1/assets/{asset_id}/history"): {
        "401",
        "403",
        "404",
        "422",
        "503",
    },
    ("get", "/api/v1/repair-requests"): {"401", "403", "422", "503"},
    ("get", "/api/v1/repair-requests/{repair_request_id}"): {
        "401",
        "403",
        "404",
        "422",
        "503",
    },
    ("post", "/api/v1/repair-requests/{repair_request_id}/approve"): {
        "401",
        "403",
        "404",
        "409",
        "422",
        "503",
    },
    ("post", "/api/v1/repair-requests/{repair_request_id}/reject"): {
        "401",
        "403",
        "404",
        "409",
        "422",
        "503",
    },
    ("patch", "/api/v1/repair-requests/{repair_request_id}/repair-details"): {
        "401",
        "403",
        "404",
        "409",
        "422",
        "500",
        "503",
    },
    ("post", "/api/v1/repair-requests/{repair_request_id}/complete"): {
        "401",
        "403",
        "404",
        "409",
        "422",
        "503",
    },
}


def _schema() -> dict:
    app.openapi_schema = None
    return app.openapi()


def _json_schema_ref(operation: dict, status_code: str) -> str:
    return operation["responses"][status_code]["content"]["application/json"]["schema"]["$ref"]


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
        assert {"$ref": "#/components/schemas/UserRole"} in parameters["role"]["schema"][
            "anyOf"
        ]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"][
            "$ref"
        ] == "#/components/schemas/PaginatedListResponse_UserRead_"

    def test_contract_errors_document_error_response_envelope(self) -> None:
        schema = _schema()

        for (method, path), expected_codes in _PROTECTED_ENDPOINT_ERROR_CODES.items():
            operation = schema["paths"][path][method]
            response_codes = set(operation["responses"])
            assert expected_codes.issubset(response_codes), f"{method.upper()} {path}"
            for status_code in expected_codes:
                assert _json_schema_ref(operation, status_code) == _ERROR_RESPONSE_REF, (
                    f"{method.upper()} {path} {status_code}"
                )

    def test_validation_errors_document_project_error_envelope(self) -> None:
        for path, operations in _schema()["paths"].items():
            if not path.startswith("/api/v1"):
                continue
            for method, operation in operations.items():
                if "422" in operation["responses"]:
                    assert _json_schema_ref(operation, "422") == _ERROR_RESPONSE_REF, (
                        f"{method.upper()} {path}"
                    )

    def test_register_does_not_document_runtime_absent_bad_request(self) -> None:
        operation = _schema()["paths"]["/api/v1/auth/register"]["post"]

        assert "400" not in operation["responses"]

    def test_api_design_assigns_malformed_json_to_validation_errors(self) -> None:
        contract = _API_DESIGN_DOC.read_text()

        assert "| 400 | `bad_request` | Malformed JSON" not in contract
        assert "| 422 | `validation_error` | Malformed JSON" in contract
        assert "**Errors:** `422` (malformed JSON or validation), `409` (email taken)" in contract

    def test_uuid_contract_is_reflected_in_path_and_body_schemas(self) -> None:
        schema = _schema()

        for method, path, param_name in _UUID_PARAM_ENDPOINTS:
            operation = schema["paths"][path][method]
            parameters = {param["name"]: param for param in operation["parameters"]}
            assert parameters[param_name]["schema"]["format"] == "uuid"

        assert schema["components"]["schemas"]["RepairRequestCreate"]["properties"][
            "asset_id"
        ]["format"] == "uuid"
        assert schema["components"]["schemas"]["AssetAssignRequest"]["properties"][
            "responsible_person_id"
        ]["format"] == "uuid"

        repair_list_params = {
            param["name"]: param
            for param in schema["paths"]["/api/v1/repair-requests"]["get"]["parameters"]
        }
        assert repair_list_params["asset_id"]["schema"]["anyOf"][0]["format"] == "uuid"
        assert repair_list_params["requester_id"]["schema"]["anyOf"][0]["format"] == "uuid"
