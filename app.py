import logging
import random
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, request
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

# Configure logging with detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s-%(thread)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('production_issues.log')
    ]
)

logger = logging.getLogger(__name__)

# Shared resources for race conditions and deadlocks
shared_counter = 0
lock_a = threading.Lock()
lock_b = threading.Lock()
shared_queue = queue.Queue(maxsize=10)
memory_leak_list = []

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

def race_condition_scenario():
    """Simulates race condition on shared counter"""
    global shared_counter
    logger.warning("RACE CONDITION: Multiple threads accessing shared counter without proper locking")
    
    temp = shared_counter
    time.sleep(random.uniform(0.001, 0.01))  # Simulate processing
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
        memory_leak_list.clear()  # Reset to prevent actual memory issues

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
        '{"key": "value"',  # Missing closing brace
        '{"key": undefined}',  # Invalid value
        "{'key': 'value'}",  # Single quotes
        '{"key": "value",}',  # Trailing comma
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
    
    # Train model with specific feature count
    X_train = np.random.rand(100, 5)
    y_train = np.random.randint(0, 2, 100)
    
    model = RandomForestClassifier(n_estimators=10, random_state=42)
    model.fit(X_train, y_train)
    logger.debug(f"ML: Model trained successfully with {X_train.shape[1]} features")
    
    # Try to predict with wrong number of features
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
    
    # Create dataset with problematic values
    X = np.random.rand(100, 4)
    
    # Inject NaN and Inf values
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

def ml_model_convergence_failure():
    """Simulates model convergence issues"""
    logger.info("ML: Training model with convergence challenges")
    
    # Create difficult dataset
    X = np.random.rand(50, 20)  # Small dataset, many features
    y = np.random.rand(50)
    
    from sklearn.linear_model import SGDRegressor
    
    model = SGDRegressor(max_iter=5, tol=1e-10, random_state=42)
    
    try:
        logger.debug("ML: Starting model training with strict convergence criteria")
        model.fit(X, y)
        
        if not hasattr(model, 'n_iter_') or model.n_iter_ >= 5:
            logger.warning("ML CONVERGENCE WARNING: Model did not converge within iteration limit")
        else:
            logger.info(f"ML: Model converged in {model.n_iter_} iterations")
    except Exception as e:
        logger.error(f"ML CONVERGENCE FAILURE: {e}")

def ml_overfitting_scenario():
    """Simulates overfitting detection"""
    logger.info("ML: Detecting potential overfitting")
    
    X = np.random.rand(100, 10)
    y = np.random.randint(0, 2, 100)
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    
    # Create overly complex model
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

def ml_data_leakage_scenario():
    """Simulates data leakage in preprocessing"""
    logger.info("ML: Preprocessing pipeline with potential data leakage")
    
    X = np.random.rand(100, 5)
    y = np.random.randint(0, 2, 100)
    
    # WRONG: Scaling before split (data leakage)
    logger.warning("ML DATA LEAKAGE: Scaling entire dataset before train/test split")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.3, random_state=42)
    
    model = RandomForestClassifier(random_state=42)
    model.fit(X_train, y_train)
    
    test_score = model.score(X_test, y_test)
    logger.error(f"ML DATA LEAKAGE: Test score {test_score:.4f} may be artificially inflated due to leakage")

def ml_class_imbalance_scenario():
    """Simulates class imbalance issues"""
    logger.info("ML: Training on imbalanced dataset")
    
    # Create highly imbalanced dataset
    n_majority = 950
    n_minority = 50
    
    X_majority = np.random.rand(n_majority, 5)
    y_majority = np.zeros(n_majority)
    
    X_minority = np.random.rand(n_minority, 5)
    y_minority = np.ones(n_minority)
    
    X = np.vstack([X_majority, X_minority])
    y = np.hstack([y_majority, y_minority])
    
    logger.warning(f"ML CLASS IMBALANCE: Dataset has {n_majority} majority samples and {n_minority} minority samples (ratio: {n_majority/n_minority:.1f}:1)")
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    
    model = RandomForestClassifier(random_state=42)
    model.fit(X_train, y_train)
    
    train_predictions = model.predict(X_train)
    minority_predicted = np.sum(train_predictions == 1)
    
    if minority_predicted < n_minority * 0.3:
        logger.error(f"ML CLASS IMBALANCE IMPACT: Model only predicts {minority_predicted} minority class samples, likely biased toward majority")

