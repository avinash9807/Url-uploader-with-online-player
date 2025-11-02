from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os, requests

load_dotenv()
app = Flask(__name__)

# Database setup
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///videos.db")
db = SQLAlchemy(app)

MUX_TOKEN_ID = os.getenv("MUX_TOKEN_ID")
MUX_TOKEN_SECRET = os.getenv("MUX_TOKEN_SECRET")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")

# Database model
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.String(255), nullable=False)
    playback_id = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255), nullable=True)

with app.app_context():
    db.create_all()

# Upload by URL
@app.route("/api/upload", methods=["POST"])
def upload_video():
    data = request.get_json()
    video_url = data.get("url")
    title = data.get("title", "Untitled")

    mux_url = "https://api.mux.com/video/v1/assets"
    response = requests.post(
        mux_url,
        auth=(MUX_TOKEN_ID, MUX_TOKEN_SECRET),
        json={"input": video_url, "playback_policy": ["public"]},
    )

    if response.status_code != 201:
        return jsonify({"error": "Mux upload failed", "details": response.text}), 400

    asset = response.json()["data"]
    video = Video(asset_id=asset["id"], playback_id=asset["playback_ids"][0]["id"], title=title)
    db.session.add(video)
    db.session.commit()
    return jsonify({"message": "Uploaded successfully", "asset_id": asset["id"]})

# List all videos
@app.route("/api/list", methods=["GET"])
def list_videos():
    videos = Video.query.all()
    return jsonify([
        {"id": v.id, "title": v.title, "asset_id": v.asset_id, "playback_id": v.playback_id}
        for v in videos
    ])

# Get one video
@app.route("/api/asset/<int:id>", methods=["GET"])
def get_video(id):
    video = Video.query.get_or_404(id)
    return jsonify({
        "id": video.id,
        "title": video.title,
        "asset_id": video.asset_id,
        "playback_id": video.playback_id,
        "stream_url": f"https://stream.mux.com/{video.playback_id}.m3u8"
    })

# Delete video (Bearer protected)
@app.route("/api/delete/<int:id>", methods=["DELETE"])
def delete_video(id):
    auth_header = request.headers.get("Authorization")
    if not auth_header or auth_header != f"Bearer {BEARER_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 403

    video = Video.query.get_or_404(id)
    delete_url = f"https://api.mux.com/video/v1/assets/{video.asset_id}"
    mux_resp = requests.delete(delete_url, auth=(MUX_TOKEN_ID, MUX_TOKEN_SECRET))

    if mux_resp.status_code not in [200, 204]:
        return jsonify({"error": "Failed to delete from Mux", "details": mux_resp.text}), 400

    db.session.delete(video)
    db.session.commit()
    return jsonify({"message": "Deleted successfully"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
