from flask import Flask, Response, jsonify, render_template
import cv2
import numpy as np
import pandas as pd
import time
from ultralytics import YOLO

app = Flask(__name__)

# Load YOLOv8 model
model = YOLO("yolov8n.pt")

# COCO class IDs for relevant objects
COCO_CLASSES = {
    0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck",
    9: "traffic_light", 36: "helmet", 37: "seatbelt"
}

# Global variables
violations = []
frame_width, frame_height = 640, 480  # Adjust based on your video resolution

# Calibration factor (pixels to meters)
# Example: If 100 pixels = 10 meters, then calibration_factor = 10 / 100 = 0.1
calibration_factor = 0.1  # Adjust this based on your camera setup

# Function to calculate speed
def calculate_speed(vehicle_id, prev_position, current_position, fps):
    if prev_position is None or current_position is None:
        return 0
    # Calculate pixel displacement
    pixel_displacement = np.linalg.norm(np.array(current_position) - np.array(prev_position))
    # Convert pixel displacement to real-world distance (in meters)
    distance = pixel_displacement * calibration_factor
    # Calculate speed (distance / time)
    speed = distance * fps * 3.6  # Convert to km/h
    return speed

# Function to get current time in HH:MM:SS format
def get_current_time():
    return time.strftime("%H:%M:%S")

# Function to process video frames
def process_video():
    cap = cv2.VideoCapture("5.webm")  # Use 0 for webcam or "video.mp4" for file
    fps = cap.get(cv2.CAP_PROP_FPS)
    vehicle_tracker = {}  # Track vehicles and their positions

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Resize frame for faster processing
        frame = cv2.resize(frame, (frame_width, frame_height))

        # Get current time
        current_time = get_current_time()

        # Overlay current time on the frame with a black border
        text = f"Time: {current_time}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1
        thickness = 2

        # Draw black border (thicker text)
        cv2.putText(frame, text, (10, 30), font, font_scale, (0, 0, 0), thickness + 3)

        # Draw white text on top
        cv2.putText(frame, text, (10, 30), font, font_scale, (255, 255, 255), thickness)

        # Run YOLOv8 inference
        results = model(frame)

        # Process detections
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                cls = int(box.cls[0])

                # Skip persons (class ID 0)
                if cls == 0:
                    continue

                # Draw bounding boxes for vehicles only
                if cls in [2, 3, 5, 7]:  # Vehicles (car, motorcycle, bus, truck)
                    vehicle_id = f"{cls}_{x1}_{y1}"  # Unique ID for each vehicle
                    current_position = ((x1 + x2) // 2, (y1 + y2) // 2)  # Center of the bounding box

                    # Calculate speed
                    if vehicle_id in vehicle_tracker:
                        prev_position, prev_time = vehicle_tracker[vehicle_id]
                        speed = calculate_speed(vehicle_id, prev_position, current_position, fps)
                        cv2.putText(frame, f"Speed: {speed:.2f} km/h", (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 2)

                        # Change bounding box color to red if speed > 50 km/h
                        if speed > 50:
                            color = (0, 0, 255)  # Red
                            # Log overspeeding violation
                            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                            violations.append(["Overspeeding", timestamp])
                        else:
                            color = (0, 255, 0)  # Green
                    else:
                        color = (0, 255, 0)  # Default color (green)

                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    vehicle_tracker[vehicle_id] = (current_position, time.time())

                # Check for other violations (helmet, seatbelt)
                if cls == 36:  # Helmet
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    violations.append(["No Helmet", time.strftime("%Y-%m-%d %H:%M:%S")])
                elif cls == 37:  # Seatbelt
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    violations.append(["No Seatbelt", time.strftime("%Y-%m-%d %H:%M:%S")])

        # Encode frame to JPEG
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    # Save violations to CSV
    if violations:
        df = pd.DataFrame(violations, columns=["Violation Type", "Timestamp"])
        df.to_csv("violations.csv", index=False)
        print("Violations saved to violations.csv")

    cap.release()

# Route for homepage
@app.route('/')
def index():
    return render_template('index.html')

# Route for live video feed
@app.route('/video_feed')
def video_feed():
    return Response(process_video(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# Route to get violations
@app.route('/violations')
def get_violations():
    return jsonify(violations)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)