def ml_model_serialization_failure():
    """Simulates model serialization/deserialization issues"""
    logger.info("ML: Testing model serialization")
    
    X = np.random.rand(100, 5)
    y = np.random.randint(0, 2, 100)
    
    model = GradientBoostingRegressor(n_estimators=50, random_state=42)
    model.fit(X, y)
    
    try:
        # Serialize model
        logger.debug("ML: Serializing model to bytes")
        model_bytes = pickle.dumps(model)
        logger.info(f"ML: Model serialized successfully, size: {len(model_bytes)} bytes")
        
        # Corrupt serialized model randomly
        if random.random() > 0.6:
            logger.warning("ML SERIALIZATION: Simulating corrupted model file")
            corrupt_index = random.randint(0, len(model_bytes) - 1)
            model_bytes = model_bytes[:corrupt_index] + b'\x00' + model_bytes[corrupt_index+1:]
        
        # Deserialize
        logger.debug("ML: Deserializing model from bytes")
        loaded_model = pickle.loads(model_bytes)
        
        # Try to predict
        X_test = np.random.rand(5, 5)
        predictions = loaded_model.predict(X_test)
        logger.info("ML: Model loaded and predictions successful")
        
    except (pickle.UnpicklingError, AttributeError, EOFError) as e:
        logger.error(f"ML DESERIALIZATION FAILURE: Corrupted model file - {type(e).__name__}: {e}")
    except Exception as e:
        logger.exception(f"ML SERIALIZATION ERROR: {e}")

def ml_feature_scaling_mismatch():
    """Simulates feature scaling inconsistencies between train and inference"""
    logger.info("ML: Testing feature scaling consistency")
    
    # Training phase
    X_train = np.random.rand(100, 4) * 100  # Scale 0-100
    y_train = np.random.rand(100)
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    
    model = LinearRegression()
    model.fit(X_train_scaled, y_train)
    logger.debug("ML: Model trained with scaled features")
    
    # Inference phase - forgot to scale or used different scaler
    if random.random() > 0.5:
        logger.warning("ML SCALING MISMATCH: Predicting on unscaled data")
        X_test = np.random.rand(1, 4) * 100  # Unscaled
    else:
        logger.warning("ML SCALING MISMATCH: Using different scaler parameters")
        wrong_scaler = StandardScaler()
        X_test = np.random.rand(10, 4) * 50  # Different scale
        X_test = wrong_scaler.fit_transform(X_test)[:1]
    
    try:
        prediction = model.predict(X_test)
        logger.error(f"ML SCALING ERROR: Prediction made on incorrectly scaled data: {prediction[0]:.4f}")
    except Exception as e:
        logger.error(f"ML PREDICTION FAILURE: {e}")

def ml_memory_explosion():
    """Simulates memory issues with large ML operations"""
    logger.info("ML: Processing large dataset")
    
    # Try to create increasingly large matrices
    size = random.choice([5000, 10000, 20000])
    features = random.choice([100, 500, 1000])
    
    try:
        logger.debug(f"ML: Allocating {size}x{features} matrix ({size*features*8/1e6:.1f} MB)")
        X = np.random.rand(size, features)
        
        logger.debug("ML: Computing correlation matrix")
        correlation = np.corrcoef(X.T)
        
        logger.debug("ML: Training ensemble model")
        y = np.random.randint(0, 2, size)
        model = RandomForestClassifier(n_estimators=100, n_jobs=-1, random_state=42)
        model.fit(X, y)
        
        logger.info(f"ML: Successfully processed large dataset ({size} samples)")
        
    except MemoryError as e:
        logger.critical(f"ML MEMORY EXHAUSTION: Failed to allocate memory for {size}x{features} dataset - {e}")
    except Exception as e:
        logger.error(f"ML PROCESSING FAILURE: {e}")

