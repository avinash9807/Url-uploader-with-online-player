# app.py
import os
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from requests.auth import HTTPBasicAuth
from functools import wraps

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mux-backend")

# Environment variables
MUX_TOKEN_ID = os.getenv("MUX_TOKEN_ID")
MUX_TOKEN_SECRET = os.getenv("MUX_TOKEN_SECRET")
API_KEY = os.getenv("API_KEY")  # optional security key
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

if not MUX_TOKEN_ID or not MUX_TOKEN_SECRET:
    logger.warning("MUX_TOKEN_ID or MUX_TOKEN_SECRET not set!")

MUX_API_BASE = "https://api.mux.com/video/v1"

# Flask app setup
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": CORS_ORIGINS}})

auth = HTTPBasicAuth(MUX_TOKEN_ID or "", MUX_TOKEN_SECRET or "")

# ---------- Optional API key decorator ----------
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_KEY:
            return f(*args, **kwargs)
        key = request.headers.get("X-API-KEY") or request.args.get("api_key")
        if not key or key != API_KEY:
            return jsonify({"error": "unauthorized", "message": "Invalid API key"}), 401
        return f(*args, **kwargs)
    return decorated

# ---------- Health check & root route ----------
@app.route("/", methods=["GET"])
def home():
    """Root route for Koyeb health check"""
    return jsonify({"status": "ok", "message": "Mux backend running"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# ---------- Create asset ----------
@app.route("/create_asset", methods=["POST", "OPTIONS"])
@require_api_key
def create_asset():
    if request.method == "OPTIONS":
        return "", 204

    url = None
    if request.is_json:
        url = request.json.get("url")
    else:
        url = request.form.get("url") or request.values.get("url")

    if not url:
        return jsonify({"error": "missing_parameter", "message": "Missing 'url'"}), 400

    payload = {"input": url}
    headers = {"Content-Type": "application/json"}

    try:
        logger.info("Creating Mux asset for URL: %s", url)
        resp = requests.post(
            f"{MUX_API_BASE}/assets",
            json=payload,
            headers=headers,
            auth=auth,
            timeout=30,
        )
    except requests.RequestException as e:
        logger.exception("Network error calling Mux Create Asset")
        return jsonify({"error": "network_error", "details": str(e)}), 502

    try:
        data = resp.json()
    except ValueError:
        data = {"body": resp.text}

    return jsonify(data), resp.status_code

# ---------- List assets ----------
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
        logger.exception("Network error calling Mux List Assets")
        return jsonify({"error": "network_error", "details": str(e)}), 502

    try:
        data = resp.json()
    except ValueError:
        data = {"body": resp.text}

    return jsonify(data), resp.status_code

# ---------- Delete asset ----------
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
        return jsonify({"error": "missing_parameter", "message": "Missing 'asset_id'"}), 400

    try:
        resp = requests.delete(f"{MUX_API_BASE}/assets/{asset_id}", auth=auth, timeout=30)
    except requests.RequestException as e:
        logger.exception("Network error calling Mux Delete Asset")
        return jsonify({"error": "network_error", "details": str(e)}), 502

    text = resp.text.strip()
    if text:
        try:
            data = resp.json()
        except ValueError:
            data = {"body": text}
    else:
        data = {"status": "deleted", "asset_id": asset_id}

    return jsonify(data), resp.status_code

# ---------- Default CORS headers ----------
@app.after_request
def set_default_headers(response):
    response.headers.setdefault("Access-Control-Allow-Origin", CORS_ORIGINS)
    response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
    response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-KEY")
    return response

# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
