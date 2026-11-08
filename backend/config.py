
"""Central configuration for the CropGuard AI backend."""

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:

    # SQLite database
    DATABASE = os.environ.get(
        "CROPGUARD_DB",
        os.path.join(BASE_DIR, "cropguard.db")
    )

    # Login token validity (days)
    TOKEN_DAYS = 7

    # Maximum request size: 6 MB
    # Supports image uploads up to 5 MB plus request overhead.
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024

    # Allowed frontend websites
    CORS_ORIGINS = [
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
    HOST = "127.0.0.1"
    PORT = 5000

    # Debug mode
    DEBUG = os.environ.get(
        "CROPGUARD_DEBUG",
        "1"
    ) == "1"