def ml_prediction_service_failure():
    """Simulates production ML prediction service failures"""
    logger.info("ML PRODUCTION: Handling prediction request")
    
    # Simulate model loading
    if random.random() > 0.85:
        logger.critical("ML PRODUCTION: Model file not found or corrupted")
        raise FileNotFoundError("Model file 'production_model.pkl' not found")
    
    # Simulate input validation
    input_data = np.random.rand(1, random.choice([4, 5, 6]))
    expected_features = 5
    
    if input_data.shape[1] != expected_features:
        logger.error(f"ML PRODUCTION: Input validation failed - expected {expected_features} features, got {input_data.shape[1]}")
        raise ValueError(f"Invalid input shape: {input_data.shape}")
    
    # Simulate prediction latency issues
    start_time = time.time()
    time.sleep(random.uniform(0.01, 0.15))
    elapsed = time.time() - start_time
    
    if elapsed > 0.1:
        logger.warning(f"ML PRODUCTION: Slow prediction - {elapsed*1000:.0f}ms (SLA: 100ms)")
    
    # Simulate prediction errors
    if random.random() > 0.9:
        logger.error("ML PRODUCTION: Model returned invalid prediction (NaN)")
        raise ValueError("Model output contains NaN values")
    
    logger.info(f"ML PRODUCTION: Prediction completed in {elapsed*1000:.1f}ms")

@app.route('/trigger-issue')
def trigger_random_issue():
    """Endpoint that triggers random issues"""
    scenarios = [
        ("race_condition", race_condition_scenario),
        ("deadlock", deadlock_scenario),
        ("memory_leak", memory_leak_scenario),
        ("null_pointer", null_pointer_scenario),
        ("resource_exhaustion", resource_exhaustion_scenario),
        ("timeout", timeout_scenario),
        ("divide_by_zero", divide_by_zero_scenario),
        ("index_out_of_bounds", index_out_of_bounds_scenario),
        ("json_parse_error", json_parse_error_scenario),
        ("queue_overflow", queue_overflow_scenario),
        ("ml_dimension_mismatch", ml_model_dimension_mismatch),
        ("ml_nan_infinity", ml_model_nan_infinity),
        ("ml_convergence_failure", ml_model_convergence_failure),
        ("ml_overfitting", ml_overfitting_scenario),
        ("ml_data_leakage", ml_data_leakage_scenario),
        ("ml_class_imbalance", ml_class_imbalance_scenario),
        ("ml_serialization_failure", ml_model_serialization_failure),
        ("ml_scaling_mismatch", ml_feature_scaling_mismatch),
        ("ml_memory_explosion", ml_memory_explosion),
        ("ml_prediction_service_failure", ml_prediction_service_failure)
    ]
    
    issue_name, scenario_func = random.choice(scenarios)
    
    logger.info(f"=== Triggering issue: {issue_name} ===")
    
    try:
        scenario_func()
        return jsonify({"status": "triggered", "issue": issue_name}), 200
    except Exception as e:
        logger.exception(f"Unhandled exception in {issue_name}: {e}")
        return jsonify({"status": "error", "issue": issue_name, "error": str(e)}), 500

@app.route('/concurrent-issues')
def trigger_concurrent_issues():
    """Triggers multiple issues concurrently to simulate high load"""
    num_threads = random.randint(5, 15)
    logger.info(f"=== Triggering {num_threads} concurrent issues ===")
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(trigger_random_issue) for _ in range(num_threads)]
        
    return jsonify({"status": "concurrent_issues_triggered", "count": num_threads}), 200

@app.route('/butterfly-effect')
def butterfly_effect():
    """Simulates butterfly effect - small change causing cascading failures"""
    logger.info("=== BUTTERFLY EFFECT: Small issue cascading into multiple failures ===")
    
    # Start with a small issue
    logger.debug("Initial condition: Minor delay in processing")
    time.sleep(0.1)
    
    # Cascade 1: Causes timeout
    logger.warning("Cascade 1: Delay causes timeout in dependent service")
    try:
        timeout_scenario()
    except:
        pass
    
    # Cascade 2: Timeout causes retry storm
    logger.warning("Cascade 2: Timeout triggers retry storm")
    for i in range(5):
        logger.error(f"Retry attempt {i+1}/5 failed")
        time.sleep(0.05)
    
    # Cascade 3: Retry storm exhausts connection pool
    logger.critical("Cascade 3: Retry storm exhausts connection pool")
    try:
        for _ in range(10):
            db.get_connection()
    except Exception as e:
        logger.critical(f"System destabilized: {e}")
    
    return jsonify({"status": "butterfly_effect_complete"}), 200

