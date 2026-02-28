from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from datetime import datetime

from services.paylabs_client import paylabs_client
from database import get_db
from models import Transaction
from config import settings

router = APIRouter(prefix="/api/v1/paylabs", tags=["Paylabs"])

@router.post("/create-qris")
async def create_qris(request: Request):
    """
    Initiate a Paylabs QRIS transaction from the frontend.
    """
    body = await request.json()
    amount = body.get("amount", "100000")
    merchant = body.get("merchant", "Demo Merchant")
    
    # In production, use a public URL. For this demo we'll just not use notify_url 
    # or rely on ngrok/local testing if the user wants webhook testing.
    # The webhook endpoint will be available at /api/v1/paylabs/webhook
    # But since Paylabs is real, they need a real publicly routed URL. 
    # For now, let's just use the server's public endpoint if configured, or None. 
    # Just let Paylabs create it without notifying us if we only care about showing the QR code,
    # OR the user handles tunnels themselves.
    # Assuming webhook is deployed publicly, wait, this is a dashboard demo.
    # We will pass a dummy notify_url to ensure request formats nicely, or omit it.
    
    try:
        response = await paylabs_client.create_qris(
            amount=amount, 
            product_name=merchant
        )
        # Handle Paylabs response
        # Paylabs format: {"errCode":"0","errInfo":"Success","merchantId":"...","merchantTradeNo":"...", "payCode":"qr_code_string..."}
        if response.get("errCode") != "0":
            raise HTTPException(status_code=400, detail=response.get("errInfo", "Failed to create QRIS"))
            
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webhook")
async def paylabs_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Webhook handler for Paylabs payment notification.
    """
    raw_body = await request.body()
    str_body = raw_body.decode('utf-8')
    headers = request.headers
    
    timestamp = headers.get("X-TIMESTAMP", "")
    signature = headers.get("X-SIGNATURE", "")
    
    if not signature or not timestamp:
        raise HTTPException(status_code=400, detail="Missing signature headers")
        
    path = "/api/v1/paylabs/webhook"
    
    # Paylabs uses the relative path in the signature. E.g. "/callback"
    # Actually, we need to know exactly what path Paylabs used to hit us.
    # We will assume it's /api/v1/paylabs/webhook 
    # Wait, Paylabs documentation uses POST:/callback:... we'll use request.url.path
    is_valid = paylabs_client.verify_sign(request.url.path, str_body, signature, timestamp)
    
    if not is_valid:
        # We can log this but not fail during hackathon test maybe, but let's stick to true validation
        # Wait! In hackathons, strict verification might fail due to reverse proxies changing paths.
        # Fallback trying just /webhook or /api/v1/paylabs/webhook
        fallback_paths = [request.url.path, "/webhook", "/api/v1/paylabs/webhook"]
        for p in fallback_paths:
            if paylabs_client.verify_sign(p, str_body, signature, timestamp):
                is_valid = True
                break
                
        if not is_valid:
            print(f"WEBHOOK SIGNATURE VERIFICATION FAILED! headers={headers}, body={str_body}")
            # If still fails, for hackathon demo we might want to continue, but let's be secure.
            # Actually, return 400.
            raise HTTPException(status_code=400, detail="Invalid signature")

    import json
    data = json.loads(str_body)
    
    # Example fields from Paylabs callback:
    # {"requestId":"...","errCode":"0","paymentType":"QRIS","amount":"15000.00","merchantTradeNo":"...","status":"02"}
    
    status = data.get("status")
    if status == "02": # 02 usually means SUCCESS in Paylabs
        # Create a legitimate transaction in SQL
        txn_id = data.get("merchantTradeNo", "TXN-" + timestamp)
        new_txn = Transaction(
            txn_id=txn_id,
            timestamp=datetime.utcnow(),
            payer="User", 
            issuer="Paylabs", 
            country="ID",
            merchant="Aegis Demo Merchant",
            city="Jakarta",
            amount_idr=int(float(data.get("amount", 0))),
            amount_foreign=0.0,
            currency="IDR",
            risk_score=0.1,  # Legitimate
            is_flagged=False,
            is_fraud=False,
            fraud_type=None,
            attack_detail=None,
            xai_reasons=[]
        )
        
        db.add(new_txn)
        await db.commit()
        print(f"Recorded legitimate Paylabs transaction: {txn_id} for {new_txn.amount_idr} IDR")
    
    return {"errCode": "0", "errInfo": "Success"}
