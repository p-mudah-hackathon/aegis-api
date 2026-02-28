import json
import hashlib
import base64
import random
import logging
from datetime import datetime, timezone, timedelta
import httpx
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA

from config import settings

logger = logging.getLogger(__name__)

class PaylabsClient:
    def __init__(self):
        self.server = "SIT"
        self.url_sit = "https://sit-pay.paylabs.co.id/payment"
        self.version = "v2.1"
        self.mid = settings.paylabs_merchant_id
        
        self.public_key = self._format_key(settings.paylabs_public_key, is_private=False)
        self.private_key = self._format_key(settings.paylabs_private_key, is_private=True)

    def _format_key(self, key_data: str, is_private: bool) -> str:
        """Helper to ensure RSA keys have proper newlines."""
        if not key_data:
            return ""
        if "BEGIN " in key_data:
            return key_data.replace("\\n", "\n")
            
        header = "-----BEGIN RSA PRIVATE KEY-----" if is_private else "-----BEGIN PUBLIC KEY-----"
        footer = "-----END RSA PRIVATE KEY-----" if is_private else "-----END PUBLIC KEY-----"
        
        # If it's a raw base64 string without headers and newlines
        chunks = [key_data[i:i+64] for i in range(0, len(key_data), 64)]
        body = "\n".join(chunks)
        return f"{header}\n{body}\n{footer}"

    def _get_datetime(self):
        jakarta_tz = timezone(timedelta(hours=7))
        now = datetime.now(jakarta_tz)
        return now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+07:00"

    def _generate_id_request(self):
        jakarta_tz = timezone(timedelta(hours=7))
        now = datetime.now(jakarta_tz)
        return str(now.strftime("%Y%m%d%H%M%S") + str(random.randint(11111, 99999)))

    def _generate_sign(self, path: str, body: dict, date_time: str) -> str:
        # Convert body to JSON string (no spaces)
        json_str = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
        sha_json = hashlib.sha256(json_str.encode()).hexdigest()

        # e.g., POST:/payment/v2.1/qris/create:hash:date
        endpoint_path = f"/payment/{self.version}{path}"
        signature_before = f"POST:{endpoint_path}:{sha_json}:{date_time}"

        private_key_obj = RSA.import_key(self.private_key)
        h = SHA256.new(signature_before.encode())
        signature = pkcs1_15.new(private_key_obj).sign(h)
        return base64.b64encode(signature).decode()

    def verify_sign(self, path: str, data_to_sign: str, sign: str, date_time: str) -> bool:
        """
        Verify the Paylabs signature.
        We expect data_to_sign to be the raw payload string.
        """
        try:
            binary_signature = base64.b64decode(sign)
            sha_json = hashlib.sha256(data_to_sign.encode()).hexdigest()
            signature_after = f"POST:{path}:{sha_json}:{date_time}"

            public_key_obj = RSA.import_key(self.public_key)
            h = SHA256.new(signature_after.encode())
            pkcs1_15.new(public_key_obj).verify(h, binary_signature)
            return True
        except (ValueError, TypeError) as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    async def create_qris(self, amount: str, product_name: str, notify_url: str = None) -> dict:
        """
        Create a dynamic QRIS code or payment.
        """
        path = "/qris/create"
        date_time = self._get_datetime()
        id_request = self._generate_id_request()

        body = {
            "merchantId": self.mid,
            "merchantTradeNo": id_request,
            "requestId": id_request,
            "paymentType": "QRIS",
            "amount": str(amount),
            "productName": product_name
        }
        
        if notify_url:
            body["notifyUrl"] = notify_url

        signature = self._generate_sign(path, body, date_time)

        headers = {
            "X-TIMESTAMP": date_time,
            "X-SIGNATURE": signature,
            "X-PARTNER-ID": self.mid,
            "X-REQUEST-ID": id_request,
            "Content-Type": "application/json;charset=utf-8"
        }

        url = f"{self.url_sit}/{self.version}{path}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=body, timeout=10.0)
            response.raise_for_status()
            return response.json()

paylabs_client = PaylabsClient()
