import threading
import uuid
import time
from concurrent.futures import ThreadPoolExecutor
from neo.core.logger import logger

# Global task registry
tasks = {}
task_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=4)

def create_task(func, *args, **kwargs):
    """Creates and submits a background task."""
    task_id = str(uuid.uuid4())
    with task_lock:
        tasks[task_id] = {
            'status': 'pending',
            'progress': 0,
            'result': None,
            'error': None,
            'start_time': time.time(),
            'end_time': None
        }
    
    def task_wrapper():
        try:
            update_task(task_id, status='running')
            # Pass task_id to the function if it supports it for progress updates
            if 'task_id' in func.__code__.co_varnames:
                kwargs['task_id'] = task_id
            
            result = func(*args, **kwargs)
            update_task(task_id, status='completed', result=result, progress=100)
        except Exception as e:
            logger.error(f"Task {task_id} failed: {str(e)}", exc_info=True)
            update_task(task_id, status='failed', error=str(e))
        finally:
            update_task(task_id, end_time=time.time())

    executor.submit(task_wrapper)
    return task_id

def update_task(task_id, **kwargs):
    """Updates task metadata."""
    with task_lock:
        if task_id in tasks:
            tasks[task_id].update(kwargs)

def get_task_status(task_id):
    """Retrieves task status."""
    with task_lock:
        return tasks.get(task_id)


def get_active_tasks():
    """Return IDs of tasks that have not finished (pending/running)."""
    with task_lock:
        return [
            tid for tid, t in tasks.items()
            if t.get('status') in ('pending', 'running')
        ]

def cleanup_tasks(expiry_seconds=86400):
    """Removes old tasks from the registry."""
    now = time.time()
    with task_lock:
        to_delete = [
            tid for tid, t in tasks.items() 
            if t['end_time'] and now - t['end_time'] > expiry_seconds
        ]
        for tid in to_delete:
            del tasks[tid]

# Background thread for periodic cleanup
def start_cleanup_worker():
    def worker():
        while True:
            time.sleep(3600) # Every hour
            cleanup_tasks()
    t = threading.Thread(target=worker, daemon=True)
    t.start()

start_cleanup_worker()
