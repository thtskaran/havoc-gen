import logging
import random
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit
from concurrent.futures import ThreadPoolExecutor
import queue
import json
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import pickle
import warnings

warnings.filterwarnings('ignore')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'production-monitoring-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Custom logging handler to stream logs via WebSocket
class WebSocketHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        try:
            socketio.emit('log', {
                'timestamp': datetime.now().isoformat(),
                'level': record.levelname,
                'message': log_entry,
                'thread': record.threadName
            }, namespace='/')
        except:
            pass

# Configure logging with WebSocket handler
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s-%(thread)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('production_issues.log'),
        WebSocketHandler()
    ]
)

logger = logging.getLogger(__name__)

# Shared resources for race conditions and deadlocks
shared_counter = 0
lock_a = threading.Lock()
lock_b = threading.Lock()
shared_queue = queue.Queue(maxsize=10)
memory_leak_list = []

# Auto-generation control
auto_generation_active = True
auto_generation_thread = None

class DatabaseSimulator:
    """Simulates database connection issues"""
    def __init__(self):
        self.connection_count = 0
        self.max_connections = 5
        
    def get_connection(self):
        self.connection_count += 1
        if self.connection_count > self.max_connections:
            logger.error(f"DATABASE CONNECTION POOL EXHAUSTED: {self.connection_count}/{self.max_connections} connections")
            raise Exception("Too many database connections")
        logger.debug(f"Database connection acquired: {self.connection_count}/{self.max_connections}")
        return f"conn_{self.connection_count}"
    
    def release_connection(self):
        if self.connection_count > 0:
            self.connection_count -= 1
            logger.debug(f"Database connection released: {self.connection_count}/{self.max_connections}")

db = DatabaseSimulator()

def normal_operation_logs():
    """Generate normal operational logs"""
    operations = [
        lambda: logger.info("User authentication successful"),
        lambda: logger.info(f"Processing order #{random.randint(1000, 9999)}"),
        lambda: logger.debug(f"Cache hit for key: user_{random.randint(1, 1000)}"),
        lambda: logger.info(f"API request completed in {random.randint(10, 200)}ms"),
        lambda: logger.debug(f"Database query executed: SELECT * FROM users WHERE id={random.randint(1, 1000)}"),
        lambda: logger.info(f"Email sent to user@example.com"),
        lambda: logger.info(f"Payment processed successfully: ${random.randint(10, 500)}.{random.randint(0, 99):02d}"),
        lambda: logger.debug(f"Session created for user_{random.randint(1, 1000)}"),
        lambda: logger.info(f"File uploaded: document_{random.randint(1, 100)}.pdf"),
        lambda: logger.info(f"Report generated in {random.randint(1, 10)} seconds"),
    ]
    
    random.choice(operations)()

def race_condition_scenario():
    """Simulates race condition on shared counter"""
    global shared_counter
    logger.warning("RACE CONDITION: Multiple threads accessing shared counter without proper locking")
    
    temp = shared_counter
    time.sleep(random.uniform(0.001, 0.01))
    shared_counter = temp + 1
    
    logger.debug(f"Counter updated to: {shared_counter} by {threading.current_thread().name}")

def deadlock_scenario():
    """Simulates potential deadlock situation"""
    thread_id = threading.current_thread().name
    
    try:
        logger.warning(f"DEADLOCK RISK: {thread_id} attempting to acquire lock_a")
        lock_a.acquire()
        logger.debug(f"{thread_id} acquired lock_a")
        
        time.sleep(random.uniform(0.01, 0.05))
        
        logger.warning(f"DEADLOCK RISK: {thread_id} attempting to acquire lock_b while holding lock_a")
        if lock_b.acquire(timeout=0.1):
            logger.debug(f"{thread_id} acquired both locks")
            time.sleep(random.uniform(0.01, 0.02))
            lock_b.release()
        else:
            logger.error(f"DEADLOCK DETECTED: {thread_id} couldn't acquire lock_b, potential deadlock!")
    except Exception as e:
        logger.exception(f"Exception in deadlock scenario: {e}")
    finally:
        lock_a.release()

def memory_leak_scenario():
    """Simulates memory leak by accumulating data"""
    global memory_leak_list
    
    data_chunk = [random.randint(0, 1000) for _ in range(10000)]
    memory_leak_list.append(data_chunk)
    
    logger.warning(f"MEMORY LEAK: List growing unbounded, current size: {len(memory_leak_list)} chunks")
    
    if len(memory_leak_list) > 100:
        logger.critical(f"MEMORY LEAK CRITICAL: {len(memory_leak_list)} chunks accumulated!")
        memory_leak_list.clear()

def null_pointer_scenario():
    """Simulates null/None reference errors"""
    data = None if random.random() > 0.5 else {"key": "value"}
    
    try:
        logger.debug(f"Attempting to access data: {data}")
        result = data["key"]
        logger.info(f"Successfully accessed data: {result}")
    except (TypeError, KeyError) as e:
        logger.error(f"NULL POINTER EXCEPTION: Attempted to access None or missing key - {type(e).__name__}: {e}")

