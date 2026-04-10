"""OpenAPI 3.0 specification for the Vocal Isolator API."""

OPENAPI_VERSION = "1.0.0"

# URL prefix for the app (must match app.py / Flask blueprint). Root `/` is a plain "ok" probe.
APP_URL_PREFIX = "/vocal-isolator"


def build_openapi_dict() -> dict:
    P = APP_URL_PREFIX
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Vocal Isolator API",
            "version": OPENAPI_VERSION,
            "description": (
                "Separate vocals and instrumental from audio using Demucs v4 or "
                "Audio Separator (MelBand Roformer). Models are loaded per request "
                f"unless otherwise noted in `{P}/api/engines/status`.\n\n"
                "When VOCAL_ISOLATOR_API_KEY is set on the server, send the same "
                "value in header X-API-Key or Authorization: Bearer on protected "
                "endpoints (not required for `GET /api/engines`, so the web UI can "
                "load the model list before you paste a key).\n\n"
                "Outputs are uploaded to S3 by default (bucket "
                "`wmg-acestep-batch-input-test`, overridable via "
                "`VOCAL_ISOLATOR_S3_BUCKET`; set it empty to store files only on "
                "this server). Completed responses include presigned HTTPS URLs "
                "(`vocals_url`, `instrumental_url`) and `s3://` URIs."
            ),
        },
        "servers": [{"url": f"{P}/", "description": "Vocal isolator (all API paths use this prefix)"}],
        "security": [{"ApiKeyAuth": []}],
        "tags": [
            {"name": "meta", "description": "Discovery and engine status"},
            {"name": "separate", "description": "Synchronous separation"},
            {"name": "tasks", "description": "Async background tasks"},
            {"name": "download", "description": "Fetch output WAV files"},
        ],
        "paths": {
            f"{P}/openapi.json": {
                "get": {
                    "tags": ["meta"],
                    "summary": "OpenAPI document",
                    "description": f"Public; no API key. Legacy: `{P}/api/openapi.json` redirects here.",
                    "responses": {"200": {"description": "OpenAPI 3 JSON"}},
                    "security": [],
                }
            },
            f"{P}/docs": {
                "get": {
                    "tags": ["meta"],
                    "summary": "Swagger UI",
                    "description": f"Interactive API documentation (HTML). Public; no API key. Legacy: `{P}/api/docs` redirects here.",
                    "responses": {"200": {"description": "Swagger UI page"}},
                    "security": [],
                }
            },
            f"{P}/api/engines": {
                "get": {
                    "tags": ["meta"],
                    "summary": "List selectable engines",
                    "description": "Public even when VOCAL_ISOLATOR_API_KEY is set (browser UI needs labels before a key is entered).",
                    "security": [],
                    "responses": {
                        "200": {
                            "description": "Map of engine id to display label",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "engines": {
                                                "type": "object",
                                                "additionalProperties": {
                                                    "type": "string"
                                                },
                                            }
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            f"{P}/api/engines/status": {
                "get": {
                    "tags": ["meta"],
                    "summary": "Engine availability and runtime",
                    "description": (
                        "Which engines are installed/importable, which model each uses, "
                        "and current torch device."
                    ),
                    "responses": {
                        "200": {
                            "description": "Runtime and per-engine status",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/EnginesStatus"}
                                }
                            },
                        }
                    },
                }
            },
            f"{P}/api/separate": {
                "post": {
                    "tags": ["separate"],
                    "summary": "Separate (synchronous)",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "required": ["file"],
                                    "properties": {
                                        "file": {
                                            "type": "string",
                                            "format": "binary",
                                            "description": "Audio file",
                                        },
                                        "engine": {
                                            "type": "string",
                                            "enum": ["demucs", "audio_separator"],
                                            "default": "demucs",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": (
                                "When S3 is enabled: presigned `vocals_url` / "
                                "`instrumental_url` and `vocals_s3_uri` / "
                                "`instrumental_s3_uri`. Otherwise relative "
                                "`download_url` paths on this server."
                            ),
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "job_id": {"type": "string"},
                                            "filename": {"type": "string"},
                                            "instrumental_filename": {
                                                "type": "string"
                                            },
                                            "vocals_url": {
                                                "type": "string",
                                                "description": "Presigned GET URL (S3)",
                                            },
                                            "instrumental_url": {
                                                "type": "string",
                                                "description": "Presigned GET URL (S3)",
                                            },
                                            "vocals_s3_uri": {"type": "string"},
                                            "instrumental_s3_uri": {"type": "string"},
                                            "bucket": {"type": "string"},
                                            "s3_prefix": {"type": "string"},
                                            "presign_expires_seconds": {
                                                "type": "integer"
                                            },
                                            "download_url": {
                                                "type": "string",
                                                "description": "Relative path when S3 disabled",
                                            },
                                            "instrumental_download_url": {
                                                "type": "string",
                                                "description": "Relative path when S3 disabled",
                                            },
                                        },
                                    }
                                }
                            },
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        "500": {"$ref": "#/components/responses/Error"},
                    },
                }
            },
            f"{P}/api/tasks": {
                "post": {
                    "tags": ["tasks"],
                    "summary": "Create async task",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "required": ["file"],
                                    "properties": {
                                        "file": {
                                            "type": "string",
                                            "format": "binary",
                                        },
                                        "engine": {
                                            "type": "string",
                                            "enum": ["demucs", "audio_separator"],
                                            "default": "demucs",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {
                            "description": "Task accepted",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "task_id": {"type": "string"},
                                            "status": {"type": "string"},
                                            "poll_url": {"type": "string"},
                                            "message": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                    },
                }
            },
            f"{P}/api/tasks/{{task_id}}": {
                "get": {
                    "tags": ["tasks"],
                    "summary": "Poll task status",
                    "parameters": [
                        {
                            "name": "task_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {"description": "Task state"},
                        "404": {"$ref": "#/components/responses/NotFound"},
                    },
                },
                "delete": {
                    "tags": ["tasks"],
                    "summary": "Delete task and output files",
                    "parameters": [
                        {
                            "name": "task_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "204": {"description": "Removed"},
                        "404": {"$ref": "#/components/responses/NotFound"},
                    },
                },
            },
            f"{P}/api/download/{{job_id}}/{{stem}}": {
                "get": {
                    "tags": ["download"],
                    "summary": "Download a stem",
                    "parameters": [
                        {
                            "name": "job_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "stem",
                            "in": "path",
                            "required": True,
                            "schema": {
                                "type": "string",
                                "enum": ["vocals", "instrumental"],
                            },
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "WAV file",
                            "content": {
                                "audio/wav": {"schema": {"type": "string", "format": "binary"}}
                            },
                        },
                        "404": {"$ref": "#/components/responses/NotFound"},
                    },
                }
            },
            f"{P}/api/download/{{job_id}}": {
                "get": {
                    "tags": ["download"],
                    "summary": "Download vocals (legacy)",
                    "parameters": [
                        {
                            "name": "job_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Vocals WAV",
                            "content": {
                                "audio/wav": {"schema": {"type": "string", "format": "binary"}}
                            },
                        },
                        "404": {"$ref": "#/components/responses/NotFound"},
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "Same value as server env VOCAL_ISOLATOR_API_KEY, "
                    "or Authorization Bearer with the same secret.",
                }
            },
            "responses": {
                "Unauthorized": {
                    "description": "Missing or invalid API key",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"detail": {"type": "string", "example": "Unauthorized"}},
                            }
                        }
                    },
                },
                "BadRequest": {
                    "description": "Bad request",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"detail": {"type": "string"}},
                            }
                        }
                    },
                },
                "NotFound": {
                    "description": "Not found",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"detail": {"type": "string"}},
                            }
                        }
                    },
                },
                "Error": {
                    "description": "Server error",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"detail": {"type": "string"}},
                            }
                        }
                    },
                },
            },
            "schemas": {
                "EnginesStatus": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string", "example": "mps"},
                        "torch_version": {"type": "string"},
                        "demucs_version": {"type": "string"},
                        "engines": {
                            "type": "object",
                            "additionalProperties": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "label": {"type": "string"},
                                    "available": {
                                        "type": "boolean",
                                        "description": "Selectable and runnable",
                                    },
                                    "importable": {
                                        "type": "boolean",
                                        "description": "Python package import succeeds",
                                    },
                                    "models_loaded_in_memory": {
                                        "type": "boolean",
                                        "description": "Weights cached in RAM (usually false)",
                                    },
                                    "model": {
                                        "type": "string",
                                        "description": "Model id or checkpoint",
                                    },
                                    "package_version": {
                                        "type": "string",
                                        "nullable": True,
                                    },
                                },
                            },
                        },
                    },
                }
            },
        },
    }
