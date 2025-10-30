# src/agents/outreach_agent.py
from .base_agent import BaseAgent
from jinja2 import Template
from email_validator import validate_email, EmailNotValidError
import os

# ✅ Reusable HTML Email Template (SendGrid-friendly)
EMAIL_TEMPLATE = """
<p>Dear {{ provider_name }},</p>

<p>We are updating our records for <b>{{ practice_name }}</b>.</p>

<p>Our system noticed some missing or inconsistent details.</p>

<p><b>Current Info:</b><br>
Phone: {{ phone }}<br>
Address: {{ address }}</p>

<p>Please confirm or update your details by clicking the link below:<br>
<a href="{{ verification_link }}">Verify Now</a></p>

<p>Thank you,<br>Provider Validation Team</p>
"""

class OutreachAgent(BaseAgent):
    async def run(self, payload):
        """
        Triggers outreach only when:
        - Confidence < 0.6 OR
        - Flags exist in the profile
        """
        profile = payload.get("profile") or payload
        provider_id = profile.get("id")

        # ✅ Confidence + flag check (your original logic preserved)
        if profile.get("final_confidence", 1.0) < 0.6 or profile.get("flags"):
            provider_name = (
                profile.get("name", {}).get("value")
                if isinstance(profile.get("name"), dict)
                else profile.get("name", "Provider")
            )
            practice_name = profile.get("practice_name", provider_name)
            phone = (
                profile.get("phone", {}).get("value")
                if isinstance(profile.get("phone"), dict)
                else profile.get("phone", "N/A")
            )
            address = (
                profile.get("address", {}).get("value")
                if isinstance(profile.get("address"), dict)
                else profile.get("address", "N/A")
            )

            # ✅ Get and validate email
            email = (
                profile.get("email")
                or (profile.get("emails") and profile["emails"][0])
                or None
            )
            if email:
                try:
                    validate_email(email)
                except EmailNotValidError:
                    email = None

            # ✅ Dynamic verification link
            base_url = os.getenv("VERIFICATION_BASE_URL", "http://localhost:8000/verify")
            verification_link = f"{base_url}?provider_id={provider_id}"

            # ✅ Render template
            body = Template(EMAIL_TEMPLATE).render(
                provider_name=provider_name,
                practice_name=practice_name,
                phone=phone,
                address=address,
                verification_link=verification_link,
            )

            # ✅ Final draft returned
            return {
                "provider_id": provider_id,
                "subject": "Please verify your provider directory info",
                "body": body,
                "recipient": email,
            }

        # If no outreach needed
        return None