def resource_exhaustion_scenario():
    """Simulates resource exhaustion"""
    try:
        conn = db.get_connection()
        
        if random.random() > 0.7:
            logger.warning(f"RESOURCE LEAK: Connection {conn} not properly released")
            time.sleep(random.uniform(0.1, 0.3))
        else:
            time.sleep(random.uniform(0.01, 0.05))
            db.release_connection()
    except Exception as e:
        logger.exception(f"RESOURCE EXHAUSTION: {e}")

def timeout_scenario():
    """Simulates timeout errors"""
    timeout_duration = random.uniform(0.5, 3.0)
    max_timeout = 1.0
    
    logger.debug(f"External API call initiated, expected duration: {timeout_duration:.2f}s")
    
    if timeout_duration > max_timeout:
        logger.error(f"TIMEOUT ERROR: External service took {timeout_duration:.2f}s (max: {max_timeout}s)")
        raise TimeoutError(f"Service timeout after {max_timeout}s")
    else:
        time.sleep(timeout_duration)
        logger.info(f"External API call completed in {timeout_duration:.2f}s")

def divide_by_zero_scenario():
    """Simulates arithmetic errors"""
    denominator = random.choice([0, 1, 2, 3, 0, 5])
    numerator = random.randint(1, 100)
    
    try:
        logger.debug(f"Calculating: {numerator} / {denominator}")
        result = numerator / denominator
        logger.info(f"Calculation result: {result}")
    except ZeroDivisionError as e:
        logger.error(f"ARITHMETIC ERROR: Division by zero - {numerator} / {denominator}")

def index_out_of_bounds_scenario():
    """Simulates index/boundary errors"""
    arr = [1, 2, 3, 4, 5]
    index = random.randint(-2, 10)
    
    try:
        logger.debug(f"Accessing array index {index}, array length: {len(arr)}")
        value = arr[index]
        logger.info(f"Successfully retrieved value: {value}")
    except IndexError as e:
        logger.error(f"INDEX OUT OF BOUNDS: Attempted to access index {index} in array of size {len(arr)}")

def json_parse_error_scenario():
    """Simulates JSON parsing errors"""
    malformed_json = random.choice([
        '{"key": "value"',
        '{"key": undefined}',
        "{'key': 'value'}",
        '{"key": "value",}',
    ])
    
    try:
        logger.debug(f"Attempting to parse JSON: {malformed_json}")
        result = json.loads(malformed_json)
        logger.info(f"JSON parsed successfully: {result}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON PARSE ERROR: {e} - Input: {malformed_json}")

def queue_overflow_scenario():
    """Simulates queue/buffer overflow"""
    try:
        item = f"item_{random.randint(1000, 9999)}"
        logger.debug(f"Attempting to add {item} to queue (current size: {shared_queue.qsize()})")
        shared_queue.put(item, block=False)
        logger.info(f"Item {item} added to queue")
    except queue.Full:
        logger.error(f"QUEUE OVERFLOW: Queue is full ({shared_queue.maxsize} items), cannot add more items")

def ml_model_dimension_mismatch():
    """Simulates dimension mismatch in ML models"""
    logger.info("ML: Training model with proper dimensions")
    
    X_train = np.random.rand(100, 5)
    y_train = np.random.randint(0, 2, 100)
    
    model = RandomForestClassifier(n_estimators=10, random_state=42)
    model.fit(X_train, y_train)
    logger.debug(f"ML: Model trained successfully with {X_train.shape[1]} features")
    
    wrong_features = random.choice([3, 7, 10])
    X_test = np.random.rand(1, wrong_features)
    
    try:
        logger.debug(f"ML: Attempting prediction with {X_test.shape[1]} features")
        prediction = model.predict(X_test)
        logger.info(f"ML: Prediction successful: {prediction}")
    except ValueError as e:
        logger.error(f"ML DIMENSION MISMATCH: Model expects 5 features, got {wrong_features} - {e}")

def ml_model_nan_infinity():
    """Simulates NaN and infinity values in ML pipeline"""
    logger.info("ML: Processing data with potential NaN/Inf values")
    
    X = np.random.rand(100, 4)
    
    if random.random() > 0.5:
        X[random.randint(0, 99), random.randint(0, 3)] = np.nan
        logger.warning("ML DATA QUALITY: NaN values detected in dataset")
    
    if random.random() > 0.5:
        X[random.randint(0, 99), random.randint(0, 3)] = np.inf
        logger.warning("ML DATA QUALITY: Infinity values detected in dataset")
    
    y = np.random.rand(100)
    
    try:
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        logger.debug("ML: Data scaling completed")
        
        model = LinearRegression()
        model.fit(X_scaled, y)
        logger.info("ML: Model training completed")
    except ValueError as e:
        logger.error(f"ML TRAINING FAILURE: NaN/Inf values caused training failure - {e}")

