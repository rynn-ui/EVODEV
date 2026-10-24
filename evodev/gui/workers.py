"""Worker thread pool for executing background operations off Tkinter's event loop."""

from concurrent.futures import ThreadPoolExecutor
import logging
import queue
import threading
import tkinter as tk
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class WorkerPool:
    """Manages background task threads and dispatches results safely to Tkinter main thread."""

    def __init__(self, root: tk.Tk, max_workers: int = 4):
        self.root = root
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="EvoDevGUIWorker")
        self._queue: queue.Queue = queue.Queue()
        self._is_shutdown = False
        self._lock = threading.Lock()
        self._poll_job: Optional[str] = None
        self._start_polling()

    def _start_polling(self) -> None:
        """Start the periodic poll on the Tkinter main thread."""
        if self._is_shutdown:
            return
        self._poll()

    def _poll(self) -> None:
        """Poll queued callbacks from worker threads and run them on the main thread."""
        if self._is_shutdown:
            return
        self.process_pending()
        try:
            self._poll_job = self.root.after(20, self._poll)
        except Exception:
            pass

    def process_pending(self) -> None:
        """Process any currently queued callbacks immediately on the calling thread."""
        while not self._queue.empty():
            try:
                cb = self._queue.get_nowait()
                cb()
            except queue.Empty:
                break
            except Exception as exc:
                logger.error(f"Error in dispatched worker callback: {exc}", exc_info=True)

    def run_async(
        self,
        task_fn: Callable[[], Any],
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_finish: Optional[Callable[[], None]] = None,
    ) -> None:
        """Execute task_fn in a worker thread and queue callbacks for the Tkinter main thread."""
        with self._lock:
            if self._is_shutdown:
                logger.warning("Attempted to submit task to shut-down WorkerPool.")
                return

        def _worker_wrapper():
            result = None
            error = None
            try:
                result = task_fn()
            except Exception as exc:
                error = exc
                logger.error(f"Worker task error: {exc}", exc_info=True)

            def _dispatch_to_main():
                try:
                    if error is not None:
                        if on_error:
                            on_error(error)
                    else:
                        if on_success:
                            on_success(result)
                finally:
                    if on_finish:
                        on_finish()

            # Enqueue to thread-safe queue for main thread to execute
            self._queue.put(_dispatch_to_main)

        self._executor.submit(_worker_wrapper)

    def shutdown(self, wait: bool = False) -> None:
        """Shut down the executor thread pool and cancel periodic polling."""
        with self._lock:
            self._is_shutdown = True
        if self._poll_job:
            try:
                self.root.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        self._executor.shutdown(wait=wait, cancel_futures=True)
