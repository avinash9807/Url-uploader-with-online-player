# app.py
import os
import logging
import time
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from requests.auth import HTTPBasicAuth
from functools import wraps

# SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, JSON
from sqlalchemy.orm import sessionmaker, declarative_base

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mux-backend-jobs")

# --- Env / Mux config ---
MUX_TOKEN_ID = os.getenv("MUX_TOKEN_ID")
MUX_TOKEN_SECRET = os.getenv("MUX_TOKEN_SECRET")
API_KEY = os.getenv("API_KEY")  # optional
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///videos.db")  # override with Postgres in prod

MUX_API_BASE = "https://api.mux.com/video/v1"

# --- Flask app ---
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

# --- Database setup (SQLAlchemy) ---
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(2048), nullable=False)
    title = Column(String(512), nullable=True)
    status = Column(String(64), default="queued")  # queued, processing, ready, errored
    asset_id = Column(String(128), nullable=True)
    playback_id = Column(String(128), nullable=True)
    mux_raw = Column(JSON, nullable=True)  # store mux response(s)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# create tables
Base.metadata.create_all(bind=engine)

# --- Helpers: DB session context ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Simple health/root ---
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status":"ok","message":"Mux backend with jobs"}), 200

# --- Enqueue endpoint: frontend calls this (quick) ---
@app.route("/enqueue_asset", methods=["POST"])
@require_api_key
def enqueue_asset():
    data = request.get_json(silent=True) or request.form or request.values
    url = data.get("url") or data.get("input")
    title = data.get("title")
    if not url:
        return jsonify({"error":"missing_parameter","message":"Missing 'url'"}), 400

    # create job row
    db = next(get_db())
    job = Job(url=url, title=title, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("Enqueued job id=%s url=%s", job.id, url)
    return jsonify({"job_id": job.id, "status": job.status}), 200

# --- Get job status ---
@app.route("/job/<int:job_id>", methods=["GET"])
@require_api_key
def get_job(job_id):
    db = next(get_db())
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return jsonify({"error":"not_found"}), 404
    return jsonify({
        "job_id": job.id,
        "url": job.url,
        "title": job.title,
        "status": job.status,
        "asset_id": job.asset_id,
        "playback_id": job.playback_id,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat()
    })

# --- List recent jobs (for manage page) ---
@app.route("/list_jobs", methods=["GET"])
@require_api_key
def list_jobs():
    limit = int(request.args.get("limit", 50))
    db = next(get_db())
    rows = db.query(Job).order_by(Job.created_at.desc()).limit(limit).all()
    out = []
    for j in rows:
        out.append({
            "job_id": j.id,
            "url": j.url,
            "title": j.title,
            "status": j.status,
            "asset_id": j.asset_id,
            "playback_id": j.playback_id,
            "created_at": j.created_at.isoformat(),
            "updated_at": j.updated_at.isoformat()
        })
    return jsonify({"data": out})

# --- Process pending jobs endpoint (called by scheduler or worker) ---
@app.route("/process_pending", methods=["POST"])
@require_api_key
def process_pending():
    """
    Process N queued jobs (default 1). This endpoint does the actual create on Mux,
    creates public playback ID and polls until ready (or marks errored).
    Call repeatedly (scheduler) or run a worker that POSTs here.
    """
    max_jobs = int(request.args.get("max", 1))
    db = next(get_db())
    queued = db.query(Job).filter(Job.status == "queued").order_by(Job.created_at.asc()).limit(max_jobs).all()
    processed = []
    for job in queued:
        processed.append(job.id)
        try:
            # mark processing
            job.status = "processing"
            db.commit()
            db.refresh(job)

            # Create asset on Mux
            payload = {"input": job.url}
            if job.title:
                payload["metadata"] = {"title": job.title}
            logger.info("Creating asset for job %s url=%s", job.id, job.url)
            resp = requests.post(f"{MUX_API_BASE}/assets", json=payload, auth=auth, timeout=60)
            try:
                resp_json = resp.json()
            except ValueError:
                resp_json = {"body": resp.text}
            # normalize asset obj
            asset = resp_json.get("data") if isinstance(resp_json, dict) and "data" in resp_json else resp_json

            # save mux raw
            job.mux_raw = resp_json
            job.asset_id = asset.get("id") if isinstance(asset, dict) else None
            db.commit()

            # create public playback id if not created
            if job.asset_id:
                try:
                    pb_resp = requests.post(
                        f"{MUX_API_BASE}/assets/{job.asset_id}/playback-ids",
                        json={"policy":"public"},
                        auth=auth,
                        timeout=20
                    )
                    try:
                        pb_json = pb_resp.json()
                    except ValueError:
                        pb_json = {"body": pb_resp.text}
                    # pb_json may be wrapped
                    pb_obj = (pb_json.get("data") if isinstance(pb_json, dict) and "data" in pb_json else pb_json)
                    # persist playback id (first one)
                    if isinstance(pb_obj, dict) and pb_obj.get("id"):
                        job.playback_id = pb_obj.get("id")
                        # add to mux_raw for debug
                        job.mux_raw = (job.mux_raw or {})
                        job.mux_raw["playback_creation"] = pb_json
                        db.commit()
                except Exception as e:
                    logger.warning("Playback id creation failed for job %s: %s", job.id, str(e))
                    # continue, we'll still poll status

            # Poll asset until ready or timeout
            if job.asset_id:
                start = time.time()
                timeout = 300  # 5 minutes per job (configurable)
                interval = 4
                ready = False
                while time.time() - start < timeout:
                    try:
                        r = requests.get(f"{MUX_API_BASE}/assets/{job.asset_id}", auth=auth, timeout=20)
                        jdata = r.json() if r.ok else None
                        asset_data = jdata.get("data") if isinstance(jdata, dict) and "data" in jdata else jdata
                        # update mux_raw each poll (optional)
                        job.mux_raw = jdata
                        job.updated_at = datetime.utcnow()
                        db.commit()
                        if isinstance(asset_data, dict):
                            status = asset_data.get("status")
                            if status == "ready":
                                ready = True
                                # find playback id in asset if not set earlier
                                pids = asset_data.get("playback_ids") or []
                                if pids and isinstance(pids, list) and not job.playback_id:
                                    job.playback_id = pids[0].get("id")
                                    db.commit()
                                break
                            if status == "errored":
                                job.status = "errored"
                                job.error = str(asset_data.get("errors") or "Mux errored")
                                db.commit()
                                break
                        # wait then poll again
                    except Exception as e:
                        logger.warning("Error polling asset %s: %s", job.asset_id, str(e))
                    time.sleep(interval)
                if ready:
                    job.status = "ready"
                    job.updated_at = datetime.utcnow()
                    db.commit()
                else:
                    # timed out but not ready — leave status as processing but note it
                    if job.status != "errored":
                        job.status = "processing"
                        job.error = (job.error or "") + " Polling timeout or still processing."
                        db.commit()
            else:
                # asset not created properly
                job.status = "errored"
                job.error = "Asset creation did not return asset_id."
                db.commit()
        except Exception as exc:
            logger.exception("Processing job %s failed: %s", job.id, str(exc))
            job.status = "errored"
            job.error = str(exc)
            db.commit()

    return jsonify({"processed_job_ids": processed}), 200

# --- Keep existing endpoints (list_assets/delete_asset/asset...) if you already have them ---
# (Optionally keep /asset/<asset_id> that proxies Mux, but since we store job details we rely on DB.)

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
