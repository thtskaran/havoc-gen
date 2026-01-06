import logging
import random
import threading
import time
import asyncio
from datetime import datetime
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import queue
import json
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import pickle
import warnings
import signal

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
shared_balance = 10000
shared_inventory = {'item_a': 100, 'item_b': 50, 'item_c': 75}
lock_a = threading.Lock()
lock_b = threading.Lock()
lock_c = threading.Lock()
lock_d = threading.Lock()
lock_inventory = threading.Lock()
lock_balance = threading.Lock()
shared_queue = queue.Queue(maxsize=10)
priority_queue = queue.PriorityQueue(maxsize=15)
memory_leak_list = []

# Asyncio event loops per thread
thread_loops = {}
loop_locks = {}

# Auto-generation control
auto_generation_active = True
worker_threads = []
thread_pool = ThreadPoolExecutor(max_workers=15)

class DatabaseSimulator:
    """Simulates database connection issues"""
    def __init__(self):
        self.connection_count = 0
        self.max_connections = 5
        self.lock = threading.Lock()
        
    def get_connection(self):
        with self.lock:
            self.connection_count += 1
            if self.connection_count > self.max_connections:
                logger.error(f"DATABASE CONNECTION POOL EXHAUSTED: {self.connection_count}/{self.max_connections} connections")
                raise Exception("Too many database connections")
            logger.debug(f"Database connection acquired: {self.connection_count}/{self.max_connections}")
            return f"conn_{self.connection_count}"
    
    def release_connection(self):
        with self.lock:
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
        lambda: logger.debug(f"Websocket message delivered to {random.randint(1, 50)} clients"),
        lambda: logger.info(f"Scheduled job completed: backup_job_{random.randint(1, 20)}"),
        lambda: logger.debug(f"Redis cache updated: key=session:{random.randint(1000, 9999)}"),
        lambda: logger.info(f"Load balancer health check passed"),
        lambda: logger.debug(f"Metrics exported: CPU={random.randint(20, 80)}%, Memory={random.randint(40, 90)}%"),
    ]
    
    random.choice(operations)()

def aggressive_race_condition():
    """More aggressive race condition with multiple shared resources"""
    global shared_counter, shared_balance
    thread_name = threading.current_thread().name
    
    logger.warning(f"RACE CONDITION: {thread_name} accessing shared counter without lock")
    
    # Simulate race on counter
    temp_counter = shared_counter
    time.sleep(random.uniform(0.001, 0.02))
    shared_counter = temp_counter + random.randint(1, 10)
    
    logger.debug(f"Counter updated to: {shared_counter} by {thread_name}")
    
    # Simulate race on balance
    if random.random() > 0.5:
        logger.warning(f"RACE CONDITION: {thread_name} accessing shared balance")
        temp_balance = shared_balance
        time.sleep(random.uniform(0.001, 0.015))
        withdrawal = random.randint(100, 500)
        shared_balance = temp_balance - withdrawal
        logger.error(f"CRITICAL RACE: Balance now {shared_balance} - possible negative balance!")

def complex_deadlock_scenario():
    """More complex deadlock with multiple locks"""
    thread_id = threading.current_thread().name
    
    # Random lock acquisition order to create deadlocks
    locks = [lock_a, lock_b, lock_c, lock_d]
    random.shuffle(locks)
    
    acquired_locks = []
    
    try:
        for i, lock in enumerate(locks[:3]):
            lock_name = f"lock_{['a','b','c','d'][locks.index(lock)]}"
            logger.warning(f"DEADLOCK RISK: {thread_id} attempting to acquire {lock_name}")
            
            if lock.acquire(timeout=random.uniform(0.05, 0.15)):
                acquired_locks.append(lock)
                logger.debug(f"{thread_id} acquired {lock_name}")
                time.sleep(random.uniform(0.01, 0.05))
            else:
                logger.error(f"DEADLOCK DETECTED: {thread_id} couldn't acquire {lock_name}, holding {len(acquired_locks)} locks!")
                break
                
    except Exception as e:
        logger.exception(f"Exception in deadlock scenario: {e}")
    finally:
        for lock in acquired_locks:
            lock.release()

