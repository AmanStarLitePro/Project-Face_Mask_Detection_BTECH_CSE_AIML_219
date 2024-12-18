from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from ultralytics import YOLO
import cv2
import os
import requests
import uuid
import logging

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

model_path = "best.pt"
model = YOLO(model_path)

def smooth_bboxes(detections, alpha=0.6):
    smoothed_detections = []
    prev_detections = None

    for detection in detections:
        if prev_detections is None:
            smoothed_detections.append(detection)
        else:
            smoothed = []
            for current, prev in zip(detection, prev_detections):
                x1 = alpha * current[0] + (1 - alpha) * prev[0]
                y1 = alpha * current[1] + (1 - alpha) * prev[1]
                x2 = alpha * current[2] + (1 - alpha) * prev[2]
                y2 = alpha * current[3] + (1 - alpha) * prev[3]
                smoothed.append([x1, y1, x2, y2, current[4], current[5]])
            smoothed_detections.append(smoothed)
        prev_detections = detection
    return smoothed_detections

@app.route('/')
def index():
    return "Welcome to the YOLO Video Processing API. Use the /upload and /process_video endpoints."

@app.route('/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        logger.error('No video file provided in request')
        return jsonify({'error': 'No video file provided'}), 400

    video = request.files['video']
    video_path = os.path.join("uploads", video.filename)
    video.save(video_path)
    logger.info(f"Video uploaded successfully: {video_path}")

    return jsonify({'message': 'Video uploaded successfully', 'video_path': video_path}), 200

@app.route('/process_video', methods=['POST'])
def process_video():
    data = request.json
    video_path = data.get('video_path')

    if not video_path or not os.path.exists(video_path):
        logger.error('Invalid video file path')
        return jsonify({'error': 'Invalid video file path'}), 400

    logger.info(f"Processing video: {video_path}")

    output_video_path = f"processed_video_{uuid.uuid4().hex}.mp4"

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Failed to open video file: {video_path}")
        return jsonify({'error': 'Failed to open video file'}), 500

    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(output_video_path, fourcc, 30.0, (int(cap.get(3)), int(cap.get(4))))

    all_detections = []
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        results = model.predict(frame)
        if isinstance(results, list):
            results = results[0]
        detections = [[det.xyxy[0][0], det.xyxy[0][1], det.xyxy[0][2], det.xyxy[0][3], det.conf, det.cls]
                      for det in results.boxes]
        all_detections.append(detections)

    smoothed_detections = smooth_bboxes(all_detections)

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        for det in smoothed_detections[frame_idx]:
            x1, y1, x2, y2, conf, class_id = det
            if conf > 0.5:
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                cv2.putText(frame, model.names[int(class_id)], (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        out.write(frame)
        frame_idx += 1

    cap.release()
    out.release()

    return send_file(output_video_path, as_attachment=True)

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    app.run(host='0.0.0.0', port=5000)

