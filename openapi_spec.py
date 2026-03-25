"""OpenAPI 3.0 specification for the Vocal Isolator API."""

OPENAPI_VERSION = "1.0.0"


def build_openapi_dict() -> dict:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Vocal Isolator API",
            "version": OPENAPI_VERSION,
            "description": (
                "Separate vocals and instrumental from audio using Demucs v4 or "
                "Audio Separator (MelBand Roformer). Models are loaded per request "
                "unless otherwise noted in `/api/engines/status`.\n\n"
                "When VOCAL_ISOLATOR_API_KEY is set on the server, send the same "
                "value in header X-API-Key or Authorization: Bearer."
            ),
        },
        "servers": [{"url": "/", "description": "Current server"}],
        "security": [{"ApiKeyAuth": []}],
        "tags": [
            {"name": "meta", "description": "Discovery and engine status"},
            {"name": "separate", "description": "Synchronous separation"},
            {"name": "tasks", "description": "Async background tasks"},
            {"name": "download", "description": "Fetch output WAV files"},
        ],
        "paths": {
            "/openapi.json": {
                "get": {
                    "tags": ["meta"],
                    "summary": "OpenAPI document",
                    "description": "Public; no API key. Legacy: `/api/openapi.json` redirects here.",
                    "responses": {"200": {"description": "OpenAPI 3 JSON"}},
                    "security": [],
                }
            },
            "/docs": {
                "get": {
                    "tags": ["meta"],
                    "summary": "Swagger UI",
                    "description": "Interactive API documentation (HTML). Public; no API key. Legacy: `/api/docs` redirects here.",
                    "responses": {"200": {"description": "Swagger UI page"}},
                    "security": [],
                }
            },
            "/api/engines": {
                "get": {
                    "tags": ["meta"],
                    "summary": "List selectable engines",
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
            "/api/engines/status": {
                "get": {
                    "tags": ["meta"],
                    "summary": "Engines available, versions, device",
                    "responses": {
                        "200": {
                            "description": "Runtime and per-engine status",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/EnginesStatus"
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/engines/status": {
                "get": {
                    "tags": ["meta"],
                    "summary": "Engine availability and runtime",
                    "description": (
                        "Which engines are installed/importable, which model each uses, "
                        "and current torch device."
                    ),
                    "responses": {
                        "200": {
                            "description": "Status payload",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/EnginesStatus"}
                                }
                            },
                        }
                    },
                }
            },
            "/api/separate": {
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
                            "description": "Paths to download stems",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "job_id": {"type": "string"},
                                            "download_url": {"type": "string"},
                                            "filename": {"type": "string"},
                                            "instrumental_download_url": {
                                                "type": "string"
                                            },
                                            "instrumental_filename": {
                                                "type": "string"
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
            "/api/tasks": {
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
            "/api/tasks/{task_id}": {
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
            "/api/download/{job_id}/{stem}": {
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
            "/api/download/{job_id}": {
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