def inventory_race_condition():
    """Race condition on inventory management"""
    global shared_inventory
    thread_name = threading.current_thread().name
    
    item = random.choice(['item_a', 'item_b', 'item_c'])
    quantity = random.randint(1, 10)
    
    logger.warning(f"INVENTORY RACE: {thread_name} checking {item} stock")
    
    # Check without lock
    if shared_inventory.get(item, 0) >= quantity:
        time.sleep(random.uniform(0.01, 0.03))  # Simulate processing
        shared_inventory[item] -= quantity
        logger.info(f"{thread_name} sold {quantity} of {item}, remaining: {shared_inventory[item]}")
        
        if shared_inventory[item] < 0:
            logger.critical(f"INVENTORY CORRUPTION: {item} has negative stock: {shared_inventory[item]}")
    else:
        logger.warning(f"{thread_name} insufficient stock for {item}")

async def async_deadlock_scenario():
    """Asyncio event loop deadlock"""
    thread_id = threading.current_thread().name
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        thread_loops[thread_id] = loop
    
    logger.warning(f"ASYNC DEADLOCK: {thread_id} creating coroutine with locks")
    
    async def task_with_lock():
        logger.debug(f"{thread_id} async task acquiring lock_a")
        lock_a.acquire()
        try:
            await asyncio.sleep(random.uniform(0.02, 0.05))
            logger.debug(f"{thread_id} async task trying lock_b")
            if lock_b.acquire(timeout=0.1):
                await asyncio.sleep(random.uniform(0.01, 0.03))
                lock_b.release()
            else:
                logger.error(f"ASYNC DEADLOCK: {thread_id} event loop stuck waiting for lock_b")
        finally:
            lock_a.release()
    
    try:
        loop.run_until_complete(asyncio.wait_for(task_with_lock(), timeout=0.5))
    except asyncio.TimeoutError:
        logger.critical(f"ASYNC TIMEOUT: {thread_id} event loop timed out!")
    except Exception as e:
        logger.exception(f"Async exception: {e}")

def event_loop_blocking():
    """Blocking operations in event loop"""
    thread_id = threading.current_thread().name
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    logger.warning(f"EVENT LOOP BLOCKING: {thread_id} running blocking operation in async context")
    
    async def blocking_operation():
        logger.debug(f"{thread_id} starting blocking I/O in event loop")
        # Simulate blocking operation
        time.sleep(random.uniform(0.1, 0.3))
        logger.error(f"EVENT LOOP BLOCKED: {thread_id} blocked event loop for extended period")
    
    try:
        loop.run_until_complete(blocking_operation())
    except Exception as e:
        logger.exception(f"Event loop error: {e}")

def cascading_timeout_scenario():
    """Cascading timeouts across services"""
    thread_id = threading.current_thread().name
    
    logger.info(f"SERVICE CHAIN: {thread_id} starting service call chain")
    
    services = ['auth_service', 'user_service', 'payment_service', 'notification_service']
    
    for i, service in enumerate(services):
        timeout = random.uniform(0.1, 0.8)
        max_timeout = 0.3
        
        logger.debug(f"{thread_id} calling {service} (timeout: {max_timeout}s)")
        
        if timeout > max_timeout:
            logger.error(f"TIMEOUT CASCADE: {service} timed out after {max_timeout}s, breaking chain at step {i+1}/{len(services)}")
            
            # Retry logic causing more issues
            for retry in range(3):
                logger.warning(f"{thread_id} retry {retry+1}/3 for {service}")
                time.sleep(random.uniform(0.05, 0.1))
                if random.random() > 0.7:
                    logger.info(f"{thread_id} retry succeeded for {service}")
                    break
            else:
                logger.critical(f"RETRY EXHAUSTION: {service} failed after 3 retries")
                raise TimeoutError(f"Service chain broken at {service}")
        else:
            time.sleep(timeout)
            logger.info(f"{thread_id} {service} completed in {timeout:.3f}s")

