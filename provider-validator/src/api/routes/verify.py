# src/api/routes/verify.py
"""
Provider Email Verification Endpoint.

This is the URL that providers click when they receive an outreach email.
The link looks like: http://your-server.com/verify?provider_id=42

When clicked:
  1. mark_provider_verified() updates the outreach_logs table
  2. Returns a user-friendly HTML confirmation page
  3. The provider's confidence score should be manually updated by admin after review

To register this route in your main app.py, make sure you have:
    from src.api.routes.verify import router as verify_router
    app.include_router(verify_router)
"""

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from src.dbutils import mark_provider_verified

router = APIRouter(tags=["Verification"])


@router.get("/verify", response_class=HTMLResponse)
async def verify_provider(provider_id: int = Query(..., description="The provider's database ID")):
    """
    Called when a provider clicks the verification link in their outreach email.

    Returns a simple HTML confirmation page — no redirect needed.
    The provider just sees a "Thank you" message in their browser.
    """
    success = mark_provider_verified(provider_id, source="email_link_click")

    if success:
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <title>Verification Confirmed</title>
          <style>
            body {{ font-family: Arial, sans-serif; background: #f0f4f8;
                    display: flex; align-items: center; justify-content: center;
                    height: 100vh; margin: 0; }}
            .card {{ background: white; border-radius: 12px; padding: 40px 50px;
                     text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.1);
                     max-width: 500px; }}
            h1 {{ color: #38a169; }}
            p  {{ color: #4a5568; line-height: 1.6; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h1>✅ Thank You!</h1>
            <p>Your provider information has been confirmed.</p>
            <p>Our team will review your details and update the directory shortly.</p>
            <p style="color: #a0aec0; font-size: 13px;">Provider ID: {provider_id}</p>
          </div>
        </body>
        </html>
        """
    else:
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <title>Verification Error</title>
          <style>
            body {{ font-family: Arial, sans-serif; background: #f0f4f8;
                    display: flex; align-items: center; justify-content: center;
                    height: 100vh; margin: 0; }}
            .card {{ background: white; border-radius: 12px; padding: 40px 50px;
                     text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
            h1 {{ color: #e53e3e; }}
            p  {{ color: #4a5568; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h1>⚠️ Link Expired or Invalid</h1>
            <p>This verification link may have already been used, or the provider ID
               could not be found.</p>
            <p>Please contact the administrator if you need assistance.</p>
          </div>
        </body>
        </html>
        """

    return HTMLResponse(content=html)