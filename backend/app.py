
"""
CropGuard AI - Flask Backend
AI Crop Disease Detection using TensorFlow and PlantVillage
"""

import json
from pathlib import Path
from io import BytesIO

import numpy as np
import tensorflow as tf

from PIL import Image, UnidentifiedImageError
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

import database
from auth import ApiError, auth_bp
from config import Config
from records import records_bp


# ==========================================
# 1. LOAD TRAINED AI MODEL
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

MODEL_PATH = BASE_DIR / "models" / "cropguard_model.keras"
LABEL_PATH = BASE_DIR / "models" / "class_names.json"

if not MODEL_PATH.exists():
    raise FileNotFoundError(
        f"AI model not found: {MODEL_PATH}"
    )

if not LABEL_PATH.exists():
    raise FileNotFoundError(
        f"Class labels not found: {LABEL_PATH}"
    )

model = tf.keras.models.load_model(MODEL_PATH)

with open(LABEL_PATH, "r", encoding="utf-8") as file:
    class_names = json.load(file)

if model.output_shape[-1] != len(class_names):
    raise ValueError(
        "Model output count does not match class labels."
    )

print("CropGuard AI model loaded successfully!")
print("Disease categories:", len(class_names))


# ==========================================
# 2. DISEASE INFORMATION
# ==========================================

def get_disease_info(class_name):

    normalized = class_name.lower()

    if "healthy" in normalized:
        return {
            "condition": "Healthy",
            "severity": "None detected",
            "symptoms": "No target disease detected by the model.",
            "treatment": "No disease-specific pesticide is indicated.",
            "prevention": (
                "Continue regular monitoring, irrigation "
                "and good crop hygiene."
            ),
            "chemical": "No chemical treatment recommended."
        }

    information = {
        "condition": "Disease detected - Verify diagnosis",
        "severity": "Requires field assessment",
        "symptoms": (
            "The image resembles this PlantVillage disease category."
        ),
        "treatment": (
            "Remove severely affected plant material where appropriate "
            "and seek local agricultural advice."
        ),
        "prevention": (
            "Use healthy planting material, monitor crops regularly "
            "and avoid prolonged leaf wetness."
        ),
        "chemical": (
            "Select only a locally registered crop-specific product "
            "after confirming the diagnosis. Follow its label and "
            "local agricultural guidance."
        )
    }

    if "bacterial_spot" in normalized:
        information.update({
            "symptoms": (
                "Dark water-soaked or angular leaf spots may occur."
            ),
            "prevention": (
                "Avoid overhead irrigation and working among wet plants."
            ),
            "treatment": (
                "Remove badly affected debris and use clean planting material."
            )
        })

    elif "early_blight" in normalized:
        information.update({
            "symptoms": (
                "Brown leaf spots may show concentric rings."
            ),
            "prevention": (
                "Rotate crops, remove infected debris and avoid wetting leaves."
            ),
            "treatment": (
                "Improve airflow and remove heavily affected leaves."
            )
        })

    elif "late_blight" in normalized:
        information.update({
            "symptoms": (
                "Dark, spreading lesions may appear on leaves."
            ),
            "prevention": (
                "Avoid prolonged leaf wetness and monitor nearby plants."
            ),
            "treatment": (
                "Promptly seek local agricultural advice because "
                "this disease can spread rapidly."
            )
        })

    elif "leaf_mold" in normalized:
        information.update({
            "symptoms": (
                "Yellow patches and olive-green growth may appear "
                "on leaf undersides."
            ),
            "prevention": (
                "Improve ventilation and reduce humidity."
            ),
            "treatment": (
                "Remove affected leaves and improve airflow."
            )
        })

    elif (
        "mosaic_virus" in normalized
        or "yellow_leaf_curl" in normalized
    ):
        information.update({
            "symptoms": (
                "Mosaic patterns, leaf curling or yellowing may occur."
            ),
            "prevention": (
                "Control insect vectors and remove confirmed infected "
                "plants as locally advised."
            ),
            "treatment": (
                "There is no direct chemical cure for a plant virus."
            )
        })

    return information


# ==========================================
# 3. CREATE FLASK APPLICATION
# ==========================================