def thread_pool_exhaustion():
    """Thread pool saturation"""
    thread_id = threading.current_thread().name
    
    logger.warning(f"THREAD POOL: {thread_id} submitting tasks to pool")
    
    def slow_task(task_id):
        logger.debug(f"Task-{task_id} starting in {threading.current_thread().name}")
        time.sleep(random.uniform(0.5, 2.0))
        logger.debug(f"Task-{task_id} completed")
    
    futures = []
    num_tasks = random.randint(20, 40)
    
    for i in range(num_tasks):
        try:
            future = thread_pool.submit(slow_task, i)
            futures.append(future)
        except Exception as e:
            logger.error(f"THREAD POOL EXHAUSTED: Cannot submit task {i} - {e}")
    
    # Try to get results with timeout
    completed = 0
    for future in futures[:5]:  # Only wait for first 5
        try:
            future.result(timeout=0.1)
            completed += 1
        except FutureTimeoutError:
            logger.error(f"FUTURE TIMEOUT: Task did not complete in time")
        except Exception as e:
            logger.exception(f"Task failed: {e}")
    
    logger.warning(f"THREAD POOL: {completed}/{min(5, num_tasks)} tasks completed, {num_tasks-completed} still running")

def async_task_timeout():
    """Async tasks timing out"""
    thread_id = threading.current_thread().name
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    async def slow_async_task(task_num):
        logger.debug(f"{thread_id} async task-{task_num} started")
        await asyncio.sleep(random.uniform(0.5, 2.0))
        logger.debug(f"{thread_id} async task-{task_num} completed")
    
    async def run_with_timeout():
        tasks = [slow_async_task(i) for i in range(5)]
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=0.3)
            logger.info(f"{thread_id} all async tasks completed")
        except asyncio.TimeoutError:
            logger.error(f"ASYNC TIMEOUT: {thread_id} tasks exceeded 0.3s timeout")
    
    try:
        loop.run_until_complete(run_with_timeout())
    except Exception as e:
        logger.exception(f"Async error: {e}")

def liveliness_probe_failure():
    """Simulates k8s liveliness probe failures"""
    thread_id = threading.current_thread().name
    
    response_time = random.uniform(0.05, 2.0)
    threshold = 0.5
    
    logger.debug(f"LIVELINESS PROBE: {thread_id} health check initiated")
    
    time.sleep(response_time)
    
    if response_time > threshold:
        logger.critical(f"LIVELINESS FAILURE: {thread_id} probe took {response_time:.3f}s (threshold: {threshold}s) - pod may be restarted!")
    else:
        logger.info(f"LIVELINESS PROBE: {thread_id} passed in {response_time:.3f}s")

def circuit_breaker_trip():
    """Circuit breaker pattern failures"""
    thread_id = threading.current_thread().name
    
    failure_count = random.randint(1, 10)
    threshold = 5
    
    logger.info(f"CIRCUIT BREAKER: {thread_id} monitoring service calls")
    
    for i in range(failure_count):
        if random.random() > 0.6:
            logger.warning(f"{thread_id} service call {i+1} failed")
        else:
            logger.debug(f"{thread_id} service call {i+1} succeeded")
    
    if failure_count >= threshold:
        logger.error(f"CIRCUIT BREAKER OPEN: {thread_id} too many failures ({failure_count}/{threshold}) - circuit opened!")
        time.sleep(random.uniform(1.0, 3.0))
        logger.warning(f"CIRCUIT BREAKER: {thread_id} attempting half-open state")

