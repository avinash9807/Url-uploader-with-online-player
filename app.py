from flask import Flask, request, jsonify
import os
import mux_python
from mux_python.rest import ApiException
from werkzeug.utils import secure_filename
import sqlite3

app = Flask(__name__)

# =============================
# Database Setup (SQLite)
# =============================
DB_FILE = "database.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS videos
             (id TEXT PRIMARY KEY, title TEXT, playback_id TEXT, url TEXT)''')
conn.commit()

# =============================
# Mux Configuration
# =============================
MUX_TOKEN_ID = os.environ.get("MUX_TOKEN_ID")
MUX_TOKEN_SECRET = os.environ.get("MUX_TOKEN_SECRET")
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")

configuration = mux_python.Configuration()
configuration.username = MUX_TOKEN_ID
configuration.password = MUX_TOKEN_SECRET
assets_api = mux_python.AssetsApi(mux_python.ApiClient(configuration))

# =============================
# API ROUTES
# =============================

@app.route('/api/upload', methods=['POST'])
def upload_video():
    data = request.get_json()
    video_url = data.get("url")

    if not video_url:
        return jsonify({"error": "Missing URL"}), 400

    create_asset_request = mux_python.CreateAssetRequest(
        input=video_url,
        playback_policy=["public"]
    )

    try:
        result = assets_api.create_asset(create_asset_request)
        asset_id = result.data.id
        playback_id = result.data.playback_ids[0].id

        # Save to DB
        c.execute("INSERT INTO videos VALUES (?, ?, ?, ?)",
                  (asset_id, os.path.basename(video_url), playback_id, video_url))
        conn.commit()

        return jsonify({"message": "Video uploaded", "asset_id": asset_id, "playback_id": playback_id}), 200

    except ApiException as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/list', methods=['GET'])
def list_videos():
    c.execute("SELECT * FROM videos")
    videos = [{"id": row[0], "title": row[1], "playback_id": row[2], "url": row[3]} for row in c.fetchall()]
    return jsonify(videos)


@app.route('/api/asset/<asset_id>', methods=['GET'])
def get_asset(asset_id):
    try:
        asset = assets_api.get_asset(asset_id)
        return jsonify(asset.data.to_dict())
    except ApiException as e:
        return jsonify({"error": str(e)}), 404


@app.route('/api/delete/<asset_id>', methods=['DELETE'])
def delete_asset(asset_id):
    auth_header = request.headers.get("Authorization")
    if not auth_header or auth_header != f"Bearer {BEARER_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

    try:
        assets_api.delete_asset(asset_id)
        c.execute("DELETE FROM videos WHERE id=?", (asset_id,))
        conn.commit()
        return jsonify({"message": "Video deleted"}), 200
    except ApiException as e:
        return jsonify({"error": str(e)}), 500


@app.route('/')
def home():
    return jsonify({"status": "running", "message": "Mux Flask API active"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
