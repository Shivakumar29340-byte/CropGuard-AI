
"""Central configuration for the CropGuard AI backend."""

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:

    # SQLite database
    DATABASE = os.environ.get(
        "CROPGUARD_DB",
        os.path.join(BASE_DIR, "cropguard.db")
    )

    TOKEN_DAYS = 7

    # Maximum request size: 6 MB
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024

    # Allowed frontend websites
    CORS_ORIGINS = [
        "https://shivakumar29340-byte.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "null",
    ]

    # Supported crops
    CROPS = [
        "Tomato",
        "Potato",
        "Pepper",
        "Corn",
        "Apple",
        "Grape",
    ]

    # Backend server settings
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", 5000))

    # Debug mode disabled by default for deployment
    DEBUG = os.environ.get("CROPGUARD_DEBUG", "0") == "1"
