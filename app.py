from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import mux_python
from mux_python.rest import ApiException

app = Flask(__name__)
CORS(app)

# ============== MUX CONFIG ==============
MUX_TOKEN_ID = os.getenv("MUX_TOKEN_ID")
MUX_TOKEN_SECRET = os.getenv("MUX_TOKEN_SECRET")

configuration = mux_python.Configuration()
configuration.username = MUX_TOKEN_ID
configuration.password = MUX_TOKEN_SECRET
assets_api = mux_python.AssetsApi(mux_python.ApiClient(configuration))

videos = []  # Temporary list (DB add later)

@app.route('/api/upload', methods=['POST'])
def upload_video():
    data = request.get_json()
    video_url = data.get("url")

    if not video_url:
        return jsonify({"error": "Missing URL"}), 400

    try:
        create_asset_request = mux_python.CreateAssetRequest(
            input=video_url,
            playback_policy=["public"]
        )
        result = assets_api.create_asset(create_asset_request)
        asset_id = result.data.id
        playback_id = result.data.playback_ids[0].id
        videos.append({"asset_id": asset_id, "playback_id": playback_id, "url": video_url})

        return jsonify({
            "message": "Video uploaded successfully",
            "asset_id": asset_id,
            "playback_id": playback_id
        }), 200

    except ApiException as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/list', methods=['GET'])
def list_videos():
    return jsonify(videos)


@app.route('/')
def home():
    return jsonify({"status": "Mux Flask API running!"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
