from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os
import mux_python
from mux_python.rest import ApiException

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///videos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Mux API setup
MUX_TOKEN_ID = os.getenv("MUX_TOKEN_ID")
MUX_TOKEN_SECRET = os.getenv("MUX_TOKEN_SECRET")

configuration = mux_python.Configuration()
configuration.username = MUX_TOKEN_ID
configuration.password = MUX_TOKEN_SECRET
mux_api_client = mux_python.ApiClient(configuration)
upload_api = mux_python.DirectUploadsApi(mux_api_client)
assets_api = mux_python.AssetsApi(mux_api_client)


# Database model
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mux_id = db.Column(db.String(100))
    playback_id = db.Column(db.String(100))
    url = db.Column(db.String(200))

with app.app_context():
    db.create_all()


@app.route('/')
def home():
    return jsonify({"message": "🎬 Mux Video API running successfully!"})


# -------------------------
# Upload by URL
# -------------------------
@app.route('/upload', methods=['POST'])
def upload_video():
    try:
        data = request.get_json()
        video_url = data.get("url")

        if not video_url:
            return jsonify({"error": "No URL provided"}), 400

        # Create Direct Upload on Mux
        upload_request = mux_python.CreateDirectUploadRequest(
            new_asset_settings=mux_python.CreateAssetRequest(playback_policy=["public"]),
            cors_origin="*"
        )

        upload_response = upload_api.create_direct_upload(upload_request)
        upload_url = upload_response.data.url
        upload_id = upload_response.data.id

        # Create asset from the remote URL
        asset_request = mux_python.CreateAssetRequest(input=video_url, playback_policy=["public"])
        asset_response = assets_api.create_asset(asset_request)

        playback_id = asset_response.data.playback_ids[0].id
        mux_id = asset_response.data.id

        video = Video(mux_id=mux_id, playback_id=playback_id, url=video_url)
        db.session.add(video)
        db.session.commit()

        return jsonify({
            "message": "✅ Uploaded successfully!",
            "playback_url": f"https://stream.mux.com/{playback_id}.m3u8"
        })

    except ApiException as e:
        return jsonify({"error": f"Mux API error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------------
# Get All Videos
# -------------------------
@app.route('/videos', methods=['GET'])
def get_videos():
    videos = Video.query.all()
    output = []

    for v in videos:
        output.append({
            "id": v.id,
            "mux_id": v.mux_id,
            "playback_url": f"https://stream.mux.com/{v.playback_id}.m3u8",
            "source_url": v.url
        })
    return jsonify(output)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
