import httpx

RESEND_API_URL = "https://api.resend.com/emails"


async def send_email(
    api_key: str, from_email: str, to_email: str, subject: str, html: str
) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=30,
        )
        response.raise_for_status()
