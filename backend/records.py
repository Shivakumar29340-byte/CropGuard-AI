
"""Profile, detection-history, blockchain and admin APIs."""

import hashlib
import json
import logging
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from auth import (
    ApiError,
    check_password_rules,
    clean_name,
    get_json,
    login_required,
    user_dict
)
from database import get_db

records_bp = Blueprint("records", __name__, url_prefix="/api")

logger = logging.getLogger(__name__)


# =====================================================
# ADMIN SECURITY
# =====================================================

def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if g.user["role"] != "admin":
            raise ApiError("Admin access required.", 403)
        return view(*args, **kwargs)

    return wrapper


# =====================================================
# PROFILE APIs
# =====================================================

@records_bp.get("/profile")
@login_required
def get_profile():
    return jsonify(user=user_dict(g.user))


@records_bp.put("/profile")
@login_required
def update_profile():
    data = get_json()
    db = get_db()

    if "name" in data:
        db.execute(
            "UPDATE users SET name = ? WHERE id = ?",
            (clean_name(data["name"]), g.user["id"])
        )

    if data.get("new_password"):
        if not check_password_hash(
            g.user["password_hash"],
            str(data.get("current_password") or "")
        ):
            raise ApiError(
                "Current password is incorrect.",
                403,
                "current_password"
            )

        check_password_rules(data["new_password"])

        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (
                generate_password_hash(data["new_password"]),
                g.user["id"]
            )
        )

        db.execute(
            """
            DELETE FROM sessions
            WHERE user_id = ? AND token_hash != ?
            """,
            (g.user["id"], g.token_hash)
        )

    db.commit()

    row = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (g.user["id"],)
    ).fetchone()

    return jsonify(
        message="Profile updated.",
        user=user_dict(row)
    )


# =====================================================
# DETECTION HELPERS
# =====================================================

def detection_dict(row):
    return {
        "id": row["id"],
        "crop": row["crop"],
        "disease": row["disease"],
        "confidence": row["confidence"],
        "notes": row["notes"],
        "source": row["source"],
        "record_hash": row["record_hash"],
        "blockchain_tx": row["blockchain_tx"],
        "created_at": row["created_at"]
    }


def make_record_hash(
    user_id,
    crop,
    disease,
    confidence,
    notes,
    created_at
):
    payload = json.dumps(
        {
            "u": user_id,
            "crop": crop,
            "disease": disease,
            "confidence": confidence,
            "notes": notes,
            "t": created_at
        },
        sort_keys=True,
        separators=(",", ":")
    )

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# =====================================================
# SAVE DETECTION + BLOCKCHAIN REGISTRATION
# =====================================================

@records_bp.post("/detections")
@login_required
def save_detection():
    data = get_json()

    crop = str(data.get("crop") or "").strip().title()

    if crop not in current_app.config["CROPS"]:
        raise ApiError(
            "Crop must be one of: "
            + ", ".join(current_app.config["CROPS"]) + ".",
            field="crop"
        )

    disease = " ".join(
        str(data.get("disease") or "").split()
    )

    if not 2 <= len(disease) <= 100:
        raise ApiError(
            "Disease name must be 2 to 100 characters.",
            field="disease"
        )

    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError):
        raise ApiError(
            "Confidence must be a number between 0 and 1.",
            field="confidence"
        )

    if not 0 <= confidence <= 1 or confidence != confidence:
        raise ApiError(
            "Confidence must be a number between 0 and 1.",
            field="confidence"
        )

    notes = str(data.get("notes") or "").strip()

    if len(notes) > 500:
        raise ApiError(
            "Notes can be at most 500 characters.",
            field="notes"
        )

    db = get_db()

    created = db.execute(
        "SELECT datetime('now')"
    ).fetchone()[0]

    record_hash = make_record_hash(
        g.user["id"],
        crop,
        disease,
        confidence,
        notes,
        created
    )

    cursor = db.execute(
        """
        INSERT INTO detections
        (
            user_id,
            crop,
            disease,
            confidence,
            notes,
            record_hash,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            g.user["id"],
            crop,
            disease,
            confidence,
            notes,
            record_hash,
            created
        )
    )

    db.commit()

    record_id = cursor.lastrowid
    blockchain_tx = None
    blockchain_status = "Not registered"
    blockchain_error = None
    blockchain_block = None

    # Attempt to register the record hash on Ganache.
    try:
        from blockchain import register_record

        blockchain_result = register_record(
            record_id,
            record_hash
        )

        blockchain_tx = blockchain_result.get("transaction_hash")
        blockchain_block = blockchain_result.get("block_number")

        # If it was already registered, it is still registered.
        blockchain_status = "Registered"

        if blockchain_tx:
            db.execute(
                """
                UPDATE detections
                SET blockchain_tx = ?
                WHERE id = ? AND user_id = ?
                """,
                (blockchain_tx, record_id, g.user["id"])
            )
            db.commit()

    except Exception as exc:
        logger.exception(
            "Blockchain registration failed for detection %s",
            record_id
        )
        blockchain_error = str(exc)

    row = db.execute(
        """
        SELECT * FROM detections
        WHERE id = ? AND user_id = ?
        """,
        (record_id, g.user["id"])
    ).fetchone()

    response = {
        "message": "Detection saved.",
        "detection": detection_dict(row),
        "blockchain_status": blockchain_status,
        "blockchain_block": blockchain_block
    }

    if blockchain_error:
        response["blockchain_message"] = (
            "Detection saved, but blockchain registration failed. "
            "Check Ganache and try again."
        )

    return jsonify(response), 201


# =====================================================
# DETECTION HISTORY APIs
# =====================================================

@records_bp.get("/detections")
@login_required
def list_detections():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(
            max(int(request.args.get("per_page", 20)), 1),
            100
        )
    except ValueError:
        raise ApiError("page and per_page must be whole numbers.")

    db = get_db()

    total = db.execute(
        "SELECT COUNT(*) FROM detections WHERE user_id = ?",
        (g.user["id"],)
    ).fetchone()[0]

    rows = db.execute(
        """
        SELECT * FROM detections
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (
            g.user["id"],
            per_page,
            (page - 1) * per_page
        )
    ).fetchall()

    return jsonify(
        detections=[detection_dict(row) for row in rows],
        total=total,
        page=page,
        per_page=per_page
    )