@app.route('/ml-pipeline-failure')
def ml_pipeline_failure():
    """Simulates complete ML pipeline failure cascade"""
    logger.critical("=== ML PIPELINE FAILURE: End-to-end failure simulation ===")
    
    try:
        # Stage 1: Data loading issues
        logger.info("ML Pipeline Stage 1: Data Loading")
        if random.random() > 0.7:
            raise FileNotFoundError("Training data file not found")
        
        # Stage 2: Data quality issues
        logger.info("ML Pipeline Stage 2: Data Validation")
        ml_model_nan_infinity()
        
        # Stage 3: Feature engineering failure
        logger.info("ML Pipeline Stage 3: Feature Engineering")
        if random.random() > 0.6:
            logger.error("ML PIPELINE: Feature extraction failed - missing required columns")
            raise KeyError("Required feature 'user_age' not found in dataset")
        
        # Stage 4: Training failure
        logger.info("ML Pipeline Stage 4: Model Training")
        ml_model_convergence_failure()
        
        # Stage 5: Validation failure
        logger.info("ML Pipeline Stage 5: Model Validation")
        ml_overfitting_scenario()
        
        # Stage 6: Serialization failure
        logger.info("ML Pipeline Stage 6: Model Persistence")
        ml_model_serialization_failure()
        
        logger.info("ML PIPELINE: Completed with warnings")
        return jsonify({"status": "completed_with_warnings"}), 200
        
    except Exception as e:
        logger.critical(f"ML PIPELINE CATASTROPHIC FAILURE: {type(e).__name__}: {e}")
        return jsonify({"status": "pipeline_failed", "error": str(e)}), 500

@app.route('/ml-training-job')
def ml_training_job():
    """Simulates a long-running ML training job with various issues"""
    logger.info("=== ML TRAINING JOB: Starting distributed training ===")
    
    def training_worker(worker_id):
        try:
            logger.info(f"ML WORKER-{worker_id}: Starting training")
            time.sleep(random.uniform(0.1, 0.3))
            
            if random.random() > 0.7:
                logger.error(f"ML WORKER-{worker_id}: OOM Error during gradient computation")
                raise MemoryError(f"Worker {worker_id} ran out of memory")
            
            if random.random() > 0.8:
                logger.error(f"ML WORKER-{worker_id}: GPU out of memory")
                raise RuntimeError(f"CUDA out of memory on worker {worker_id}")
            
            logger.info(f"ML WORKER-{worker_id}: Completed epoch")
            
        except Exception as e:
            logger.exception(f"ML WORKER-{worker_id}: Training failed - {e}")
    
    # Simulate distributed training
    workers = []
    for i in range(4):
        worker = threading.Thread(target=training_worker, args=(i,), daemon=True)
        worker.start()
        workers.append(worker)
    
    for worker in workers:
        worker.join()
    
    logger.info("=== ML TRAINING JOB: Completed ===")
    return jsonify({"status": "training_completed"}), 200
    """Health check endpoint"""
    logger.info("Health check requested")
    return jsonify({
        "status": "running",
        "counter": shared_counter,
        "db_connections": db.connection_count,
        "queue_size": shared_queue.qsize(),
        "memory_chunks": len(memory_leak_list)
    }), 200

@app.route('/chaos')
def chaos_mode():
    """Continuous chaos mode - keeps generating issues"""
    duration = int(request.args.get('duration', 10))
    logger.critical(f"=== CHAOS MODE ACTIVATED: {duration} seconds ===")
    
    def run_chaos():
        end_time = time.time() + duration
        while time.time() < end_time:
            trigger_random_issue()
            time.sleep(random.uniform(0.1, 0.5))
        logger.critical("=== CHAOS MODE ENDED ===")
    
    threading.Thread(target=run_chaos, daemon=True).start()
    
    return jsonify({"status": "chaos_mode_activated", "duration": duration}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)