def memory_leak_scenario():
    """Simulates memory leak by accumulating data"""
    global memory_leak_list
    
    chunk_size = random.randint(5000, 20000)
    data_chunk = [random.randint(0, 1000) for _ in range(chunk_size)]
    memory_leak_list.append(data_chunk)
    
    logger.warning(f"MEMORY LEAK: List growing unbounded, current size: {len(memory_leak_list)} chunks ({chunk_size} items/chunk)")
    
    if len(memory_leak_list) > 50:
        logger.critical(f"MEMORY LEAK CRITICAL: {len(memory_leak_list)} chunks accumulated! Estimated {len(memory_leak_list) * chunk_size * 8 / 1e6:.1f}MB")
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
        
        if random.random() > 0.6:
            logger.warning(f"RESOURCE LEAK: Connection {conn} not properly released")
            time.sleep(random.uniform(0.1, 0.5))
        else:
            time.sleep(random.uniform(0.01, 0.05))
            db.release_connection()
    except Exception as e:
        logger.exception(f"RESOURCE EXHAUSTION: {e}")

def starvation_scenario():
    """Thread starvation"""
    thread_id = threading.current_thread().name
    priority = random.randint(1, 10)
    
    logger.warning(f"THREAD STARVATION: {thread_id} priority={priority} waiting for resources")
    
    if priority < 3:
        time.sleep(random.uniform(1.0, 3.0))
        logger.critical(f"STARVATION: Low priority {thread_id} waited {3}s, still not scheduled!")
    else:
        time.sleep(random.uniform(0.01, 0.1))
        logger.info(f"{thread_id} executed with priority {priority}")

# Auto-generation workers
def aggressive_worker(worker_id):
    """Aggressive worker that generates errors frequently"""
    thread_name = f"AggressiveWorker-{worker_id}"
    threading.current_thread().name = thread_name
    
    logger.info(f"🔥 {thread_name} started - HIGH HAZARD MODE")
    
    error_scenarios = [
        aggressive_race_condition,
        complex_deadlock_scenario,
        inventory_race_condition,
        cascading_timeout_scenario,
        thread_pool_exhaustion,
        async_task_timeout,
        circuit_breaker_trip,
        memory_leak_scenario,
        resource_exhaustion_scenario,
        starvation_scenario,
        liveliness_probe_failure,
    ]
    
    while auto_generation_active:
        try:
            # Generate 2-4 operations per cycle
            for _ in range(random.randint(2, 4)):
                if random.random() < 0.4:  # 40% normal, 60% errors
                    normal_operation_logs()
                else:
                    scenario = random.choice(error_scenarios)
                    try:
                        scenario()
                    except Exception as e:
                        logger.exception(f"{thread_name} scenario error: {e}")
            
            time.sleep(random.uniform(0.3, 1.5))
            
        except Exception as e:
            logger.exception(f"{thread_name} critical error: {e}")
            time.sleep(1)

def async_worker(worker_id):
    """Worker focused on async operations"""
    thread_name = f"AsyncWorker-{worker_id}"
    threading.current_thread().name = thread_name
    
    logger.info(f"⚡ {thread_name} started - ASYNC OPERATIONS")
    
    async_scenarios = [
        async_deadlock_scenario,
        event_loop_blocking,
        async_task_timeout,
    ]
    
    while auto_generation_active:
        try:
            scenario = random.choice(async_scenarios)
            scenario()
            time.sleep(random.uniform(0.5, 2.0))
        except Exception as e:
            logger.exception(f"{thread_name} error: {e}")
            time.sleep(1)

def normal_worker(worker_id):
    """Worker that generates mostly normal logs"""
    thread_name = f"NormalWorker-{worker_id}"
    threading.current_thread().name = thread_name
    
    logger.info(f"✅ {thread_name} started - NORMAL OPERATIONS")
    
    while auto_generation_active:
        try:
            for _ in range(random.randint(3, 6)):
                normal_operation_logs()
            time.sleep(random.uniform(0.5, 2.5))
        except Exception as e:
            logger.exception(f"{thread_name} error: {e}")
            time.sleep(1)

