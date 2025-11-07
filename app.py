# app.py
import os
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from requests.auth import HTTPBasicAuth
from functools import wraps

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mux-backend")

# Environment variables (set these in Koyeb)
MUX_TOKEN_ID = os.getenv("MUX_TOKEN_ID")
MUX_TOKEN_SECRET = os.getenv("MUX_TOKEN_SECRET")
API_KEY = os.getenv("API_KEY")  # optional shared secret for protected endpoints
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

if not MUX_TOKEN_ID or not MUX_TOKEN_SECRET:
    logger.warning("MUX_TOKEN_ID or MUX_TOKEN_SECRET not set. Set env vars before production use.")

MUX_API_BASE = "https://api.mux.com/video/v1"

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": CORS_ORIGINS}})

auth = HTTPBasicAuth(MUX_TOKEN_ID or "", MUX_TOKEN_SECRET or "")

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_KEY:
            return f(*args, **kwargs)
        key = request.headers.get("X-API-KEY") or request.args.get("api_key")
        if not key or key != API_KEY:
            return jsonify({"error": "unauthorized", "message": "Missing or invalid API key"}), 401
        return f(*args, **kwargs)
    return decorated

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "message": "Mux backend running"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# ----------------- create_asset (creates playback id too) -----------------
@app.route("/create_asset", methods=["POST", "OPTIONS"])
@require_api_key
def create_asset():
    if request.method == "OPTIONS":
        return "", 204

    url = None
    title = None

    if request.is_json:
        body = request.get_json(silent=True) or {}
        url = body.get("url")
        title = body.get("title")
    else:
        url = request.form.get("url") or request.values.get("url")
        title = request.form.get("title") or request.values.get("title")

    if not url:
        return jsonify({"error":"missing_parameter","message":"Missing 'url' parameter"}), 400

    payload = {"input": url}
    if title:
        payload["metadata"] = {"title": title}

    try:
        logger.info("Creating Mux asset for URL: %s (title=%s)", url, title)
        resp = requests.post(f"{MUX_API_BASE}/assets", json=payload, auth=auth, timeout=30)
    except requests.RequestException as e:
        logger.exception("Network error when calling Mux Create Asset")
        return jsonify({"error":"network_error","details": str(e)}), 502

    # Parse create response
    try:
        data = resp.json()
    except ValueError:
        data = {"body": resp.text}

    # Normalize asset dict (Mux may return { "data": { ... } })
    asset = None
    if isinstance(data, dict):
        asset = data.get("data") or data
    if asset and isinstance(asset, dict):
        asset_id = asset.get("id")
    else:
        asset_id = None

    # If asset_id present, create a public playback id (if not existing)
    if asset_id:
        try:
            existing_playback_ids = asset.get("playback_ids") or []
            has_public = any((p.get("policy") == "public") for p in existing_playback_ids)
            if not has_public:
                logger.info("Creating public playback ID for asset %s", asset_id)
                pb_resp = requests.post(
                    f"{MUX_API_BASE}/assets/{asset_id}/playback-ids",
                    json={"policy": "public"},
                    auth=auth,
                    timeout=15
                )
                try:
                    pb_data = pb_resp.json()
                except ValueError:
                    pb_data = {"body": pb_resp.text}
                if pb_resp.ok and isinstance(pb_data, dict):
                    # Determine playback object (wrapped as data or raw)
                    pb_obj = pb_data.get("data") or pb_data
                    # merge into asset.playback_ids
                    if "playback_ids" not in asset:
                        asset["playback_ids"] = []
                    asset["playback_ids"].append(pb_obj)
                    # update the top-level response shape if needed
                    if isinstance(data, dict) and ("data" in data):
                        data["data"] = asset
                    else:
                        data = asset
        except requests.RequestException as e:
            logger.warning("Failed to create playback id for asset %s: %s", asset_id, str(e))

    # Return create response (possibly augmented)
    return jsonify(data), resp.status_code

# ----------------- get single asset by id -----------------
@app.route("/asset/<asset_id>", methods=["GET", "OPTIONS"])
@require_api_key
def get_asset(asset_id):
    if request.method == "OPTIONS":
        return "", 204
    try:
        resp = requests.get(f"{MUX_API_BASE}/assets/{asset_id}", auth=auth, timeout=30)
    except requests.RequestException as e:
        logger.exception("Network error when calling Mux Get Asset")
        return jsonify({"error":"network_error","details": str(e)}), 502
    try:
        data = resp.json()
    except ValueError:
        data = {"body": resp.text}
    return jsonify(data), resp.status_code

# ----------------- list assets -----------------
@app.route("/list_assets", methods=["GET", "OPTIONS"])
@require_api_key
def list_assets():
    if request.method == "OPTIONS":
        return "", 204
    limit = request.args.get("limit", "50")
    page = request.args.get("page", "0")
    params = {"limit": limit, "page": page}
    try:
        resp = requests.get(f"{MUX_API_BASE}/assets", params=params, auth=auth, timeout=30)
    except requests.RequestException as e:
        logger.exception("Network error when calling Mux List Assets")
        return jsonify({"error":"network_error","details": str(e)}), 502
    try:
        data = resp.json()
    except ValueError:
        data = {"body": resp.text}
    return jsonify(data), resp.status_code

# ----------------- delete asset -----------------
@app.route("/delete_asset", methods=["POST", "DELETE", "OPTIONS"])
@require_api_key
def delete_asset():
    if request.method == "OPTIONS":
        return "", 204
    asset_id = None
    if request.method == "DELETE":
        asset_id = request.args.get("asset_id")
    else:
        if request.is_json:
            asset_id = request.json.get("asset_id")
        else:
            asset_id = request.form.get("asset_id") or request.values.get("asset_id")
    if not asset_id:
        return jsonify({"error":"missing_parameter","message":"Missing 'asset_id'"}), 400
    try:
        resp = requests.delete(f"{MUX_API_BASE}/assets/{asset_id}", auth=auth, timeout=30)
    except requests.RequestException as e:
        logger.exception("Network error when calling Mux Delete Asset")
        return jsonify({"error":"network_error","details": str(e)}), 502
    text = resp.text.strip()
    if text:
        try:
            data = resp.json()
        except ValueError:
            data = {"body": text}
    else:
        data = {"status":"deleted","asset_id": asset_id}
    return jsonify(data), resp.status_code

# Ensure CORS headers (safety/net)
@app.after_request
def set_default_headers(response):
    response.headers.setdefault("Access-Control-Allow-Origin", CORS_ORIGINS)
    response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
    response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-KEY")
    return response

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
