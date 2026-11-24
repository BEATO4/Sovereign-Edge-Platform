"""
Amazon SQS compatible task queue interface.
Decouples external API requests from internal infrastructure provisioning workers.
"""
import time
import json
import uuid
import os
from typing import Dict, Any, Optional, List

QUEUE_FILE = os.path.join(os.path.dirname(__file__), "osb_sqs_queue.json")

class SQSQueue:
    def __init__(self, queue_file: str = QUEUE_FILE, visibility_timeout_sec: int = 30):
        self.queue_file = queue_file
        self.visibility_timeout = visibility_timeout_sec
        self._messages: List[Dict[str, Any]] = []
        self._dlq: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._messages = data.get("messages", [])
                    self._dlq = data.get("dlq", [])
            except Exception:
                pass

    def _save(self):
        os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
        with open(self.queue_file, "w", encoding="utf-8") as f:
            json.dump({
                "messages": self._messages,
                "dlq": self._dlq
            }, f, indent=2)

    def send_message(self, body: Dict[str, Any], message_attributes: Optional[Dict[str, Any]] = None) -> str:
        msg_id = f"msg-{uuid.uuid4().hex[:12]}"
        message = {
            "MessageId": msg_id,
            "Body": body,
            "Attributes": message_attributes or {},
            "SentTimestamp": time.time(),
            "VisibleAfter": time.time(),
            "ReceiptHandle": None,
            "ApproximateReceiveCount": 0
        }
        self._messages.append(message)
        self._save()
        return msg_id

    def receive_messages(self, max_number: int = 1) -> List[Dict[str, Any]]:
        now = time.time()
        received = []
        for msg in self._messages:
            if msg["VisibleAfter"] <= now and msg["ReceiptHandle"] is None:
                msg["ApproximateReceiveCount"] += 1
                if msg["ApproximateReceiveCount"] > 5:
                    # Move to DLQ if exceeded max receive count
                    self._dlq.append(msg)
                    self._messages.remove(msg)
                    continue
                receipt_handle = f"rcpt-{uuid.uuid4().hex[:16]}"
                msg["ReceiptHandle"] = receipt_handle
                msg["VisibleAfter"] = now + self.visibility_timeout
                received.append({
                    "MessageId": msg["MessageId"],
                    "ReceiptHandle": receipt_handle,
                    "Body": msg["Body"],
                    "Attributes": msg["Attributes"],
                    "ApproximateReceiveCount": msg["ApproximateReceiveCount"]
                })
                if len(received) >= max_number:
                    break
        if received or self._dlq:
            self._save()
        return received

    def delete_message(self, receipt_handle: str) -> bool:
        for i, msg in enumerate(self._messages):
            if msg.get("ReceiptHandle") == receipt_handle:
                self._messages.pop(i)
                self._save()
                return True
        return False

    def get_stats(self) -> Dict[str, int]:
        now = time.time()
        visible = sum(1 for m in self._messages if m["VisibleAfter"] <= now and m["ReceiptHandle"] is None)
        in_flight = sum(1 for m in self._messages if m["ReceiptHandle"] is not None and m["VisibleAfter"] > now)
        return {
            "approximate_visible": visible,
            "approximate_in_flight": in_flight,
            "approximate_dlq": len(self._dlq)
        }