def chaos_worker(worker_id):
    """Chaotic worker with random behaviors"""
    thread_name = f"ChaosWorker-{worker_id}"
    threading.current_thread().name = thread_name
    
    logger.info(f"💥 {thread_name} started - CHAOS MODE")
    
    all_scenarios = [
        aggressive_race_condition,
        complex_deadlock_scenario,
        inventory_race_condition,
        async_deadlock_scenario,
        event_loop_blocking,
        cascading_timeout_scenario,
        thread_pool_exhaustion,
        async_task_timeout,
        liveliness_probe_failure,
        circuit_breaker_trip,
        memory_leak_scenario,
        null_pointer_scenario,
        resource_exhaustion_scenario,
        starvation_scenario,
    ]
    
    while auto_generation_active:
        try:
            # Burst of activity
            burst_size = random.randint(1, 8)
            for _ in range(burst_size):
                if random.random() < 0.3:
                    normal_operation_logs()
                else:
                    scenario = random.choice(all_scenarios)
                    try:
                        scenario()
                    except Exception as e:
                        logger.exception(f"{thread_name} scenario failed: {e}")
            
            # Variable sleep
            time.sleep(random.uniform(0.1, 3.0))
            
        except Exception as e:
            logger.exception(f"{thread_name} critical error: {e}")
            time.sleep(1)

def start_all_workers():
    """Start all worker threads"""
    global worker_threads
    
    worker_threads = []
    
    # Start 3 aggressive workers
    for i in range(3):
        thread = threading.Thread(target=aggressive_worker, args=(i,), daemon=True)
        thread.start()
        worker_threads.append(thread)
    
    # Start 2 async workers
    for i in range(2):
        thread = threading.Thread(target=async_worker, args=(i,), daemon=True)
        thread.start()
        worker_threads.append(thread)
    
    # Start 2 normal workers
    for i in range(2):
        thread = threading.Thread(target=normal_worker, args=(i,), daemon=True)
        thread.start()
        worker_threads.append(thread)
    
    # Start 3 chaos workers
    for i in range(3):
        thread = threading.Thread(target=chaos_worker, args=(i,), daemon=True)
        thread.start()
        worker_threads.append(thread)
    
    logger.info(f"🚀 Started {len(worker_threads)} worker threads")

# WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    logger.info(f"🔌 Client connected: {request.sid}")
    emit('status', {'message': 'Connected to log stream', 'status': 'active', 'workers': len(worker_threads)})

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
        "service": "Production Issues Simulator - HAZARDOUS MODE",
        "version": "3.0",
        "features": [
            "Real-time log streaming via WebSocket",
            "Multi-threaded chaos generation",
            "Async/await deadlocks",
            "Cascading timeouts",
            "Thread pool exhaustion"
        ],
        "websocket_url": "/socket.io",
        "active_workers": len([t for t in worker_threads if t.is_alive()]),
        "auto_generation": "active" if auto_generation_active else "inactive"
    }), 200

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "running" if auto_generation_active else "stopped",
        "counter": shared_counter,
        "balance": shared_balance,
        "inventory": shared_inventory,
        "db_connections": db.connection_count,
        "queue_size": shared_queue.qsize(),
        "memory_chunks": len(memory_leak_list),
        "active_workers": len([t for t in worker_threads if t.is_alive()]),
        "thread_pool_queue": thread_pool._work_queue.qsize()
    }), 200

@app.route('/auto-generation/start')
def start_auto_generation():
    """Start automatic log generation"""
    global auto_generation_active
    
    if auto_generation_active:
        return jsonify({"status": "already_running", "workers": len(worker_threads)}), 200
    
    auto_generation_active = True
    start_all_workers()
    
    logger.info("🚀 AUTO-GENERATION: Started via API")
    return jsonify({"status": "started", "workers": len(worker_threads)}), 200

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
        "workers": len(worker_threads),
        "alive_workers": len([t for t in worker_threads if t.is_alive()])
    }), 200

if __name__ == '__main__':
    # Start all workers on startup
    start_all_workers()
    
    logger.info("="*80)
    logger.info("🚀 Production Issues Simulator Starting - MAXIMUM HAZARD MODE")
    logger.info("WebSocket endpoint: ws://localhost:5000/socket.io")
    logger.info(f"Workers: {len(worker_threads)} threads active")
    logger.info("Features: Race conditions, Deadlocks, Async deadlocks, Cascading timeouts")
    logger.info("="*80)
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)