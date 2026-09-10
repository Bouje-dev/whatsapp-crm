"""Email backends for local SMTP and hosts that block outbound SMTP.

Railway (and many Docker hosts) drop connections to ports 25/465/587.
That shows up as:

    OSError: [Errno 101] Network is unreachable   (IPv6 first)
    TimeoutError: timed out                       (IPv4 SMTP blocked)

Local laptops can still reach Hostinger SMTP. Production must send over
HTTPS (Brevo / Resend / SendGrid API on port 443).
"""
from __future__ import annotations

import smtplib
import socket


from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend


def _connect_ipv4(host, port, timeout):
    last_err = None
    infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    for family, socktype, proto, _canon, sockaddr in infos:
        sock = socket.socket(family, socktype, proto)
        try:
            sock.settimeout(timeout)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            last_err = exc
            try:
                sock.close()
            except OSError:
                pass
    if last_err is not None:
        raise last_err
    raise OSError(f"SMTP IPv4 connect failed for {host}:{port}")


class SMTPIPv4(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        return _connect_ipv4(host, port, timeout)


class SMTP_SSL_IPv4(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        sock = _connect_ipv4(host, port, timeout)
        return self.context.wrap_socket(sock, server_hostname=self._host)


class IPv4EmailBackend(DjangoSMTPBackend):
    @property
    def connection_class(self):
        if self.use_ssl:
            return SMTP_SSL_IPv4
        return SMTPIPv4


class HttpsMailRequiredBackend(BaseEmailBackend):
    """Fail immediately on hosts that cannot reach SMTP, instead of hanging."""

    def send_messages(self, email_messages):
        raise OSError(
            "Outbound SMTP is blocked here. Set BREVO_API_KEY or RESEND_API_KEY."
        )
