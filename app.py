from flask import Flask, request, jsonify
from flask_cors import CORS
import mux_python
from mux_python.rest import ApiException
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
CORS(app)

# Load Mux API credentials
MUX_TOKEN_ID = os.getenv("MUX_TOKEN_ID")
MUX_TOKEN_SECRET = os.getenv("MUX_TOKEN_SECRET")

configuration = mux_python.Configuration()
configuration.username = MUX_TOKEN_ID
configuration.password = MUX_TOKEN_SECRET
mux_api = mux_python.AssetsApi(mux_python.ApiClient(configuration))

videos = []  # Temporary storage for testing

@app.route("/")
def home():
    return jsonify({"message": "Mux uploader backend working!"})

@app.route("/upload", methods=["POST"])
def upload():
    try:
        data = request.get_json()
        video_url = data.get("video_url")

        if not video_url:
            return jsonify({"error": "Missing URL"}), 400

        # ✅ Create Mux asset directly from URL
        create_asset_request = mux_python.CreateAssetRequest(
            input=video_url,
            playback_policy=[mux_python.PlaybackPolicy.PUBLIC]
        )

        asset = mux_api.create_asset(create_asset_request)
        asset_url = f"https://stream.mux.com/{asset.data.playback_ids[0].id}.m3u8"

        # Store in memory (you can connect DB later)
        videos.append({"url": asset_url})

        return jsonify({"message": "Upload successful", "url": asset_url}), 200

    except ApiException as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/videos", methods=["GET"])
def get_videos():
    return jsonify(videos)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