def _own_detection(detection_id):
    row = get_db().execute(
        """
        SELECT * FROM detections
        WHERE id = ? AND user_id = ?
        """,
        (detection_id, g.user["id"])
    ).fetchone()

    if row is None:
        raise ApiError("Detection not found.", 404)

    return row


@records_bp.get("/detections/<int:detection_id>")
@login_required
def get_detection(detection_id):
    return jsonify(
        detection=detection_dict(
            _own_detection(detection_id)
        )
    )


@records_bp.delete("/detections/<int:detection_id>")
@login_required
def delete_detection(detection_id):
    _own_detection(detection_id)

    db = get_db()

    db.execute(
        """
        DELETE FROM detections
        WHERE id = ? AND user_id = ?
        """,
        (detection_id, g.user["id"])
    )

    db.commit()

    return jsonify(message="Detection deleted.")


# =====================================================
# BLOCKCHAIN VERIFICATION API
# =====================================================

@records_bp.post("/blockchain/verify")
@login_required
def verify_blockchain_record():
    data = request.get_json(silent=True) or {}
    search_value = str(data.get("record_id") or "").strip()

    if not search_value:
        raise ApiError("Enter a record ID or record hash.")

    db = get_db()

    if search_value.isdigit():
        row = db.execute(
            """
            SELECT * FROM detections
            WHERE id = ? AND user_id = ?
            """,
            (int(search_value), g.user["id"])
        ).fetchone()
    else:
        normalized_hash = search_value.lower().removeprefix("0x")

        row = db.execute(
            """
            SELECT * FROM detections
            WHERE LOWER(record_hash) = ? AND user_id = ?
            """,
            (normalized_hash, g.user["id"])
        ).fetchone()

    if row is None:
        raise ApiError(
            "Record not found in your detection history.",
            404
        )

    if not row["blockchain_tx"]:
        return jsonify({
            "success": True,
            "verified": False,
            "message": "This record has not been registered on the blockchain.",
            "record_id": row["id"],
            "crop": row["crop"],
            "disease": row["disease"],
            "record_hash": row["record_hash"],
            "blockchain_tx": None,
            "blockchain_exists": False
        })

    try:
        from blockchain import verify_record

        result = verify_record(
            row["id"],
            row["record_hash"]
        )

        verified = bool(
            result["exists"] and result["valid"]
        )

        return jsonify({
            "success": True,
            "verified": verified,
            "message": (
                "Record successfully verified on the blockchain."
                if verified
                else "Verification failed. The blockchain hash does not match."
            ),
            "record_id": row["id"],
            "crop": row["crop"],
            "disease": row["disease"],
            "record_hash": row["record_hash"],
            "stored_hash": result["stored_hash"],
            "blockchain_tx": row["blockchain_tx"],
            "blockchain_timestamp": result["timestamp"],
            "blockchain_exists": result["exists"],
            "chain_id": result["chain_id"],
            "contract_address": result["contract_address"]
        })

    except (ConnectionError, FileNotFoundError) as exc:
        logger.exception("Blockchain connection error")
        raise ApiError(str(exc), 503)

    except Exception:
        logger.exception("Blockchain verification failed")
        raise ApiError(
            "Blockchain verification failed. Check Ganache, "
            "the contract deployment and blockchain configuration.",
            503
        )


# =====================================================
# ADMIN STATISTICS API
# =====================================================

@records_bp.get("/admin/stats")
@admin_required
def admin_stats():
    db = get_db()

    total_users = db.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    total_detections = db.execute(
        "SELECT COUNT(*) FROM detections"
    ).fetchone()[0]

    blockchain_records = db.execute(
        """
        SELECT COUNT(*) FROM detections
        WHERE blockchain_tx IS NOT NULL
        AND TRIM(blockchain_tx) != ''
        """
    ).fetchone()[0]

    disease_classes = current_app.config.get(
        "DISEASE_CLASSES", 0
    )

    return jsonify({
        "total_users": total_users,
        "total_detections": total_detections,
        "blockchain_records": blockchain_records,
        "disease_classes": disease_classes
    })


# =====================================================
# ADMIN USER LIST API
# =====================================================

@records_bp.get("/admin/users")
@admin_required
def admin_users():
    db = get_db()

    try:
        limit = min(
            max(int(request.args.get("limit", 100)), 1),
            500
        )
    except ValueError:
        raise ApiError("limit must be a whole number.")

    rows = db.execute(
        """
        SELECT id, name, email, role, created_at
        FROM users
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    users = [
        {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "role": row["role"],
            "created_at": row["created_at"]
        }
        for row in rows
    ]

    return jsonify(users=users)
