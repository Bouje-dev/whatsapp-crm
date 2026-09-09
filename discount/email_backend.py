"""SMTP backend that connects over IPv4 only.

Railway (and many Docker hosts) have no IPv6 route. smtp.hostinger.com often
returns an AAAA record first, then Python fails with:

    OSError: [Errno 101] Network is unreachable

Local laptops still work because they can reach IPv6 or skip it. Forcing
AF_INET uses the A record and restores password-reset / notification mail.
"""
from __future__ import annotations

import smtplib
import socket

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
