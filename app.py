from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import mux_python
from mux_python.rest import ApiException
import sqlite3

app = Flask(__name__, static_folder="static")
CORS(app)

# =============================
# Database Setup (SQLite)
# =============================
DB_FILE = "database.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS videos
             (id TEXT PRIMARY KEY, title TEXT, playback_id TEXT, source_url TEXT)''')
conn.commit()

# =============================
# Mux Configuration
# =============================
MUX_TOKEN_ID = os.environ.get("MUX_TOKEN_ID")
MUX_TOKEN_SECRET = os.environ.get("MUX_TOKEN_SECRET")
BEARER_TOKEN = os.environ.get("BEARER_TOKEN", "mysecret")

configuration = mux_python.Configuration()
configuration.username = MUX_TOKEN_ID
configuration.password = MUX_TOKEN_SECRET
assets_api = mux_python.AssetsApi(mux_python.ApiClient(configuration))

# =============================
# API ROUTES
# =============================

@app.route('/upload', methods=['POST'])
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
        c.execute("INSERT OR REPLACE INTO videos VALUES (?, ?, ?, ?)",
                  (asset_id, os.path.basename(video_url), playback_id, video_url))
        conn.commit()

        return jsonify({
            "message": "Video uploaded successfully!",
            "asset_id": asset_id,
            "playback_id": playback_id
        }), 200

    except ApiException as e:
        return jsonify({"error": str(e)}), 500


@app.route('/videos', methods=['GET'])
def list_videos():
    c.execute("SELECT * FROM videos")
    videos = []
    for row in c.fetchall():
        playback_url = f"https://stream.mux.com/{row[2]}.m3u8"
        videos.append({
            "id": row[0],
            "title": row[1],
            "playback_id": row[2],
            "source_url": row[3],
            "playback_url": playback_url
        })
    return jsonify(videos)


@app.route('/delete/<asset_id>', methods=['DELETE'])
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
def index():
    return send_from_directory("static", "index.html")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