def ml_overfitting_scenario():
    """Simulates overfitting detection"""
    logger.info("ML: Detecting potential overfitting")
    
    X = np.random.rand(100, 10)
    y = np.random.randint(0, 2, 100)
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    
    model = RandomForestClassifier(n_estimators=100, max_depth=None, min_samples_split=2, random_state=42)
    model.fit(X_train, y_train)
    
    train_score = model.score(X_train, y_train)
    test_score = model.score(X_test, y_test)
    
    logger.debug(f"ML: Training score: {train_score:.4f}, Test score: {test_score:.4f}")
    
    score_diff = train_score - test_score
    if score_diff > 0.15:
        logger.warning(f"ML OVERFITTING DETECTED: Score difference of {score_diff:.4f} between train and test")
    else:
        logger.info("ML: Model generalization appears healthy")

# Auto-generation function
def auto_generate_logs():
    """Automatically generates logs at random intervals"""
    global auto_generation_active
    
    error_scenarios = [
        race_condition_scenario,
        deadlock_scenario,
        memory_leak_scenario,
        null_pointer_scenario,
        resource_exhaustion_scenario,
        timeout_scenario,
        divide_by_zero_scenario,
        index_out_of_bounds_scenario,
        json_parse_error_scenario,
        queue_overflow_scenario,
        ml_model_dimension_mismatch,
        ml_model_nan_infinity,
        ml_overfitting_scenario,
    ]
    
    logger.info("🚀 AUTO-GENERATION: Started automatic log generation")
    
    while auto_generation_active:
        try:
            # Generate 1-3 logs per iteration
            num_logs = random.randint(1, 3)
            
            for _ in range(num_logs):
                # 70% chance of normal logs, 30% chance of errors
                if random.random() < 0.7:
                    normal_operation_logs()
                else:
                    scenario = random.choice(error_scenarios)
                    try:
                        scenario()
                    except Exception as e:
                        logger.exception(f"Error in scenario execution: {e}")
            
            # Wait between 0.5 to 3 seconds before next batch
            time.sleep(random.uniform(0.5, 3.0))
            
        except Exception as e:
            logger.exception(f"Error in auto-generation loop: {e}")
            time.sleep(1)
    
    logger.info("🛑 AUTO-GENERATION: Stopped automatic log generation")

# WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    logger.info(f"🔌 Client connected: {request.sid}")
    emit('status', {'message': 'Connected to log stream', 'status': 'active'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"🔌 Client disconnected: {request.sid}")

@socketio.on('ping')
def handle_ping():
    emit('pong', {'timestamp': datetime.now().isoformat()})

# HTTP Endpoints
@app.route('/')
def index():
    return jsonify({
        "service": "Production Issues Simulator",
        "version": "2.0",
        "features": [
            "Real-time log streaming via WebSocket",
            "Automatic log generation",
            "Manual trigger endpoints"
        ],
        "websocket_url": "/socket.io",
        "auto_generation": "active" if auto_generation_active else "inactive"
    }), 200

@app.route('/health')
def health():
    """Health check endpoint"""
    logger.info("Health check requested")
    return jsonify({
        "status": "running",
        "counter": shared_counter,
        "db_connections": db.connection_count,
        "queue_size": shared_queue.qsize(),
        "memory_chunks": len(memory_leak_list),
        "auto_generation": auto_generation_active
    }), 200

@app.route('/auto-generation/start')
def start_auto_generation():
    """Start automatic log generation"""
    global auto_generation_active, auto_generation_thread
    
    if auto_generation_active and auto_generation_thread and auto_generation_thread.is_alive():
        return jsonify({"status": "already_running"}), 200
    
    auto_generation_active = True
    auto_generation_thread = threading.Thread(target=auto_generate_logs, daemon=True)
    auto_generation_thread.start()
    
    logger.info("🚀 AUTO-GENERATION: Started via API")
    return jsonify({"status": "started"}), 200

@app.route('/auto-generation/stop')
def stop_auto_generation():
    """Stop automatic log generation"""
    global auto_generation_active
    
    auto_generation_active = False
    logger.info("🛑 AUTO-GENERATION: Stopped via API")
    
    return jsonify({"status": "stopped"}), 200

@app.route('/auto-generation/status')
def auto_generation_status():
    """Check auto-generation status"""
    return jsonify({
        "active": auto_generation_active,
        "thread_alive": auto_generation_thread.is_alive() if auto_generation_thread else False
    }), 200

if __name__ == '__main__':
    # Start auto-generation on startup
    auto_generation_thread = threading.Thread(target=auto_generate_logs, daemon=True)
    auto_generation_thread.start()
    
    logger.info("="*60)
    logger.info("🚀 Production Issues Simulator Starting")
    logger.info("WebSocket endpoint: ws://localhost:5000/socket.io")
    logger.info("Auto-generation: ENABLED")
    logger.info("="*60)
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)