def create_app(overrides=None):

    app = Flask(__name__)

    app.config.from_object(Config)

    if overrides:
        app.config.update(overrides)

    # Number of disease categories from trained AI model.
    app.config["DISEASE_CLASSES"] = len(class_names)

    # CORS CONFIGURATION
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": app.config["CORS_ORIGINS"]
            }
        },
        allow_headers=[
            "Content-Type",
            "Authorization"
        ],
        methods=[
            "GET",
            "POST",
            "PUT",
            "DELETE",
            "OPTIONS"
        ]
    )

    # DATABASE INITIALIZATION
    database.init_app(app)

    # REGISTER BLUEPRINTS
    app.register_blueprint(auth_bp)
    app.register_blueprint(records_bp)

    # ======================================
    # 4. HEALTH CHECK API
    # ======================================

    @app.get("/api/health")
    def health():

        return jsonify({
            "status": "ok",
            "service": "CropGuard AI backend",
            "ai_model": "loaded",
            "disease_categories": len(class_names)
        })

    # ======================================
    # 5. AI IMAGE PREDICTION API
    # ======================================

    @app.post("/api/predict")
    def predict():

        if "image" not in request.files:
            return jsonify({
                "status": "error",
                "error": "Please upload a crop leaf image."
            }), 400

        uploaded_file = request.files["image"]

        if not uploaded_file.filename:
            return jsonify({
                "status": "error",
                "error": "Please select an image."
            }), 400

        try:

            # Read and convert image to RGB
            image = Image.open(
                BytesIO(uploaded_file.read())
            ).convert("RGB")

            # Resize image to model input size
            image = image.resize(
                (224, 224),
                Image.Resampling.BILINEAR
            )

            # Convert image into NumPy array
            image_array = np.asarray(
                image,
                dtype=np.float32
            )

            # Add batch dimension
            image_array = np.expand_dims(
                image_array,
                axis=0
            )

            # AI prediction
            predictions = model.predict(
                image_array,
                verbose=0
            )[0]

            predicted_index = int(
                np.argmax(predictions)
            )

            # Confidence percentage
            confidence = float(
                predictions[predicted_index]
            ) * 100

            disease = class_names[predicted_index]

            # Confidence status
            if confidence < 60:

                confidence_status = (
                    "Low confidence - Needs verification"
                )

                diagnosis_warning = (
                    "The AI is uncertain about this result. "
                    "Please upload a clearer leaf image and "
                    "consult an agricultural expert."
                )

            elif confidence < 80:

                confidence_status = "Moderate confidence"

                diagnosis_warning = (
                    "This prediction should be verified "
                    "before taking treatment decisions."
                )

            else:

                confidence_status = "High model confidence"

                diagnosis_warning = (
                    "This is a model prediction, not a confirmed "
                    "field diagnosis. Verify before treatment."
                )

            # Get disease information
            info = get_disease_info(disease)

            condition = info["condition"]

            if confidence < 60:
                condition = (
                    "Uncertain prediction - Verification required"
                )

            # Return prediction result
            return jsonify({

                "status": "success",

                "crop_disease": disease,
                "disease": disease,

                "confidence": round(confidence, 2),
                "confidence_status": confidence_status,
                "diagnosis_warning": diagnosis_warning,

                "condition": condition,
                "severity": info["severity"],
                "symptoms": info["symptoms"],
                "treatment": info["treatment"],
                "chemical_recommendation": info["chemical"],
                "prevention": info["prevention"]

            }), 200

        except (UnidentifiedImageError, OSError):

            return jsonify({
                "status": "error",
                "error": "Invalid or unsupported image file."
            }), 400

        except Exception:

            app.logger.exception(
                "AI prediction failed"
            )

            return jsonify({
                "status": "error",
                "error": "Unable to process the image."
            }), 500

    # ======================================
    # 6. ERROR HANDLERS
    # ======================================

    @app.errorhandler(ApiError)
    def api_error(error):

        body = {
            "error": error.message
        }

        if error.field:
            body["field"] = error.field

        return jsonify(body), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):

        messages = {
            404: "Not found.",
            405: "Method not allowed.",
            413: "Uploaded file is too large."
        }

        return jsonify({
            "error": messages.get(
                error.code,
                error.description
            )
        }), error.code

    @app.errorhandler(Exception)
    def unexpected(error):

        app.logger.exception(
            "Unhandled server error"
        )

        return jsonify({
            "error": "Something went wrong on the server."
        }), 500

    return app


# ==========================================
# 7. START SERVER
# ==========================================

# IMPORTANT:
# Keep this outside the __main__ block.
# Gunicorn needs this module-level variable.

application = create_app()


if __name__ == "__main__":

    application.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG
    )
