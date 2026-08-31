import logging
from typing import Any, Dict, List, Optional, Union

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection, send_mail

logger = logging.getLogger(__name__)


class EmailService:

    @classmethod
    def send_email(
        cls,
        subject: str,
        recipient_list: Union[str, List[str]],
        body: str,
        html_message: Optional[str] = None,
        from_email: Optional[str] = None,
        fail_silently: bool = False,
    ) -> bool:
        if isinstance(recipient_list, str):
            recipients = [recipient_list]
        else:
            recipients = list(recipient_list)

        sender = from_email or settings.DEFAULT_FROM_EMAIL

        try:
            if html_message:
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=body,
                    from_email=sender,
                    to=recipients,
                )
                email.attach_alternative(html_message, "text/html")
                email.send(fail_silently=fail_silently)
            else:
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=sender,
                    recipient_list=recipients,
                    fail_silently=fail_silently,
                )
            return True
        except Exception:
            if not fail_silently:
                logger.exception("Failed to send email to recipients")
            return False

    @classmethod
    def send_bulk_email(
        cls,
        subject: str,
        recipients: List[str],
        body: str,
        html_message: Optional[str] = None,
        from_email: Optional[str] = None,
        send_mode: str = "bcc",
        fail_silently: bool = False,
    ) -> Dict[str, Any]:
        """Send one email to multiple recipients.

        send_mode:
        - 'bcc' (default): Sends 1 email with recipients in BCC (hides recipients from each other).
        - 'individual': Sends separate individual emails using a single SMTP connection.
        - 'to': Sends 1 email with recipients in TO list.
        """
        sender = from_email or settings.DEFAULT_FROM_EMAIL
        clean_recipients = list(dict.fromkeys([r.strip() for r in recipients if r and r.strip()]))

        if not clean_recipients:
            return {
                "success": False,
                "total_recipients": 0,
                "sent_count": 0,
                "failed_count": 0,
                "failed_recipients": [],
                "error": "No valid recipients provided.",
                "send_mode": send_mode,
            }

        sent_count = 0
        failed_recipients = []
        connection = None

        try:
            connection = get_connection(fail_silently=fail_silently)
            connection.open()

            if send_mode == "individual":
                for recipient in clean_recipients:
                    try:
                        email = EmailMultiAlternatives(
                            subject=subject,
                            body=body,
                            from_email=sender,
                            to=[recipient],
                            connection=connection,
                        )
                        if html_message:
                            email.attach_alternative(html_message, "text/html")
                        count = email.send(fail_silently=fail_silently)
                        if count > 0:
                            sent_count += 1
                        else:
                            failed_recipients.append(recipient)
                    except Exception:
                        failed_recipients.append(recipient)
                        if not fail_silently:
                            logger.exception("Failed to send email to %s", recipient)

            elif send_mode == "to":
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=body,
                    from_email=sender,
                    to=clean_recipients,
                    connection=connection,
                )
                if html_message:
                    email.attach_alternative(html_message, "text/html")
                sent = email.send(fail_silently=fail_silently)
                if sent > 0:
                    sent_count = len(clean_recipients)
                else:
                    failed_recipients = list(clean_recipients)

            else:  # 'bcc' mode (default)
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=body,
                    from_email=sender,
                    to=[sender],
                    bcc=clean_recipients,
                    connection=connection,
                )
                if html_message:
                    email.attach_alternative(html_message, "text/html")
                sent = email.send(fail_silently=fail_silently)
                if sent > 0:
                    sent_count = len(clean_recipients)
                else:
                    failed_recipients = list(clean_recipients)

            success = sent_count > 0
            return {
                "success": success,
                "total_recipients": len(clean_recipients),
                "sent_count": sent_count,
                "failed_count": len(failed_recipients),
                "failed_recipients": failed_recipients,
                "send_mode": send_mode,
            }

        except Exception as exc:
            if not fail_silently:
                logger.exception("Failed to send bulk email to recipients")
            return {
                "success": False,
                "total_recipients": len(clean_recipients),
                "sent_count": sent_count,
                "failed_count": len(clean_recipients) - sent_count,
                "failed_recipients": [r for r in clean_recipients if r not in failed_recipients] or clean_recipients,
                "error": str(exc),
                "send_mode": send_mode,
            }
        finally:
            if connection:
                try:
                    connection.close()
                except Exception:
                    pass

    @classmethod
    def send_password_reset_email(cls, tenant, user, link: str, address: str) -> bool:
        boutique = getattr(tenant, 'name', '') or 'your boutique'
        subject = f"Set your {boutique} password"
        timeout_minutes = getattr(settings, 'PASSWORD_RESET_TIMEOUT', 3600) // 60

        body = (
            f"An administrator has issued a sign-in link for {address} on {boutique}.\n\n"
            f"Open it to choose your password:\n\n{link}\n\n"
            f"The link stops working in {timeout_minutes} minutes, and once you use it "
            f"every device signed in to this account is signed out.\n\n"
            f"If you were not expecting this, ignore it -- nothing has changed until the link is used."
        )

        try:
            return cls.send_email(
                subject=subject,
                recipient_list=[address],
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                fail_silently=False,
            )
        except Exception:
            logger.exception("Password reset email delivery failed for recipient: %s", address)
            return False

